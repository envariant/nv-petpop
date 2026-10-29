"""Stage A: brief to PetSpec (BRIEF Section 6.1). The kiosk has already merged preset, taps and the parsed
brief via /spec/parse; here the worker validates and normalises the spec, screens the free text, and compiles
the prompts (vocabulary only) and morph weights every later stage reads."""
from __future__ import annotations

import json

from petpop_core.schemas import spec_errors
from petpop_core.spec import fill_colour_names
from petpop_core.vocab import morph_weights, vocab
from petpop_core.prompts.compiler import compile_prompts

from .backends.mock.pacing import Pace
from .context import StageFailed


def run(job_id, spec, manifest, *, ctx) -> list[str]:
    with Pace("A"):
        ctx.check_fault("A")
        spec = fill_colour_names(spec)
        errs = spec_errors(spec)
        if errs:
            raise StageFailed("A", f"invalid PetSpec: {errs[:3]}")
        words = vocab()["personality_words"]
        blocked = [w for w in vocab()["blocklist"] if w in spec.get("free_text", "").lower()]
        spec["personality"] = [p for p in spec.get("personality", []) if not any(b in p.lower() for b in vocab()["blocklist"])]
        prompts = compile_prompts(spec)
        info = {"prompts": prompts, "morph_weights": morph_weights(spec), "parser": ctx.backends.parser.name,
                "screened_words": len(blocked), "personality_mapped": [p for p in spec["personality"] if p in words]}
        keys = [ctx.put(manifest, "spec.json", "spec", "A", (json.dumps(spec, indent=1) + "\n").encode()),
                ctx.put(manifest, "prompts.json", "spec", "A", (json.dumps(info, indent=1) + "\n").encode())]
    ctx.state["spec"] = spec
    return keys
