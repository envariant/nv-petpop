"""Stage E UV unwrap for generated meshes that arrive without UVs (self-hosted shape models): Smart UV Project,
islands packed with a small margin. Returns per-corner UVs in triangle order (decision 116)."""
import math
from pathlib import Path

import bpy  # noqa: I001
import numpy as np

from common import activate, reset


def main(job: dict) -> dict:
    reset()
    co = np.load(job["co"]).astype(np.float64)
    tris = np.load(job["tris"]).astype(np.int64)
    me = bpy.data.meshes.new("figure")
    me.from_pydata([tuple(p) for p in co], [], [tuple(int(i) for i in t) for t in tris])
    me.update()
    obj = bpy.data.objects.new("figure", me)
    bpy.context.scene.collection.objects.link(obj)
    activate(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(float(job.get("angle_deg", 66))),
                             island_margin=float(job.get("margin", 0.004)))
    bpy.ops.object.mode_set(mode="OBJECT")
    uv = np.empty(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    start = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_start", start)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    uv = uv.reshape(-1, 2)
    idx = start[:, None] + np.arange(3)[None, :]
    if not np.array_equal(lv[idx], tris):  # Blender may rotate a polygon's loops; map corners by vertex
        idx = np.array([[s + list(lv[s:s + 3]).index(v) for v in t] for s, t in zip(start, tris)])
    out = Path(job["out_dir"]) / "corner_uv.npy"
    np.save(out, uv[idx].astype(np.float32))
    return {"corner_uv": str(out)}
