"""Stage B and D adapters over a commercial API provider (backend/worker/providers). The profile names the provider
and its options per stage; these adapters only translate the pipeline's calls into provider capabilities and
record what each call cost in the stage notes.

    image:  backend: api, provider: <name>, params: {...}, views: none | provider
    shape:  backend: api, provider: <name>, views: [front] | [front, left, back, right], params: {...},
            fallback: {seed_offset, params}
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
        raise NotImplementedError("this profile shapes from the concept alone (image.views: none); Stage C is skipped")


class ApiShapeBackend:
    name = "api"

    def __init__(self, provider, profile) -> None:
        self.p = provider
        self.cfg = profile["shape"]
        self.name = f"api:{provider.name}"

    def _shape(self, ctx, g) -> ShapeResult:
        return ShapeResult(glb=normalise_glb(g.data, self.cfg), co=None, tris=None, backend=self.name)

    def multiview(self, ctx, spec, views):
        params, seed = dict(self.cfg.get("params") or {}), int(spec["seed"])
        wanted = {v: views[v] for v in self.cfg["views"] if v in views}
        if list(wanted) == ["front"]:  # one image: the provider's image-to-model
            g = self.p.image_to_model(ctx, wanted["front"], params, seed)
        else:
            g = self.p.multiview_to_model(ctx, wanted, params, seed)
        _note(ctx, "D", g.note(self.p.name))
        return self._shape(ctx, g)

    def single_view(self, ctx, spec, front):
        fb = self.cfg.get("fallback") or {}
        params: dict[str, Any] = {**(self.cfg.get("params") or {}), **(fb.get("params") or {})}
        g = self.p.image_to_model(ctx, front, params, int(spec["seed"]) + int(fb.get("seed_offset", 1)))
        _note(ctx, "D", g.note(self.p.name) + " (single-view retry)")
        return self._shape(ctx, g)
