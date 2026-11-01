#!/usr/bin/env python3
"""Library coverage for M9 (BRIEF Section 16, docs/HANDOFF-M9.md): which breed presets a release covers with a
family on a labelled mesh, which breeds share a mesh, which are still only on the proxy template, and which marking
enumerations have a pattern layer.

    python scripts/library_coverage.py var/releases/inbox/release-dog-2.tar   # a bundle Studio packed
    python scripts/library_coverage.py dog                                    # the newest bundle for dog

Exit 0 when every breed preset has a family on a generated mesh and every marking has a pattern layer (the
coverage half of gate 9), else 1.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: E402,F401  (puts packages/*/python on sys.path)

from petpop_core.breeds import all_breeds  # noqa: E402
from petpop_library import release  # noqa: E402

# Markings and coat patterns -> the pattern layers the kiosk starts a breed with (packages/scene/src/compose.ts).
MARKING_LAYERS = {"white_blaze": "pattern_blaze", "white_socks": "pattern_socks", "white_chest": "pattern_chest",
                  "dark_mask": "pattern_mask", "points": "pattern_points"}
PATTERN_LAYERS = {"saddle_with_white_chest": ["pattern_saddle", "pattern_chest"], "tricolour": ["pattern_saddle", "pattern_chest"],
                  "bicolour": ["pattern_tuxedo"], "tuxedo": ["pattern_tuxedo"], "colourpoint": ["pattern_points"],
                  "sable": ["pattern_saddle"], "brindle": ["pattern_brindle"], "tabby": ["pattern_tabby"],
                  "merle": ["pattern_merle"], "spotted": ["pattern_merle"], "calico": ["pattern_merle", "pattern_chest"]}


def newest(species: str) -> Path:
    found = [p for d in (ROOT / "var" / "releases" / "inbox", ROOT / "fixtures" / "library")
             for p in d.glob(f"release-{species}-*.tar")]
    if not found:
        raise SystemExit(f"no release bundle for {species}")
    return max(found, key=lambda p: int(p.stem.rsplit("-", 1)[1]))


def report(manifest: dict) -> tuple[list[str], bool]:
    species = manifest["species"]
    meshes = {m["id"]: m for m in manifest["meshes"]}
    generated = {mid for mid, m in meshes.items() if m.get("source") == "generated"}
    on: dict[str, set[str]] = {}
    for f in manifest["families"]:
        for b in f["breeds"]:
            on.setdefault(b, set()).add(f["mesh_id"])
    breeds = [b for b in all_breeds(species) if b["id"] != "mixed"]
    real = [b["id"] for b in breeds if on.get(b["id"], set()) & generated]
    proxy = [b["id"] for b in breeds if b["id"] in on and b["id"] not in real]
    missing = [b["id"] for b in breeds if b["id"] not in on]
    layers = {p["id"] for p in manifest["pattern_layers"]}
    need = sorted({*MARKING_LAYERS.values(), *(x for v in PATTERN_LAYERS.values() for x in v)})
    lines = [f"{manifest['release_version']} ({species}, {manifest['segmentation_version']}): {len(meshes)} meshes "
             f"({len(generated)} generated), {len(manifest['families'])} families",
             f"breeds on a generated mesh: {len(real)}/{len(breeds)}"]
    if proxy:
        lines.append(f"  only on the proxy template ({len(proxy)}): {', '.join(proxy)}")
    if missing:
        lines.append(f"  no family yet ({len(missing)}): {', '.join(missing)}")
    shared = [(m["name"], m["breeds"]) for m in meshes.values() if m.get("source") == "generated" and len(m["breeds"]) > 1]
    for name, bs in shared:
        lines.append(f"  shared mesh {name}: {', '.join(bs)}")
    absent = [p for p in need if p not in layers]
    lines.append(f"pattern layers for every marking and coat pattern: {'yes' if not absent else 'missing ' + ', '.join(absent)}")
    return lines, not proxy and not missing and not absent


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "dog"
    path = Path(arg) if arg.endswith(".tar") else newest(arg)
    manifest, _ = release.read(path.read_bytes())
    lines, ok = report(manifest)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
