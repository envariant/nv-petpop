"""Figurine meshes (decision 116): every figurine keeps its own mesh, labelled to the species segmentation schema.

A figurine mesh has the same data shape as a template (meshkit.BaseMesh): positions, triangles with per-corner
UVs, part weights (`groups`, named as the schema's parts), pattern-region values (`masks`), landmarks and shells.
So the UV rasteriser, the writers, the accessory anchors, the pattern fields, the print mesh and the paint check
work on it unchanged. It has no morph targets, and its `mesh_id` is a content hash: two figurines (or breeds)
share a mesh only when their geometry is identical, and are labelled so.
"""
from __future__ import annotations

import hashlib
import io
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from petpop_core.paths import DATA

from .meshkit import BaseMesh

SHELLS = ["body", "ear_L", "ear_R", "tail", "eye_L", "eye_R", "nose"]  # the template's shell order


@lru_cache
def schema(species: str) -> dict:
    """data/segmentation/{species}.json (validated by data/schema/segmentation.schema.json)."""
    return json.loads((DATA / "segmentation" / f"{species}.json").read_text())


def compute_mesh_id(co: np.ndarray, tris: np.ndarray, uv: np.ndarray | None = None) -> str:
    """Content hash of the geometry (positions to 1 micron) and UVs: equal meshes have equal ids."""
    h = hashlib.sha256()
    h.update(np.round(np.asarray(co, np.float64), 3).astype(np.float32).tobytes())
    h.update(np.asarray(tris, np.int64).tobytes())
    if uv is not None:
        h.update(np.round(np.asarray(uv, np.float64), 5).astype(np.float32).tobytes())
    return "m_" + h.hexdigest()[:16]


def shells_from_parts(species: str, group_names: list[str], groups: np.ndarray) -> np.ndarray:
    """(n,) shell index per vertex from its dominant part's role in the schema (a figurine is one surface)."""
    role = {p["name"]: SHELLS.index(p["shell"]) for p in schema(species)["parts"]}
    dominant = np.argmax(groups, axis=0)
    lut = np.array([role.get(g, 0) for g in group_names], np.int64)
    return lut[dominant]


def make(species: str, co: np.ndarray, tris: np.ndarray, corner_uv: np.ndarray, group_names: list[str],
         groups: np.ndarray, mask_names: list[str], masks: np.ndarray, landmarks: dict[str, int],
         schema_version: str | None = None) -> BaseMesh:
    """A figurine mesh from triangles with per-corner UVs ((t, 3, 2))."""
    co = np.asarray(co, np.float64)
    tris = np.asarray(tris, np.int64)
    t = len(tris)
    uv = np.asarray(corner_uv, np.float64).reshape(t * 3, 2)
    groups = np.asarray(groups, np.float32)
    return BaseMesh(
        species=species, co=co, tri_verts=tris, tri_loops=np.arange(t * 3, dtype=np.int64).reshape(t, 3), uv=uv,
        loops_v=tris.reshape(-1), poly_start=np.arange(0, t * 3, 3, dtype=np.int64), poly_total=np.full(t, 3, np.int64),
        poly_mat=np.zeros(t, np.int64), tri_poly=np.arange(t, dtype=np.int64),
        shell=shells_from_parts(species, group_names, groups), group_names=list(group_names), groups=groups,
        morph_names=[], morph_deltas=np.zeros((0, len(co), 3), np.float32),
        mask_names=list(mask_names), masks=np.asarray(masks, np.float32), landmarks=dict(landmarks),
        mesh_id=compute_mesh_id(co, tris, uv), schema_version=schema_version or schema(species)["schema_version"],
        source="generated")


def from_template(base: BaseMesh, co: np.ndarray) -> BaseMesh:
    """The morphed template as a figurine of its own (the parametric fallback): template topology and UVs."""
    from dataclasses import replace

    return replace(base, co=np.asarray(co, np.float64), morph_names=[], morph_deltas=np.zeros((0, len(co), 3), np.float32),
                   mesh_id=compute_mesh_id(co, base.tri_verts, base.uv), schema_version=schema(base.species)["schema_version"],
                   source="template")


_ARRAYS = ("co", "tri_verts", "tri_loops", "uv", "loops_v", "poly_start", "poly_total", "poly_mat", "tri_poly", "shell",
           "groups", "masks")


def save(mesh: BaseMesh) -> bytes:
    """figure_mesh.npz: every array plus names, landmarks, mesh_id and schema version."""
    meta = {"species": mesh.species, "group_names": mesh.group_names, "mask_names": mesh.mask_names,
            "landmarks": mesh.landmarks, "mesh_id": mesh.mesh_id, "schema_version": mesh.schema_version,
            "source": mesh.source}
    buf = io.BytesIO()
    np.savez_compressed(buf, meta=np.frombuffer(json.dumps(meta).encode(), np.uint8),
                        **{k: getattr(mesh, k) for k in _ARRAYS})
    return buf.getvalue()


def load(data: bytes | str | Path) -> BaseMesh:
    z = np.load(io.BytesIO(data) if isinstance(data, bytes) else data)
    meta = json.loads(bytes(z["meta"]).decode())
    arrays = {k: z[k] for k in _ARRAYS}
    return BaseMesh(species=meta["species"], group_names=meta["group_names"], mask_names=meta["mask_names"],
                    landmarks={k: int(v) for k, v in meta["landmarks"].items()}, morph_names=[],
                    morph_deltas=np.zeros((0, len(arrays["co"]), 3), np.float32), mesh_id=meta["mesh_id"],
                    schema_version=meta["schema_version"], source=meta.get("source", ""), **arrays)


def read_glb(data: bytes):
    """A generated mesh from Stage D's shape.glb: (co Z-up mm, tris, corner_uv (t, 3, 2) or None, albedo PIL image
    or None). Vertices split at UV seams are welded, so parts and landmarks see one connected surface, while the
    UVs stay per corner."""
    import trimesh
    from PIL import Image

    m = trimesh.load(io.BytesIO(data), file_type="glb", force="mesh", process=False)
    v = np.asarray(m.vertices, np.float64)
    co = np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1)  # glTF Y-up -> Z-up, front -Y
    faces = np.asarray(m.faces, np.int64)
    uv = getattr(m.visual, "uv", None)
    corner_uv = np.asarray(uv, np.float64)[faces] if uv is not None and len(uv) == len(v) else None
    albedo = None
    mat = getattr(m.visual, "material", None)
    if corner_uv is not None and mat is not None:
        img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
        if img is not None:
            arr = np.asarray(img.convert("RGB"), np.float32)
            factor = getattr(mat, "baseColorFactor", None)
            if factor is not None:
                f = np.asarray(factor, np.float32)[:3]
                arr = arr * (f / 255.0 if f.max() > 1 else f)
            albedo = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    key = np.round(co, 4)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    co = co[first]
    tris = inverse.reshape(-1)[faces]
    keep = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    if corner_uv is not None:
        corner_uv = corner_uv[keep]
    return co, tris[keep], corner_uv, albedo


def grid_uvs(t: int) -> np.ndarray:
    """Per-corner UVs that give every triangle its own cell (the unwrap when Blender is not available)."""
    cells = int(np.ceil(np.sqrt(t)))
    i = np.arange(t)
    x, y = (i % cells).astype(np.float64), (i // cells).astype(np.float64)
    pad = 0.12
    a = np.stack([x + pad, y + pad], 1)
    b = np.stack([x + 1 - 2 * pad, y + pad], 1)
    c = np.stack([x + pad, y + 1 - 2 * pad], 1)
    return np.stack([a, b, c], axis=1) / cells


def parts_png(mesh: BaseMesh, size: int) -> bytes:
    """The part label of every texel in the mesh's own UV layout (8-bit: 0 empty, i + 1 for the schema's i-th part),
    for the painter kernel (BRIEF Section 10)."""
    from PIL import Image

    from .meshkit import raster_uv

    order = [p["name"] for p in schema(mesh.species)["parts"]]
    dominant = np.argmax(mesh.groups[:, mesh.tri_verts].mean(axis=2), axis=0)  # per triangle
    label = np.array([order.index(mesh.group_names[d]) + 1 for d in dominant], np.float32)
    img, _ = raster_uv(mesh, label[:, None], size, per_face=True)
    buf = io.BytesIO()
    Image.fromarray(np.round(img[..., 0]).astype(np.uint8), "L").save(buf, format="PNG")
    return buf.getvalue()
