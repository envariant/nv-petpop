"""Proxy part kits (decision 127): each species' labelled template mesh cut into the five parts, head, torso, front leg,
hind leg and tail, as GLBs in the part library's frame (glTF: +Y up, +Z front, +X the pet's left; millimetres), the way
a real kit arrives: labelled files, one per part, split in place from one figure, open where they were cut. A few
variants come from the template's morphs (a slim and a stocky torso, long legs, a plume tail). They stand in for
authored parts until Nishant's library arrives, and they are what the tests rig.

    python scripts/make_proxy_parts.py            # writes fixtures/parts/<species>/mixed__<kind>[__<variant>].glb
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/python"), str(ROOT / "packages/library/python")]

from petpop_library.meshkit import load_base  # noqa: E402

GROUPS = {"head": ["head", "muzzle", "ear_L", "ear_R", "eye_L", "eye_R", "nose"], "torso": ["body", "base"],
          "front_leg": ["leg_FL"], "hind_leg": ["leg_BL"], "tail": ["tail"]}
VARIANTS = {"torso": {"slim": {"body_slim": 1.0}, "stocky": {"body_stocky": 1.0}}, "front_leg": {"long": {"leg_len": 1.0}},
            "hind_leg": {"long": {"leg_len": 1.0}}, "tail": {"plume": {"tail_plume": 1.0}}}
OUT = ROOT / "fixtures" / "parts"


def to_gltf(co: np.ndarray) -> np.ndarray:
    """Template frame (+Z up, front -Y) to glTF (+Y up, front +Z); +X stays the pet's left."""
    return np.stack([co[:, 0], co[:, 2], -co[:, 1]], axis=1)


def split(species: str) -> dict[str, bytes]:
    base = load_base(species)
    label = np.argmax(base.groups, axis=0)
    names = base.group_names
    kind_of = np.full(len(names), "", dtype=object)
    for kind, groups in GROUPS.items():
        for g in groups:
            kind_of[names.index(g)] = kind
    vkind = kind_of[label]
    # a face belongs to the kind most of its corners have (ties: the first corner's)
    corners = vkind[base.tri_verts]
    fkind = np.where(corners[:, 1] == corners[:, 2], corners[:, 1], corners[:, 0])
    out: dict[str, bytes] = {}
    for kind in GROUPS:
        faces = base.tri_verts[fkind == kind]
        variants = {"": {}} | VARIANTS.get(kind, {})
        for variant, morphs in variants.items():
            if any(m not in base.morph_names for m in morphs):
                continue  # this species' template has no such morph
            co = base.co.copy()
            for m, w in morphs.items():
                co = co + w * base.morph_deltas[base.morph_names.index(m)]
            used, inv = np.unique(faces, return_inverse=True)
            mesh = trimesh.Trimesh(to_gltf(co[used]), inv.reshape(-1, 3), process=False)
            name = f"mixed__{kind}" + (f"__{variant}" if variant else "") + ".glb"
            out[name] = mesh.export(file_type="glb")
    return out


def main() -> None:
    for species in ("dog", "cat"):
        d = OUT / species
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.glb"):
            old.unlink()
        for name, data in split(species).items():
            (d / name).write_bytes(data)
        print(species, sorted(p.name for p in d.glob("*.glb")))


if __name__ == "__main__":
    main()
