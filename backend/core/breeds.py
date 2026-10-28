"""Breed presets from data/breeds/{species}.json."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .paths import BREEDS_DIR


@lru_cache
def breed_doc(species: str) -> dict[str, Any]:
    return json.loads((BREEDS_DIR / f"{species}.json").read_text())


def all_breeds(species: str) -> list[dict[str, Any]]:
    return breed_doc(species)["breeds"]


def get_breed(species: str, breed_id: str) -> dict[str, Any] | None:
    for b in all_breeds(species):
        if b["id"] == breed_id:
            return b
    return None


def search(species: str, q: str | None = None) -> list[dict[str, Any]]:
    """Case-insensitive search on label and id; prefix matches first, 'mixed' always last."""
    items = all_breeds(species)
    if q:
        ql = q.strip().lower()
        hits = [b for b in items if ql in b["label"].lower() or ql in b["id"]]
        hits.sort(key=lambda b: (not b["label"].lower().startswith(ql),
                                 not any(w.startswith(ql) for w in b["label"].lower().split()), b["label"]))
    else:
        hits = sorted(items, key=lambda b: b["label"])
    mixed = [b for b in hits if b["id"] == "mixed"]
    return [b for b in hits if b["id"] != "mixed"] + mixed
