"""The Mac GenAI host kit is pinned end to end, and the shape server wires up the fork the way the fork does.

No Mac, torch or weights here: the pin checks read the committed files, and the shape-server test runs the real
mac/shape_server/server.py against stub `torch`, fork (`backend`, `compat_patches`) and upstream (`hy3dshape`)
modules laid out as mac/setup.sh lays out the real checkouts.
"""
from __future__ import annotations

import importlib.util
import io
import json
import time
import re
import sys
import types
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MAC = ROOT / "mac"
HEX = {"sha256": 64, "sha512": 128}


def test_tools_are_pinned_releases_with_hashes():
    rows = [line.split() for line in (MAC / "tools.lock").read_text().splitlines() if line.strip() and not line.startswith("#")]
    names = {r[0] for r in rows}
    assert {"uv", "ollama", "caddy", "cloudflared", "python"} <= names
    for name, version, digest, url in rows:
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), name
        if name == "python":
            assert digest == "uv"  # uv checks its CPython builds against hashes it ships with
            continue
        algo, _, value = digest.partition(":")
        assert algo in HEX and re.fullmatch(rf"[0-9a-f]{{{HEX[algo]}}}", value), name
        assert url.startswith("https://") and version in url, name


@pytest.mark.parametrize("name", ["comfyui", "shape", "tools"])
def test_python_locks_pin_every_package_with_hashes(name):
    text = (MAC / "locks" / f"{name}.txt").read_text()
    reqs = re.findall(r"^([A-Za-z0-9_.\-\[\]]+)==(\S+) \\\n((?:    --hash=sha256:[0-9a-f]{64}.*\n)+)", text, re.M)
    lines = [ln for ln in text.splitlines() if re.match(r"^[A-Za-z0-9]", ln)]
    assert reqs and len(reqs) == len(lines), "every requirement must be ==pinned with hashes"
    pins = {n.lower(): v for n, v, _ in reqs}
    if name != "tools":
        assert pins["torch"].startswith("2.13."), "both GPU venvs run the torch the fork measured on an M4 Pro"
    assert "Python " + _tool("python")[0] in text.splitlines()[0]


def test_code_checkouts_are_pinned_commits():
    pins = {}
    for line in (ROOT / "pipelines" / "comfy" / "requirements.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            name, url, commit, hosts = line.split()
            pins[name] = commit
            assert re.fullmatch(r"[0-9a-f]{40}", commit), name
    setup = (MAC / "setup.sh").read_text()
    cloned = re.findall(r"^clone_at (\S+) ", setup, re.M)
    assert {"ComfyUI", "ComfyUI_IPAdapter_plus", "hunyuan3d-2.1-mac", "Hunyuan3D-2.1"} <= set(cloned)
    for name in cloned:
        assert name in pins, f"setup.sh clones {name} without a pin"


def test_setup_runs_no_unpinned_installer():
    setup = (MAC / "setup.sh").read_text()
    code = "\n".join(re.sub(r'"[^"]*"|#.*$', '""', ln) for ln in setup.splitlines())  # commands, not messages
    for pattern in (r"\bbrew\s", r"install\.sh", r"\bpip3?\s+install\b", r"curl[^\n]*\|\s*(ba)?sh"):
        assert not re.search(pattern, code), pattern
    assert "uv pip sync" in code and "--require-hashes" in code


def test_weights_are_pinned_in_yaml_and_lock():
    doc = yaml.safe_load((ROOT / "pipelines" / "comfy" / "models.yaml").read_text())
    lock = json.loads((ROOT / "pipelines" / "comfy" / "models.lock.json").read_text())["entries"]
    for m in doc["models"]:
        if m["repo"] == "local":
            continue
        assert re.fullmatch(r"[0-9a-f]{64}", m["sha256"]), m["name"]
        entry = lock[m["name"]]
        assert entry["revision"] == m["revision"] and entry["sha256"] == m["sha256"], m["name"]
        assert all(re.fullmatch(r"[0-9a-f]{64}", f["sha256"]) for f in entry["files"].values()), m["name"]
    for tag in doc["ollama"]:
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", tag["manifest_digest"]), tag["tag"]


def test_mac_profile_shape_snapshot_is_the_dit_folder_only():
    doc = yaml.safe_load((ROOT / "pipelines" / "comfy" / "models.yaml").read_text())
    snap = next(m for m in doc["models"] if m["name"] == "hunyuan3d-2.1-shape-snapshot")
    server = yaml.safe_load((ROOT / "config" / "genai" / "mac-m4pro.yaml").read_text())["shape"]["server"]
    assert all(f.startswith(server["subfolder"] + "/") for f in snap["files"])


def _tool(name: str) -> list[str]:
    for line in (MAC / "tools.lock").read_text().splitlines():
        if line.split()[:1] == [name]:
            return line.split()[1:]
    raise KeyError(name)


# ------------------------------------------------------------------ shape server against stubs
FORK_BACKEND = '''
import os
EVENTS = []
class B:
    device = os.environ["HY3D_BACKEND"]
def detect():
    EVENTS.append(("detect", os.environ.get("HY3D_BACKEND"), os.environ.get("HY3D_DTYPE")))
    return B()
'''
FORK_COMPAT = '''
import backend
def apply(b):
    backend.EVENTS.append(("apply", b.device))
def patch_scheduler_timestep_lookup():
    import hy3dshape  # only importable once the upstream paths are on sys.path
    backend.EVENTS.append(("scheduler_patch",))
'''
UPSTREAM_PIPELINES = '''
import os, trimesh
CALLS = []
class Hunyuan3DDiTFlowMatchingPipeline:
    @classmethod
    def from_pretrained(cls, model_path, device="cuda", dtype=None, use_safetensors=False, variant="fp16",
                        subfolder="hunyuan3d-dit-v2-1", **kw):
        cfg = os.path.join(model_path, subfolder, "config.yaml")
        assert os.path.exists(cfg), cfg
        CALLS.append(dict(model_path=model_path, subfolder=subfolder, device=device, dtype=dtype,
                          use_safetensors=use_safetensors, variant=variant, offline=os.environ.get("HF_HUB_OFFLINE")))
        return cls()
    def __call__(self, image, num_inference_steps, guidance_scale, octree_resolution, num_chunks, generator, output_type):
        CALLS.append(dict(steps=num_inference_steps, guidance=guidance_scale, octree=octree_resolution, seed=generator.seed))
        return [trimesh.creation.box()]
'''


def _stub_torch() -> types.ModuleType:
    t = types.ModuleType("torch")

    class Gen:
        def __init__(self, device="cpu"):
            self.seed = None

        def manual_seed(self, s):
            self.seed = s
            return self

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    t.Generator = Gen
    t.inference_mode = lambda: _Ctx()
    t.float16 = "float16"
    t.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
    t.mps = types.SimpleNamespace(empty_cache=lambda: None)
    return t


@pytest.fixture
def server(tmp_path, monkeypatch):
    fork = tmp_path / "hunyuan3d-2.1-mac"
    (fork / "Hunyuan3D-2.1" / "hy3dshape" / "hy3dshape").mkdir(parents=True)
    (fork / "backend.py").write_text(FORK_BACKEND)
    (fork / "compat_patches.py").write_text(FORK_COMPAT)
    pkg = fork / "Hunyuan3D-2.1" / "hy3dshape" / "hy3dshape"
    (pkg / "__init__.py").write_text("")
    (pkg / "pipelines.py").write_text(UPSTREAM_PIPELINES)
    models = tmp_path / "models"
    (models / "hf" / "tencent" / "Hunyuan3D-2.1" / "hunyuan3d-dit-v2-1").mkdir(parents=True)
    monkeypatch.setenv("GENAI_PROFILE", "mac-m4pro")
    monkeypatch.setenv("HY3D_DIR", str(fork))
    monkeypatch.setenv("PETPOP_MODELS", str(models))
    for k in ("HY3D_BACKEND", "HY3D_DTYPE", "HF_HUB_OFFLINE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setitem(sys.modules, "torch", _stub_torch())
    for mod in ("backend", "compat_patches", "hy3dshape", "hy3dshape.pipelines", "petpop_shape_server"):
        monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location("petpop_shape_server", MAC / "shape_server" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod, models
    for m in ("backend", "compat_patches", "hy3dshape", "hy3dshape.pipelines"):
        sys.modules.pop(m, None)


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (64, 64), (200, 120, 60, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_shape_server_follows_the_fork_and_stays_offline(server):
    from fastapi.testclient import TestClient

    mod, models = server
    events = sys.modules["backend"].EVENTS
    assert events == [("detect", "mps", "float16"), ("apply", "mps")], "fork runtime must load at startup"
    client = TestClient(mod.app)
    assert client.get("/health").json()["weights"] is False
    params = {"octree_resolution": 192, "steps": 30, "guidance": 5.0, "num_chunks": 8000, "seed": 41, "unload_after": True}
    r = client.post("/v1/shape", data={"params": json.dumps(params)}, files={"view_front": ("f.png", _png(), "image/png")})
    assert r.status_code == 503 and "make -C mac models" in r.json()["detail"]

    (models / "hf" / "tencent" / "Hunyuan3D-2.1" / "hunyuan3d-dit-v2-1" / "config.yaml").write_text("model: {}\n")
    # A mesh is a job: the POST answers at once (the tunnel cuts requests off after ~100 s), then it is polled.
    r = client.post("/v1/shape", data={"params": json.dumps(params)}, files={"view_front": ("f.png", _png(), "image/png")})
    assert r.status_code == 202 and r.json()["status"] in ("queued", "running")
    job_id = r.json()["job_id"]
    for _ in range(200):
        st = client.get(f"/v1/shape/{job_id}").json()
        if st["status"] in ("done", "failed"):
            break
        time.sleep(0.02)
    assert st["status"] == "done", st
    r = client.get(f"/v1/shape/{job_id}/mesh")
    assert r.status_code == 200 and r.content[:4] == b"glTF" and r.headers["x-engine"] == "hunyuan3d-2.1-mps"
    assert client.get("/v1/shape/nope").status_code == 404
    load, call = sys.modules["hy3dshape.pipelines"].CALLS
    assert load["model_path"] == str(models / "hf" / "tencent" / "Hunyuan3D-2.1")
    assert (load["subfolder"], load["device"], load["variant"], load["use_safetensors"]) == ("hunyuan3d-dit-v2-1", "mps", "fp16", False)
    assert load["offline"] == "1"
    assert call == {"steps": 30, "guidance": 5.0, "octree": 192, "seed": 41}
    assert ("scheduler_patch",) in events
    assert mod._pipe is None, "unload_after must drop the model (one resident model at a time)"
    # /v1/free never waits for a running mesh: it answers now and unloads afterwards.
    with mod._lock:
        t0 = time.perf_counter()
        assert client.post("/v1/free").json() == {"status": "after current job"}
        assert time.perf_counter() - t0 < 1.0
    assert client.post("/v1/free").json() == {"status": "freed"}
