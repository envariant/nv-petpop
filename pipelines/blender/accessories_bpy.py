"""Accessory library builder (run by scripts/make_accessories.py)."""
import math
import sys

import bpy  # noqa: I001
import bmesh

OUT = sys.argv[-1]
bpy.ops.wm.read_factory_settings(use_empty=True)


def finish(obj, name):
    obj.name = name
    obj.data.name = name
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=8 / 1024)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def join(objs, name):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    return finish(bpy.context.view_layer.objects.active, name)


# Collar: torus of radius 1 around Z plus a tag disc at the front (-Y).
bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.17, major_segments=32, minor_segments=8)
ring = bpy.context.active_object
ring.scale = (1, 1, 0.8)
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.2, depth=0.16, location=(0, -1.18, -0.24), rotation=(math.pi / 2, 0, 0))
tag = bpy.context.active_object
join([ring, tag], "acc_collar")

# Bandana: a flattened triangle hanging from the neck front.
bm = bmesh.new()
v = [bm.verts.new(p) for p in [(-0.9, -0.85, 0.1), (0.9, -0.85, 0.1), (0, -1.15, -0.9), (-0.9, -0.55, 0.15), (0.9, -0.55, 0.15), (0, -0.9, -0.85)]]
bm.faces.new([v[0], v[1], v[2]])
bm.faces.new([v[5], v[4], v[3]])
bm.faces.new([v[0], v[3], v[4], v[1]])
bm.faces.new([v[1], v[4], v[5], v[2]])
bm.faces.new([v[2], v[5], v[3], v[0]])
me = bpy.data.meshes.new("acc_bandana")
bm.to_mesh(me)
obj = bpy.data.objects.new("acc_bandana", me)
bpy.context.scene.collection.objects.link(obj)
finish(obj, "acc_bandana")

# Bow: two lobes and a knot.
parts = []
for side in (-1, 1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.5, location=(side * 0.55, 0, 0))
    o = bpy.context.active_object
    o.scale = (1.0, 0.45, 0.7)
    parts.append(o)
bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.25)
parts.append(bpy.context.active_object)
join(parts, "acc_bow")

# Hat: brim plus crown.
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=1.0, depth=0.18)
brim = bpy.context.active_object
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.62, depth=0.8, location=(0, 0, 0.4))
crown = bpy.context.active_object
join([brim, crown], "acc_hat")

# Glasses: two rings and a bridge, facing -Y.
parts = []
for side in (-1, 1):
    bpy.ops.mesh.primitive_torus_add(major_radius=0.55, minor_radius=0.2, major_segments=24, minor_segments=6,
                                     location=(side * 1.0, 0, 0), rotation=(math.pi / 2, 0, 0))
    parts.append(bpy.context.active_object)
bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.16, depth=0.9, rotation=(0, math.pi / 2, 0))
parts.append(bpy.context.active_object)
join(parts, "acc_glasses")

bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
for o in bpy.data.objects:
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT.replace(".blend", ".glb"), use_selection=True, export_yup=True, export_materials="NONE")
print("ACCESSORIES_OK", [o.name for o in bpy.data.objects])
