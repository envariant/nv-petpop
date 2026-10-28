"""PetPop shape server for the Mac GenAI host (Hunyuan3D-2.1 on PyTorch MPS).

Runs inside the venv of VladimirTalyzin/hunyuan3d-2.1-mac (HY3D_DIR) and serves the API the worker's
HttpShapeBackend calls. Engine, model, device and dtype come from the GenAI profile (shape.server), so this
file names no model either:

    GENAI_PROFILE=mac-m4pro HY3D_DIR=~/petpop-genai/hunyuan3d-2.1-mac PETPOP_MODELS=~/petpop-models \
        $HY3D_DIR/venv/bin/python mac/shape_server/server.py --port 8190

    GET  /health                -> {"status": "ok", "engine": ..., "loaded": bool}
    POST /v1/shape              multipart view_front=<png> [view_left ...], params=<json> -> model/gltf-binary
    POST /v1/free               -> unload the model (one resident model at a time on 24 GB)
"""
from __future__ import annotations

import argparse
import gc
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

app = FastAPI(title="PetPop shape server")
_lock = threading.Lock()
_pipe = None


def model_path() -> str:
    """The pinned snapshot from `make -C mac models` if present, else the Hugging Face repo id."""
    local = Path(os.environ.get("PETPOP_MODELS", "~/petpop-models")).expanduser() / "hf" / CFG["repo"]
    return str(local) if (local / CFG["subfolder"]).exists() else CFG["repo"]


def load():
    global _pipe
    if _pipe is None:
        import importlib

        import torch

        code = Path(os.environ.get(CFG["code_dir_env"], "")).expanduser()
        for p in (code, code / "hy3dshape"):
            if p.exists() and str(p) not in sys.path:
                sys.path.insert(0, str(p))
        cls = getattr(importlib.import_module(CFG["module"]), CFG["class"])
        _pipe = cls.from_pretrained(model_path(), subfolder=CFG["subfolder"], device=CFG["device"],
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
    return {"status": "ok", "engine": CFG["engine"], "loaded": _pipe is not None, "model": model_path()}


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
    extra = {k: v for k, v in {"left": view_left, "back": view_back, "right": view_right}.items() if v is not None}
    if extra:  # Hunyuan3D-2.1 is single-view; extra views are accepted and ignored
        pass
    t0 = time.time()
    with _lock:
        try:
            pipe = load()
            gen = torch.Generator().manual_seed(int(p.get("seed", 0)))
            mesh = pipe(image=front, num_inference_steps=int(p.get("steps", 30)), guidance_scale=float(p.get("guidance", 5.0)),
                        octree_resolution=int(p.get("octree_resolution", 256)), num_chunks=int(p.get("num_chunks", 8000)),
                        generator=gen, output_type="trimesh")[0]
            glb = mesh.export(file_type="glb")
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
