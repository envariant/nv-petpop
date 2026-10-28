"""MockImageBackend: Blender Cycles renders of the morphed, flat-coloured base mesh (BRIEF Section 13);
the numpy renderer stands in when bpy is missing (fidelity low)."""
from __future__ import annotations

from backend.core import lowfi
from backend.core.colouring import vertex_colours
from backend.core.meshkit import load_base
from backend.core.vocab import morph_weights
from backend.worker import blender
from backend.worker.imaging import matte_square

from .pacing import Pace


class MockImageBackend:
    name = "mock"

    def _render(self, ctx, spec, which: list[str]) -> dict[str, bytes]:
        q = ctx.quality
        if blender.available(ctx.settings.bpy_python):
            out = ctx.workdir("render")
            res = blender.run(ctx.settings.bpy_python, ["render_views"], {
                "species": spec["species"], "weights": morph_weights(spec), "albedo": str(ctx.fetch("control/flat_albedo.png")),
                "accessories": spec.get("accessories", []), "quality": q, "out_dir": str(out), "views": which,
            }, timeout=ctx.remaining())
            return {k: open(v, "rb").read() for k, v in res["files"].items()}
        ctx.state["fidelity"] = "low"
        base = load_base(spec["species"])
        co = base.morph(morph_weights(spec))
        cols = vertex_colours(base, spec, co)
        res = {}
        for k in which:
            az = 0.0 if k == "concept" else lowfi.VIEWS[k]
            px = q["concept_px"] if k == "concept" else q["view_px"]
            res[k] = lowfi.png_bytes(lowfi.flat_render(base, co, cols, az, int(px), True))
        return res

    def concept(self, ctx, spec, prompts, control):
        with Pace("B"):
            img = self._render(ctx, spec, ["concept"])["concept"]
            return matte_square(img, ctx.quality["concept_px"])

    def views(self, ctx, spec, prompts, control, concept):
        with Pace("C"):
            res = self._render(ctx, spec, ["front", "left", "back", "right"])
            return {k: matte_square(v, ctx.quality["view_px"]) for k, v in res.items()}
