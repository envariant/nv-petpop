"""Stage C: four turnaround views (BRIEF Section 6.3)."""
from __future__ import annotations

import json

from .context import StageFailed

VIEWS = ["front", "left", "back", "right"]


def run(job_id, spec, manifest, *, ctx) -> list[str]:
    ctx.check_fault("C")
    spec = json.loads(ctx.get("spec.json"))
    prompts = json.loads(ctx.get("prompts.json"))["prompts"]
    control = {f"{v}_depth": ctx.get(f"control/{v}_depth.png") for v in VIEWS}
    views = ctx.backends.image.views(ctx, spec, prompts, control, ctx.get("concept.png"))
    if set(views) != set(VIEWS):
        raise StageFailed("C", f"expected four views, got {sorted(views)}")
    keys = [ctx.put(manifest, f"views/{v}.png", "view", "C", views[v]) for v in VIEWS]
    for v, k in zip(VIEWS, keys):
        ctx.progress("C", 45, "Four views ready", preview=(f"view_{v}", k))
    return keys
