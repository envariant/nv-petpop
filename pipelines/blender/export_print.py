"""Stage F print mesh (BRIEF Sections 6.6 and 10): the figurine's own mesh joined with its accessories, fuse the flat base disc,
voxel-remesh for watertightness, cut the mandrel socket (blind hole with keying flat from
config/mandrel.json), decimate, check the minimum wall and export STL (the worker writes the 3MF)."""
import json
from pathlib import Path

import bpy  # noqa: I001
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from common import ROOT, activate, add_accessories, mesh_and_object, reset


def apply(obj, mod):
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def cleanup(obj) -> None:
    """Make the decimated mesh printable: merge doubles, fill pin-holes, drop loose fragments (< 0.5 % of
    faces), triangulate and make normals consistent."""
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)
    bm.faces.ensure_lookup_table()
    seen: set[int] = set()
    parts = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for e in cur.edges:
                for nb in e.link_faces:
                    if nb.index not in seen:
                        seen.add(nb.index)
                        stack.append(nb)
        parts.append(comp)
    total = len(bm.faces)
    loose = [f for comp in parts if len(comp) < 0.005 * total for f in comp]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="FACES")
    boundary = [e for e in bm.edges if e.is_boundary]
    if boundary:
        bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def min_wall(obj, samples: int = 2000) -> float:
    me = obj.data
    me.calc_loop_triangles()
    bvh = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    rng = np.random.default_rng(0)
    polys = me.polygons
    idx = rng.choice(len(polys), size=min(samples, len(polys)), replace=False)
    dists = []
    for i in idx:
        p = polys[int(i)]
        n = p.normal
        origin = p.center - n * 1e-3
        hit, _, _, d = bvh.ray_cast(origin, -n, 50.0)
        if hit is not None and d > 1e-2:
            dists.append(d)
    return float(np.percentile(dists, 1)) if dists else float("nan")


def main(job: dict) -> dict:
    cfg = json.loads((ROOT / "config" / "mandrel.json").read_text())
    q = job["quality"]
    reset()
    base, co, obj = mesh_and_object(job)
    parts = [obj] + add_accessories(job.get("accessories", []), co, base.landmarks, base.shell)
    disc = cfg["base_disc"]
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=disc["diameter_mm"] / 2, depth=disc["thickness_mm"],
                                        location=(0, 0, -disc["thickness_mm"] / 2 + 0.6))
    parts.append(bpy.context.active_object)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.join()
    fig = bpy.context.view_layer.objects.active
    fig.vertex_groups.clear()
    fig.name = "print"
    rm = fig.modifiers.new("voxel", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = float(q["voxel_mm"])
    rm.adaptivity = 0.0
    apply(fig, rm)
    sock = cfg["socket"]
    bottom = -disc["thickness_mm"] + 0.6
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=sock["diameter_mm"] / 2, depth=sock["depth_mm"] * 2,
                                        location=(0, 0, bottom))
    hole = bpy.context.active_object
    # Keying flat: a box filling the circle segment beyond the flat on +X.
    flat_x = sock["diameter_mm"] / 2 - sock["keying_flat_mm"]
    bpy.ops.mesh.primitive_cube_add(size=1, location=(flat_x + sock["keying_flat_mm"], 0, bottom))
    key = bpy.context.active_object
    key.scale = (sock["keying_flat_mm"] * 2, sock["diameter_mm"] + 2, sock["depth_mm"] * 2.2)
    activate(key)
    bpy.ops.object.transform_apply(scale=True)
    kb = hole.modifiers.new("key", "BOOLEAN")
    kb.operation = "DIFFERENCE"
    kb.object = key
    kb.solver = "EXACT"
    apply(hole, kb)
    bpy.data.objects.remove(key, do_unlink=True)
    cut = fig.modifiers.new("socket", "BOOLEAN")
    cut.operation = "DIFFERENCE"
    cut.object = hole
    cut.solver = "EXACT"
    apply(fig, cut)
    bpy.data.objects.remove(hole, do_unlink=True)
    tris_now = sum(len(p.vertices) - 2 for p in fig.data.polygons)
    if tris_now > q["print_tris"]:
        dec = fig.modifiers.new("decimate", "DECIMATE")
        dec.ratio = q["print_tris"] / tris_now
        dec.use_collapse_triangulate = True
        apply(fig, dec)
    tri = fig.modifiers.new("tri", "TRIANGULATE")
    apply(fig, tri)
    cleanup(fig)
    # Base flat on the build plate.
    zmin = min(v.co.z for v in fig.data.vertices)
    for v in fig.data.vertices:
        v.co -= Vector((0, 0, zmin))
    fig.data.update()
    wall = min_wall(fig)
    out = Path(job["out_dir"])
    activate(fig)
    bpy.ops.wm.stl_export(filepath=str(out / "figure.stl"), export_selected_objects=True, ascii_format=False)
    zs = [v.co.z for v in fig.data.vertices]
    return {"stl": str(out / "figure.stl"), "tris": len(fig.data.polygons), "height_mm": round(max(zs) - min(zs), 2),
            "min_wall_mm": round(wall, 3), "min_wall_ok": bool(wall >= cfg["min_wall_mm"] or np.isnan(wall))}
