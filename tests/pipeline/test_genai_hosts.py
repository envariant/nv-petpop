"""The host-agnostic switch, end to end (M2.5): the full pipeline on the mac-m4pro and nvidia-24gb GenAI
profiles against a fake GenAI host (tests/fakes/genai_host.py) behind a bearer token. Exercises the real
ComfyUI, shape-server and Ollama adapters, the generated workflows, the residency rules and the manifest."""
from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn

from backend.api.store import LocalStore
from backend.core.config import settings
from petpop_core.schemas import manifest_errors
from petpop_core.spec import default_spec
from backend.worker.backends.real.ollama import OllamaParser
from backend.worker.local_run import run_pipeline
from tests.fakes.genai_host import FakeHost

TOKEN = "fake-token"


@pytest.fixture(scope="module")
def host():
    fake = FakeHost(TOKEN)
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
def env(monkeypatch, tmp_path, host):
    def use(profile: str, **extra):
        monkeypatch.setenv("GENAI_PROFILE", profile)
        monkeypatch.setenv("PETPOP_QUALITY", "test")
        monkeypatch.setenv("PETPOP_VAR", str(tmp_path / "var"))
        monkeypatch.setenv("GENAI_TOKEN", TOKEN)
        for svc in ("comfy", "shape", "ollama"):
            monkeypatch.setenv(f"{svc.upper()}_URL", f"{host.base}/{svc}")
        for k, v in extra.items():
            monkeypatch.setenv(k, v)
        host.log.clear()
        return settings()
    return use


def test_auth_is_required(host):
    assert httpx.get(f"{host.base}/comfy/system_stats").status_code == 401
    assert httpx.get(f"{host.base}/comfy/system_stats", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_mac_m4pro_profile(env, host, tmp_path):
    s = env("mac-m4pro")
    m = run_pipeline("j_mac", default_spec("dog", "beagle", seed=21, pet_name="Bea"), LocalStore(tmp_path / "s"), s).data
    assert manifest_errors(m) == []
    g = m["genai"]
    assert g["profile"] == "mac-m4pro" and g["accelerator"] == "mps" and g["quality"] == "test"
    assert g["adapters"] == {"parser": "ollama", "image": "comfy", "shape": "http", "texture": "projection"}
    assert g["models"]["image.checkpoint"] == "sd_xl_base_1.0.safetensors"
    assert g["models"]["shape"] == "tencent/Hunyuan3D-2.1/hunyuan3d-dit-v2-1"
    assert m["versions"]["workflows"]["01_concept_front"] == "1-unvalidated"
    paths = [e["path"] for e in host.log]
    prompts = [i for i, p in enumerate(paths) if p == "/comfy/prompt"]
    assert len(prompts) == 2  # concept, then the four-view graph
    for i in prompts:  # one resident model: every ComfyUI prompt is followed by /free
        assert "/comfy/free" in paths[i:]
    frees = [e for e in host.log if e["path"] == "/comfy/free"]
    assert all(e["json"]["unload_models"] for e in frees) and len(frees) >= 2
    shape = next(e for e in host.log if e["path"] == "/shape/v1/shape#params")["json"]
    assert shape["octree_resolution"] == 192 and shape["steps"] == 30 and shape["unload_after"] is True
    # The mesh is a job that is polled (the tunnel cuts off any request after ~100 s): submit, poll, download.
    shape_paths = [e["path"] for e in host.log if e["path"].startswith("/shape/v1/shape/")]
    assert any(p.endswith("/mesh") for p in shape_paths) and sum(not p.endswith("/mesh") for p in shape_paths) >= 2
    slowest = max((e for e in host.log if "seconds" in e), key=lambda e: e["seconds"])
    assert slowest["seconds"] < 30, f"{slowest['path']} took {slowest['seconds']:.0f} s through the tunnel"
    concept = next(e for e in host.log if e["path"] == "/comfy/prompt")["json"]["prompt"]
    ckpt = next(n for n in concept.values() if n["class_type"] == "CheckpointLoaderSimple")
    assert ckpt["inputs"]["ckpt_name"] == "sd_xl_base_1.0.safetensors"  # the model name came from the profile
    assert not any(n["class_type"] == "LoraLoader" for n in concept.values())  # no LoRA yet: bypassed
    assert m["metrics"]["print_watertight"]


def test_nvidia_24gb_profile(env, host, tmp_path):
    s = env("nvidia-24gb")
    m = run_pipeline("j_nv", default_spec("cat", "siamese", seed=22, pet_name="Luna"), LocalStore(tmp_path / "s"), s).data
    assert manifest_errors(m) == []
    assert m["genai"]["adapters"]["shape"] == "comfy"
    prompts = [e["json"]["prompt"] for e in host.log if e["path"] == "/comfy/prompt"]
    shape_graph = next(p for p in prompts if any(n["class_type"] == "VAEDecodeHunyuan3D" for n in p.values()))
    dec = next(n for n in shape_graph.values() if n["class_type"] == "VAEDecodeHunyuan3D")
    k = next(n for n in shape_graph.values() if n["class_type"] == "KSampler")
    assert dec["inputs"]["octree_resolution"] == 384 and k["inputs"]["steps"] == 50 and k["inputs"]["cfg"] == 5.5
    paths = [e["path"] for e in host.log]
    shape_i = next(i for i, e in enumerate(host.log) if e["path"] == "/comfy/prompt" and e["json"]["prompt"] is shape_graph)
    assert "/comfy/free" in paths[:shape_i]  # image stack unloaded before Stage D
    assert m["fallback"] in ("none", "single_view")


def test_nvidia_hy_paint_opt_in(env, host, tmp_path):
    s = env("nvidia-24gb", TEXTURE_BACKEND="hy_paint")
    m = run_pipeline("j_paint", default_spec("dog", "pug", seed=23), LocalStore(tmp_path / "s"), s).data
    assert m["genai"]["adapters"]["texture"] == "hy_paint" and m["genai"]["models"]["texture"] == "hunyuan3d-paint-v2-0"
    graphs = [e["json"]["prompt"] for e in host.log if e["path"] == "/comfy/prompt"]
    assert any(any(n["class_type"] == "Hy3DBakeFromMultiview" for n in g.values()) for g in graphs)


def test_ollama_parser_uses_profile(env, host):
    s = env("mac-m4pro")
    r = OllamaParser(s.genai).parse("droopy ears and very cheeky", "dog", default_spec("dog", "beagle", seed=1), [])
    assert r.patch["ears"]["shape"] == "drop" and "cheeky" in r.personality
    chat = next(e for e in host.log if e["path"] == "/ollama/api/chat")["json"]
    assert chat["model"] == "qwen2.5:7b-instruct-q4_K_M" and chat["keep_alive"] == 0
