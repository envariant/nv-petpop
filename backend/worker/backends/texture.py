"""Texture sources for Stage F, chosen by the GenAI profile (texture.backend, overridable with TEXTURE_BACKEND):

- projection (default on every profile): Blender stage that projects the four Stage C views onto the wrapped
  mesh in the fixed UV layout (pipelines/blender/project_texture.py), then per-region colour correction.
- flat: the PetSpec colours painted over the region masks (no views needed).
- hy_paint (optional, NVIDIA only): Hunyuan3D-Paint through the profile's ComfyUI workflow.
"""
from __future__ import annotations

import io
import json
import sys

import numpy as np
from PIL import Image

from backend.core import lowfi
from backend.core.meshkit import load_base
from backend.core.paths import PIPELINES
from backend.worker import blender

from .mock.pacing import Pace

sys.path.insert(0, str(PIPELINES / "blender"))
import bake  # noqa: E402
import project_texture  # noqa: E402


class FlatTexture:
    name = "flat"

    def paint(self, ctx, spec, wrapped_obj, coords, views):
        with Pace("F"):
            base = load_base(spec["species"])
            return lowfi.png_bytes(bake.flat_albedo(base, spec, coords, int(ctx.quality["albedo_px"])))


class ProjectionTexture:
    name = "projection"

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg

    def paint(self, ctx, spec, wrapped_obj, coords, views):
        size = int(ctx.quality["albedo_px"])
        power, pad = float(self.cfg.get("view_weight_power", 2.0)), int(self.cfg.get("seam_pad_px", 2))
        base = load_base(spec["species"])
        with Pace("F"):
            if blender.available(ctx.settings.bpy_python):
                work = ctx.workdir("project")
                (work / "spec.json").write_text(json.dumps(spec))
                np.save(work / "coords.npy", coords.astype(np.float32))
                paths = {}
                for v, data in views.items():
                    (work / f"{v}.png").write_bytes(data)
                    paths[v] = str(work / f"{v}.png")
                res = blender.run(ctx.settings.bpy_python, ["project_texture"], {
                    "spec": str(work / "spec.json"), "coords": str(work / "coords.npy"), "views": paths, "size": size,
                    "power": power, "seam_pad": pad, "out_dir": str(work)}, timeout=ctx.remaining())
                img = Image.open(res["albedo"]).convert("RGB")
            else:
                arr = {v: np.asarray(Image.open(io.BytesIO(d)).convert("RGBA"), dtype=np.float32) / 255 for v, d in views.items()}
                img = Image.fromarray((project_texture.project(base, spec, coords, arr, size, power, pad) * 255).astype(np.uint8))
            if self.cfg.get("colour_correct", True):
                img = bake.colour_correct(base, spec, img)
            return lowfi.png_bytes(img)


class HyPaintTexture:
    name = "hy_paint"

    def __init__(self, cfg: dict, comfy_factory) -> None:
        self.cfg = cfg["hy_paint"]
        self.correct = cfg.get("projection", {}).get("colour_correct", True)
        self.comfy = comfy_factory

    def paint(self, ctx, spec, wrapped_obj, coords, views):
        from .real.comfy import _version

        c = self.comfy()
        values = {"mesh_path": "input/" + c.upload(f"{ctx.job_id}_wrapped.obj", wrapped_obj, "text/plain"),
                  "ref_image": c.upload(f"{ctx.job_id}_front.png", views["front"]), "model": self.cfg["model"],
                  "seed": int(spec["seed"]), "texture_size": int(ctx.quality["albedo_px"]), **self.cfg["params"]}
        out, meta = c.run(self.cfg["workflow"], values, timeout=ctx.remaining())
        _version(ctx, self.cfg["workflow"], meta)
        img = Image.open(io.BytesIO(out["albedo"][0])).convert("RGB")
        if self.correct:
            img = bake.colour_correct(load_base(spec["species"]), spec, img)
        return lowfi.png_bytes(img)


def make_texture(profile, comfy_factory=None):
    cfg = profile["texture"]
    kind = cfg["backend"]
    if kind == "projection":
        return ProjectionTexture(cfg.get("projection", {}))
    if kind == "hy_paint":
        return HyPaintTexture(cfg, comfy_factory)
    return FlatTexture()
