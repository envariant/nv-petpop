#!/usr/bin/env python3
"""Build the proxy library releases from the proxy base meshes (BRIEF Section 16, M7):
fixtures/library/release-dog-1.tar and release-cat-1.tar.

No GenAI: the proxy library has one mesh per species, the template itself (decision 118), and every family and
part variant is built on it: part variants are region deltas made from the template's own shape keys, one per
enumeration value the breed presets use (vocab.json maps each value to shape-key weights), so every preset has a
matching part; families are full-mesh body and head variants, so every breed shares this one mesh and the release
says so. Shells are the accessory library on its sockets; pattern layers are the ten masks of
petpop_library.patterns, rasterised in the mesh's UVs. Studio replaces this with curated parts in M8; the kiosk cannot tell the
difference because both arrive as signed release bundles.

    python scripts/make_proxy_library.py [dog|cat ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: E402,F401  (puts packages/*/python on sys.path)

from petpop_core.breeds import all_breeds  # noqa: E402
from petpop_core.vocab import vocab  # noqa: E402
from petpop_library import accessories, content, figure, release  # noqa: E402
from petpop_library.atlas import mesh_texel_map  # noqa: E402
from petpop_library.deltas import encode, region_weights  # noqa: E402
from petpop_library.meshkit import load_base  # noqa: E402
from petpop_library.patterns import CHANNELS, PATTERNS, build_masks  # noqa: E402

OUT = ROOT / "fixtures" / "library"
ATLAS = 1024
CREATED_AT = "2026-10-29T00:00:00Z"  # fixed, so rebuilding gives byte-identical bundles
SHELLS = [("collar", "Collar", "neck", "#DD3333"), ("bandana", "Bandana", "neck", "#3366CC"), ("bow", "Bow", "head", "#E04A8A"),
          ("hat", "Party hat", "head", "#F2C230"), ("glasses", "Glasses", "face", "#1E1B1A")]
REGION_SLOTS = {"ears": ["ears.shape", "ears.size"], "tail": ["tail.type", "tail.length"], "muzzle": ["head.muzzle_length", "head.brachycephalic"],
                "legs": ["body.leg_length"]}
HEAD_PARTS = [("head_classic", "Classic head", {}), ("head_big", "Big head", {"head_scale": 0.6}), ("head_small", "Small head", {"head_scale": -0.4})]


def slot_weights(species: str, slot: str, value) -> dict[str, float]:
    """Shape-key weights of one slot value, with the species' substitutes applied (as vocab.morph_weights does)."""
    v = vocab()
    entry = v["slots"][slot][str(value).lower() if isinstance(value, bool) else value]
    targets, subs = v["morph_targets"][species], v["species_substitutes"].get(species, {})
    out: dict[str, float] = {}
    for name, w in entry["morph"].items():
        if name in targets:
            out[name] = out.get(name, 0.0) + float(w)
        for sub, k in subs.get(name, {}).items():
            if sub in targets:
                out[sub] = out.get(sub, 0.0) + float(w) * k
    return out


def get(preset: dict, path: str):
    node = preset
    for part in path.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def label(slot: str, value) -> str:
    return {"ears.shape": "{} ears", "ears.size": "{} ears", "tail.type": "{} tail", "tail.length": "{} tail",
            "head.muzzle_length": "{} muzzle", "head.brachycephalic": "Flat face", "body.leg_length": "{} legs"}[slot].format(
        str(value).replace("_", " ").capitalize())


def build(species: str) -> Path:
    base = load_base(species)
    mesh = figure.from_template(base, base.co)
    breeds = all_breeds(species)
    files: dict[str, bytes] = {}
    region_deltas, families, shell_parts, pattern_layers = [], [], [], []

    def add_delta(pid: str, name: str, region: str, weights: dict[str, float], tags: list[str]) -> None:
        d = content.delta_from_weights(base, weights, region)
        files[f"deltas/{pid}.f16"] = encode(d)
        files[f"thumbs/{pid}.png"] = content.thumbnail(base, base.co + d, content.highlight(base, region_weights(base, region)))
        region_deltas.append({"id": pid, "name": name, "region": region, "mesh_id": mesh.mesh_id, "delta": f"deltas/{pid}.f16", "tags": tags, "version": 1,
                              "thumbnail": f"thumbs/{pid}.png", "source_job": None, "curator_score": None})

    # Region deltas: one per slot value the species' presets use (plus the neutral "classic" part per region).
    for region, slots in REGION_SLOTS.items():
        add_delta(f"{region}_classic", f"Classic {region}", region, {}, [])
        for slot in slots:
            values = sorted({str(get(b["preset"], slot)).lower() for b in breeds if get(b["preset"], slot) is not None})
            for value in values:
                key = value if slot != "head.brachycephalic" else value == "true"
                w = slot_weights(species, slot, key)
                if not any(w.values()):
                    continue
                add_delta(f"{region}_{slot.split('.')[-1]}_{value}".replace("brachycephalic_true", "flat"), label(slot, value), region, w,
                          [f"{slot}:{value}"])
    for pid, name, w in HEAD_PARTS:
        add_delta(pid, name, "head", w, [])

    # Families: full-mesh body (and, for dogs, head) variants with breeds assigned from their presets.
    fam_defs = [("standard", "Standard", {}), ("stocky", "Stocky", slot_weights(species, "body.build", "stocky")),
                ("slim", "Slim", slot_weights(species, "body.build", "slim"))]
    if "brachy" in vocab()["morph_targets"][species]:
        fam_defs.append(("brachy", "Flat-faced", {**slot_weights(species, "head.brachycephalic", True), "head_scale": 0.3}))
    defaults = {"ears": "ears_classic", "tail": "tail_classic", "muzzle": "muzzle_classic", "head": "head_classic", "legs": "legs_classic"}
    for fid, name, w in fam_defs:
        d = content.delta_from_weights(base, w)
        files[f"deltas/family_{fid}.f16"] = encode(d)
        files[f"thumbs/family_{fid}.png"] = content.thumbnail(base, base.co + d)
        members = []
        for b in breeds:
            brachy = bool(get(b["preset"], "head.brachycephalic"))
            build_ = get(b["preset"], "body.build") or "standard"
            fam = "brachy" if brachy and any(f[0] == "brachy" for f in fam_defs) else build_
            if fam == fid:
                members.append(b["id"])
        families.append({"id": f"family_{fid}", "name": name, "mesh_id": mesh.mesh_id, "delta": f"deltas/family_{fid}.f16", "default_parts": defaults,
                         "breeds": members, "tags": [f"body.build:{fid}"] if fid != "brachy" else ["head.brachycephalic:true"],
                         "version": 1, "thumbnail": f"thumbs/family_{fid}.png", "source_job": None})

    # Shell parts: the accessory library on its sockets.
    lib = accessories.library()
    for kind, name, socket, colour in SHELLS:
        if kind not in lib:
            continue
        v, f = lib[kind]
        import trimesh  # noqa: PLC0415

        files[f"shells/{kind}.glb"] = trimesh.Trimesh(v, f, process=False).export(file_type="glb")
        files[f"thumbs/shell_{kind}.png"] = content.mesh_thumbnail(v, f, colour)
        shell_parts.append({"id": f"shell_{kind}", "name": name, "socket": socket, "kind": kind, "mesh": f"shells/{kind}.glb",
                            "default_colour": colour, "tags": [f"accessory:{kind}"], "version": 1, "thumbnail": f"thumbs/shell_{kind}.png"})

    # The mesh, with its pattern masks packed four to a PNG (eye and nose in the last file).
    entry, mfiles = content.mesh_entry(mesh, f"Classic {species}", [], size=ATLAS)
    files.update(mfiles)
    masks = build_masks(mesh, mesh_texel_map(mesh, ATLAS))
    channels = {name: i for i, name in enumerate(CHANNELS)}
    for p in PATTERNS:
        ch = channels[p.id]
        files[f"thumbs/pattern_{p.id}.png"] = content.pattern_thumbnail(base, masks, f"pattern_{p.id}", ch, p.coverage[2], p.colour)
        pattern_layers.append({"id": f"pattern_{p.id}", "name": p.name, "channel": ch, "default_colour": p.colour,
                               "coverage": {"min": p.coverage[0], "max": p.coverage[1], "default": p.coverage[2]},
                               "tags": [f"marking:{p.id}"], "version": 1, "thumbnail": f"thumbs/pattern_{p.id}.png"})

    m = content.manifest(species, 1, mesh.schema_version, "make_proxy_library.py", CREATED_AT, [entry], families,
                         region_deltas, shell_parts, pattern_layers,
                         notes="Proxy library on the proxy template mesh (no GenAI). Replaced by Studio releases (M8).")
    bundle = release.pack(m, files, key=release.DEV_RELEASE_KEY.encode())
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"release-{species}-1.tar"
    out.write_bytes(bundle)
    print(f"{out.relative_to(ROOT)}: {len(families)} families, {len(region_deltas)} region deltas, {len(shell_parts)} shells, "
          f"{len(pattern_layers)} patterns, {len(bundle) / 1e6:.1f} MB")
    return out


if __name__ == "__main__":
    for sp in [a for a in sys.argv[1:] if a in ("dog", "cat")] or ["dog", "cat"]:
        build(sp)
