"""Region deltas and family deltas on the base mesh (BRIEF Section 16).

After Stage E every figurine is the base mesh with moved vertices, so a part is the vertex offsets inside one
region, feathered at the region's boundary by the vertex-group weights the base mesh already carries. Deltas
from different figurines combine on one chassis because the boundary loops are identical. A family is a
full-mesh delta (body or head variant). All deltas are stored as little-endian float16 (n, 3) arrays keyed by the
base-mesh version; the kiosk applies the same arrays as morph offsets in the preview.
"""
from __future__ import annotations

import numpy as np

from .meshkit import BaseMesh

REGIONS: dict[str, tuple[str, ...]] = {
    "ears": ("ear_L", "ear_R"),
    "tail": ("tail",),
    "muzzle": ("muzzle",),
    "head": ("head",),
    "legs": ("leg_FL", "leg_FR", "leg_BL", "leg_BR"),
}


def region_weights(base: BaseMesh, region: str) -> np.ndarray:
    """(n,) feathered weights of a region. Head excludes the muzzle and ears so regions never double-count."""
    w = np.max(np.stack([base.group(g) for g in REGIONS[region]]), axis=0).astype(np.float64)
    if region == "head":
        w = w * (1.0 - base.group("muzzle").astype(np.float64))
        w[np.isin(base.shell, (1, 2))] = 0.0  # ear shells belong to the ears region
    return np.clip(w, 0.0, 1.0)


def encode(delta: np.ndarray) -> bytes:
    return np.asarray(delta, dtype="<f2").tobytes()


def decode(data: bytes, n: int) -> np.ndarray:
    arr = np.frombuffer(data, dtype="<f2")
    if arr.size != n * 3:
        raise ValueError(f"delta has {arr.size} values, expected {n * 3}")
    return arr.reshape(n, 3).astype(np.float64)


def region_delta(base: BaseMesh, offsets: np.ndarray, region: str) -> np.ndarray:
    """Restrict full-mesh offsets to a region, feathered at its boundary; float16-exact."""
    d = offsets * region_weights(base, region)[:, None]
    return d.astype("<f2").astype(np.float64)


def compose(base: BaseMesh, family: np.ndarray | None, parts: list[np.ndarray]) -> np.ndarray:
    """Vertex positions of a composition: base + family delta + every region delta (all float16 values)."""
    co = base.co.astype(np.float64).copy()
    if family is not None:
        co += family
    for d in parts:
        co += d
    return co


def mirror_x(p: list[float] | np.ndarray) -> list[float]:
    """The base mesh is symmetric about X, so symmetry mirrors a stamp's base-space position in X."""
    return [-float(p[0]), float(p[1]), float(p[2])]
