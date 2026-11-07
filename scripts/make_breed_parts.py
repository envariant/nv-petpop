"""Seed the per-breed parts file (decision 131) from the breed database: each breed's part types offered and default,
at their size guesses, the torso with its default preset, the sitting hind leg, its colours as the default texture.

    python scripts/make_breed_parts.py [--db data/breeds/dog_pebbles_simple.json] [--out data/breeds/dog_breed_parts.json]

Breeds already in the file are kept as they are (edit them by hand, or in Studio's workbench); only new breeds are added.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/python"), str(ROOT / "packages/library/python")]

from petpop_library import breed_parts as B  # noqa: E402

NOTE = ("Which parts each breed uses (decision 131, docs/PARTS.md). Per kind: 'offer' (variants customers may choose; "
        "the shared library's or the breed's own), 'default'. Per offered variant: 'stretch' [x, y, z] (null: the size "
        "guess). Per torso variant: 'presets', the shape choices, the first 'default'; each a 'stretch' (null: the "
        "variant's) and 'sockets': per slot {'translate': [x, y, z] mm, 'rotate': [x, y, z] degrees}. 'sitting': the hind "
        "leg variant the sitting pose swaps in. Studio seeds a breed's kit from its entry; scripts/make_breed_parts.py "
        "only adds breeds.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, default=ROOT / "data/breeds/dog_pebbles_simple.json")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    db = json.loads(a.db.read_text())
    out = a.out or B.path(db["species"])
    have = json.loads(out.read_text()) if out.is_file() else {"version": "breed-parts-1", "species": db["species"], "breeds": {}}
    have["note"] = NOTE
    added = [b["id"] for b in db["breeds"] if b["id"] not in have["breeds"]]
    for b in db["breeds"]:
        have["breeds"].setdefault(b["id"], B.seed(b))
    out.write_text(json.dumps(have, indent=1) + "\n")
    print(f"{len(added)} breeds added, {len(have['breeds']) - len(added)} kept -> {out}")


if __name__ == "__main__":
    main()
