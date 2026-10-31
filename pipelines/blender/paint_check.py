"""Stage F paint check (BRIEF Section 6.6): for each face, the free-space distance along its normal to the
next surface; faces closer than the painter head stand-off are flagged. Returns per-triangle flags in the
mesh's triangle order; the worker rasterises them into paint_mask.png in UV space."""
import json
from pathlib import Path

import bpy  # noqa: I001
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from common import ROOT, add_accessories, mesh_and_object, reset


def main(job: dict) -> dict:
    standoff = json.loads((ROOT / "config" / "mandrel.json").read_text())["paint_head_standoff_mm"]
    reset()
    base, co, obj = mesh_and_object(job)
    accs = add_accessories(job.get("accessories", []), co, base.landmarks, base.shell)
    verts = [tuple(p) for p in co]
    polys = [tuple(int(i) for i in t) for t in base.tri_verts]
    offset = len(verts)
    for a in accs:
        mw = a.matrix_world
        for v in a.data.vertices:
            verts.append(tuple(mw @ v.co))
        a.data.calc_loop_triangles()
        polys += [tuple(offset + i for i in t.vertices) for t in a.data.loop_triangles]
        offset = len(verts)
    bvh = BVHTree.FromPolygons(verts, polys, all_triangles=True)
    t = base.tri_verts
    v0, v1, v2 = co[t[:, 0]], co[t[:, 1]], co[t[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    c = (v0 + v1 + v2) / 3
    flags = np.zeros(len(t), dtype=np.uint8)
    for i in range(len(t)):
        if base.shell[t[i, 0]] > 3:
            continue  # eyes and nose are painted flat by the kernel
        hit, _, _, d = bvh.ray_cast(Vector(c[i] + n[i] * 0.05), Vector(n[i]), standoff)
        if hit is not None:
            flags[i] = 1
    out = Path(job["out_dir"])
    np.save(out / "paint_flags.npy", flags)
    return {"flags": str(out / "paint_flags.npy"), "pct": round(float(flags.mean() * 100), 2)}
