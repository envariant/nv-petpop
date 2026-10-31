"""The Tripo provider's retry rules: polls and downloads ride out drops and 5xx; a task-creating POST is never
re-sent after an ambiguous failure (it may already be spending credits); a 429 is re-sent (nothing ran); a failed
task and a task still running at the stage deadline raise with what Tripo said."""
from __future__ import annotations

import json

import httpx
import pytest

from backend.core.genai import Profile
from backend.worker.providers import base as pbase
from backend.worker.providers.base import ProviderError
from backend.worker.providers.manifest import ManifestProvider


class Ctx:
    def __init__(self, left: float = 600.0) -> None:
        self.left = left

    def remaining(self) -> float:
        return self.left


class Api:
    def __init__(self, script: dict[str, list]) -> None:
        self.script, self.calls = {k: list(v) for k, v in script.items()}, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.path}"
        self.calls.append(key)
        step = self.script[key].pop(0) if len(self.script.get(key, [])) > 1 else self.script[key][0]
        if isinstance(step, Exception):
            raise step
        status, body = step
        return httpx.Response(status, content=body if isinstance(body, bytes) else json.dumps(body).encode())


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("TRIPO_API_KEY", "tsk_test")
    monkeypatch.setattr(pbase.time, "sleep", lambda s: None)

    def make(api: Api) -> ManifestProvider:
        p = ManifestProvider(Profile("tripo"), "tripo")
        p.api.http = httpx.Client(transport=httpx.MockTransport(api))
        return p
    return make


DROP = httpx.RemoteProtocolError("Server disconnected without sending a response.")
OK_UPLOAD = (200, {"code": 0, "data": {"file_token": "file_1"}})
OK_CREATE = (200, {"code": 0, "data": {"task_id": "11111111-1111-1111-1111-111111111111"}})
TASK = "GET /v3/tasks/11111111-1111-1111-1111-111111111111"
DONE = (200, {"code": 0, "data": {"status": "success", "output": {"model_url": "https://cdn.example/m.glb?sig=1"},
                                  "credits_consumed": 30}})


def test_polls_survive_drops_and_a_5xx(provider):
    api = Api({"POST /v3/files": [OK_UPLOAD], "POST /v3/generation/image-to-model": [OK_CREATE],
               TASK: [DROP, (503, {"code": 1}), (200, {"code": 0, "data": {"status": "running"}}), DONE],
               "GET /m.glb": [DROP, (200, b"glb")]})
    g = provider(api).image_to_model(Ctx(), b"png", {"model_version": "v3.1-20260211"}, 7)
    assert g.data == b"glb" and g.credits == 30 and api.calls.count("POST /v3/generation/image-to-model") == 1


def test_an_ambiguous_create_is_not_resent(provider):
    api = Api({"POST /v3/files": [OK_UPLOAD], "POST /v3/generation/image-to-model": [DROP, OK_CREATE]})
    with pytest.raises(ProviderError, match="not retried"):
        provider(api).image_to_model(Ctx(), b"png", {}, 7)
    assert api.calls.count("POST /v3/generation/image-to-model") == 1


def test_a_rate_limited_create_is_resent(provider):
    api = Api({"POST /v3/files": [OK_UPLOAD], "POST /v3/generation/image-to-model": [(429, {"code": 2000}), OK_CREATE],
               TASK: [DONE], "GET /m.glb": [(200, b"glb")]})
    assert provider(api).image_to_model(Ctx(), b"png", {}, 7).data == b"glb"


def test_a_failed_task_says_why(provider):
    api = Api({"POST /v3/files": [OK_UPLOAD], "POST /v3/generation/image-to-model": [OK_CREATE],
               TASK: [(200, {"code": 0, "data": {"status": "failed", "error_code": 2010, "error_msg": "bad image"}})]})
    with pytest.raises(ProviderError, match="failed: 2010 bad image"):
        provider(api).image_to_model(Ctx(), b"png", {}, 7)


def test_the_stage_deadline_is_reported(provider):
    api = Api({"POST /v3/files": [OK_UPLOAD], "POST /v3/generation/image-to-model": [OK_CREATE],
               TASK: [(200, {"code": 0, "data": {"status": "running"}})]})
    with pytest.raises(ProviderError, match="stage deadline"):
        provider(api).image_to_model(Ctx(left=1.0), b"png", {}, 7)


def test_an_api_error_envelope_is_raised(provider):
    api = Api({"POST /v3/generation/text-to-image": [(200, {"code": 2002, "message": "insufficient credits"})]})
    with pytest.raises(ProviderError, match="insufficient credits"):
        provider(api).text_to_image(Ctx(), "a dog", "", {}, 1)
