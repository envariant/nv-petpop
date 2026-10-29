"""The shape adapter submits a job and polls it (mac/shape_server): it rides out a brief tunnel outage, reports a
failed job, and gives up at the stage deadline, with every request bounded far below the tunnel's ~100 s."""
from __future__ import annotations

import httpx
import pytest

from backend.worker.backends.real import shape_http
from backend.worker.backends.real.shape_http import HttpShapeBackend, ShapeServiceError


class Profile(dict):
    def url(self, _service: str) -> str:
        return "https://tunnel.example/shape"

    def auth_headers(self) -> dict:
        return {"Authorization": "Bearer t"}


class Ctx:
    def __init__(self, budget: float = 60.0) -> None:
        self.budget, self.state = budget, {}

    def remaining(self) -> float:
        self.budget -= 1.0
        return self.budget


def backend() -> HttpShapeBackend:
    return HttpShapeBackend(Profile(shape={"service": "shape", "views": ["front"], "params": {"steps": 30}, "model": "m"},
                                    residency={"shape_unload_after_call": True}))


def fake(monkeypatch, statuses: list, mesh: bytes = b"glTF....") -> list:
    calls: list = []

    def post(url, **kw):
        calls.append(("POST", url, kw["timeout"]))
        return httpx.Response(202, json={"job_id": "abc", "status": "queued"}, request=httpx.Request("POST", url))

    def get(url, **kw):
        calls.append(("GET", url, kw["timeout"]))
        if url.endswith("/mesh"):
            return httpx.Response(200, content=mesh, headers={"x-engine": "hy"}, request=httpx.Request("GET", url))
        s = statuses.pop(0)
        if isinstance(s, Exception):
            raise s
        return httpx.Response(200, json={"status": s, "error": "OOM" if s == "failed" else None}, request=httpx.Request("GET", url))

    monkeypatch.setattr(shape_http.httpx, "post", post)
    monkeypatch.setattr(shape_http.httpx, "get", get)
    monkeypatch.setattr(shape_http, "POLL_S", 0.0)
    monkeypatch.setattr(shape_http, "normalise_glb", lambda glb, cfg: glb)
    return calls


def test_submit_poll_download_survives_a_tunnel_blip(monkeypatch):
    calls = fake(monkeypatch, ["queued", httpx.ConnectError("tunnel down"), "running", "done"])
    r = backend().single_view(Ctx(), {"seed": 3}, b"png")
    assert r.glb.startswith(b"glTF")
    assert [c[0] for c in calls] == ["POST", "GET", "GET", "GET", "GET", "GET"]
    assert calls[-1][1].endswith("/v1/shape/abc/mesh")
    assert all(c[2] <= 30 for c in calls), "every request must finish far inside the tunnel's ~100 s"


def test_failed_job_is_reported(monkeypatch):
    fake(monkeypatch, ["running", "failed"])
    with pytest.raises(ShapeServiceError, match="failed: OOM"):
        backend().single_view(Ctx(), {"seed": 3}, b"png")


def test_gives_up_at_the_stage_deadline(monkeypatch):
    fake(monkeypatch, ["running"] * 100)
    with pytest.raises(ShapeServiceError, match="did not finish in time"):
        backend().single_view(Ctx(budget=5), {"seed": 3}, b"png")


def test_a_lasting_outage_fails_the_call(monkeypatch):
    fake(monkeypatch, [httpx.ConnectError("down")] * 10)
    with pytest.raises(ShapeServiceError, match="status unavailable"):
        backend().single_view(Ctx(), {"seed": 3}, b"png")
