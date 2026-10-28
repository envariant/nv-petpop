#!/usr/bin/env python3
"""Pre-render the Build-screen tiles from the base mesh (BRIEF Section 4).

Pattern and marking tiles show the pattern projected on the neutral base mesh; ear, tail, muzzle, size and
coat tiles show the morphed base mesh, so a swatch always matches what the user gets. Re-run whenever the
base mesh changes (`make tiles`). Output: assets/tiles/{species}/{slot}__{value}.png + index.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core import lowfi  # noqa: E402
from backend.core.colouring import vertex_colours  # noqa: E402
from backend.core.meshkit import load_base  # noqa: E402
from backend.core.spec import apply_patch, default_spec  # noqa: E402
from backend.core.vocab import morph_weights, vocab  # noqa: E402

OUT = ROOT / "assets" / "tiles"
SIZE = 192
NEUTRAL = {"base": {"name": "tan", "hex": "#B88A5A"}, "secondary": {"name": "white", "hex": "#F4EFE6"}}
PATTERNS = {
    "dog": ["solid", "bicolour", "tricolour", "saddle_with_white_chest", "merle", "brindle", "sable", "spotted"],
    "cat": ["solid", "bicolour", "tabby", "tuxedo", "calico", "colourpoint", "spotted", "tricolour"],
}
GEOMETRY = {
    "ears.shape": (25.0, ["erect", "semi_erect", "drop", "folded", "rose"]),
    "tail.type": (90.0, ["curled", "plume", "straight", "bob", "long_thin"]),
    "head.muzzle_length": (90.0, ["short", "medium", "long"]),
    "body.size": (25.0, ["tiny", "small", "medium", "large"]),
    "body.build": (25.0, ["slim", "standard", "stocky"]),
    "coat.length": (25.0, ["short", "medium", "long"]),
}


def neutral(species: str) -> dict:
    spec = default_spec(species, "mixed", seed=4242)
    spec["colour"] = {**NEUTRAL, "pattern": "solid", "markings": []}
    spec["ears"] = {"shape": "semi_erect", "size": "medium", "tip": "rounded"}
    spec["tail"] = {"type": "straight", "length": "medium", "curl": "none"}
    return spec


def tile(species: str, spec: dict, azimuth: float, path: Path) -> None:
    base = load_base(species)
    co = base.morph(morph_weights(spec))
    cols = vertex_colours(base, spec, co)
    img = lowfi.flat_render(base, co, cols, azimuth, SIZE, True)
    img.save(path, optimize=True)


def main() -> None:
    index: dict[str, dict[str, list[str]]] = {}
    for species in ("dog", "cat"):
        d = OUT / species
        d.mkdir(parents=True, exist_ok=True)
        index[species] = {}
        for p in PATTERNS[species]:
            spec = neutral(species)
            spec["colour"]["pattern"] = p
            if p == "colourpoint":
                spec["colour"] = {"base": {"name": "cream", "hex": "#EAD9B8"},
                                  "secondary": {"name": "chocolate", "hex": "#5C3A21"}, "pattern": p, "markings": []}
            tile(species, spec, 140.0 if p in ("saddle_with_white_chest", "sable") else 30.0, d / f"colour.pattern__{p}.png")
        index[species]["colour.pattern"] = PATTERNS[species]
        markings = list(vocab()["slots"]["colour.markings"])
        for mk in markings:
            spec = neutral(species)
            spec["colour"] = {"base": {"name": "chocolate", "hex": "#5C3A21"},
                              "secondary": {"name": "white", "hex": "#F4EFE6"}, "pattern": "solid", "markings": [mk]}
            tile(species, spec, 20.0, d / f"colour.markings__{mk}.png")
        index[species]["colour.markings"] = markings
        for slot, (az, values) in GEOMETRY.items():
            ok = []
            for v in values:
                spec = neutral(species)
                section, key = slot.split(".")
                spec, _ = apply_patch(spec, {section: {key: v}})
                if slot == "tail.type" and v == "curled":
                    spec["tail"]["curl"] = "tight"
                tile(species, spec, az, d / f"{slot}__{v}.png")
                ok.append(v)
            index[species][slot] = ok
        print(species, sum(len(v) for v in index[species].values()), "tiles")
    (OUT / "index.json").write_text(json.dumps(index, indent=1) + "\n")


if __name__ == "__main__":
    main()
