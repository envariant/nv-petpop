"""Slot vocabulary: prompt phrases, morph weights and palette lookups (BRIEF Section 7)."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .paths import SCHEMA_DIR


@lru_cache
def vocab() -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / "vocab.json").read_text())


def slot_key(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def entry(slot: str, value: Any) -> dict[str, Any]:
    return vocab()["slots"][slot][slot_key(value)]


def phrase(slot: str, value: Any) -> str:
    return entry(slot, value)["prompt"]


def get_path(spec: dict[str, Any], path: str, default: Any = None) -> Any:
    node: Any = spec
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


MORPH_SLOTS = [
    "body.size", "body.build", "body.leg_length", "head.muzzle_length", "head.muzzle_width",
    "head.brachycephalic", "ears.shape", "ears.size", "ears.tip", "ears.tufted", "tail.type", "tail.length",
    "tail.curl", "coat.length", "coat.texture",
]


def morph_weights(spec: dict[str, Any]) -> dict[str, float]:
    """PetSpec -> shape-key weights for the species base mesh, summed, substituted and clamped."""
    v = vocab()
    species = spec["species"]
    targets = v["morph_targets"][species]
    subs = v["species_substitutes"].get(species, {})
    raw: dict[str, float] = {}
    for slot in MORPH_SLOTS:
        value = get_path(spec, slot)
        if value is None:
            continue
        for name, w in entry(slot, value)["morph"].items():
            raw[name] = raw.get(name, 0.0) + float(w)
    fluffiness = get_path(spec, "coat.fluffiness")
    if isinstance(fluffiness, (int, float)):
        raw["fluff"] = raw.get("fluff", 0.0) + 0.5 * float(fluffiness)
    out = {t: 0.0 for t in targets}
    for name, w in raw.items():
        if name in out:
            out[name] += w
        elif name in subs:
            for sub, k in subs[name].items():
                if sub in out:
                    out[sub] += w * k
    return {k: round(max(-1.0, min(1.0, val)), 4) for k, val in out.items()}


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def nearest_palette(hexv: str) -> str:
    r, g, b = hex_to_rgb(hexv)
    best, bd = "grey", 1e9
    for name, e in vocab()["palette"].items():
        pr, pg, pb = hex_to_rgb(e["hex"])
        d = (r - pr) ** 2 * 0.3 + (g - pg) ** 2 * 0.59 + (b - pb) ** 2 * 0.11
        if d < bd:
            best, bd = name, d
    return best
