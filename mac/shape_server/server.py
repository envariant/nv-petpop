"""PetPop shape server for the Mac GenAI host (Hunyuan3D-2.1 on PyTorch MPS).

Runs in the locked shape venv (mac/locks/shape.txt) against two pinned checkouts: the MPS fork
VladimirTalyzin/hunyuan3d-2.1-mac at HY3D_DIR, and Tencent's Hunyuan3D-2.1 inside it (HY3D_DIR/Hunyuan3D-2.1),
the layout the fork's own app uses. Engine, model, device, dtype, import paths and environment come from the
GenAI profile (shape.server), so this file names no model either:

    GENAI_PROFILE=mac-m4pro HY3D_DIR=~/petpop-genai/hunyuan3d-2.1-mac PETPOP_MODELS=~/petpop-models \
        ~/petpop-genai/venvs/shape/bin/python mac/shape_server/server.py --port 8190

    GET  /health                  -> {"status": "ok", "engine": ..., "loaded": bool, "weights": bool, "busy": bool}
    POST /v1/shape                multipart view_front=<png> [view_left ...], params=<json>
                                  -> 202 {"job_id", "status": "queued", "position"}
    GET  /v1/shape/{job_id}       -> {"job_id", "status": queued|running|done|failed, "seconds", "error"}
    GET  /v1/shape/{job_id}/mesh  -> model/gltf-binary once done (409 before)
    POST /v1/free                 -> unload the model now, or after the running job (never blocks)

A mesh takes minutes and the Cloudflare tunnel cuts any request off after about 100 s, so generation is a job,
like ComfyUI's /prompt + /history: every request answers in well under a second. One worker thread runs the jobs
in order (one resident model at a time on 24 GB); finished jobs are kept for an hour.

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
import queue
import sys
import threading
import time
import uuid
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
_lock = threading.Lock()  # held while the model loads, runs or unloads
_pipe = None
KEEP_S = 3600.0  # finished jobs (and their meshes) are dropped after an hour
_jobs: dict[str, dict] = {}
_queue: queue.Queue[str] = queue.Queue()
_free_after = threading.Event()


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
    return {"status": "ok", "engine": CFG["engine"], "loaded": _pipe is not None, "weights": weights_present(),
            "busy": _lock.locked()}


@app.post("/v1/free")
def free():
    if not _lock.acquire(blocking=False):  # a mesh is being made: unload when it is done, answer now
        _free_after.set()
        return {"status": "after current job"}
    try:
        unload()
    finally:
        _lock.release()
    return {"status": "freed"}


def generate(front: Image.Image, p: dict) -> bytes:
    import torch

    pipe = load()
    gen = torch.Generator(device="cpu").manual_seed(int(p.get("seed", 0)))
    with torch.inference_mode():
        out = pipe(image=front, num_inference_steps=int(p["steps"]), guidance_scale=float(p["guidance"]),
                   octree_resolution=int(p["octree_resolution"]), num_chunks=int(p.get("num_chunks", 8000)),
                   generator=gen, output_type="trimesh")
    mesh = out[0] if isinstance(out, (list, tuple)) else out
    return mesh.export(file_type="glb")


def _prune() -> None:
    now = time.time()
    for jid in [j for j, job in _jobs.items() if job.get("finished") and now - job["finished"] > KEEP_S]:
        del _jobs[jid]


def worker() -> None:
    """Runs queued jobs one at a time, for the life of the server."""
    while True:
        job = _jobs.get(_queue.get())
        if job is None:
            continue
        with _lock:
            job.update(status="running", started=time.time())
            try:
                job["glb"] = generate(job.pop("front"), job["params"])
                job["status"] = "done"
            except Exception as exc:  # noqa: BLE001 - reported to the worker, which falls back
                job.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            finally:
                job["finished"] = time.time()
                if job["params"].get("unload_after", True) or _free_after.is_set():
                    unload()
                    _free_after.clear()


threading.Thread(target=worker, name="shape-worker", daemon=True).start()


def _status(job_id: str, job: dict) -> dict:
    end = job.get("finished") or time.time()
    return {"job_id": job_id, "status": job["status"], "error": job.get("error"),
            "seconds": round(end - job["started"], 1) if job.get("started") else None,
            "position": sum(1 for j in _jobs.values() if j["status"] == "queued" and j["created"] <= job["created"])}


@app.post("/v1/shape", status_code=202)
async def shape(params: str = Form("{}"), view_front: UploadFile = File(...), view_left: UploadFile | None = File(None),
                view_back: UploadFile | None = File(None), view_right: UploadFile | None = File(None)):
    p = json.loads(params)
    missing = [k for k in ("steps", "guidance", "octree_resolution") if k not in p]
    if missing:
        raise HTTPException(422, f"params missing {missing}")
    if not weights_present():  # refuse now rather than fail minutes later
        raise HTTPException(503, f"no weights at {model_dir() / CFG['subfolder']}; run `make -C mac models`")
    front = Image.open(io.BytesIO(await view_front.read())).convert("RGBA")
    # Hunyuan3D-2.1 is single-view: view_left/back/right are accepted (the API is shared) and ignored.
    _prune()
    job_id = uuid.uuid4().hex[:16]
    _jobs[job_id] = {"status": "queued", "created": time.time(), "params": p, "front": front}
    _queue.put(job_id)
    return _status(job_id, _jobs[job_id])


def _job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"unknown shape job {job_id}")
    return job


@app.get("/v1/shape/{job_id}")
def shape_status(job_id: str):
    return _status(job_id, _job(job_id))


@app.get("/v1/shape/{job_id}/mesh")
def shape_mesh(job_id: str):
    job = _job(job_id)
    if job["status"] != "done":
        raise HTTPException(409, f"shape job {job_id} is {job['status']}")
    return Response(job["glb"], media_type="model/gltf-binary",
                    headers={"x-engine": CFG["engine"], "x-seconds": f"{job['finished'] - job['started']:.1f}"})


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
