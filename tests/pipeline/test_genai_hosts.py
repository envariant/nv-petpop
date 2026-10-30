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


def classes(graph: dict) -> set[str]:
    return {n["class_type"] for n in graph.values()}


def test_mac_m4pro_profile(env, host, tmp_path):
    """The library path: txt2img concept, BiRefNet mattes, MV-Adapter views, Hunyuan3D-2mv through ComfyUI."""
    s = env("mac-m4pro")
    m = run_pipeline("j_mac", default_spec("dog", "beagle", seed=21, pet_name="Bea"), LocalStore(tmp_path / "s"), s).data
    assert manifest_errors(m) == []
    g = m["genai"]
    assert g["profile"] == "mac-m4pro" and g["accelerator"] == "mps" and g["quality"] == "test"
    assert g["adapters"] == {"parser": "ollama", "image": "comfy", "shape": "comfy", "texture": "projection"}
    assert g["models"]["image.checkpoint"] == "sd_xl_base_1.0.safetensors"
    assert g["models"]["shape.multiview"] == "hunyuan3d-dit-v2-mv.fp16.safetensors"
    assert g["models"]["shape.fallback"] == "tencent/Hunyuan3D-2.1/hunyuan3d-dit-v2-1"
    wf = m["versions"]["workflows"]
    assert wf["02b_views_mvadapter"] == "1" and wf["03_shape_hy2mv"] == "1"  # validated on the Mac
    assert wf["01b_concept_txt2img"] == "1" and wf["05_matte_birefnet"] == "1"
    # The fake's views are ellipses, so their hull need not wrap onto the dog base mesh (E may ship it unwrapped);
    # what matters here is that D used the multi-view shape with no fallback.
    assert m["fallback"] in ("none", "unwrapped")
    assert next(st for st in m["stages"] if st["stage"] == "D")["status"] == "ok"
    paths = [e["path"] for e in host.log]
    prompts = [i for i, p in enumerate(paths) if p == "/comfy/prompt"]
    assert len(prompts) == 8  # concept, its matte, the MV-Adapter views (one graph), four view mattes, the shape
    for i in prompts:  # one resident model: every ComfyUI prompt is followed by /free
        assert "/comfy/free" in paths[i:]
    graphs = [e["json"]["prompt"] for e in host.log if e["path"] == "/comfy/prompt"]
    concept, mv, shape = graphs[0], graphs[2], graphs[-1]
    assert "EmptyLatentImage" in classes(concept) and not classes(concept) & {"ControlNetApplyAdvanced", "LoadImage"}
    text = next(n["inputs"]["text"] for n in concept.values() if n["class_type"] == "CLIPTextEncode" and "figurine" in n["inputs"]["text"])
    assert not text.startswith("petpop_style")  # no LoRA yet: its trigger word is dropped
    assert not any(n["class_type"] == "LoraLoader" for n in concept.values())  # and the LoRA node bypassed
    assert "DiffusersMVSampler" in classes(mv)
    assert sum("RemoveBackground" in classes(gr) for gr in graphs) == 5
    bg = next(n for gr in graphs for n in gr.values() if n["class_type"] == "LoadBackgroundRemovalModel")
    assert bg["inputs"]["bg_removal_name"] == "birefnet.safetensors"
    dec = next(n for n in shape.values() if n["class_type"] == "VAEDecodeHunyuan3D")
    k = next(n for n in shape.values() if n["class_type"] == "KSampler")
    mesh = next(n for n in shape.values() if n["class_type"] == "VoxelToMesh")
    assert dec["inputs"]["octree_resolution"] == 256 and k["inputs"]["steps"] == 50 and mesh["inputs"]["algorithm"] == "surface net"
    assert not any(p.startswith("/shape/v1/shape") for p in paths)  # the shape server is only the fallback
    slowest = max((e for e in host.log if "seconds" in e), key=lambda e: e["seconds"])
    assert slowest["seconds"] < 30, f"{slowest['path']} took {slowest['seconds']:.0f} s through the tunnel"
    assert m["metrics"]["print_watertight"]


def test_mac_bespoke_fast_path(env, host, tmp_path):
    """Bespoke jobs take the profile's fast path: the front view alone on the shape server, polled as a job."""
    s = env("mac-m4pro")
    m = run_pipeline("j_fast", default_spec("dog", "pug", seed=24), LocalStore(tmp_path / "s"), s, kind="bespoke").data
    assert manifest_errors(m) == [] and m["fallback"] in ("none", "unwrapped")
    graphs = [e["json"]["prompt"] for e in host.log if e["path"] == "/comfy/prompt"]
    assert not any("VAEDecodeHunyuan3D" in classes(gr) for gr in graphs)
    shape = next(e for e in host.log if e["path"] == "/shape/v1/shape#params")["json"]
    assert shape["octree_resolution"] == 192 and shape["steps"] == 30 and shape["unload_after"] is True
    assert shape["seed"] == 24 + 1  # the fallback's seed offset
    shape_paths = [e["path"] for e in host.log if e["path"].startswith("/shape/v1/shape/")]
    assert any(p.endswith("/mesh") for p in shape_paths) and sum(not p.endswith("/mesh") for p in shape_paths) >= 2
    d = next(st for st in m["stages"] if st["stage"] == "D")
    assert d["status"] == "ok" and "fast path" in d["notes"]


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
    assert sum("RemoveBackground" in classes(gr) for gr in prompts) == 5  # concept + four views matted by BiRefNet


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
