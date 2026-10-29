"""PetSpec construction and merging: breed preset -> user taps -> parser patch (BRIEF Sections 3 and 6.1)."""
from __future__ import annotations

import copy
import random
from typing import Any

from .breeds import get_breed
from .vocab import nearest_palette, vocab

SPEC_VERSION = "1.0"


def flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Nested dict -> {dotted.path: leaf}. Lists are leaves. Keys that already contain dots stay whole."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        p = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict) and v and prefix != "overrides" and k != "overrides":
            out.update(flatten(v, p))
        elif k == "overrides" and isinstance(v, dict):
            for ok, ov in v.items():
                out[f"overrides.{ok}"] = ov
        else:
            out[p] = v
    return out


def set_path(d: dict[str, Any], path: str, value: Any) -> None:
    if path.startswith("overrides."):
        d.setdefault("overrides", {})[path[len("overrides."):]] = value
        return
    parts = path.split(".")
    node = d
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def unflatten(flat: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in flat.items():
        set_path(out, k, v)
    return out


def is_tapped(path: str, tapped: set[str]) -> bool:
    """A tap on a field or any of its parents protects it from the parser."""
    parts = path.split(".")
    return any(".".join(parts[:i]) in tapped for i in range(1, len(parts) + 1))


def default_spec(species: str, breed_id: str = "mixed", seed: int | None = None,
                 pet_name: str | None = None) -> dict[str, Any]:
    breed = get_breed(species, breed_id) or get_breed(species, "mixed")
    assert breed is not None
    spec: dict[str, Any] = {
        "spec_version": SPEC_VERSION,
        "species": species,
        "breed": {"id": breed["id"], "label": breed["label"], "confidence": 1.0},
        **copy.deepcopy(breed["preset"]),
        "accessories": [],
        "personality": [],
        "free_text": "",
        "overrides": {},
        "seed": seed if seed is not None else random.SystemRandom().randrange(0, 2**31 - 1),
    }
    if pet_name:
        spec["pet_name"] = pet_name
    return spec


def apply_patch(spec: dict[str, Any], patch: dict[str, Any], tapped: set[str] | None = None
                ) -> tuple[dict[str, Any], list[str]]:
    """Apply a parser patch, skipping tapped fields. Returns the new spec and the changed dotted paths."""
    tapped = tapped or set()
    out = copy.deepcopy(spec)
    before = flatten(spec)
    changed: list[str] = []
    for path, value in flatten(patch).items():
        if is_tapped(path, tapped):
            continue
        if path == "breed.id":
            continue  # handled with label below
        set_path(out, path, value)
        if before.get(path) != value:
            changed.append(path)
    if "breed" in patch and not is_tapped("breed.id", tapped):
        out["breed"] = {**out.get("breed", {}), **patch["breed"]}
        if before.get("breed.id") != patch["breed"].get("id"):
            changed.append("breed.id")
    return out, changed


def fill_colour_names(spec: dict[str, Any]) -> dict[str, Any]:
    """Make palette names agree with hex values (custom colours get the nearest palette name)."""
    out = copy.deepcopy(spec)
    col = out.get("colour", {})
    for key in ("base", "secondary"):
        if key in col and "hex" in col[key]:
            col[key]["name"] = nearest_palette(col[key]["hex"])
    for acc in out.get("accessories", []):
        acc["colour_name"] = nearest_palette(acc["colour_hex"])
    eyes = out.get("eyes")
    if eyes and "colour" in eyes and "hex" not in eyes:
        eyes["hex"] = vocab()["eye_palette"][eyes["colour"]]["hex"]
    return out
