"""Provider manifests (decision 109): every manifest in config/providers validates, and an equivalent API with a
different wire format runs through the same ManifestProvider from its manifest alone; create_extras (e.g. a
privacy flag) goes on every generation request."""
from __future__ import annotations

import json

import httpx
import pytest
import yaml

from backend.core.genai import Profile
from backend.worker.providers import base as pbase
from backend.worker.providers import manifest as pm
from backend.worker.providers.base import ProviderUnsupported
from backend.worker.providers.manifest import ManifestProvider, load_manifest


class Ctx:
    def remaining(self) -> float:
        return 600.0


def test_every_shipped_manifest_validates():
    names = [p.stem for p in pm.MANIFEST_DIR.glob("*.yaml")]
    assert "tripo-v3" in names
    for name in names:
        m = load_manifest(name)
        assert m["licence"]["private"] in ("account", "request", "none")


ACME = {  # a made-up equivalent API: other routes and field names, no JSON envelope, a privacy flag per request
    "manifest": "acme-v1", "version": 1, "vendor": "Acme 3D", "auth": {"scheme": "bearer"}, "envelope": {},
    "licence": {"private": "request", "commercial": "account"}, "create_extras": {"visibility": "private"},
    "upload": {"route": "POST /api/assets", "form_field": "image", "token": "asset.id"},
    "tasks": {"id": "job", "poll": "GET /api/jobs/{task_id}", "status": "state", "success": ["done"],
              "failed": ["error"], "credits": "cost.credits", "error": ["reason"], "output": "result"},
    "capabilities": {"image_to_model": {"route": "POST /api/jobs/image3d", "body": {"source": "$image"},
                                        "rename": {"model_version": "engine"}, "seeds": ["seed"],
                                        "result": ["files.glb"]}},
}


@pytest.fixture
def acme(monkeypatch, tmp_path):
    (tmp_path / "acme-v1.yaml").write_text(yaml.safe_dump(ACME))
    monkeypatch.setattr(pm, "MANIFEST_DIR", tmp_path)
    pm.load_manifest.cache_clear()
    monkeypatch.setenv("ACME_KEY", "k")
    monkeypatch.setattr(pbase.time, "sleep", lambda s: None)
    prof = Profile("tripo")
    prof.doc["providers"]["acme"] = {"kind": "manifest", "manifest": "acme-v1", "url": "https://acme.example", "key_env": "ACME_KEY"}
    yield prof
    pm.load_manifest.cache_clear()


def test_an_equivalent_api_needs_only_a_manifest(acme):
    sent = []

    def api(request: httpx.Request) -> httpx.Response:
        sent.append((request.method, request.url.path, request.content))
        if request.url.path == "/api/assets":
            return httpx.Response(200, json={"asset": {"id": "a1"}})
        if request.url.path == "/api/jobs/image3d":
            return httpx.Response(200, json={"job": "j1"})
        if request.url.path == "/api/jobs/j1":
            return httpx.Response(200, json={"state": "done", "cost": {"credits": 12},
                                             "result": {"files": {"glb": "https://cdn.acme.example/j1.glb"}}})
        return httpx.Response(200, content=b"glb-bytes")

    p = ManifestProvider(acme, "acme")
    p.api.http = httpx.Client(transport=httpx.MockTransport(api))
    g = p.image_to_model(Ctx(), b"png", {"model_version": "turbo-2"}, 9)
    assert g.data == b"glb-bytes" and g.task_id == "j1" and g.credits == 12
    create = json.loads(next(c for m, path, c in sent if path == "/api/jobs/image3d"))
    assert create == {"source": "a1", "engine": "turbo-2", "seed": 9, "visibility": "private"}
    assert p.describe()["licence"] == {"private": "request", "commercial": "account"}
    with pytest.raises(ProviderUnsupported):
        p.text_to_image(Ctx(), "a dog", "", {}, 1)
