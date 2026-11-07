"""Compose a figure from a part kit in Blender (decision 127, docs/PARTS.md section 3).

job: {"parts": [{"path": GLB, "matrix": 4x4 row-major in the glTF frame, "mirrored": bool, "slot": str,
                 "source": zip of the uploaded OBJ + MTL + textures | absent, "source_matrix": 4x4}, ...],
      "out_glb": path, "out_stl": path | null, "fuse": bool, "voxel_mm": float, "modify": path to a .py | null}

Each part is imported, moved by its matrix (glTF frame, converted to Blender's Z-up and back), its faces turned back
outward when the matrix mirrors it, then all are joined. A part uploaded as an OBJ (decision 138) is read from its
original, quads and n-gons as authored, moved by its upload matrix (the scale onto its size guess) then its own.
`fuse` remeshes the joined figure into one watertight surface (voxel size `voxel_mm`) so the print has no internal
walls at the joints. `modify` names a Python file whose
`modify(obj, job)` runs last: the place for the final authoring edits (joint fillets, sculpted blends, decimation).
"""
from __future__ import annotations

import importlib.util

import bpy
import bmesh
from mathutils import Matrix

# glTF (+Y up, +Z front) to Blender (+Z up, -Y front): (x, y, z) -> (x, -z, y)
G2B = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))


def _clear() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _import(path: str) -> bpy.types.Object:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def _import_obj(zip_path: str, slot: str) -> bpy.types.Object:
    """The original OBJ, its MTL and textures beside it, read in its own frame (no axis change): the glTF frame."""
    import tempfile  # noqa: PLC0415
    import zipfile  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    where = Path(tempfile.mkdtemp(prefix=f"petpop_{slot}_"))
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(where)
    obj_file = next(p for p in where.iterdir() if p.suffix.lower() == ".obj")
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=str(obj_file), forward_axis="Y", up_axis="Z")
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for img in bpy.data.images:  # the temp folder goes away: keep the textures in the file
        if img.source == "FILE" and not img.packed_file:
            img.pack()
    return obj


def main(job: dict) -> dict:
    _clear()
    objs = []
    for part in job["parts"]:
        m = Matrix([row for row in part["matrix"]])
        if part.get("source"):  # the authored OBJ: raw glTF-frame coordinates, its upload matrix, then the placement
            obj = _import_obj(part["source"], part.get("slot", "part"))
            total = m @ Matrix([row for row in part["source_matrix"]])
            obj.data.transform(G2B @ total)
            flip = total.determinant() < 0
        else:
            obj = _import(part["path"])
            obj.data.transform(G2B @ m @ G2B.inverted())
            flip = bool(part.get("mirrored"))
        if flip:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
            bm.to_mesh(obj.data)
            bm.free()
        obj.name = part.get("slot", obj.name)
        objs.append(obj)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    fig = bpy.context.view_layer.objects.active
    fig.name = "figure"
    lift = 0.0
    if job.get("floor", True):  # stand the figure on the floor (Blender's z = 0): a breed's stretch moves its feet
        import mathutils  # noqa: PLC0415

        lift = -min((fig.matrix_world @ v.co).z for v in fig.data.vertices)
        fig.data.transform(mathutils.Matrix.Translation((0.0, 0.0, lift)))
    if job.get("fuse"):
        mod = fig.modifiers.new("fuse", "REMESH")
        mod.mode = "VOXEL"
        mod.voxel_size = float(job.get("voxel_mm", 0.35))
        bpy.ops.object.modifier_apply(modifier=mod.name)
    if job.get("modify"):
        spec = importlib.util.spec_from_file_location("petpop_modify", job["modify"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.modify(fig, job)
    bpy.ops.object.select_all(action="DESELECT")
    fig.select_set(True)
    bpy.ops.export_scene.gltf(filepath=job["out_glb"], export_format="GLB", use_selection=True, export_yup=True)
    if job.get("out_stl"):
        bpy.ops.wm.stl_export(filepath=job["out_stl"], export_selected_objects=True)
    me = fig.data
    quads = sum(1 for p in me.polygons if p.loop_total > 3)
    return {"vertices": len(me.vertices), "faces": len(me.polygons), "quads": quads, "engine": "bpy", "floor_mm": round(lift, 3)}
