"""Stage B and D adapters over a commercial API provider (backend/worker/providers). The profile names the provider
and its options per stage; these adapters only translate the pipeline's calls into provider capabilities and
record what each call cost in the stage notes.

    image:  backend: api, provider: <name>, params: {...}
    shape:  backend: api, provider: <name>, params: {...}, fallback: {seed_offset, params}
    paths:  the pipelines (decision 114): views: none (shape from the concept) | generate (Stage C asks the provider
            for four views; Stage D then sends all four to its multiview-to-model)
"""
from __future__ import annotations

from typing import Any

from ..base import ShapeResult
from .comfy import normalise_glb


def _note(ctx, stage: str, text: str) -> None:
    notes = ctx.state.setdefault("provider_notes", {})
    notes[stage] = f"{notes[stage]}; {text}" if stage in notes else text


class ApiImageBackend:
    name = "api"

    def __init__(self, provider, profile) -> None:
        self.p = provider
        self.cfg = profile["image"]
        self.name = f"api:{provider.name}"

    def _positive(self, text: str) -> str:
        trigger = self.cfg.get("lora_trigger")
        if trigger and text.startswith(f"{trigger}, "):  # a provider has no style LoRA: drop its trigger word
            return text[len(trigger) + 2:]
        return text

    def concept(self, ctx, spec, prompts, control):
        from backend.worker.imaging import matte

        g = self.p.text_to_image(ctx, self._positive(prompts["positive"]), prompts["negative"],
                                 dict(self.cfg.get("params") or {}), int(spec["seed"]))
        _note(ctx, "B", g.note(self.p.name))
        return matte(g.data, self.cfg["matting"], int(ctx.quality["concept_px"]))

    def views(self, ctx, spec, prompts, control, concept):
        """Four turnaround views from the matted concept (the provider's image-to-multiview), matted like the concept."""
        from backend.worker.imaging import matte

        g = self.p.image_to_multiview(ctx, concept, dict(self.cfg.get("views_params") or {}), int(spec["seed"]))
        _note(ctx, "C", g.note(self.p.name))
        size = int(ctx.quality["view_px"])
        return {v: matte(g.files[v], self.cfg["matting"], size) for v in ("front", "left", "back", "right")}


class ApiShapeBackend:
    name = "api"

    def __init__(self, provider, profile) -> None:
        self.p = provider
        self.cfg = profile["shape"]
        self.name = f"api:{provider.name}"

    def _shape(self, ctx, g) -> ShapeResult:
        return ShapeResult(glb=normalise_glb(g.data, self.cfg), co=None, tris=None, backend=self.name)

    def _params(self, ctx, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """The profile's shape parameters, the job's quality switches (decision 115) on top, then `extra`."""
        from backend.core.genai import option_params

        return {**(self.cfg.get("params") or {}), **option_params(ctx.settings.genai, getattr(ctx, "options", None)), **(extra or {})}

    def multiview(self, ctx, spec, views):
        """Stage D from whatever views there are: all four (a multiview pipeline) or the concept alone."""
        params, seed = self._params(ctx), int(spec["seed"])
        wanted = {v: views[v] for v in ("front", "left", "back", "right") if v in views}
        if list(wanted) == ["front"]:  # one image: the provider's image-to-model
            g = self.p.image_to_model(ctx, wanted["front"], params, seed)
        else:
            g = self.p.multiview_to_model(ctx, wanted, params, seed)
        _note(ctx, "D", g.note(self.p.name))
        return self._shape(ctx, g)

    def single_view(self, ctx, spec, front):
        fb = self.cfg.get("fallback") or {}
        params = self._params(ctx, fb.get("params"))
        g = self.p.image_to_model(ctx, front, params, int(spec["seed"]) + int(fb.get("seed_offset", 1)))
        _note(ctx, "D", g.note(self.p.name) + " (single-view retry)")
        return self._shape(ctx, g)
