"""The commercial-API backend (decision 108) end to end: the full pipeline on the tripo profile against a fake
Tripo apiv3 (tests/fakes/tripo_api.py), with the real provider, the api adapters, the skipped Stage C, the
texture-keeping normalisation and the texture transfer onto the base UV layout."""
from __future__ import annotations

import io
import socket
import threading
import time

import httpx
import numpy as np
import pytest
import trimesh
import uvicorn
from PIL import Image

from backend.api.store import LocalStore
from backend.core.config import settings
from backend.worker.local_run import run_pipeline
from backend.worker.runner import JobFailed
from petpop_core.schemas import manifest_errors
from petpop_core.spec import default_spec
from tests.fakes.tripo_api import FakeTripo

KEY = "tsk_fake_key"


@pytest.fixture(scope="module")
def tripo():
    fake = FakeTripo(KEY)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(fake.app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    fake.base = f"http://127.0.0.1:{port}"
    yield fake
    server.should_exit = True
    t.join(5)


@pytest.fixture
def env(monkeypatch, tmp_path, tripo):
    def use(key: str | None = KEY):
        monkeypatch.setenv("GENAI_PROFILE", "tripo")
        monkeypatch.setenv("PETPOP_QUALITY", "test")
        monkeypatch.setenv("PETPOP_VAR", str(tmp_path / "var"))
        monkeypatch.setenv("TRIPO_API_URL", tripo.base)
        if key is None:
            monkeypatch.delenv("TRIPO_API_KEY", raising=False)
        else:
            monkeypatch.setenv("TRIPO_API_KEY", key)
        monkeypatch.setattr("backend.worker.providers.base.POLL_S", (0.01, 0.05))
        tripo.log.clear()
        return settings()
    return use


def test_tripo_profile_end_to_end(env, tripo, tmp_path):
    s = env()
    store = LocalStore(tmp_path / "s")
    m = run_pipeline("j_tripo", default_spec("dog", "beagle", seed=31), store, s).data
    assert manifest_errors(m) == []
    g = m["genai"]
    assert g["profile"] == "tripo" and g["host"] == "api"
    assert g["adapters"] == {"parser": "rules", "image": "api", "shape": "api", "texture": "transfer"}
    assert g["models"]["shape.tripo"] == "v3.1-20260211" and g["models"]["provider.tripo"] == "tripo-v3 v1"
    stages = {st["stage"]: st for st in m["stages"]}
    assert stages["C"]["status"] == "skipped"
    assert "tripo task" in stages["B"]["notes"] and "5 credits" in stages["B"]["notes"]
    assert "tripo task" in stages["D"]["notes"] and "30 credits" in stages["D"]["notes"]
    assert stages["D"]["status"] == "ok" and m["metrics"]["iou_views"]  # front silhouette checked
    # Every API call carried the key; result downloads (signed URLs) did not need it.
    api = [e for e in tripo.log if e["path"].startswith("/v3/")]
    assert api and all(e["auth"] == f"Bearer {KEY}" for e in api)
    posts = [e["path"] for e in api if e["method"] == "POST"]
    assert posts == ["/v3/generation/text-to-image", "/v3/files", "/v3/generation/image-to-model"]
    body = next(e["json"] for e in api if e["path"] == "/v3/generation/image-to-model")
    assert body["model"] == "v3.1-20260211" and body["texture"] is True and body["pbr"] is False
    assert body["model_seed"] == 31 and body["input"].startswith("file_")
    t2i = next(e["json"] for e in api if e["path"] == "/v3/generation/text-to-image")
    assert not t2i["prompt"].startswith("petpop_style")  # no LoRA at a provider: trigger dropped
    # The provider's texture survived normalisation and was transferred onto the base UV layout.
    shape = trimesh.load(io.BytesIO(store.get("jobs/j_tripo/shape.glb")), file_type="glb", force="mesh")
    assert shape.visual.kind == "texture"
    albedo = np.asarray(Image.open(io.BytesIO(store.get("jobs/j_tripo/albedo.png"))).convert("RGB")).reshape(-1, 3)
    orange = (np.abs(albedo.astype(int) - [200, 140, 80]).max(axis=1) < 40).mean()
    # the fake's "pet" is a slab the dog base mesh wraps only loosely, so texels far from it stay flat; the exact
    # transfer is checked in tests/unit/test_transfer_texture.py
    assert orange > 0.02, f"only {orange:.1%} of the albedo carries the provider's colour"
    assert m["metrics"]["print_watertight"]


def test_missing_key_fails_stage_b_clearly(env, tmp_path):
    s = env(key=None)
    with pytest.raises(JobFailed, match="TRIPO_API_KEY"):
        run_pipeline("j_nokey", default_spec("cat", "siamese", seed=1), LocalStore(tmp_path / "s"), s)


def test_parametric_fallback_paints_flat(env, tripo, tmp_path, monkeypatch):
    """When the provider fails twice, D ships the parametric base mesh and the transfer texture falls back to flat."""
    s = env()
    from backend.worker.providers.manifest import ManifestProvider
    from backend.worker.providers.base import ProviderError

    def broken(self, ctx, image, params, seed):
        raise ProviderError("tripo task x failed: 2010 generation failed")
    monkeypatch.setattr(ManifestProvider, "image_to_model", broken)
    m = run_pipeline("j_param", default_spec("cat", "tuxedo", seed=5), LocalStore(tmp_path / "s"), s).data
    assert manifest_errors(m) == [] and m["fallback"] == "parametric"
    assert next(st for st in m["stages"] if st["stage"] == "F")["status"] == "ok"
