"""The species UV atlas as a texel map: which triangle owns each texel and where on the base mesh it lies.

Library mode paints in the atlas (BRIEF Section 16): pattern masks, stamps and the export's albedo. Every one of
them is evaluated per texel from the texel's 3D position on the base mesh, which is what makes a stamp that
crosses a UV seam land correctly on both islands. The rules here are mirrored exactly by
packages/viewer/src/atlas.ts (same texel-centre convention, triangle order and barycentric formula, all in
float64), so the kiosk's preview and the export paint the same texels.

Convention (WebGL's): texel (x, y), row 0 at the top, has its centre at u = (x + 0.5) / S, v = 1 - (y + 0.5) / S.
Triangles are rasterised in index order; a texel centre inside (barycentrics >= -1e-9) a later triangle
overwrites an earlier one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .meshkit import BaseMesh, load_base

EPS = -1e-9


@dataclass(frozen=True)
class TexelMap:
    size: int
    tri: np.ndarray       # (S, S) int32 triangle id, -1 where no triangle covers the texel centre
    bary: np.ndarray      # (S, S, 3) float64 barycentric weights of the triangle's three corners
    order: np.ndarray     # covered texel flat indices sorted by triangle
    starts: np.ndarray    # (t + 1,) CSR offsets into `order` per triangle

    def texels_of(self, t: int) -> np.ndarray:
        return self.order[self.starts[t]:self.starts[t + 1]]

    @property
    def covered(self) -> np.ndarray:
        return self.tri >= 0


def corner_px(base: BaseMesh, size: int) -> np.ndarray:
    """(t, 3, 2) corner positions in texel space (x right, y down; texel centres at integers)."""
    uv = base.uv[base.tri_loops].astype(np.float64)
    px = np.empty_like(uv)
    px[..., 0] = uv[..., 0] * size - 0.5
    px[..., 1] = (1.0 - uv[..., 1]) * size - 0.5
    return px


def build_texel_map(base: BaseMesh, size: int) -> TexelMap:
    tri = np.full((size, size), -1, np.int32)
    bary = np.zeros((size, size, 3), np.float64)
    px = corner_px(base, size)
    for t in range(len(px)):
        (x0, y0), (x1, y1), (x2, y2) = px[t]
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if den == 0.0:
            continue
        minx = max(int(math.ceil(min(x0, x1, x2))), 0)
        maxx = min(int(math.floor(max(x0, x1, x2))), size - 1)
        miny = max(int(math.ceil(min(y0, y1, y2))), 0)
        maxy = min(int(math.floor(max(y0, y1, y2))), size - 1)
        if maxx < minx or maxy < miny:
            continue
        xs, ys = np.meshgrid(np.arange(minx, maxx + 1, dtype=np.float64), np.arange(miny, maxy + 1, dtype=np.float64))
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
        g = 1.0 - a - b
        inside = (a >= EPS) & (b >= EPS) & (g >= EPS)
        if not inside.any():
            continue
        yy, xx = ys[inside].astype(np.intp), xs[inside].astype(np.intp)
        tri[yy, xx] = t
        bary[yy, xx, 0] = a[inside]
        bary[yy, xx, 1] = b[inside]
        bary[yy, xx, 2] = g[inside]
    flat = tri.ravel()
    covered = np.nonzero(flat >= 0)[0]
    order = covered[np.argsort(flat[covered], kind="stable")]
    counts = np.bincount(flat[covered], minlength=len(px))
    starts = np.zeros(len(px) + 1, np.int64)
    np.cumsum(counts, out=starts[1:])
    return TexelMap(size=size, tri=tri, bary=bary, order=order, starts=starts)


@lru_cache(maxsize=8)
def texel_map(species: str, size: int) -> TexelMap:
    return build_texel_map(load_base(species), size)


def texel_values(base: BaseMesh, tm: TexelMap, values: np.ndarray) -> np.ndarray:
    """Per-vertex values (n,) or (n, C) interpolated to every covered texel: (S, S) or (S, S, C); 0 elsewhere."""
    vals = values if values.ndim == 2 else values[:, None]
    out = np.zeros((tm.size, tm.size, vals.shape[1]), np.float64)
    cov = tm.covered
    tv = base.tri_verts[tm.tri[cov]]
    w = tm.bary[cov]
    out[cov] = w[:, 0:1] * vals[tv[:, 0]] + w[:, 1:2] * vals[tv[:, 1]] + w[:, 2:3] * vals[tv[:, 2]]
    return out if values.ndim == 2 else out[..., 0]


def texel_positions(base: BaseMesh, tm: TexelMap, co: np.ndarray | None = None) -> np.ndarray:
    """3D position (mm) of every covered texel on the base mesh (or on `co`), (S, S, 3)."""
    return texel_values(base, tm, (base.co if co is None else co).astype(np.float64))


def dilate_into_padding(img: np.ndarray, covered: np.ndarray, px: int) -> np.ndarray:
    """Copy edge texels outwards `px` texels so bilinear sampling never reads an empty texel at a seam."""
    out = img.copy()
    have = covered.copy()
    for _ in range(px):
        grown = out.copy()
        new = have.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src_have = np.roll(have, (dy, dx), axis=(0, 1))
            take = src_have & ~new
            grown[take] = np.roll(out, (dy, dx), axis=(0, 1))[take]
            new |= take
        out, have = grown, new
    return out
