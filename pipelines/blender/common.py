"""Shared bpy helpers for the PetPop Blender stages.

Every stage script is a module with `main(job: dict) -> dict` and runs under `run.py`, which reads a JSON
job (input paths, output paths, parameters) and writes a JSON result. The worker downloads inputs from the
artefact store into a temp dir and uploads the outputs, so these scripts never see the store.
Units: millimetres, Z up, front -Y (the base-mesh convention).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy  # noqa: I001
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "packages" / "library" / "python", ROOT / "packages" / "core" / "python", ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

EXTENT_MM = 110.0
CENTRE_Z = 45.0


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def activate(obj) -> None:
    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def load_base(species: str, base_dir: str | None = None):
    """Append the species base mesh object (with UVs, vertex groups and materials) into the scene."""
    blend = Path(base_dir or ROOT / "assets" / "base" / species) / "base.blend"
    with bpy.data.libraries.load(str(blend), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("petpop_base_")]
    obj = dst.objects[0]
    bpy.context.scene.collection.objects.link(obj)
    return obj


def figure_object(mesh):
    """A Blender object built from a figurine mesh package (petpop_library.figure): polygons and its own UVs (no
    stage reads vertex groups, so the part weights stay in the package)."""
    starts, totals = np.asarray(mesh.poly_start), np.asarray(mesh.poly_total)
    loops = np.concatenate([np.arange(s, s + n) for s, n in zip(starts, totals)])
    me = bpy.data.meshes.new("figure")
    me.from_pydata([tuple(p) for p in mesh.co], [], [tuple(int(v) for v in mesh.loops_v[s:s + n]) for s, n in zip(starts, totals)])
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    uvl.data.foreach_set("uv", np.asarray(mesh.uv[loops], np.float32).ravel())
    obj = bpy.data.objects.new("figure", me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def mesh_and_object(job: dict):
    """(numpy mesh, coords, Blender object) for a stage job: the figurine mesh when the job names one
    (decision 116), otherwise the species template moved to the job's coords (library compositions)."""
    if job.get("mesh"):
        from petpop_library import figure

        mesh = figure.load(job["mesh"])
        if mesh.source == "template":  # the template's own topology: append it from its .blend, which is quicker
            obj = load_base(mesh.species)
            set_coords(obj, mesh.co)
            return mesh, mesh.co.astype(np.float64), obj
        return mesh, mesh.co.astype(np.float64), figure_object(mesh)
    from petpop_library.meshkit import load_base as np_base

    mesh = np_base(job["species"])
    co = np.load(job["coords"]).astype(np.float64)
    obj = load_base(job["species"])
    set_coords(obj, co)
    return mesh, co, obj


def set_coords(obj, co: np.ndarray) -> None:
    """Replace vertex positions (same order), dropping shape keys: the result is the morphed/wrapped mesh."""
    if obj.data.shape_keys:
        obj.shape_key_clear()
    obj.data.vertices.foreach_set("co", np.asarray(co, dtype=np.float32).ravel())
    obj.data.update()


def get_coords(obj) -> np.ndarray:
    co = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    obj.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3).astype(np.float64)


def image_material(name: str, image_path: str, roughness: float = 0.55):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    tex.interpolation = "Linear"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def flat_material(name: str, rgb, roughness: float = 0.55):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*srgb_to_linear(rgb), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def srgb_to_linear(rgb):
    out = []
    for c in rgb:
        c = float(c)
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def assign_material(obj, mat) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.material_index = 0


def scene_setup(res: int, samples: int, transparent: bool, background: float = 1.0) -> None:
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = max(1, samples)
    sc.cycles.use_denoising = False
    sc.cycles.seed = 0
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    for name in ("key", "fill"):
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    world = bpy.data.worlds.get("world") or bpy.data.worlds.new("world")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (background, background, background, 1)
    bg.inputs[1].default_value = 0.6
    key = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
    key.data.energy = 3.0
    key.rotation_euler = (math.radians(50), 0, math.radians(-30))
    sc.collection.objects.link(key)
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "SUN"))
    fill.data.energy = 1.2
    fill.rotation_euler = (math.radians(60), 0, math.radians(150))
    sc.collection.objects.link(fill)


def ortho_camera(azimuth_deg: float, extent: float = EXTENT_MM, centre_z: float = CENTRE_Z, elevation_deg: float = 0.0):
    """Orthographic camera orbiting +Z; azimuth 0 looks at the front (camera on -Y), 90 at the pet's left (+X)."""
    sc = bpy.context.scene
    cam = sc.camera
    if cam is None:
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        sc.collection.objects.link(cam)
        sc.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = extent
    cam.data.clip_start = 1.0
    cam.data.clip_end = 2000.0
    a = math.radians(azimuth_deg)
    e = math.radians(elevation_deg)
    r = 500.0
    cam.location = (r * math.sin(a) * math.cos(e), -r * math.cos(a) * math.cos(e), centre_z + r * math.sin(e))
    cam.rotation_euler = (math.pi / 2 - e, 0.0, a)
    return cam


def render_to(path: str) -> None:
    sc = bpy.context.scene
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


# --------------------------------------------------------------------------- accessories

def load_accessory(kind: str):
    """Append one accessory mesh from assets/accessories/accessories.blend (unit-sized, anchor at origin)."""
    blend = ROOT / "assets" / "accessories" / "accessories.blend"
    with bpy.data.libraries.load(str(blend), link=False) as (src, dst):
        dst.objects = [f"acc_{kind}"]
    obj = dst.objects[0]
    bpy.context.scene.collection.objects.link(obj)
    return obj


from petpop_library.accessories import accessory_anchors  # noqa: E402  (shared with the numpy mock shape)


def add_accessories(accessories: list[dict], co: np.ndarray, landmarks: dict[str, int], shell: np.ndarray) -> list:
    anchors = accessory_anchors(co, landmarks, shell)
    out = []
    for a in accessories:
        kind = a["type"]
        obj = load_accessory(kind)
        frame = anchors[kind]
        obj.location = frame["loc"]
        obj.scale = frame["scale"]
        hexv = a.get("colour_hex", "#DD3333").lstrip("#")
        if len(hexv) == 3:
            hexv = "".join(c * 2 for c in hexv)
        rgb = [int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        assign_material(obj, flat_material(f"acc_{kind}_mat", rgb, roughness=0.45))
        activate(obj)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        obj.name = f"accessory_{kind}"
        out.append(obj)
    return out
