"""Numpy mesh utilities over the base-mesh package (assets/base/{species}/base_raw.npz).

Used by the S0 fixture generator, the low-fidelity trimesh stand-in and checks that must run without bpy:
morphing, UV-space rasterisation (masks, albedo), a small orthographic z-buffer renderer (silhouettes,
depth, flat-shaded previews) and OBJ/GLB writers that keep the fixed UV layout.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .paths import BASE_DIR


@dataclass
class BaseMesh:
    species: str
    co: np.ndarray            # (n, 3) basis positions, mm
    tri_verts: np.ndarray     # (t, 3) vertex indices
    tri_loops: np.ndarray     # (t, 3) loop indices (for UVs)
    uv: np.ndarray            # (loops, 2)
    loops_v: np.ndarray
    poly_start: np.ndarray
    poly_total: np.ndarray
    poly_mat: np.ndarray
    tri_poly: np.ndarray
    shell: np.ndarray         # (n,) shell index: body, ear_L, ear_R, tail, eye_L, eye_R, nose
    group_names: list[str]
    groups: np.ndarray        # (g, n)
    morph_names: list[str]
    morph_deltas: np.ndarray  # (m, n, 3)
    mask_names: list[str]
    masks: np.ndarray         # (k, n)
    landmarks: dict[str, int]

    def group(self, name: str) -> np.ndarray:
        return self.groups[self.group_names.index(name)]

    def mask(self, name: str) -> np.ndarray:
        return self.masks[self.mask_names.index(name)]

    def morph(self, weights: dict[str, float]) -> np.ndarray:
        co = self.co.astype(np.float64).copy()
        for name, w in weights.items():
            if name in self.morph_names and w:
                co += self.morph_deltas[self.morph_names.index(name)] * w
        return co

    def topology_hash(self) -> str:
        h = hashlib.sha256()
        h.update(self.tri_verts.tobytes())
        h.update(self.poly_total.tobytes())
        return h.hexdigest()[:16]

    def uv_hash(self) -> str:
        return hashlib.sha256(np.round(self.uv, 5).astype(np.float32).tobytes()).hexdigest()[:16]


@lru_cache
def load_base(species: str, base_dir: str | None = None) -> BaseMesh:
    d = Path(base_dir) if base_dir else BASE_DIR / species
    z = np.load(d / "base_raw.npz")
    lm = json.loads((d / "landmarks.json").read_text())["landmarks"]
    return BaseMesh(
        species=str(z["species"]),
        co=z["co"], tri_verts=z["tri_verts"], tri_loops=z["tri_loops"], uv=z["uv"], loops_v=z["loops_v"],
        poly_start=z["poly_start"], poly_total=z["poly_total"], poly_mat=z["poly_mat"], tri_poly=z["tri_poly"],
        shell=z["shell"], group_names=[str(x) for x in z["group_names"]], groups=z["groups"],
        morph_names=[str(x) for x in z["morph_names"]], morph_deltas=z["morph_deltas"],
        mask_names=[str(x) for x in z["mask_names"]], masks=z["masks"],
        landmarks={k: int(v["vertex"]) for k, v in lm.items()},
    )


# --------------------------------------------------------------------------- UV-space rasterisation

def raster_uv(base: BaseMesh, values: np.ndarray, size: int, per_face: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Rasterise per-vertex (n, C) or per-triangle (t, C) values into the UV atlas. Returns (img, coverage)."""
    vals = values if values.ndim == 2 else values[:, None]
    c = vals.shape[1]
    img = np.zeros((size, size, c), np.float32)
    cov = np.zeros((size, size), bool)
    uvs = base.uv[base.tri_loops] * (size - 1)  # (t, 3, 2)
    uvs[..., 1] = (size - 1) - uvs[..., 1]      # image rows go down
    for ti in range(len(uvs)):
        (x0, y0), (x1, y1), (x2, y2) = uvs[ti]
        minx, maxx = int(math.floor(min(x0, x1, x2))), int(math.ceil(max(x0, x1, x2)))
        miny, maxy = int(math.floor(min(y0, y1, y2))), int(math.ceil(max(y0, y1, y2)))
        minx, miny = max(minx, 0), max(miny, 0)
        maxx, maxy = min(maxx, size - 1), min(maxy, size - 1)
        if maxx < minx or maxy < miny:
            continue
        xs, ys = np.meshgrid(np.arange(minx, maxx + 1) + 0.0, np.arange(miny, maxy + 1) + 0.0)
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-12:
            continue
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
        g = 1 - a - b
        inside = (a >= -0.02) & (b >= -0.02) & (g >= -0.02)
        if not inside.any():
            continue
        if per_face:
            col = np.broadcast_to(vals[ti], (inside.sum(), c))
        else:
            tv = base.tri_verts[ti]
            col = a[inside][:, None] * vals[tv[0]] + b[inside][:, None] * vals[tv[1]] + g[inside][:, None] * vals[tv[2]]
        yy, xx = ys[inside].astype(int), xs[inside].astype(int)
        img[yy, xx] = col
        cov[yy, xx] = True
    return img, cov


def dilate(img: np.ndarray, cov: np.ndarray, px: int) -> np.ndarray:
    """Seam padding: grow covered texels outwards by px pixels."""
    out, c = img.copy(), cov.copy()
    for _ in range(px):
        acc = np.zeros_like(out)
        cnt = np.zeros(c.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sc = np.roll(np.roll(c, dy, 0), dx, 1)
            si = np.roll(np.roll(out, dy, 0), dx, 1)
            acc += si * sc[..., None]
            cnt += sc
        grow = (~c) & (cnt > 0)
        out[grow] = acc[grow] / cnt[grow][:, None]
        c = c | grow
    return out


# --------------------------------------------------------------------------- orthographic renderer

VIEWS = {"front": 0.0, "left": 90.0, "back": 180.0, "right": 270.0}
EXTENT_DEFAULT = 110.0   # orthographic view width in mm (same framing as the Blender cameras)
CENTRE_Z_DEFAULT = 45.0


def view_matrix(azimuth_deg: float) -> np.ndarray:
    """Camera orbiting around +Z; azimuth 0 looks at the front (camera on -Y), 90 at the pet's left (+X)."""
    a = math.radians(azimuth_deg)
    # Rotate the world by -a about Z, then map to camera space (x right, y up, z towards camera).
    rz = np.array([[math.cos(a), math.sin(a), 0], [-math.sin(a), math.cos(a), 0], [0, 0, 1]])
    to_cam = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    return to_cam @ rz


def render(co: np.ndarray, tris: np.ndarray, azimuth: float, size: int, colours: np.ndarray | None = None,
           extent: float = EXTENT_DEFAULT, centre_z: float = CENTRE_Z_DEFAULT, light=(0.4, 0.6, 0.7)) -> dict[str, np.ndarray]:
    """Z-buffer render. Returns depth (camera distance, inf = empty), alpha and an RGB image if colours given."""
    m = view_matrix(azimuth)
    p = (co - np.array([0, 0, centre_z])) @ m.T
    scale = (size - 1) / extent
    px = p[:, 0] * scale + (size - 1) / 2
    py = (size - 1) / 2 - p[:, 1] * scale
    pz = p[:, 2]
    depth = np.full((size, size), np.inf, np.float32)
    rgb = np.ones((size, size, 3), np.float32)
    v0, v1, v2 = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12
    cam_n = fn @ m.T
    ld = np.array(light) / np.linalg.norm(light)
    shade = np.clip(0.35 + 0.65 * np.abs(cam_n @ ld), 0, 1)
    for ti in range(len(tris)):
        i0, i1, i2 = tris[ti]
        x0, x1, x2 = px[i0], px[i1], px[i2]
        y0, y1, y2 = py[i0], py[i1], py[i2]
        minx, maxx = max(int(min(x0, x1, x2)), 0), min(int(math.ceil(max(x0, x1, x2))), size - 1)
        miny, maxy = max(int(min(y0, y1, y2)), 0), min(int(math.ceil(max(y0, y1, y2))), size - 1)
        if maxx < minx or maxy < miny:
            continue
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        xs, ys = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
        g = 1 - a - b
        inside = (a >= 0) & (b >= 0) & (g >= 0)
        if not inside.any():
            continue
        z = -(a * pz[i0] + b * pz[i1] + g * pz[i2])  # distance from the camera plane
        yy, xx = (ys - 0.5).astype(int), (xs - 0.5).astype(int)
        sub = depth[miny:maxy + 1, minx:maxx + 1]
        closer = inside & (z < sub)
        if not closer.any():
            continue
        sub[closer] = z[closer]
        if colours is not None:
            col = colours[[i0, i1, i2]].mean(axis=0) * shade[ti]
            rgb[yy[closer], xx[closer]] = col
    alpha = np.isfinite(depth)
    return {"depth": depth, "alpha": alpha, "rgb": rgb}


def silhouette_iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 1.0


def depth_png16(depth: np.ndarray) -> np.ndarray:
    """Normalise finite depth to 16-bit, near = bright (ControlNet convention), background 0."""
    out = np.zeros(depth.shape, np.uint16)
    fin = np.isfinite(depth)
    if fin.any():
        d = depth[fin]
        lo, hi = d.min(), d.max()
        out[fin] = (65535 * (1 - (d - lo) / max(hi - lo, 1e-6)) * 0.9 + 65535 * 0.1).astype(np.uint16)
    return out


# --------------------------------------------------------------------------- writers

def write_obj(path: Path, base: BaseMesh, co: np.ndarray) -> None:
    """OBJ with the base-mesh UV layout verbatim (polygons, not triangles)."""
    buf = io.StringIO()
    buf.write(f"# PetPop figure, species {base.species}, topology {base.topology_hash()}, uv {base.uv_hash()}\n")
    for p in co:
        buf.write(f"v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}\n")
    for t in base.uv:
        buf.write(f"vt {t[0]:.6f} {t[1]:.6f}\n")
    for s, n in zip(base.poly_start, base.poly_total):
        idx = range(int(s), int(s + n))
        buf.write("f " + " ".join(f"{base.loops_v[i] + 1}/{i + 1}" for i in idx) + "\n")
    Path(path).write_text(buf.getvalue())


def to_trimesh(base: BaseMesh, co: np.ndarray, texture=None, yup: bool = False):
    """Loop-split trimesh (one vertex per loop) so the UVs survive; optional PIL texture.
    yup=True converts Blender Z-up/front -Y to glTF Y-up/front +Z (for GLB export)."""
    import trimesh
    from trimesh.visual import TextureVisuals
    from trimesh.visual.material import PBRMaterial

    loops = base.tri_loops.reshape(-1)
    verts = co[base.loops_v[loops]]
    if yup:
        verts = np.stack([verts[:, 0], verts[:, 2], -verts[:, 1]], axis=1)
    faces = np.arange(len(loops)).reshape(-1, 3)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    if texture is not None:
        mat = PBRMaterial(baseColorTexture=texture, metallicFactor=0.0, roughnessFactor=0.55)
        mesh.visual = TextureVisuals(uv=base.uv[loops], material=mat)
    mesh.merge_vertices(merge_tex=False, merge_norm=True)
    return mesh
