"""A fake GenAI host for the cloud VM: speaks enough of the ComfyUI, PetPop shape-server and Ollama HTTP APIs,
behind the same bearer-token check as mac/Caddyfile, to run the real adapters and the generated workflows end
to end without a GPU. It is a protocol stand-in, not a model:

- ComfyUI: /upload/image, /prompt, /history/<id>, /view, /free, /system_stats. A SaveImage output is a "render"
  of the depth image that feeds it upstream (subject shaded on white); a SaveGLB output is the visual hull of
  the view images that feed it; the texture graph returns a flat albedo.
- Shape server: /health, /v1/shape (visual hull of the uploaded views), /v1/free.
- Ollama: /api/tags, /api/chat (a fixed, schema-valid patch).

    python -m tests.fakes.genai_host --port 8787 --token devtoken   # then point COMFY_URL etc. at it
"""
from __future__ import annotations

import argparse
import io
import json
import threading
import uuid
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image

VIEW_NAMES = ["front", "left", "back", "right"]


class FakeHost:
    def __init__(self, token: str = "") -> None:
        self.token = token
        self.uploads: dict[str, bytes] = {}
        self.outputs: dict[str, bytes] = {}
        self.history: dict[str, Any] = {}
        self.log: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.app = self._build()

    # ------------------------------------------------------------------ fake "models"
    @staticmethod
    def render_from_depth(depth_png: bytes, size: int | None = None) -> bytes:
        d = np.asarray(Image.open(io.BytesIO(depth_png)).convert("I")).astype(np.float32)
        d = d / max(float(d.max()), 1.0)
        fg = d > 0.02
        rgb = np.full(d.shape + (3,), 255, np.uint8)
        shade = (0.55 + 0.45 * d)[..., None]
        rgb[fg] = (np.array([200, 140, 80]) * shade[fg]).astype(np.uint8)
        img = Image.fromarray(rgb, "RGB")
        if size:
            img = img.resize((size, size))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def visual_hull(views: dict[str, bytes], n: int = 48) -> bytes:
        """Carve a voxel grid with the silhouettes of whichever orthographic views are given (Z up, front -Y)."""
        import trimesh

        def mask(png: bytes) -> np.ndarray:
            a = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))
            m = a[..., 3] > 127 if a[..., 3].min() < 255 else a[..., :3].min(axis=2) < 236
            ys, xs = np.nonzero(m)
            m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            return m

        masks = {k: mask(v) for k, v in views.items()}
        h = max(m.shape[0] for m in masks.values())
        grid = np.ones((n, n, n), bool)  # x, y, z in [-0.5,0.5]x[-0.5,0.5]x[0,1] of the subject height
        c = (np.arange(n) + 0.5) / n
        X, Y, Z = np.meshgrid(c - 0.5, c - 0.5, c, indexing="ij")

        def sample(m: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
            mh, mw = m.shape
            col = np.clip((u * mh + mw / 2).astype(int), -1, mw)  # u in subject-height units, centred
            row = np.clip(((1 - v) * mh).astype(int), 0, mh - 1)
            inside = (col >= 0) & (col < mw)
            out = np.zeros(u.shape, bool)
            out[inside] = m[row[inside], col[inside]]
            return out

        # image right = +X (front), +Y (left: camera at +X), -X (back), -Y (right: camera at -X)
        horiz = {"front": X, "left": Y, "back": -X, "right": -Y}
        for name, m in masks.items():
            grid &= sample(m, horiz[name], Z)
        if len(masks) == 1:  # one view: assume a body about as deep as it is wide
            grid &= sample(masks["front"], Y, Z)
        vg = trimesh.voxel.VoxelGrid(grid, transform=trimesh.transformations.scale_and_translate(1.0 / n, [-0.5, -0.5, 0]))
        m = vg.as_boxes()
        v = m.vertices * 90.0
        m.vertices = np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1)  # Z-up front -Y -> glTF Y-up front +Z
        return m.export(file_type="glb")

    # ------------------------------------------------------------------ ComfyUI graph execution
    @staticmethod
    def upstream(graph: dict, node_id: str, cls: str) -> list[str]:
        seen, stack, found = set(), [node_id], []
        while stack:
            nid = stack.pop()
            if nid in seen or nid not in graph:
                continue
            seen.add(nid)
            if graph[nid]["class_type"] == cls:
                found.append(nid)
            for v in graph[nid]["inputs"].values():
                if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                    stack.append(v[0])
        return found

    def run_prompt(self, graph: dict) -> dict:
        outputs: dict[str, Any] = {}
        for nid, node in graph.items():
            ct = node["class_type"]
            if ct not in ("SaveImage", "SaveGLB"):
                continue
            loads = [graph[i]["inputs"]["image"] for i in self.upstream(graph, nid, "LoadImage")]
            if ct == "SaveImage" and any("depth" in name for name in loads):
                depth = next(n for n in loads if "depth" in n)
                width = next((graph[i]["inputs"]["width"] for i in self.upstream(graph, nid, "ImageScale")), None)
                width = width or next((graph[i]["inputs"]["width"] for i in self.upstream(graph, nid, "EmptyLatentImage")), None)
                data, key = self.render_from_depth(self.uploads[depth], width), "images"
            elif ct == "SaveImage":  # texture graph: flat albedo
                buf = io.BytesIO()
                Image.new("RGB", (512, 512), (190, 130, 80)).save(buf, format="PNG")
                data, key = buf.getvalue(), "images"
            else:
                views = {v: self.uploads[n] for n in loads for v in VIEW_NAMES if f"shape_{v}" in n}
                data, key = self.visual_hull(views), "3d"
            fname = f"{uuid.uuid4().hex[:8]}.{'png' if key == 'images' else 'glb'}"
            self.outputs[fname] = data
            outputs[nid] = {key: [{"filename": fname, "subfolder": "petpop", "type": "output"}]}
        return outputs

    # ------------------------------------------------------------------ app
    def _build(self) -> FastAPI:
        app = FastAPI(title="fake GenAI host")
        host = self

        @app.middleware("http")
        async def auth_and_log(request: Request, call_next):
            if host.token and request.headers.get("authorization") != f"Bearer {host.token}":
                return Response("unauthorised", status_code=401)
            body = await request.body()
            entry = {"method": request.method, "path": request.url.path}
            if request.headers.get("content-type", "").startswith("application/json") and body:
                entry["json"] = json.loads(body)
            with host.lock:
                host.log.append(entry)
            return await call_next(request)

        # ComfyUI ------------------------------------------------------------------
        @app.get("/comfy/system_stats")
        def stats():
            return {"system": {"os": "fake"}, "devices": [{"name": "fake", "type": "cpu"}]}

        @app.post("/comfy/upload/image")
        async def upload(image: UploadFile = File(...), overwrite: str = Form("true")):
            host.uploads[image.filename] = await image.read()
            return {"name": image.filename, "subfolder": "", "type": "input"}

        @app.post("/comfy/prompt")
        async def prompt(request: Request):
            body = await request.json()
            pid = uuid.uuid4().hex
            host.history[pid] = {"status": {"status_str": "success", "completed": True},
                                 "outputs": host.run_prompt(body["prompt"])}
            return {"prompt_id": pid, "number": len(host.history), "node_errors": {}}

        @app.get("/comfy/history/{pid}")
        def history(pid: str):
            return {pid: host.history[pid]} if pid in host.history else {}

        @app.get("/comfy/view")
        def view(filename: str, subfolder: str = "", type: str = "output"):  # noqa: A002
            return Response(host.outputs[filename], media_type="application/octet-stream")

        @app.post("/comfy/free")
        def free():
            return {}

        # Shape server ---------------------------------------------------------------
        @app.get("/shape/health")
        def shape_health():
            return {"status": "ok", "engine": "fake-visual-hull", "loaded": False}

        @app.post("/shape/v1/shape")
        async def shape(params: str = Form("{}"), view_front: UploadFile = File(...), view_left: UploadFile | None = File(None),
                        view_back: UploadFile | None = File(None), view_right: UploadFile | None = File(None)):
            with host.lock:
                host.log.append({"method": "POST", "path": "/shape/v1/shape#params", "json": json.loads(params)})
            views = {"front": await view_front.read()}
            for k, f in (("left", view_left), ("back", view_back), ("right", view_right)):
                if f is not None:
                    views[k] = await f.read()
            return Response(host.visual_hull(views), media_type="model/gltf-binary", headers={"x-engine": "fake-visual-hull"})

        @app.post("/shape/v1/free")
        def shape_free():
            return {"status": "freed"}

        # Ollama ---------------------------------------------------------------------
        @app.get("/ollama/api/tags")
        def tags():
            return {"models": [{"name": "fake"}]}

        @app.post("/ollama/api/chat")
        async def chat(request: Request):
            patch = {"personality": ["cheeky"], "ears": {"shape": "drop"}, "free_text_unmapped": ""}
            return JSONResponse({"message": {"role": "assistant", "content": json.dumps(patch)}, "done": True})

        @app.get("/_log")
        def get_log():
            return host.log

        return app


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--token", default="")
    a = ap.parse_args()
    uvicorn.run(FakeHost(a.token).app, host="127.0.0.1", port=a.port)
