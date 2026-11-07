"""Which parts each breed uses (decision 131): data/breeds/<species>_breed_parts.json, kept apart from the breed
database (data/breeds/<species>_pebbles_simple.json), which describes bodies. Per breed and kind: the variants it
offers and its default; per offered variant, its stretch (null: the size guess, petpop_library.part_sizes); per torso
variant, its named presets (the customers' shape choices), each a stretch and socket offsets (translation and rotation
per slot); its default texture configuration; the variant its sitting pose swaps in.

The file is a starting point: Studio seeds each breed's kit from it, and the workbench changes the kit from there.
scripts/make_breed_parts.py writes entries for breeds it does not have yet (from the breed database's part types) and
never overwrites one.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from petpop_core.paths import BREEDS_DIR

from .parts import SHARED

KIND_KEYS = {"torso": "torso", "front_leg": "fore_leg", "hind_leg": "hind_leg", "tail": "tail"}  # the database's names


def path(species: str):
    return BREEDS_DIR / f"{species}_breed_parts.json"


@lru_cache
def table(species: str) -> dict[str, Any] | None:
    p = path(species)
    return json.loads(p.read_text()) if p.is_file() else None


def clear() -> None:
    table.cache_clear()


def default_preset() -> dict[str, Any]:
    return {"preset_id": "default", "label": "Standard", "stretch": None, "sockets": {}}


def seed(entry: dict[str, Any]) -> dict[str, Any]:
    """A breed's starting entry from its breed database row: its part types offered and default, each at its size
    guess, the torso with its default preset only, the sitting hind leg, its colours as the default texture."""
    types, colour = entry.get("part_types", {}), (entry.get("preset") or {}).get("colour") or {}
    parts: dict[str, Any] = {"head": {"default": "default", "offer": {}}}
    for kind, key in KIND_KEYS.items():
        v = types.get(key)
        if not v:
            continue
        offer: dict[str, Any] = {v: {"presets": [default_preset()]} if kind == "torso" else {"stretch": None}}
        if kind == "hind_leg" and types.get("hind_leg_sitting"):
            offer[types["hind_leg_sitting"]] = {"stretch": None}
        parts[kind] = {"default": v, "offer": offer}
    texture = None
    if colour.get("base"):
        texture = {"base": colour["base"], "secondary": colour.get("secondary"), "pattern": colour.get("pattern"),
                   "markings": list(colour.get("markings") or [])}
    return {"label": entry.get("label", entry["id"]), "parts": parts, "sitting": types.get("hind_leg_sitting"), "texture": texture}


def recipe(species: str, breed_id: str) -> dict[str, Any]:
    """What a breed's kit starts with: defaults and offered variants per kind, stretches set in the file
    ("kind/variant" to [x, y, z]), torso presets ("torso/variant" to the list), the sitting variant, the texture."""
    row = ((table(species) or {}).get("breeds") or {}).get(breed_id) if breed_id != SHARED else None
    out: dict[str, Any] = {"defaults": {}, "allowed": {}, "stretch": {}, "presets": {}, "sitting": None, "texture": None}
    if not row:
        return out
    for kind, spec in (row.get("parts") or {}).items():
        if spec.get("default") and kind != "head":
            out["defaults"][kind] = spec["default"]
        offer = spec.get("offer") or {}
        if offer:
            out["allowed"][kind] = list(offer)
        for v, o in offer.items():
            if o.get("stretch"):
                out["stretch"][f"{kind}/{v}"] = [float(x) for x in o["stretch"]]
            if kind == "torso" and o.get("presets"):
                out["presets"][f"torso/{v}"] = o["presets"]
    out["sitting"], out["texture"] = row.get("sitting"), row.get("texture")
    return out
