"""Stage F texture by transfer from a provider's textured mesh (decision 108), numpy only like project_texture.

A commercial image-to-model API returns the shape with its own texture, made against its own geometry. Each
texel of the base mesh's fixed UV layout is placed on the wrapped mesh (Stage E), matched to the nearest point of
a dense colour sample of the provider surface (position plus a normal term, so the inside of a thin ear does not
take the outside's colour), and takes that colour. Texels with no provider surface nearby (where the wrap left the
shape) fall back to the PetSpec flat colours; seams are padded. No views are projected, so nothing can ghost.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "packages" / "library" / "python", ROOT / "packages" / "core" / "python", ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from petpop_library.colouring import vertex_colours  # noqa: E402
from petpop_library.meshkit import dilate, raster_uv  # noqa: E402


def _vertex_normals(co: np.ndarray, tris: np.ndarray) -> np.ndarray:
    fn = np.cross(co[tris[:, 1]] - co[tris[:, 0]], co[tris[:, 2]] - co[tris[:, 0]])
    vn = np.zeros_like(co)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)


def _material_colour(m, face: np.ndarray, bary: np.ndarray) -> np.ndarray:
    """RGB in [0, 1] at surface samples: the base-colour texture through the UVs (a glTF PBR material or a simple
    one), times the base-colour factor; vertex colours; or the factor alone."""
    vis = m.visual
    if getattr(vis, "kind", None) == "vertex":
        vc = np.asarray(vis.vertex_colors, np.float64)[:, :3] / 255.0
        return (vc[m.faces[face]] * bary[:, :, None]).sum(axis=1)
    mat = getattr(vis, "material", None)
    factor = np.ones(3)
    raw = getattr(mat, "baseColorFactor", None)
    if raw is not None:
        raw = np.asarray(raw, np.float64)[:3]
        factor = raw / 255.0 if raw.max() > 1.0 else raw
    tex = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
    uv = getattr(vis, "uv", None)
    if tex is None or uv is None:
        return np.tile(factor, (len(face), 1))
    img = np.asarray(tex.convert("RGB"), np.float64) / 255.0
    h, w = img.shape[:2]
    fuv = (np.asarray(uv, np.float64)[m.faces[face]] * bary[:, :, None]).sum(axis=1) % 1.0
    x, y = fuv[:, 0] * (w - 1), (1.0 - fuv[:, 1]) * (h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    rgb = (img[y0, x0] * (1 - fx) + img[y0, x1] * fx) * (1 - fy) + (img[y1, x0] * (1 - fx) + img[y1, x1] * fx) * fy
    return rgb * factor


def surface_colours(glb: bytes, count: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Points, unit normals (Z-up, the base mesh frame) and RGB in [0, 1] sampled over a glTF mesh's surface."""
    import trimesh

    m = trimesh.load(io.BytesIO(glb), file_type="glb", force="mesh")
    pts, face, bary = trimesh.sample.sample_surface(m, count, return_barycentric=True, seed=seed)
    rgb = _material_colour(m, face, np.asarray(bary, np.float64))
    n = m.face_normals[face]
    to_zup = lambda a: np.stack([a[:, 0], -a[:, 2], a[:, 1]], axis=1)  # glTF Y-up -> Z-up
    return to_zup(np.asarray(pts, np.float64)), to_zup(np.asarray(n, np.float64)), np.clip(rgb, 0, 1)


def transfer(base, spec: dict, co: np.ndarray, glb: bytes, size: int, samples: int = 1_500_000,
             normal_mm: float = 4.0, max_mm: float = 4.0, seam_pad: int = 2) -> np.ndarray:
    """Return an (size, size, 3) float albedo in [0, 1] in the base UV layout."""
    from scipy.spatial import cKDTree

    tris = base.tri_verts
    pos_img, cov = raster_uv(base, np.concatenate([co, _vertex_normals(co, tris)], axis=1).astype(np.float32), size)
    texels = np.nonzero(cov)
    p = pos_img[texels][:, :3].astype(np.float64)
    n = pos_img[texels][:, 3:].astype(np.float64)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    sp, sn, rgb = surface_colours(glb, samples)
    tree = cKDTree(np.concatenate([sp, sn * normal_mm], axis=1))
    _, idx = tree.query(np.concatenate([p, n * normal_mm], axis=1), workers=-1)
    gap = np.linalg.norm(sp[idx] - p, axis=1)
    flat_img, _ = raster_uv(base, vertex_colours(base, spec, co), size)
    flat = flat_img[texels]
    w = np.clip((2 * max_mm - gap) / max_mm, 0, 1)[:, None]  # full colour within max_mm, flat beyond 2x
    out = np.zeros((size, size, 3), np.float32)
    out[texels] = rgb[idx] * w + flat * (1 - w)
    return np.clip(dilate(out, cov, seam_pad), 0, 1)
