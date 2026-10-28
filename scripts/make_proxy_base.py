#!/usr/bin/env python3
"""Build the proxy base meshes for dog and cat (BRIEF Section 13, "Stand-ins").

Runs pipelines/blender/proxy_base_bpy.py under the bpy interpreter, then derives the UV-space region masks
(mask_a.png: chest, socks, blaze, points; mask_b.png: saddle, face mask, coat, eye+nose) and morphs.json.
The hand-built meshes from Section 10 replace these files with no code change.

    python scripts/make_proxy_base.py [dog|cat ...]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.meshkit import dilate, load_base, raster_uv  # noqa: E402
from backend.core.paths import BASE_DIR, bpy_python  # noqa: E402

MASK_SIZE = 1024
PROXY_VERSION = "proxy-1.0"


def build(species: str) -> None:
    out = BASE_DIR / species
    out.mkdir(parents=True, exist_ok=True)
    script = ROOT / "pipelines/blender/proxy_base_bpy.py"
    res = subprocess.run([bpy_python(), str(script), species, str(out)], capture_output=True, text=True)
    if "PROXY_OK" not in res.stdout:
        sys.stderr.write(res.stdout[-3000:] + res.stderr[-3000:])
        raise SystemExit(f"proxy build failed for {species}")
    load_base.cache_clear()
    base = load_base(species)
    m = {n: base.mask(n) for n in base.mask_names}
    a = np.stack([m["chest"], m["socks"], m["blaze"], m["points"]], axis=1)
    b = np.stack([m["saddle"], m["face_mask"], m["coat"], np.clip(m["eye"] + m["nose"] * 0.5, 0, 1)], axis=1)
    for name, vals in (("mask_a.png", a), ("mask_b.png", b)):
        img, cov = raster_uv(base, vals, MASK_SIZE)
        img = dilate(img, cov, 4)
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8), "RGBA").save(out / name, optimize=True)
    (out / "morphs.json").write_text(json.dumps({
        "species": species,
        "version": PROXY_VERSION,
        "kind": "proxy",
        "morph_targets": base.morph_names,
        "vertex_groups": base.group_names,
        "shells": ["body", "ear_L", "ear_R", "tail", "eye_L", "eye_R", "nose"],
        "masks": {"mask_a.png": ["chest", "socks", "blaze", "points"],
                  "mask_b.png": ["saddle", "face_mask", "coat", "eye_nose"]},
        "vertices": int(len(base.co)),
        "polygons": int(len(base.poly_total)),
        "triangles": int(len(base.tri_verts)),
        "topology_hash": base.topology_hash(),
        "uv_hash": base.uv_hash(),
    }, indent=1) + "\n")
    print(f"{species}: {len(base.co)} verts, {len(base.poly_total)} polys -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    for sp in sys.argv[1:] or ["dog", "cat"]:
        build(sp)
