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


ATLAS = 1024


def mesh_entry(mesh: BaseMesh, name: str, breeds: list[str], version: int = 1, source_job: str | None = None,
               size: int = ATLAS, texture: bytes | None = None) -> tuple[dict[str, Any], dict[str, bytes]]:
    """One release mesh (decision 116) and its files under meshes/<mesh_id>/: the viewer's binary and info, the
    figure package the export reads, the pattern masks in the mesh's own UVs, its texture and a thumbnail."""
    from . import figure
    from .atlas import mesh_texel_map
    from .basebin import base_bin, mesh_json
    from .patterns import CHANNELS, build_masks, pack_png

    d = f"meshes/{mesh.mesh_id}"
    files = {f"{d}/mesh.bin": base_bin(mesh), f"{d}/mesh.json": mesh_json(mesh, f"{d}/mesh.bin"),
             f"{d}/figure_mesh.npz": figure.save(mesh), f"{d}/thumb.png": thumbnail(mesh, mesh.co)}
    masks = pack_png(build_masks(mesh, mesh_texel_map(mesh, size)))
    for i, data in enumerate(masks):
        files[f"{d}/masks_{i}.png"] = data
    if texture is not None:
        files[f"{d}/texture.png"] = texture
    entry = {"id": mesh.mesh_id, "name": name, "source": mesh.source or "template", "bin": f"{d}/mesh.bin",
             "info": f"{d}/mesh.json", "package": f"{d}/figure_mesh.npz", "texture": f"{d}/texture.png" if texture else None,
             "atlas": {"size": size, "mask_files": [f"{d}/masks_{i}.png" for i in range(len(masks))],
                       "channels": {c: i for i, c in enumerate(CHANNELS)}},
             "breeds": sorted(set(breeds)), "source_job": source_job, "version": version, "thumbnail": f"{d}/thumb.png"}
    return entry, files


def manifest(species: str, number: int, segmentation_version: str, created_by: str, created_at: str,
             meshes: list[dict[str, Any]], families: list[dict[str, Any]], region_deltas: list[dict[str, Any]],
             shell_parts: list[dict[str, Any]], pattern_layers: list[dict[str, Any]], notes: str = "") -> dict[str, Any]:
    """A release 2.0 manifest (decision 118). Each mesh lists the breeds of every family built on it, so breeds that
    share a mesh say so."""
    breeds: dict[str, set[str]] = {}
    for f in families:
        breeds.setdefault(f["mesh_id"], set()).update(f["breeds"])
    meshes = [{**m, "breeds": sorted(set(m["breeds"]) | breeds.get(m["id"], set()))} for m in meshes]
    return {
        "release_schema": "2.0", "release_version": f"release-{species}-{number}", "species": species, "number": number,
        "segmentation_version": segmentation_version, "meshes": meshes, "notes": notes, "created_at": created_at,
        "created_by": created_by, "families": families, "region_deltas": region_deltas, "shell_parts": shell_parts,
        "pattern_layers": pattern_layers, "files": [],
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
