"""Golden data for the part kits' TypeScript twin and Studio's standalone mode (decision 127): the first-guess rig of
the dog proxy kit (fixtures/parts/dog) and, for every slot and a few poses, the 4x4 placement Python computes.
packages/scene/src/parts.test.ts checks parts.ts against it; Studio's MSW handlers serve the rig.

    python scripts/make_parts_golden.py      # writes fixtures/parts/golden.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/python"), str(ROOT / "packages/library/python")]

from petpop_library import parts as P  # noqa: E402

POSES = [{}, {"legs": {"front_left": 1, "front_right": 1, "hind_left": 2, "hind_right": 0}},
         {"head": {"yaw": 25, "pitch": -10, "roll": 8}}]


def main() -> None:
    d = ROOT / "fixtures" / "parts" / "dog"
    meshes = {}
    for p in sorted(d.glob("*.glb")):
        _, kind, *var = p.stem.split("__")
        m = trimesh.load(p, force="mesh", process=False)
        meshes[f"{kind}/{var[0] if var else 'default'}"] = (np.asarray(m.vertices), np.asarray(m.faces), p.name, int(len(m.faces)))
    rig = P.auto_rig({k: v[:2] for k, v in meshes.items() if not k.startswith("torso/")}, meshes["torso/default"][:2])
    parts = []
    for key, (_, _, name, tris) in meshes.items():
        kind, variant = key.split("/")
        part = {"kind": kind, "variant": variant, "file": name, "tris": tris}
        if kind == "torso":
            part["attachments"] = {s: {"position": P._r(a["position"], 4), "axis": P._r(a["axis"], 6), "twist": 0.0}
                                   for s, a in rig.attachments.items()}
            part["guess"] = {s: {"method": a["method"], "confidence": a["confidence"]} for s, a in rig.attachments.items()}
        else:
            j = rig.joints[key]
            part["joint"] = {"pivot": P._r(j["pivot"], 4), "axis": P._r(j["axis"], 6), "twist": 0.0}
            part["guess"] = {"joint": {"method": j["method"], "confidence": j["confidence"]}}
            if kind == "head":
                part["limits"] = P.DEFAULT_HEAD_LIMITS
        parts.append(part)
    placements = []
    by = {(p["kind"], p["variant"]): p for p in parts}
    torso = by[("torso", "default")]
    for pose in POSES:
        for slot in P.SLOTS:
            part = by[(P.SLOT_KIND[slot], "default")]
            jp = P.Joint.of(part["joint"])
            ja = P.Joint.of(torso["attachments"][slot])
            # with a twist on the joint too, so the frames' twist is exercised
            jp.twist = 15.0
            R, t = P.placement(jp, ja, slot, pose)
            M = np.eye(4)
            M[:3, :3] = R @ (P.MIRROR if slot in P.MIRRORED else np.eye(3))
            M[:3, 3] = t
            placements.append({"slot": slot, "pose": pose, "joint_twist": 15.0, "matrix": [round(float(x), 6) for x in M.T.ravel()]})
    out = {"species": "dog", "breed_id": "mixed", "parts": parts, "placements": placements}
    (ROOT / "fixtures" / "parts" / "golden.json").write_text(json.dumps(out, indent=1) + "\n")
    print("wrote fixtures/parts/golden.json:", len(parts), "parts,", len(placements), "placements")


if __name__ == "__main__":
    main()
