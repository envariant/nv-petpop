"""Stage F texture by projection (BRIEF Section 6.6, the default texture source on every GenAI profile).

The four Stage C views are projected onto the wrapped mesh in the fixed UV layout: each texel's surface
point is placed in each orthographic view camera, registered to the matted view by silhouette bounding box
(the views are re-centred after matting), occlusion-tested against a z-buffer of the wrapped mesh, and blended
with weight max(0, n.v)^power. Texels no view sees (under the chin, between the legs) fall back to the PetSpec
flat colours; seams are padded. Runs as a Blender stage task (`run.py project_texture`) and is pure numpy, so
it is also unit-testable outside Blender.
"""
from __future__ import annotations

import io
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "packages" / "library" / "python", ROOT / "packages" / "core" / "python", ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from petpop_library.accessories import placed  # noqa: E402
from petpop_library.colouring import vertex_colours  # noqa: E402
from petpop_library.meshkit import CENTRE_Z_DEFAULT, EXTENT_DEFAULT, VIEWS, dilate, raster_uv, render, view_matrix  # noqa: E402

RENDER_PX = 512


def _vertex_normals(co: np.ndarray, tris: np.ndarray) -> np.ndarray:
    fn = np.cross(co[tris[:, 1]] - co[tris[:, 0]], co[tris[:, 2]] - co[tris[:, 0]])
    vn = np.zeros_like(co)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)


def _bbox(mask: np.ndarray) -> tuple[float, float, float, float] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)


def _bilinear(img: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    a, b = img[y0, x0], img[y0, x0 + 1]
    c, d = img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def project(base, spec: dict, co: np.ndarray, views: dict[str, np.ndarray], size: int, power: float = 2.0,
            seam_pad: int = 2) -> np.ndarray:
    """Return an (size, size, 3) float albedo in [0, 1]. views: name -> RGBA float array in [0, 1]."""
    tris = base.tri_verts
    normals = _vertex_normals(co, tris)
    pos_img, cov = raster_uv(base, np.concatenate([co, normals], axis=1).astype(np.float32), size)
    texels = np.nonzero(cov)
    p = pos_img[texels][:, :3].astype(np.float64)
    n = pos_img[texels][:, 3:]
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    acc = np.zeros((len(p), 3))
    wsum = np.zeros(len(p))
    scale = (RENDER_PX - 1) / EXTENT_DEFAULT
    # Accessories occlude the body and appear in the views, so they join the z-buffer and the silhouette.
    av, af = placed(spec.get("accessories", []), co, base.landmarks, base.shell)
    occ_co = np.concatenate([co, av]) if len(av) else co
    occ_tris = np.concatenate([tris, af + len(co)]) if len(af) else tris
    for name, view in views.items():
        az = VIEWS[name]
        r = render(occ_co, occ_tris, az, RENDER_PX)
        sil_box, view_box = _bbox(r["alpha"]), _bbox(view[..., 3] > 0.5)
        if sil_box is None or view_box is None:
            continue
        m = view_matrix(az)
        pc = (p - np.array([0, 0, CENTRE_Z_DEFAULT])) @ m.T
        rx = pc[:, 0] * scale + (RENDER_PX - 1) / 2
        ry = (RENDER_PX - 1) / 2 - pc[:, 1] * scale
        depth = -pc[:, 2]
        ix = np.clip(np.round(rx).astype(int), 0, RENDER_PX - 1)
        iy = np.clip(np.round(ry).astype(int), 0, RENDER_PX - 1)
        visible = depth <= r["depth"][iy, ix] + 0.4
        # Register render pixels to view pixels by silhouette bounding box (uniform scale on height).
        s = (view_box[3] - view_box[1]) / max(sil_box[3] - sil_box[1], 1e-6)
        vx = (rx - (sil_box[0] + sil_box[2]) / 2) * s + (view_box[0] + view_box[2]) / 2
        vy = (ry - (sil_box[1] + sil_box[3]) / 2) * s + (view_box[1] + view_box[3]) / 2
        a = math.radians(az)
        to_cam = np.array([math.sin(a), -math.cos(a), 0.0])
        w = np.clip(n @ to_cam, 0, 1) ** power * visible
        sample = _bilinear(view, vx, vy)
        w = w * (sample[:, 3] > 0.5)
        acc += sample[:, :3] * w[:, None]
        wsum += w
    flat_img, _ = raster_uv(base, vertex_colours(base, spec, co), size)
    flat = flat_img[texels]
    seen = wsum > 1e-3
    out_vals = flat.copy()
    out_vals[seen] = acc[seen] / wsum[seen][:, None]
    # Soften the boundary between projected and fallback texels.
    blend = np.clip(wsum / 0.15, 0, 1)[:, None]
    out_vals = out_vals * blend + flat * (1 - blend)
    out = np.zeros((size, size, 3), np.float32)
    out[texels] = out_vals
    return np.clip(dilate(out, cov, seam_pad), 0, 1)


def main(job: dict) -> dict:
    """run.py task: inputs species, spec, coords (.npy), views {name: png path}, size, power, seam_pad."""
    import json

    from PIL import Image

    from petpop_library.meshkit import load_base

    spec = json.loads(Path(job["spec"]).read_text())
    base = load_base(spec["species"])
    co = np.load(job["coords"]).astype(np.float64)
    views = {k: np.asarray(Image.open(v).convert("RGBA"), dtype=np.float32) / 255.0 for k, v in job["views"].items()}
    img = project(base, spec, co, views, int(job["size"]), float(job.get("power", 2.0)), int(job.get("seam_pad", 2)))
    out = Path(job["out_dir"]) / "albedo_projected.png"
    buf = io.BytesIO()
    Image.fromarray((img * 255).astype(np.uint8), "RGB").save(buf, format="PNG")
    out.write_bytes(buf.getvalue())
    return {"albedo": str(out)}
