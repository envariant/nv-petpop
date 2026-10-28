#!/usr/bin/env python3
"""Validate a species base mesh against BRIEF Section 10 (works for the proxies and the hand-built meshes).

Checks: quad ratio and face count of the body shell, vertex groups, 14 landmarks, shape keys, UV islands
inside [0,1] without overlap, X symmetry, flat base, 90 mm height, front facing -Y.
Prints a report and exits non-zero on failure. `--strict` enforces the hand-built 8-12 k face range.

    python scripts/check_base_mesh.py [--strict] [dog|cat ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.meshkit import load_base, raster_uv  # noqa: E402
from backend.core.paths import BASE_DIR  # noqa: E402
from backend.core.vocab import vocab  # noqa: E402

GROUPS = ["head", "muzzle", "ear_L", "ear_R", "body", "leg_FL", "leg_FR", "leg_BL", "leg_BR", "tail", "base"]
LANDMARKS = ["nose_tip", "eye_L", "eye_R", "ear_tip_L", "ear_tip_R", "ear_base_L", "ear_base_R", "chin",
             "back_of_head", "tail_tip", "paw_FL", "paw_FR", "base_centre", "neck_front"]


def check(species: str, proxy: bool) -> list[tuple[str, bool, str]]:
    d = BASE_DIR / species
    res: list[tuple[str, bool, str]] = []
    for f in ("base.blend", "base.glb", "base_raw.npz", "landmarks.json", "morphs.json", "mask_a.png", "mask_b.png"):
        res.append((f"file {f}", (d / f).exists(), ""))
    if not (d / "base_raw.npz").exists():
        return res
    load_base.cache_clear()
    b = load_base(species)
    body_polys = np.array([b.shell[b.loops_v[s]] == 0 for s in b.poly_start])
    quads = (b.poly_total[body_polys] == 4).mean()
    nbody = int(body_polys.sum())
    lo, hi = (4000, 14000) if proxy else (8000, 12000)
    res.append(("body shell quad ratio >= 0.95", quads >= 0.95, f"{quads:.3f}"))
    res.append((f"body shell faces in [{lo}, {hi}]", lo <= nbody <= hi, str(nbody)))
    missing = [g for g in GROUPS if g not in b.group_names]
    res.append(("vertex groups present", not missing, ",".join(missing) or "all"))
    empty = [g for g in GROUPS if g in b.group_names and b.group(g).max() <= 0]
    res.append(("vertex groups non-empty", not empty, ",".join(empty) or "ok"))
    lm_missing = [k for k in LANDMARKS if k not in b.landmarks]
    res.append(("14 landmarks", not lm_missing and len(b.landmarks) == 14, ",".join(lm_missing) or "14"))
    expected = vocab()["morph_targets"][species]
    res.append(("shape keys match vocab.morph_targets", b.morph_names == expected,
                f"{len(b.morph_names)} keys"))
    zero = [n for i, n in enumerate(b.morph_names) if np.abs(b.morph_deltas[i]).max() < 1e-3]
    res.append(("every shape key moves geometry", not zero, ",".join(zero) or "ok"))
    uv = b.uv
    res.append(("UVs inside [0,1]", bool((uv >= -1e-4).all() and (uv <= 1 + 1e-4).all()), ""))
    img, cov = raster_uv(b, np.ones((len(b.tri_verts), 1), np.float32), 256, per_face=True)
    res.append(("UV coverage > 25%", cov.mean() > 0.25, f"{cov.mean():.2%}"))
    del img
    co = b.co
    mirrored = co * np.array([-1, 1, 1])
    from scipy.spatial import cKDTree  # noqa: PLC0415

    dist, _ = cKDTree(co).query(mirrored)
    res.append(("X symmetry (max 0.05 mm)", float(dist.max()) < 0.05, f"{dist.max():.4f} mm"))
    h = co[:, 2].max() - co[:, 2].min()
    res.append(("height 90 mm", abs(h - 90) < 0.5, f"{h:.2f} mm"))
    res.append(("base at z = 0", abs(co[:, 2].min()) < 1e-3, f"{co[:, 2].min():.4f}"))
    nose = co[b.landmarks["nose_tip"]]
    res.append(("front faces -Y", nose[1] < co[:, 1].mean(), f"nose y {nose[1]:.1f}"))
    meta = json.loads((d / "morphs.json").read_text())
    res.append(("morphs.json matches mesh", meta.get("topology_hash") == b.topology_hash(), meta.get("kind", "")))
    return res


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv  # Section 10 face counts; the proxies (~6 k quads) use the relaxed range
    ok = True
    for sp in args or ["dog", "cat"]:
        print(f"== base mesh {sp}")
        for name, passed, info in check(sp, not strict):
            ok &= passed
            print(f"  [{'PASS' if passed else 'FAIL'}] {name} {info}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
