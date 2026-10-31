"""Stage F preview: figure.glb (Draco, albedo, metallic 0, roughness 0.55 vinyl), a thumbnail and the
turntable frames (36 at full quality) that the worker encodes to turntable.mp4."""
import math
from pathlib import Path

import bpy  # noqa: I001
import numpy as np

from common import activate, add_accessories, assign_material, image_material, mesh_and_object, ortho_camera, render_to, reset, scene_setup


def main(job: dict) -> dict:
    q = job["quality"]
    reset()
    base, co, obj = mesh_and_object(job)
    obj.vertex_groups.clear()
    assign_material(obj, image_material("vinyl", job["albedo"], roughness=0.55))
    accs = add_accessories(job.get("accessories", []), co, base.landmarks, base.shell)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in [obj, *accs]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obj
    out = Path(job["out_dir"])
    bpy.ops.export_scene.gltf(filepath=str(out / "figure.glb"), use_selection=True, export_yup=True,
                              export_draco_mesh_compression_enable=bool(job.get("draco", True)),
                              export_image_format="AUTO", export_materials="EXPORT", export_morph=False)
    scene_setup(256, int(q["samples"]), transparent=False, background=1.0)
    ortho_camera(25.0, elevation_deg=10.0)
    render_to(str(out / "thumbnail.png"))
    frames = int(q["turntable_frames"])
    fdir = out / "frames"
    fdir.mkdir(exist_ok=True)
    if frames:
        scene_setup(int(q["turntable_px"]), max(1, int(q["samples"]) // 2), transparent=False, background=1.0)
        for i in range(frames):
            ortho_camera(i * 360.0 / frames, elevation_deg=10.0)
            render_to(str(fdir / f"f{i:03d}.png"))
    activate(obj)
    return {"glb": str(out / "figure.glb"), "thumbnail": str(out / "thumbnail.png"), "frames_dir": str(fdir),
            "frames": frames, "fps": max(1, round(frames / 6)), "elev": math.radians(10)}
