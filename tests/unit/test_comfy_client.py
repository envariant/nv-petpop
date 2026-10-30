"""ComfyClient through a flaky tunnel: polls ride out dropped connections, a POST cut off after the host queued
it is not sent twice, and a prompt the client gives up on is taken off the host (no orphan for a retry to queue
behind)."""
from __future__ import annotations

import json

import httpx
import pytest

from backend.core.genai import Profile
from backend.worker.backends.real import comfy
from backend.worker.backends.real.comfy import ComfyClient, ComfyError

WF = "05_matte_birefnet.json"
VALUES = {"image": "in.png", "bg_model": "m.safetensors"}


class Host:
    """A scripted ComfyUI: `faults` maps a request key to how many times it fails before answering."""

    def __init__(self, faults: dict[str, int] | None = None, finish: bool = True) -> None:
        self.faults, self.finish, self.calls = dict(faults or {}), finish, []
        self.queued: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/comfy")
        key = f"{request.method} /{path.strip('/').split('/')[0]}"
        self.calls.append((key, request.content))
        if key == "POST /prompt":
            pid = json.loads(request.content)["prompt_id"]
            self.queued.append(pid)  # the host queues it even when the answer is then lost
        if self.faults.get(key, 0) > 0:
            self.faults[key] -= 1
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        if key == "POST /prompt":
            return httpx.Response(200, json={"prompt_id": pid})
        if key == "GET /history":
            pid = path.rsplit("/", 1)[1]
            out = {"5": {"images": [{"filename": "m.png", "subfolder": "", "type": "output"}]}}
            done = self.finish and pid in self.queued
            return httpx.Response(200, json={pid: {"status": {"status_str": "success"}, "outputs": out}} if done else {})
        if key == "GET /queue":
            return httpx.Response(200, json={"queue_running": [[0, i] for i in self.queued[:1]],
                                             "queue_pending": [[1, i] for i in self.queued[1:]]})
        if key == "GET /view":
            return httpx.Response(200, content=b"png")
        return httpx.Response(200, json={})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(comfy.time, "sleep", lambda s: None)

    def make(host: Host) -> ComfyClient:
        c = ComfyClient(Profile("mac-m4pro"))
        c.http = httpx.Client(transport=httpx.MockTransport(host.handler), base_url=c.url)
        return c
    return make


def posts(host: Host, key: str) -> int:
    return sum(k == key for k, _ in host.calls)


def test_poll_survives_a_dropped_connection(client):
    host = Host({"GET /history": 2})
    out, _ = client(host).run(WF, VALUES, timeout=60)
    assert out["mask"] == [b"png"] and posts(host, "POST /prompt") == 1


def test_a_lost_answer_to_prompt_is_not_sent_twice(client):
    host = Host({"POST /prompt": 1})
    out, _ = client(host).run(WF, VALUES, timeout=60)
    assert out["mask"] == [b"png"] and len(host.queued) == 1  # found in the queue under our id, not resubmitted


def test_a_prompt_given_up_on_is_cancelled(client, monkeypatch):
    clock = iter(range(0, 10_000, 30))
    monkeypatch.setattr(comfy.time, "monotonic", lambda: next(clock))
    host = Host(finish=False)
    with pytest.raises(ComfyError, match="timed out"):
        client(host).run(WF, VALUES, timeout=60)
    assert posts(host, "POST /interrupt") == 1  # it was running: interrupted, so a retry starts on an idle host
    assert posts(host, "POST /free") == 1
