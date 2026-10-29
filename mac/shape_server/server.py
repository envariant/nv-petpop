"""PetPop shape server for the Mac GenAI host (Hunyuan3D-2.1 on PyTorch MPS).

Runs in the locked shape venv (mac/locks/shape.txt) against two pinned checkouts: the MPS fork
VladimirTalyzin/hunyuan3d-2.1-mac at HY3D_DIR, and Tencent's Hunyuan3D-2.1 inside it (HY3D_DIR/Hunyuan3D-2.1),
the layout the fork's own app uses. Engine, model, device, dtype, import paths and environment come from the
GenAI profile (shape.server), so this file names no model either:

    GENAI_PROFILE=mac-m4pro HY3D_DIR=~/petpop-genai/hunyuan3d-2.1-mac PETPOP_MODELS=~/petpop-models \
        ~/petpop-genai/venvs/shape/bin/python mac/shape_server/server.py --port 8190

    GET  /health                -> {"status": "ok", "engine": ..., "loaded": bool, "weights": bool}
    POST /v1/shape              multipart view_front=<png> [view_left ...], params=<json> -> model/gltf-binary
    POST /v1/free               -> unload the model (one resident model at a time on 24 GB)

Weights load only from the local directory `make -C mac models` fills (checked against models.lock.json), and
HF_HUB_OFFLINE is set by the profile, so the server never downloads anything.
"""
from __future__ import annotations

import argparse
import gc
import importlib
import io
import json
import os
import sys
import threading
import time
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
PROFILE = yaml.safe_load((REPO / "config" / "genai" / f"{os.environ.get('GENAI_PROFILE', 'mac-m4pro')}.yaml").read_text())
CFG = PROFILE["shape"]["server"]
for k, v in (CFG.get("env") or {}).items():
    os.environ.setdefault(k, str(v))

CODE = Path(os.environ.get(CFG["code_dir_env"], "")).expanduser()
for rel in reversed(CFG.get("code_paths", ["."])):
    p = (CODE / rel).resolve()
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# The fork's runtime layer must load before torch: `backend` sets the MPS environment and `compat_patches`
# redirects upstream's hard-coded CUDA calls (autocast, torch.cuda.*, sdp_kernel). As in the fork's gradio_app.
_compat = None
if CFG.get("compat") == "hunyuan3d-2.1-mac":
    _backend = importlib.import_module("backend")
    _compat = importlib.import_module("compat_patches")
    _compat.apply(_backend.detect())

app = FastAPI(title="PetPop shape server")
_lock = threading.Lock()
_pipe = None


def model_dir() -> Path:
    """The pinned snapshot `make -C mac models` writes (Hugging Face layout under the model root)."""
    return Path(os.environ.get("PETPOP_MODELS", "~/petpop-models")).expanduser() / "hf" / CFG["repo"]


def weights_present() -> bool:
    return (model_dir() / CFG["subfolder"] / "config.yaml").exists()


def load():
    global _pipe
    if _pipe is None:
        import torch

        if not weights_present():
            raise HTTPException(503, f"no weights at {model_dir() / CFG['subfolder']}; run `make -C mac models`")
        cls = getattr(importlib.import_module(CFG["module"]), CFG["class"])
        if _compat is not None:  # needs hy3dshape importable, hence here (as in the fork)
            _compat.patch_scheduler_timestep_lookup()
        _pipe = cls.from_pretrained(str(model_dir()), subfolder=CFG["subfolder"], use_safetensors=False,
                                    variant=CFG.get("variant", "fp16"), device=CFG["device"],
                                    dtype=getattr(torch, CFG["dtype"]))
    return _pipe


def unload() -> None:
    global _pipe
    _pipe = None
    gc.collect()
    try:
        import torch

        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:  # noqa: BLE001
        pass


@app.get("/health")
def health():
    return {"status": "ok", "engine": CFG["engine"], "loaded": _pipe is not None, "weights": weights_present()}


@app.post("/v1/free")
def free():
    with _lock:
        unload()
    return {"status": "freed"}


@app.post("/v1/shape")
async def shape(params: str = Form("{}"), view_front: UploadFile = File(...), view_left: UploadFile | None = File(None),
                view_back: UploadFile | None = File(None), view_right: UploadFile | None = File(None)):
    import torch

    p = json.loads(params)
    front = Image.open(io.BytesIO(await view_front.read())).convert("RGBA")
    # Hunyuan3D-2.1 is single-view: view_left/back/right are accepted (the API is shared) and ignored.
    t0 = time.time()
    with _lock:
        try:
            pipe = load()
            gen = torch.Generator(device="cpu").manual_seed(int(p.get("seed", 0)))
            with torch.inference_mode():
                out = pipe(image=front, num_inference_steps=int(p["steps"]), guidance_scale=float(p["guidance"]),
                           octree_resolution=int(p["octree_resolution"]), num_chunks=int(p.get("num_chunks", 8000)),
                           generator=gen, output_type="trimesh")
            mesh = out[0] if isinstance(out, (list, tuple)) else out
            glb = mesh.export(file_type="glb")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - reported to the worker, which falls back
            raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc
        finally:
            if p.get("unload_after", True):
                unload()
    return Response(glb, media_type="model/gltf-binary",
                    headers={"x-engine": CFG["engine"], "x-seconds": f"{time.time() - t0:.1f}"})


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8190)
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")
