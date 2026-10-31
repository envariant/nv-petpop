"""Stage D: shape generation with the silhouette confidence check (BRIEF Section 6.4).

The runner calls multiview() then, on failure or low confidence, single_view(); a second failure makes the
runner skip D and ship the parametric base mesh (fallback = parametric)."""
from __future__ import annotations

import io
import json

import numpy as np

from petpop_library.meshkit import VIEWS, render

from .context import StageFailed
from .imaging import alpha_of, matte_square



def silhouettes_iou(spec, shape_co, tris, views: dict[str, bytes], size: int) -> list[float]:
    from PIL import Image

    out = []
    for name, az in VIEWS.items():
        if name not in views:
            continue
        sil = render(shape_co, tris, az, 256)["alpha"]
        img = Image.fromarray(np.dstack([np.zeros(sil.shape + (3,), np.uint8), (sil * 255).astype(np.uint8)]), "RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        a = alpha_of(matte_square(buf.getvalue(), size))
        b = alpha_of(views[name])
        if b.shape != a.shape:
            b = np.asarray(Image.fromarray(b.astype(np.uint8) * 255).resize(a.shape[::-1])) > 127
        inter, union = np.logical_and(a, b).sum(), np.logical_or(a, b).sum()
        out.append(round(float(inter / union) if union else 1.0, 4))
    return out


def shape_geometry(result) -> tuple[np.ndarray, np.ndarray]:
    if result.co is not None:
        return result.co, result.tris
    import trimesh

    m = trimesh.load(io.BytesIO(result.glb), file_type="glb", force="mesh")
    v = np.asarray(m.vertices)
    return np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1), np.asarray(m.faces)  # Y-up -> Z-up


def run(job_id, spec, manifest, *, ctx, single_view: bool = False) -> list[str]:
    ctx.check_fault("D")
    spec = json.loads(ctx.get("spec.json"))
    views = {v: ctx.get(f"views/{v}.png") for v in VIEWS if ctx.store.exists(ctx.key(f"views/{v}.png"))}
    if not views:  # no Stage C (profile image.views: none): the matted concept is the front view
        views = {"front": ctx.get("concept.png")}
    shape = ctx.backends.shape
    result = shape.single_view(ctx, spec, views["front"]) if single_view else shape.multiview(ctx, spec, views)
    co, tris = shape_geometry(result)
    ious = silhouettes_iou(spec, co, tris, views, int(ctx.quality["view_px"]))
    ctx.state["iou"] = ious
    iou_min = float(ctx.settings.genai["shape"]["iou_min"])
    if float(np.mean(ious)) < iou_min:
        raise StageFailed("D", f"low confidence: mean IoU {np.mean(ious):.3f} < {iou_min}")
    key = ctx.put(manifest, "shape.glb", "shape", "D", result.glb)
    ctx.progress("D", 70, "Raw shape ready", preview=("shape", key))
    return [key]
