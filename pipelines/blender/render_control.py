"""Control renders (BRIEF Section 8): 16-bit depth PNGs of the morphed base mesh from the five cameras
(concept front + four views), normalised to the mesh bounds, near = bright, background 0. Silhouette alphas
are derived from depth > 0 by the worker."""
from pathlib import Path

import bpy  # noqa: I001
import numpy as np

from common import CENTRE_Z, EXTENT_MM, add_accessories, load_base, ortho_camera, render_to, reset, set_coords

CAMERAS = {"concept_front": 0.0, "front": 0.0, "left": 90.0, "back": 180.0, "right": 270.0}


def depth_material(near: float, far: float):
    mat = bpy.data.materials.new("depth")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    cam = nt.nodes.new("ShaderNodeCameraData")
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = near
    rng.inputs["From Max"].default_value = far
    rng.inputs["To Min"].default_value = 1.0
    rng.inputs["To Max"].default_value = 0.1
    rng.clamp = True
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(cam.outputs["View Z Depth"], rng.inputs["Value"])
    nt.links.new(rng.outputs["Result"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


def main(job: dict) -> dict:
    from backend.core.meshkit import load_base as np_base

    reset()
    base = np_base(job["species"])
    co = base.morph(job["weights"])
    obj = load_base(job["species"])
    set_coords(obj, co)
    add_accessories(job.get("accessories", []), co, base.landmarks, base.shell)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 1
    sc.cycles.use_denoising = False
    sc.cycles.pixel_filter_type = "BOX"
    sc.cycles.filter_width = 0.01
    res = int(job["quality"]["control_px"])
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "BW"
    sc.render.image_settings.color_depth = "16"
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.0
    sc.world = world
    radius = float(np.max(np.linalg.norm(co - np.array([0, 0, CENTRE_Z]), axis=1))) + 2
    sc.view_layers[0].material_override = depth_material(500 - radius, 500 + radius)
    out = Path(job["out_dir"])
    files = {}
    for name, az in CAMERAS.items():
        ortho_camera(az, EXTENT_MM, CENTRE_Z)
        p = out / f"{name}_depth.png"
        render_to(str(p))
        files[name] = str(p)
    return {"depth": files}
