"""Delta extraction (BRIEF Section 16, M8): a generated figurine becomes one family and one part per region.

After Stage E a figurine is the base mesh with moved vertices, so its offsets D = wrapped - base split exactly
along the base mesh's feathered vertex groups:

    part_r  = D * w_r / max(1, sum w)      for each region r (ears, tail, muzzle, head, legs)
    family  = D - sum_r part_r             the rest of the body, a full-mesh delta

so family + all its parts reproduces the figurine (to float16), and each part carries its region's shape onto any
other family because the boundary loops are identical. Mixing parts across figurines is what the QC metrics in
petpop_library.qc then judge.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .deltas import REGIONS, region_weights
from .meshkit import BaseMesh


@dataclass
class PartsSet:
    """One figurine's family delta and region parts, all float16-exact (n, 3) float64 arrays."""
    family: np.ndarray
    parts: dict[str, np.ndarray]

    def compose(self, base: BaseMesh) -> np.ndarray:
        return base.co.astype(np.float64) + self.family + sum(self.parts.values())


def f16(a: np.ndarray) -> np.ndarray:
    return np.asarray(a, dtype="<f2").astype(np.float64)


def normalised_weights(base: BaseMesh) -> dict[str, np.ndarray]:
    """Region weights scaled so they never sum past 1 at a vertex (the groups overlap only in feather bands)."""
    w = {r: region_weights(base, r) for r in REGIONS}
    total = np.maximum(1.0, sum(w.values()))
    return {r: v / total for r, v in w.items()}


def extract(base: BaseMesh, wrapped: np.ndarray) -> PartsSet:
    offsets = np.asarray(wrapped, dtype=np.float64) - base.co.astype(np.float64)
    weights = normalised_weights(base)
    parts = {r: f16(offsets * w[:, None]) for r, w in weights.items()}
    # The family absorbs float16 rounding of the parts, so the set recomposes the figurine as closely as float16 allows.
    family = f16(offsets - sum(parts.values()))
    return PartsSet(family=family, parts=parts)
