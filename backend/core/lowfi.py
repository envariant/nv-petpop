"""Low-fidelity, CPU-only pipeline over numpy + trimesh (BRIEF Section 13 "trimesh stand-in").

Used for the S0 fixture pack and by the worker whenever bpy is unavailable; outputs are marked
`fidelity: low`. Every function keeps the base-mesh vertex order and UV layout.
"""
from __future__ import annotations

import io
import json
from typing import Any

import numpy as np
from PIL import Image

from .colouring import vertex_colours
from .meshkit import VIEWS, BaseMesh, depth_png16, dilate, raster_uv, render, silhouette_iou
from .paths import CONFIG

CAMERAS = {"concept_front": 0.0, **VIEWS}


def mandrel() -> dict[str, Any]:
    return json.loads((CONFIG / "mandrel.json").read_text())


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def control_renders(base: BaseMesh, co: np.ndarray, size: int = 512) -> dict[str, dict[str, bytes]]:
    """16-bit depth and silhouette alpha for the five cameras (Section 8, 'Depth inputs from Blender')."""
    tris = base.tri_verts
    out = {}
    for cam, az in CAMERAS.items():
        r = render(co, tris, az, size)
        depth = Image.fromarray(depth_png16(r["depth"]))  # uint16 -> I;16; Pillow 13 rejects mode= here
        alpha = Image.fromarray((r["alpha"] * 255).astype(np.uint8), "L")
        out[cam] = {"depth": png_bytes(depth), "alpha": png_bytes(alpha)}
    return out


def flat_render(base: BaseMesh, co: np.ndarray, colours: np.ndarray, azimuth: float, size: int,
                transparent: bool) -> Image.Image:
    r = render(co, base.tri_verts, azimuth, size, colours=colours)
    rgb = (np.clip(r["rgb"], 0, 1) * 255).astype(np.uint8)
    if transparent:
        a = (r["alpha"] * 255).astype(np.uint8)
        return Image.fromarray(np.dstack([rgb, a]), "RGBA")
    rgb[~r["alpha"]] = 255
    return Image.fromarray(rgb, "RGB")


def mock_shape(base: BaseMesh, co: np.ndarray, seed: int) -> np.ndarray:
    """MockShapeBackend: morphed base + low-frequency noise + small random ear/tail perturbation."""
    rng = np.random.default_rng(seed)
    p = co.copy()
    n = vertex_normals(base, co)
    freq = rng.uniform(0.05, 0.09, size=3)
    phase = rng.uniform(0, 6.28, size=3)
    noise = (np.sin(p[:, 0] * freq[0] + phase[0]) + np.sin(p[:, 1] * freq[1] + phase[1])
             + np.sin(p[:, 2] * freq[2] + phase[2])) / 3.0
    coat = (base.shell <= 3)
    p += n * (noise * 0.8 * coat)[:, None]
    for shell in (1, 2, 3):
        m = base.shell == shell
        p[m] += rng.normal(0, 0.8, size=3)
    return p


def vertex_normals(base: BaseMesh, co: np.ndarray) -> np.ndarray:
    t = base.tri_verts
    fn = np.cross(co[t[:, 1]] - co[t[:, 0]], co[t[:, 2]] - co[t[:, 0]])
    vn = np.zeros_like(co)
    for k in range(3):
        np.add.at(vn, t[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)


def iou_check(base: BaseMesh, shape_co: np.ndarray, view_alphas: dict[str, np.ndarray], size: int) -> list[float]:
    out = []
    for name, az in VIEWS.items():
        sil = render(shape_co, base.tri_verts, az, size)["alpha"]
        out.append(round(silhouette_iou(sil, view_alphas[name]), 4))
    return out


def wrap_nearest(base: BaseMesh, morphed: np.ndarray, target_co: np.ndarray, target_tris: np.ndarray,
                 strength: float = 0.85) -> np.ndarray:
    """Nearest-point wrap of the morphed base onto the generated shape; eye inserts and nose never wrap."""
    import trimesh

    tm = trimesh.Trimesh(target_co, target_tris, process=False)
    closest, _, _ = trimesh.proximity.closest_point(tm, morphed)
    w = np.where(base.shell <= 3, strength, 0.0)[:, None]
    return morphed + (closest - morphed) * w


def bake_albedo(base: BaseMesh, spec: dict[str, Any], co: np.ndarray, size: int = 1024) -> Image.Image:
    cols = vertex_colours(base, spec, co)
    img, cov = raster_uv(base, cols, size)
    img = dilate(img, cov, 2)
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8), "RGB")


def print_mesh(base: BaseMesh, co: np.ndarray):
    """Join shells, fuse the base disc and cut the mandrel socket; manifold booleans keep it watertight."""
    import trimesh

    cfg = mandrel()
    parts = []
    for s in range(7):
        m = base.shell[base.tri_verts[:, 0]] == s
        part = trimesh.Trimesh(co, base.tri_verts[m], process=True)
        part.remove_unreferenced_vertices()
        part.merge_vertices()
        part.fix_normals()  # strong morphs can turn a small shell inside out
        if part.volume < 0:
            part.invert()
        parts.append(part)
    disc = trimesh.creation.cylinder(radius=cfg["base_disc"]["diameter_mm"] / 2,
                                     height=cfg["base_disc"]["thickness_mm"], sections=96)
    disc.apply_translation([0, 0, -cfg["base_disc"]["thickness_mm"] / 2 + 0.6])
    body = trimesh.boolean.union(parts + [disc], engine="manifold")
    sock = cfg["socket"]
    hole = trimesh.creation.cylinder(radius=sock["diameter_mm"] / 2, height=sock["depth_mm"] * 2, sections=48)
    hole.apply_translation([0, 0, -cfg["base_disc"]["thickness_mm"] + 0.6])
    key = trimesh.creation.box([sock["keying_flat_mm"] * 2, sock["diameter_mm"], sock["depth_mm"] * 2])
    key.apply_translation([sock["diameter_mm"] / 2 + sock["keying_flat_mm"] * 0.0, 0,
                           -cfg["base_disc"]["thickness_mm"] + 0.6])
    socket = trimesh.boolean.difference([hole, key], engine="manifold")
    out = trimesh.boolean.difference([body, socket], engine="manifold")
    out.apply_translation([0, 0, -out.bounds[0][2]])
    return out


def min_wall(mesh, samples: int = 1500, seed: int = 0) -> float:
    """Approximate minimum wall: inward ray from sampled faces to the opposite surface."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(mesh.faces), size=min(samples, len(mesh.faces)), replace=False)
    origins = mesh.triangles_center[idx] - mesh.face_normals[idx] * 1e-3
    dirs = -mesh.face_normals[idx]
    locs, ray_idx, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=False)
    if len(locs) == 0:
        return float("nan")
    d = np.linalg.norm(locs - origins[ray_idx], axis=1)
    d = d[d > 1e-2]
    return float(np.percentile(d, 1)) if len(d) else float("nan")


def paint_check(base: BaseMesh, co: np.ndarray, size: int = 1024) -> tuple[Image.Image, float]:
    """Faces whose free space along the normal is below the head stand-off go into paint_mask.png."""
    import trimesh

    standoff = mandrel()["paint_head_standoff_mm"]
    tm = trimesh.Trimesh(co, base.tri_verts, process=False)
    centres = tm.triangles_center
    normals = tm.face_normals
    origins = centres + normals * 0.05
    locs, ray_idx, tri_idx = tm.ray.intersects_location(origins, normals, multiple_hits=False)
    free = np.full(len(centres), np.inf)
    if len(locs):
        free[ray_idx] = np.linalg.norm(locs - origins[ray_idx], axis=1)
    flagged = (free < standoff).astype(np.float32)
    img, cov = raster_uv(base, flagged[:, None], size, per_face=True)
    img = dilate(img, cov, 2)
    mask = Image.fromarray((img[..., 0] > 0.5).astype(np.uint8) * 255, "L")
    return mask, float(flagged.mean() * 100)
