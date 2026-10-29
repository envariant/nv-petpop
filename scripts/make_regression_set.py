#!/usr/bin/env python3
"""Write tests/regression/pets.json: 30 PetSpecs (15 dog, 15 cat) covering every ear, tail and coat
enumeration at least once (BRIEF Section 12). Deterministic: breeds and overrides are fixed below."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: E402,F401  (puts packages/*/python on sys.path)

from petpop_core.schemas import spec_errors  # noqa: E402
from petpop_core.spec import apply_patch, default_spec, fill_colour_names  # noqa: E402

DOGS = [
    ("corgi_pembroke", {}), ("labrador", {}), ("german_shepherd", {}), ("french_bulldog", {}), ("pug", {}),
    ("poodle_standard", {}), ("dachshund", {}), ("husky", {}), ("shiba_inu", {}), ("border_collie", {}),
    ("boxer", {}), ("dalmatian", {}), ("schnauzer_mini", {"coat": {"texture": "wiry"}}),
    ("greyhound", {"ears": {"shape": "rose"}}), ("bulldog", {"ears": {"shape": "folded"}, "coat": {"length": "medium"}}),
]
CATS = [
    ("domestic_shorthair", {}), ("persian", {}), ("maine_coon", {}), ("siamese", {}), ("scottish_fold", {}),
    ("bengal", {}), ("sphynx", {}), ("ragdoll", {}), ("british_shorthair", {}), ("tuxedo", {}),
    ("calico", {"tail": {"type": "curled", "curl": "tight"}}), ("manx", {}), ("devon_rex", {"ears": {"shape": "semi_erect"}}),
    ("tabby_orange", {"ears": {"shape": "drop"}, "coat": {"texture": "silky", "length": "medium"}}),
    ("norwegian_forest", {"tail": {"type": "straight"}}),
]


def main() -> None:
    pets = []
    for species, rows in (("dog", DOGS), ("cat", CATS)):
        for i, (breed, patch) in enumerate(rows):
            spec = default_spec(species, breed, seed=10_000 + len(pets), pet_name=f"{species}{i + 1:02d}")
            spec, _ = apply_patch(spec, patch)
            spec = fill_colour_names(spec)
            assert not spec_errors(spec), (breed, spec_errors(spec))
            pets.append({"id": f"{species}_{breed}", "spec": spec})
    out = ROOT / "tests/regression/pets.json"
    out.write_text(json.dumps({"version": 1, "pets": pets}, indent=1) + "\n")
    print(f"wrote {len(pets)} pets -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
