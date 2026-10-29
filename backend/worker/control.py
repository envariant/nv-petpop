"""Control renders and flat colours from the morphed base mesh (BRIEF Section 8, 'Depth inputs from
Blender'): 16-bit depth + silhouette alpha for the five cameras, plus the flat-colour albedo and front
render that steer Stage B (img2img init) and the mock image backend."""
from __future__ import annotations

import json
import sys

from backend.core import lowfi
from petpop_library.colouring import vertex_colours
from petpop_library.meshkit import load_base
from backend.core.paths import PIPELINES
from petpop_core.vocab import morph_weights

from . import blender
from .backends.mock.pacing import Pace
from .imaging import depth_to_alpha

sys.path.insert(0, str(PIPELINES / "blender"))
import bake  # noqa: E402

CAMERAS = ["concept_front", "front", "left", "back", "right"]


def run(job_id, spec, manifest, *, ctx) -> list[str]:
    spec = json.loads(ctx.get("spec.json"))
    keys = []
    with Pace("control"):
        ctx.check_fault("control")
        base = load_base(spec["species"])
        weights = morph_weights(spec)
        co = base.morph(weights)
        q = ctx.quality
        if blender.available(ctx.settings.bpy_python):
            out = ctx.workdir("control")
            res = blender.run(ctx.settings.bpy_python, ["render_control"], {
                "species": spec["species"], "weights": weights, "accessories": spec.get("accessories", []),
                "quality": q, "out_dir": str(out)}, timeout=ctx.remaining())
            depth = {cam: open(res["depth"][cam], "rb").read() for cam in CAMERAS}
        else:
            ctx.state["fidelity"] = "low"
            r = lowfi.control_renders(base, co, int(q["control_px"]))
            depth = {cam: r[cam]["depth"] for cam in CAMERAS}
        for cam in CAMERAS:
            keys.append(ctx.put(manifest, f"control/{cam}_depth.png", "control", "control", depth[cam]))
            keys.append(ctx.put(manifest, f"control/{cam}_alpha.png", "control", "control", depth_to_alpha(depth[cam])))
        albedo = bake.flat_albedo(base, spec, co, int(q["albedo_px"]))
        keys.append(ctx.put(manifest, "control/flat_albedo.png", "control", "control", lowfi.png_bytes(albedo)))
        front = lowfi.flat_render(base, co, vertex_colours(base, spec, co), 0.0, int(q["control_px"]), False)
        keys.append(ctx.put(manifest, "control/flat_front.png", "control", "control", lowfi.png_bytes(front)))
    return keys
