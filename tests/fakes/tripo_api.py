"""A fake Tripo3D apiv3 for the VM: the wire format of backend/worker/providers/tripo.py behind a bearer key, so the
real provider runs end to end without credits. A protocol stand-in, not a model:

- POST /v3/files -> file_token; POST /v3/generation/text-to-image -> a JPEG "figure" (ellipse on light grey);
  POST /v3/generation/image-to-multiview -> four such views (wider from the side), under generate_multiview_image;
  POST /v3/generation/{image,multiview}-to-model -> a textured GLB: the front silhouette's visual hull with the
  uploaded image projected on it as its texture (Y-up, front +Z, like Tripo's output).
- GET /v3/tasks/<id>: "running" on the first poll, then "success" with signed URLs under /dl/ (no key needed) and
  credits_consumed. GET /v3/account/balance. Every request is logged.
"""
from __future__ import annotations

import io
import threading
import uuid
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw

CREDITS = {"text-to-image": 5.0, "image-to-model": 30.0, "multiview-to-model": 30.0, "image-to-multiview": 10.0}


def surface(grid: np.ndarray):
    """The outer surface of a voxel grid (a quad wherever a filled voxel meets an empty one), welded; vertices in
    voxel units, voxel i spanning [i - 0.5, i + 0.5] like trimesh's boxes."""
    import trimesh

    padded = np.pad(grid, 1)
    quads = []
    corners = {0: [(0, 0), (1, 0), (1, 1), (0, 1)]}
    for axis in range(3):
        for step in (1, -1):
            nb = np.roll(padded, -step, axis=axis)
            face = padded & ~nb
            idx = np.argwhere(face) - 1  # back to grid coordinates
            if not len(idx):
                continue
            u, w = [a for a in range(3) if a != axis]
            base = idx.astype(np.float64) - 0.5
            base[:, axis] += 1.0 if step > 0 else 0.0
            quad = np.repeat(base[:, None, :], 4, axis=1)
            for k, (du, dw) in enumerate(corners[0]):
                quad[:, k, u] += du
                quad[:, k, w] += dw
            if step < 0:
                quad = quad[:, ::-1]
            quads.append(quad)
    q = np.concatenate(quads)
    verts = q.reshape(-1, 3)
    i = np.arange(len(q))[:, None] * 4
    faces = np.concatenate([i + np.array([0, 1, 2]), i + np.array([0, 2, 3])])
    mesh = trimesh.Trimesh(verts, faces, process=True)
    mesh.fix_normals()
    return mesh


class FakeTripo:
    def __init__(self, key: str = "tsk_fake") -> None:
        self.key, self.base = key, ""
        self.files: dict[str, bytes] = {}
        self.blobs: dict[str, bytes] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.log: list[dict[str, Any]] = []
        self.balance = 1000.0
        self.lock = threading.Lock()
        self.app = self._build()

    # ------------------------------------------------------------------ fake "models"
    @staticmethod
    def figure(size: int = 1024, view: str = "front") -> bytes:
        img = Image.new("RGB", (size, size), (236, 236, 236))
        d = ImageDraw.Draw(img)
        half = 0.20 if view in ("front", "back") else 0.26  # a body is deeper than it is wide
        d.ellipse([size * (0.5 - half), size * 0.10, size * (0.5 + half), size * 0.92], fill=(200, 140, 80))
        d.ellipse([size * 0.38, size * 0.25, size * 0.46, size * 0.33], fill=(20, 20, 20))  # an "eye"
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        return buf.getvalue()

    @staticmethod
    def _mask(png: bytes) -> tuple[np.ndarray, Image.Image, tuple[int, int, int, int]]:
        img = Image.open(io.BytesIO(png)).convert("RGBA")
        a = np.asarray(img)
        m = a[..., 3] > 127 if a[..., 3].min() < 255 else a[..., :3].min(axis=2) < 200
        ys, xs = np.nonzero(m)
        box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        return m[box[1]:box[3], box[0]:box[2]], img, box

    @classmethod
    def textured_hull(cls, png: bytes, side: bytes | None = None, n: int = 40) -> bytes:
        """The visual hull of the front silhouette (and the side one, when given), the front image as its texture."""
        import trimesh

        mask, img, box = cls._mask(png)
        h, w = mask.shape
        side_mask = cls._mask(side)[0] if side else None
        grid = np.zeros((n, n, n), bool)  # x across, y depth, z up
        for i in range(n):
            for k in range(n):
                row = int((1 - (k + 0.5) / n) * h)
                col = int((i + 0.5) / n * w)
                if not mask[min(row, h - 1), min(col, w - 1)]:
                    continue
                if side_mask is None:
                    grid[i, n // 4: 3 * n // 4, k] = True
                    continue
                sh, sw = side_mask.shape
                srow = side_mask[min(int((1 - (k + 0.5) / n) * sh), sh - 1)]
                for j in range(n):
                    grid[i, j, k] = srow[min(int((j + 0.5) / n * sw), sw - 1)]
        mesh = surface(grid)
        trimesh.smoothing.filter_taubin(mesh, iterations=6)  # a generator's surface is smooth, not blocky
        v = mesh.vertices / n
        aspect = w / h  # the grid is a unit cube; the subject is as wide as its silhouette
        depth = (side_mask.shape[1] / side_mask.shape[0]) if side_mask is not None else aspect
        verts = np.stack([(v[:, 0] - 0.5) * aspect, v[:, 2], -(v[:, 1] - 0.5) * depth], axis=1)  # -> glTF Y-up, front +Z
        u = np.clip(v[:, 0], 0, 1)
        t = np.clip(v[:, 2], 0, 1)
        tex = img.crop(box).convert("RGB")
        material = trimesh.visual.material.PBRMaterial(baseColorTexture=tex, baseColorFactor=[255, 255, 255, 255])
        visual = trimesh.visual.TextureVisuals(uv=np.stack([u, t], axis=1), material=material)
        out = trimesh.Trimesh(verts, mesh.faces, visual=visual, process=False)
        return out.export(file_type="glb")

    # ------------------------------------------------------------------ app
    def _task(self, kind: str, output: dict[str, Any]) -> dict:
        tid = str(uuid.uuid4())
        self.tasks[tid] = {"polls": 0, "kind": kind, "output": output}
        self.balance -= CREDITS[kind]
        return {"code": 0, "data": {"task_id": tid}}

    def _blob(self, data: bytes, ext: str) -> str:
        name = f"{uuid.uuid4().hex}.{ext}"
        self.blobs[name] = data
        return f"{self.base}/dl/{name}?sig=fake"

    def _build(self) -> FastAPI:
        app = FastAPI(title="fake Tripo apiv3")
        fake = self

        @app.middleware("http")
        async def auth_and_log(request: Request, call_next):
            entry = {"method": request.method, "path": request.url.path,
                     "auth": request.headers.get("authorization")}
            if request.headers.get("content-type", "").startswith("application/json"):
                entry["json"] = await request.json()
            with fake.lock:
                fake.log.append(entry)
            if request.url.path.startswith("/v3/") and entry["auth"] != f"Bearer {fake.key}":
                return JSONResponse({"code": 2, "status": "error", "message": "Authentication required"}, status_code=401)
            return await call_next(request)

        @app.post("/v3/files")
        async def upload(file: UploadFile = File(...)):
            token = f"file_{uuid.uuid4().hex[:12]}"
            fake.files[token] = await file.read()
            return {"code": 0, "data": {"file_token": token}}

        @app.post("/v3/generation/text-to-image")
        async def t2i(request: Request):
            body = await request.json()
            assert body.get("prompt")
            return fake._task("text-to-image", {"generated_image_url": fake._blob(fake.figure(), "jpg")})

        @app.post("/v3/generation/image-to-model")
        async def i2m(request: Request):
            body = await request.json()
            png = fake.files[body["input"]]
            return fake._task("image-to-model", {"model_url": fake._blob(fake.textured_hull(png), "glb")})

        @app.post("/v3/generation/multiview-to-model")
        async def mv2m(request: Request):
            body = await request.json()
            inputs = body["inputs"]
            front, left = fake.files[inputs[0]], fake.files[inputs[1]] if len(inputs) > 1 and inputs[1] else None
            return fake._task("multiview-to-model", {"model_url": fake._blob(fake.textured_hull(front, left), "glb")})

        @app.post("/v3/generation/image-to-multiview")
        async def i2mv(request: Request):
            body = await request.json()
            assert body["input"] in fake.files
            views = {f"{v}_view_url": fake._blob(fake.figure(768, v), "jpg") for v in ("front", "left", "back", "right")}
            return fake._task("image-to-multiview", {"generate_multiview_image": views})

        @app.get("/v3/tasks/{tid}")
        def task(tid: str):
            t = fake.tasks.get(tid)
            if t is None:
                return JSONResponse({"code": 2001, "message": "task not found"}, status_code=404)
            t["polls"] += 1
            if t["polls"] < 2:
                return {"code": 0, "data": {"task_id": tid, "status": "running", "progress": 50, "output": {}}}
            return {"code": 0, "data": {"task_id": tid, "status": "success", "progress": 100, "output": t["output"],
                                        "credits_consumed": CREDITS[t["kind"]]}}

        @app.get("/v3/account/balance")
        def balance():
            return {"code": 0, "data": {"balance": fake.balance, "frozen": 0}}

        @app.get("/dl/{name}")
        def download(name: str):
            return Response(fake.blobs[name], media_type="application/octet-stream")

        return app
