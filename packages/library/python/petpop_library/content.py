"""Building library content: deltas from shape-key weights or from generated figurines, thumbnails, and the
release manifest. Shared by scripts/make_proxy_library.py (the proxy library) and Studio's publish (M8)."""
from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image

from .deltas import region_delta
from .meshkit import BaseMesh, render

NEUTRAL = np.array([0.80, 0.74, 0.66])
ACCENT = np.array([1.0, 0.54, 0.24])


def delta_from_weights(base: BaseMesh, weights: dict[str, float], region: str | None = None) -> np.ndarray:
    """Full-mesh offsets of a set of shape-key weights, restricted to a region if given (float16-exact)."""
    d = np.zeros_like(base.co, dtype=np.float64)
    for name, w in weights.items():
        if w and name in base.morph_names:
            d += base.morph_deltas[base.morph_names.index(name)].astype(np.float64) * float(w)
    if region is None:
        return d.astype("<f2").astype(np.float64)
    return region_delta(base, d, region)


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def thumbnail(base: BaseMesh, co: np.ndarray, colours: np.ndarray | None = None, size: int = 192, azimuth: float = 30.0) -> bytes:
    """A small transparent render of a composed mesh with per-vertex colours (neutral if None)."""
    col = np.broadcast_to(NEUTRAL, co.shape).copy() if colours is None else colours
    r = render(co, base.tri_verts, azimuth, size, colours=col)
    rgb = (np.clip(r["rgb"], 0, 1) * 255).astype(np.uint8)
    a = (r["alpha"] * 255).astype(np.uint8)
    return png(Image.fromarray(np.dstack([rgb, a]), "RGBA"))


def highlight(base: BaseMesh, weights: np.ndarray) -> np.ndarray:
    """Per-vertex colours with a region highlighted in the accent colour."""
    w = np.clip(weights, 0, 1)[:, None]
    return NEUTRAL * (1 - w) + ACCENT * w


def mesh_thumbnail(vertices: np.ndarray, faces: np.ndarray, colour: str, size: int = 192) -> bytes:
    """Render a shell part on its own."""
    v = vertices - vertices.mean(axis=0)
    v = v / max(np.abs(v).max(), 1e-6) * 40.0 + np.array([0.0, 0.0, 45.0])
    rgb = np.array([int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0
    r = render(v, faces, 30.0, size, colours=np.broadcast_to(rgb, v.shape).copy())
    out = (np.clip(r["rgb"], 0, 1) * 255).astype(np.uint8)
    a = (r["alpha"] * 255).astype(np.uint8)
    return png(Image.fromarray(np.dstack([out, a]), "RGBA"))


def manifest(species: str, number: int, base: BaseMesh, base_version: str, created_by: str, created_at: str,
             families: list[dict[str, Any]], region_deltas: list[dict[str, Any]], shell_parts: list[dict[str, Any]],
             pattern_layers: list[dict[str, Any]], atlas: dict[str, Any], notes: str = "") -> dict[str, Any]:
    return {
        "release_schema": "1.0", "release_version": f"release-{species}-{number}", "species": species, "number": number,
        "base_mesh_version": base_version, "base_topology": base.topology_hash(), "atlas": atlas, "mesh": "mesh.json",
        "notes": notes, "created_at": created_at, "created_by": created_by, "families": families,
        "region_deltas": region_deltas, "shell_parts": shell_parts, "pattern_layers": pattern_layers, "files": [],
    }


BACK_PATTERNS = ("pattern_saddle", "pattern_tabby", "pattern_brindle", "pattern_merle")


def pattern_thumbnail(base: BaseMesh, masks: np.ndarray, pattern_id: str, channel: int, coverage: float, colour: str) -> bytes:
    """A pattern at a coverage on the bare base mesh, from the front, or from behind for back markings."""
    size = masks.shape[0]
    uv = np.zeros((len(base.co), 2))
    uv[base.tri_verts.ravel()] = base.uv[base.tri_loops].reshape(-1, 2)
    xs = np.clip(np.floor(uv[:, 0] * size), 0, size - 1).astype(int)
    ys = np.clip(np.floor((1 - uv[:, 1]) * size), 0, size - 1).astype(int)
    on = masks[ys, xs, channel].astype(float) < coverage * 250
    rgb = np.array([int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0
    colours = np.where(on[:, None], rgb, NEUTRAL)
    return thumbnail(base, base.co, colours, azimuth=150.0 if pattern_id in BACK_PATTERNS else 30.0)
