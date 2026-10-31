"""Commercial GenAI API providers (decisions 108, 109). A provider is one vendor's HTTP API behind a small set of
capabilities the pipeline needs; the GenAI profile says which provider serves which stage, with which models and
options, so switching vendors is a new provider class plus a profile, never a change to the stages.

Capabilities (a provider implements the ones its vendor offers; the rest raise ProviderUnsupported):

    text_to_image(ctx, prompt, negative, params, seed)         -> Generated(PNG)       Stage B concept
    image_to_model(ctx, image, params, seed)                   -> Generated(GLB)       Stage D, textured if asked
    multiview_to_model(ctx, views, params, seed)               -> Generated(GLB)       Stage D from Stage C views
    balance()                                                  -> {"balance", ...}     genai_check, cost guard

Every vendor call here is an asynchronous task: upload the inputs, create a task, poll it, download the result.
TaskClient holds that shape once: the bearer key comes from the environment variable the profile names (never
logged), polls and downloads ride out tunnel drops and 429/5xx with backoff, and a task-creating POST is never
retried after an ambiguous failure, so a dropped connection cannot spend credits twice.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

log = logging.getLogger("petpop.worker")

RETRY_STATUSES = {429, 500, 502, 503, 504}
TRIES = 6           # GET attempts (1, 2, 4, 8, 15 s back-off)
REQUEST_S = 60.0    # every single request
POLL_S = (2.0, 15.0)  # first and largest poll interval


class ProviderError(RuntimeError):
    pass


class ProviderUnsupported(ProviderError):
    pass


class AwaitingOperator(Exception):
    """Manual mode (decision 111): the request is written for the operator, who runs it in the vendor's own app and
    uploads the output. Not a failure: the job pauses (status `waiting`) and resumes from its stored stages."""

    def __init__(self, packet: dict[str, Any]) -> None:
        super().__init__(f"waiting for the operator: {packet.get('title', packet.get('capability'))}")
        self.packet = packet


@dataclass
class Generated:
    data: bytes
    task_id: str
    credits: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def note(self, provider: str) -> str:
        cost = f", {self.credits:g} credits" if self.credits is not None else ""
        return f"{provider} task {self.task_id}{cost}"


class Provider(Protocol):
    name: str

    def text_to_image(self, ctx, prompt: str, negative: str, params: dict[str, Any], seed: int) -> Generated: ...
    def image_to_model(self, ctx, image: bytes, params: dict[str, Any], seed: int) -> Generated: ...
    def multiview_to_model(self, ctx, views: dict[str, bytes], params: dict[str, Any], seed: int) -> Generated: ...
    def balance(self) -> dict[str, Any]: ...


def provider_config(profile, name: str) -> dict[str, Any]:
    providers = profile.get("providers") or {}
    if name not in providers:
        raise ProviderError(f"profile {profile.name} has no provider {name!r}")
    return providers[name]


class TaskClient:
    """HTTP for one provider: base URL and key from the profile's provider entry (url / url_env, key_env)."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.url = (os.environ.get(cfg.get("url_env", "")) or cfg["url"]).rstrip("/")
        self.key_env = cfg["key_env"]
        self.http = httpx.Client(timeout=REQUEST_S, follow_redirects=True)

    def headers(self) -> dict[str, str]:
        key = os.environ.get(self.key_env, "").strip()
        if not key:
            raise ProviderError(f"{self.key_env} is not set: add the provider's API key to the environment")
        return {"Authorization": f"Bearer {key}", "Accept": "application/json"}

    @staticmethod
    def _wait(attempt: int, retry_after: str | None = None) -> None:
        delay = min(2 ** attempt, POLL_S[1])
        if retry_after:
            try:
                delay = min(max(float(retry_after), 0.0), 60.0)
            except ValueError:
                pass
        time.sleep(delay)

    def get(self, path: str, **params) -> httpx.Response:
        """GET an API path (with the key) and retry what is safe to retry."""
        err: Exception | None = None
        for attempt in range(TRIES):
            try:
                r = self.http.get(f"{self.url}{path}", params=params or None, headers=self.headers())
                if r.status_code not in RETRY_STATUSES:
                    return r
                err = ProviderError(f"GET {path}: HTTP {r.status_code}")
                self._wait(attempt, r.headers.get("retry-after"))
            except httpx.TransportError as exc:
                err = exc
                self._wait(attempt)
            log.warning("provider GET %s failed (%s), retrying", path, err)
        raise ProviderError(f"provider unreachable for {path}: {err}")

    def post(self, path: str, *, json: dict | None = None, files: dict | None = None) -> httpx.Response:
        """POST once. Only a 429 (the request was refused, so nothing ran) is retried."""
        for attempt in range(TRIES):
            try:
                r = self.http.post(f"{self.url}{path}", json=json, files=files, headers=self.headers())
            except httpx.TransportError as exc:
                raise ProviderError(f"POST {path} failed ({exc}); not retried, it may have been accepted") from exc
            if r.status_code != 429:
                return r
            self._wait(attempt, r.headers.get("retry-after"))
        raise ProviderError(f"POST {path}: still rate-limited")

    def download(self, url: str) -> bytes:
        """A signed result URL: no API key, retried like a GET."""
        err: Exception | None = None
        for attempt in range(TRIES):
            try:
                r = self.http.get(url)
                if r.status_code == 200:
                    return r.content
                err = ProviderError(f"download HTTP {r.status_code}")
            except httpx.TransportError as exc:
                err = exc
            self._wait(attempt)
        raise ProviderError(f"result download failed: {err}")

    @staticmethod
    def poll_interval(n: int) -> float:
        return min(POLL_S[0] * (1.5 ** n), POLL_S[1])
