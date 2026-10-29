"""QC metrics for library parts (BRIEF Section 16, M8): wrap validity, symmetry error, boundary strain and
self-intersection, per region and for the family, with the auto-reject thresholds Studio applies before review.

- wrap validity: Stage E's own verdict (the manifest's wrap_valid); an invalid wrap rejects the whole figurine.
- symmetry error (mm): how far a delta is from its own mirror image in X, weighted by the region (the base mesh is
  exactly symmetric, so a symmetric pet has zero error; ears and legs are judged as pairs).
- boundary strain: the 95th-percentile relative change in edge length across the region's feather band when the
  part is applied to the bare base mesh, i.e. how hard the part pulls at the seam it shares with every family.
- self-intersection: triangles of one shell that cross each other in the composed figurine, counted per region.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from .deltas import REGIONS
from .extract import PartsSet, normalised_weights
from .meshkit import BaseMesh, load_base

# Auto-reject thresholds, calibrated on the pipeline's fixture pack (DECISIONS 76). A region failing any of them is
# rejected before review; the curator sees the metric and can still override. Tails are exempt from symmetry
# (a curled or sickle tail is meant to be asymmetric).
THRESHOLDS: dict[str, float] = {"symmetry_mm": 3.0, "boundary_strain": 2.0, "self_intersections": 0}
NO_SYMMETRY = {"tail"}


@dataclass
class RegionQC:
    symmetry_mm: float
    boundary_strain: float
    self_intersections: int
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.reasons

    def as_dict(self) -> dict[str, Any]:
        return {"symmetry_mm": round(self.symmetry_mm, 3), "boundary_strain": round(self.boundary_strain, 3),
                "self_intersections": int(self.self_intersections), "passed": self.passed, "reasons": self.reasons}


@lru_cache(maxsize=4)
def mirror_index(species: str) -> np.ndarray:
    """For each base vertex, the vertex at its mirror position (-x, y, z)."""
    co = load_base(species).co.astype(np.float64)
    _, idx = cKDTree(co).query(co * np.array([-1.0, 1.0, 1.0]))
    return idx


def symmetry_error(base: BaseMesh, delta: np.ndarray, weights: np.ndarray) -> float:
    m = mirror_index(base.species)
    mirrored = delta[m] * np.array([-1.0, 1.0, 1.0])
    err = np.linalg.norm(delta - mirrored, axis=1)
    w = np.clip(weights, 0, 1)
    return float((err * w).sum() / max(w.sum(), 1e-9))


def edges(base: BaseMesh) -> np.ndarray:
    t = base.tri_verts
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    return np.unique(np.sort(e, axis=1), axis=0)


def boundary_strain(base: BaseMesh, part: np.ndarray, weights: np.ndarray) -> float:
    band = (weights > 0.02) & (weights < 0.98)
    e = edges(base)
    e = e[band[e[:, 0]] | band[e[:, 1]]]
    if not len(e):
        return 0.0
    co = base.co.astype(np.float64)
    moved = co + part
    l0 = np.linalg.norm(co[e[:, 0]] - co[e[:, 1]], axis=1)
    l1 = np.linalg.norm(moved[e[:, 0]] - moved[e[:, 1]], axis=1)
    return float(np.percentile(np.abs(l1 / np.maximum(l0, 1e-9) - 1.0), 95))


@lru_cache(maxsize=4)
def base_crossings(species: str) -> np.ndarray:
    """Triangles that already cross in the undeformed base mesh (a proxy-mesh artefact, not the part's fault)."""
    base = load_base(species)
    return _crossing(base, base.co.astype(np.float64))


def self_intersecting_triangles(base: BaseMesh, co: np.ndarray) -> np.ndarray:
    """(t,) bool: triangles that cross another non-adjacent triangle of the same shell, beyond the base mesh's own."""
    return _crossing(base, co) & ~base_crossings(base.species)


def _crossing(base: BaseMesh, co: np.ndarray) -> np.ndarray:
    tri = base.tri_verts
    p = co[tri]  # (t, 3, 3)
    cen = p.mean(axis=1)
    rad = np.linalg.norm(p - cen[:, None], axis=2).max(axis=1)
    pairs = cKDTree(cen).query_pairs(2.0 * float(rad.max()), output_type="ndarray")
    if not len(pairs):
        return np.zeros(len(tri), bool)
    a, b = pairs[:, 0], pairs[:, 1]
    keep = np.linalg.norm(cen[a] - cen[b], axis=1) <= rad[a] + rad[b]
    shell = base.shell[tri[:, 0]]
    keep &= shell[a] == shell[b]
    shared = (tri[a][:, :, None] == tri[b][:, None, :]).any(axis=(1, 2))
    keep &= ~shared
    a, b = a[keep], b[keep]
    hit = _edges_cross(p[a], p[b]) | _edges_cross(p[b], p[a])
    out = np.zeros(len(tri), bool)
    out[a[hit]] = True
    out[b[hit]] = True
    return out


def _edges_cross(A: np.ndarray, B: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    """(k,) whether any edge of triangle A[k] passes through the interior of triangle B[k] (Moller-Trumbore)."""
    hit = np.zeros(len(A), bool)
    e1, e2 = B[:, 1] - B[:, 0], B[:, 2] - B[:, 0]
    for i, j in ((0, 1), (1, 2), (2, 0)):
        o, d = A[:, i], A[:, j] - A[:, i]
        h = np.cross(d, e2)
        det = np.einsum("ij,ij->i", e1, h)
        ok = np.abs(det) > eps
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - B[:, 0]
        u = inv * np.einsum("ij,ij->i", s, h)
        q = np.cross(s, e1)
        v = inv * np.einsum("ij,ij->i", d, q)
        t = inv * np.einsum("ij,ij->i", e2, q)
        hit |= ok & (u > eps) & (v > eps) & (u + v < 1 - eps) & (t > eps) & (t < 1 - eps)
    return hit


def evaluate(base: BaseMesh, parts: PartsSet, wrap_valid: bool = True,
             thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """QC for one figurine's parts set: per region and for the family, each with pass/fail reasons."""
    th = {**THRESHOLDS, **(thresholds or {})}
    weights = normalised_weights(base)
    crossing = self_intersecting_triangles(base, parts.compose(base))
    # A crossing triangle counts against every region that owns one of its vertices (weight >= 0.5).
    vert_hits = np.zeros(len(base.co), bool)
    vert_hits[base.tri_verts[crossing].ravel()] = True
    out: dict[str, Any] = {"wrap_valid": bool(wrap_valid), "self_intersecting_triangles": int(crossing.sum()), "regions": {}}
    family_w = 1.0 - np.clip(sum(weights.values()), 0, 1)
    for name, w, delta in [*((r, weights[r], parts.parts[r]) for r in REGIONS), ("family", family_w, parts.family)]:
        q = RegionQC(symmetry_mm=symmetry_error(base, delta, w),
                     boundary_strain=boundary_strain(base, delta, w) if name != "family" else 0.0,
                     self_intersections=int((vert_hits & (w >= 0.5)).sum()))
        if not wrap_valid:
            q.reasons.append("wrap invalid")
        if name not in NO_SYMMETRY and q.symmetry_mm > th["symmetry_mm"]:
            q.reasons.append(f"symmetry error {q.symmetry_mm:.2f} mm > {th['symmetry_mm']}")
        if q.boundary_strain > th["boundary_strain"]:
            q.reasons.append(f"boundary strain {q.boundary_strain:.2f} > {th['boundary_strain']}")
        if q.self_intersections > th["self_intersections"]:
            q.reasons.append(f"{q.self_intersections} self-intersecting vertices")
        out["regions"][name] = q.as_dict()
    out["passed_regions"] = [r for r, q in out["regions"].items() if q["passed"]]
    return out
