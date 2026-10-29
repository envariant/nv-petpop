"""Stage E: template wrap (BRIEF Section 6.5) in Blender; the trimesh nearest-point stand-in without bpy.
With the parametric fallback (Stage D skipped) the morphed base mesh ships unwrapped."""
from __future__ import annotations

import io
import json

import numpy as np

from backend.core import lowfi
from petpop_library.meshkit import load_base, write_obj
from petpop_core.vocab import morph_weights

from . import blender
from .backends.mock.pacing import Pace


def run(job_id, spec, manifest, *, ctx, parametric: bool = False) -> list[str]:
    spec = json.loads(ctx.get("spec.json"))
    base = load_base(spec["species"])
    weights = morph_weights(spec)
    morphed = base.morph(weights)
    with Pace("E"):
        if parametric:
            wrapped, info = morphed, {"valid": True, "fallback": "parametric", "notes": "Stage D skipped: morphed base mesh"}
        elif blender.available(ctx.settings.bpy_python):
            out = ctx.workdir("wrap")
            info = blender.run(ctx.settings.bpy_python, ["wrap"], {
                "species": spec["species"], "weights": weights, "shape_glb": str(ctx.fetch("shape.glb")),
                "out_dir": str(out), "fail": ctx.settings.fail_stage == "E"}, timeout=ctx.remaining())
            wrapped = np.load(info["coords"]).astype(np.float64)
        else:
            import trimesh

            ctx.state["fidelity"] = "low"
            m = trimesh.load(io.BytesIO(ctx.get("shape.glb")), file_type="glb", force="mesh")
            v = np.asarray(m.vertices)
            tgt = np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1)
            if ctx.settings.fail_stage == "E":
                wrapped, info = morphed, {"valid": False, "fallback": "unwrapped", "notes": "fault injection"}
            else:
                wrapped = lowfi.wrap_nearest(base, morphed, tgt, np.asarray(m.faces))
                info = {"valid": True, "fallback": "none", "notes": "nearest-point stand-in"}
    ctx.state["wrap"] = info
    buf = io.BytesIO()
    np.save(buf, wrapped.astype(np.float32))
    keys = [ctx.put(manifest, "wrapped_coords.npy", "wrapped", "E", buf.getvalue())]
    tmp = ctx.workdir("wrap_obj") / "figure_wrapped.obj"
    write_obj(tmp, base, wrapped)
    keys.append(ctx.put(manifest, "figure_wrapped.obj", "wrapped", "E", tmp.read_bytes()))
    return keys
