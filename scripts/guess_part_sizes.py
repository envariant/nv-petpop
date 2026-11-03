"""Guess every breed's part sizes from the pebble breed database (decision 128, petpop_library.part_sizes).

    python scripts/guess_part_sizes.py [--db data/breeds/dog_pebbles_simple.json] [--out data/breeds/dog_part_sizes.json]
        [--figure-mm 90] [--show corgi_pembroke ...]

Rerun it whenever the database changes; Studio reads the table when a part arrives at a scale that is not millimetres.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/python"), str(ROOT / "packages/library/python")]

from petpop_library import part_sizes as S  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, default=ROOT / "data/breeds/dog_pebbles_simple.json")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--figure-mm", type=float, default=S.FIGURE_MM)
    ap.add_argument("--show", nargs="*", default=[], help="print these breeds' rows")
    a = ap.parse_args()
    db = json.loads(a.db.read_text())
    t = S.build_table(db, a.figure_mm)
    t["source"] = str(a.db.relative_to(ROOT)) if a.db.resolve().is_relative_to(ROOT) else a.db.name
    out = a.out or ROOT / "data/breeds" / f"{db['species']}_part_sizes.json"
    out.write_text(json.dumps(t, indent=1) + "\n")
    notes = sum(len(b["notes"]) for b in t["breeds"].values())
    print(f"{len(t['breeds'])} breeds -> {out.relative_to(ROOT) if out.resolve().is_relative_to(ROOT) else out} ({notes} notes)")
    for b in a.show:
        print(json.dumps(t["breeds"][b], indent=1))


if __name__ == "__main__":
    main()
