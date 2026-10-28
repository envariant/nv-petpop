"""Stage B: concept render, front (BRIEF Section 6.2)."""
from __future__ import annotations

import json

from .context import StageFailed


def run(job_id, spec, manifest, *, ctx) -> list[str]:
    ctx.check_fault("B")
    spec = json.loads(ctx.get("spec.json"))
    prompts = json.loads(ctx.get("prompts.json"))["prompts"]
    control = {"concept_front_depth": ctx.get("control/concept_front_depth.png"), "flat_front": ctx.get("control/flat_front.png")}
    png = ctx.backends.image.concept(ctx, spec, prompts, control)
    if not png:
        raise StageFailed("B", "no concept image")
    key = ctx.put(manifest, "concept.png", "concept", "B", png)
    ctx.progress("B", 24, "Concept ready", preview=("concept", key))
    return [key]
