#!/usr/bin/env python3
"""Library coverage for M9 (BRIEF Section 16, docs/HANDOFF-M9.md): which breed presets a release covers, with a
part kit (decisions 127 to 139) or a family on a labelled mesh, which breeds share a mesh, which are still only on
the proxy template, which marking enumerations have a pattern layer, and which kits lack a mask their breed's
texture names.

    python scripts/library_coverage.py var/releases/inbox/release-dog-2.tar   # a bundle Studio packed
    python scripts/library_coverage.py dog [--json out.json]                  # the newest bundle for dog

Exit 0 when every breed preset is covered (a kit, or a family on a generated mesh), every kit has the masks its
texture names, and, for breeds on families, every marking has a pattern layer (the coverage half of gate 9), else 1.
"""
from __future__ import annotations

import json
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


def kit_gaps(manifest: dict) -> dict[str, list[str]]:
    """Per kit, the pattern and markings its default texture names that no part of it has a mask for."""
    masks = {(m["uv_layout"], m["name"]) for m in manifest.get("masks") or []}
    out = {}
    for kit in manifest.get("kits") or []:
        layouts = {p.get("uv_layout") for p in kit["parts"]} - {None}
        t = kit.get("texture") or {}
        names = [n for n in [t.get("pattern"), *(t.get("markings") or [])] if n and n != "solid"]
        missing = [n for n in names if not any((lay, n) in masks for lay in layouts)]
        if missing:
            out[kit["breed_id"]] = missing
    return out


def report(manifest: dict) -> tuple[list[str], bool]:
    lines, ok, _ = summary(manifest)
    return lines, ok


def summary(manifest: dict) -> tuple[list[str], bool, dict]:
    species = manifest["species"]
    meshes = {m["id"]: m for m in manifest["meshes"]}
    generated = {mid for mid, m in meshes.items() if m.get("source") == "generated"}
    on: dict[str, set[str]] = {}
    for f in manifest["families"]:
        for b in f["breeds"]:
            on.setdefault(b, set()).add(f["mesh_id"])
    breeds = [b for b in all_breeds(species) if b["id"] != "mixed"]
    kits = {k["breed_id"] for k in manifest.get("kits") or []}
    real = [b["id"] for b in breeds if on.get(b["id"], set()) & generated and b["id"] not in kits]
    kit = [b["id"] for b in breeds if b["id"] in kits]
    proxy = [b["id"] for b in breeds if b["id"] in on and b["id"] not in real and b["id"] not in kits]
    missing = [b["id"] for b in breeds if b["id"] not in on and b["id"] not in kits]
    layers = {p["id"] for p in manifest["pattern_layers"]}
    need = sorted({*MARKING_LAYERS.values(), *(x for v in PATTERN_LAYERS.values() for x in v)})
    lines = [f"{manifest['release_version']} ({species}, {manifest['segmentation_version']}): {len(meshes)} meshes "
             f"({len(generated)} generated), {len(manifest['families'])} families",
             f"breeds covered: {len(kit) + len(real)}/{len(breeds)} ({len(kit)} as part kits, {len(real)} on a generated mesh)"]
    if proxy:
        lines.append(f"  only on the proxy template ({len(proxy)}): {', '.join(proxy)}")
    if missing:
        lines.append(f"  no family yet ({len(missing)}): {', '.join(missing)}")
    shared = [(m["name"], m["breeds"]) for m in meshes.values() if m.get("source") == "generated" and len(m["breeds"]) > 1]
    for name, bs in shared:
        lines.append(f"  shared mesh {name}: {', '.join(bs)}")
    gaps = kit_gaps(manifest)
    for b, names in sorted(gaps.items()):
        lines.append(f"  kit {b}: no mask for {', '.join(names)} (named by its default texture)")
    families_needed = bool(real or proxy)  # pattern layers paint whole-figure meshes only; kits paint from masks
    absent = [p for p in need if p not in layers] if families_needed else []
    lines.append(f"pattern layers for every marking and coat pattern: {'yes' if not absent else 'missing ' + ', '.join(absent)}"
                 + ("" if families_needed else " (no breed on a whole-figure mesh needs them)"))
    ok = not proxy and not missing and not absent and not gaps
    data = {"release_version": manifest["release_version"], "species": species, "breeds": len(breeds), "kits": kit,
            "generated": real, "proxy_only": proxy, "missing": missing, "kit_mask_gaps": gaps, "pattern_layers_missing": absent,
            "complete": ok}
    return lines, ok, data


def main() -> int:
    args = sys.argv[1:]
    out = None
    if "--json" in args:
        i = args.index("--json")
        out = Path(args[i + 1])
        del args[i:i + 2]
    arg = args[0] if args else "dog"
    path = Path(arg) if arg.endswith(".tar") else newest(arg)
    manifest, _ = release.read(path.read_bytes())
    lines, ok, data = summary(manifest)
    print("\n".join(lines))
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({**data, "bundle": str(path)}, indent=1) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
