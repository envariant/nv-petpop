"""Draft a breed's figure from parts exported one at a time (decisions 128, 130; docs/PARTS.md section 1a).

    python scripts/draft_parts.py --files ~/exports/corgi [--shared ~/exports/shared] --out var/drafts/corgi_pembroke
        [--breed corgi_pembroke] [--species dog] [--front +z|-z|+x|-x] [--keep-scale] [--fuse]

The draft runs Studio's own part library (backend/api/part_library.py) on a throwaway database and store, so it
guesses exactly what an upload to Studio would:
  1. names   <breed>__<kind>[__<variant>].glb, the breed's head (and any parts of its own); shared__<kind>__<variant>.glb
             the shared library of torsos, legs and tails (--files may hold both; --shared adds another folder)
  2. facing  every part turned about +Y so the pet faces +Z (--front: where the exports' front is)
  3. size    every part fitted to its size guess (the breed's; for a shared part the median of the breeds using that
             variant), centred, textures kept; --keep-scale for parts already in proportion
  4. rig     the first guess at every joint and socket, each leg slid to stand on the floor
  5. breed   the variants it allows and its defaults (its part types in the breed database), each shared part
             stretched to its proportions, its poses (sitting, once the sitting hind leg is there)
  6. compose the figure in every pose, and once per other allowed variant
Writes <out>/<breed>.draft-kit.json (a kit-2 document, version 0, its problems listed), <out>/<breed>__draft*.glb (+ .stl,
.plan.json) and the fitted parts under <out>/store/parts/. Final authoring starts there: upload the same exports to
Studio (Parts), rig and commit, then compose the committed kit with your own edits (make compose-parts ... ARGS="--modify ...").
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "packages/core/python"), str(ROOT / "packages/library/python")]

from compose_parts import compose  # noqa: E402
from petpop_library import part_sizes as S  # noqa: E402
from petpop_library import parts as P  # noqa: E402

FRONT = {"+z": 0.0, "-z": 180.0, "+x": -90.0, "-x": 90.0}  # degrees about +Y that bring that axis to +Z


def figures(kit: dict) -> list[tuple[str, str, dict]]:
    """(name, pose, variants): each pose with the defaults, then each other allowed variant on its own."""
    out = [("draft" if p["pose_id"] == kit["default_pose"] else f"draft__{p['pose_id']}", p["pose_id"], {}) for p in kit["poses"]]
    swapped = {(k, v) for p in kit["poses"] for k, v in (p.get("variants") or {}).items()}
    for kind, variants in kit.get("allowed", {}).items():
        for v in variants:
            if v != kit["defaults"][kind] and (kind, v) not in swapped:
                out.append((f"draft__{kind}-{v}", kit["default_pose"], {kind: v}))
    return out


def draft(files: list[Path], out: Path, species: str = "dog", breed: str | None = None, front: str = "+z",
          scale: bool = True, fuse: bool = False, engine: str = "auto") -> dict:
    from backend.api.db import session_factory  # noqa: PLC0415
    from backend.api.part_library import PartLibrary  # noqa: PLC0415
    from backend.api.store import LocalStore  # noqa: PLC0415

    for old in ("draft.db", "draft.db-wal", "draft.db-shm", "store"):
        p = out / old
        shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    lib = PartLibrary(session_factory(f"sqlite:///{(out / 'draft.db').resolve()}"), LocalStore(out / "store"), "draft")
    turn = np.eye(4)
    turn[:3, :3] = P.rot([0, 1, 0], FRONT[front])
    shared, own, notes, breeds = [], [], [], set()
    for path in sorted(files):
        parsed = P.parse_name(path.name)
        if not parsed:
            notes.append(f"{path.name}: skipped, expected <breed>__<kind>[__<variant>].glb")
            continue
        data = path.read_bytes()
        data = data if front == "+z" else S.transform_glb(data, turn)
        if parsed[0] == P.SHARED:
            shared.append((path.name, data))
        else:
            own.append((path.name, data))
            breeds.add(breed or parsed[0])
    if len(breeds) != 1:
        raise SystemExit(f"expected one breed's head (and parts), found {sorted(breeds) or 'none'} (--breed sets it)")
    breed = breeds.pop()
    for batch, override in ((shared, None), (own, breed)):
        if batch:
            r = lib.upload(species, batch, "draft", override, scale)
            notes += r.skipped + r.notes
    kit = lib.document(species, breed)
    (out / f"{breed}.draft-kit.json").write_text(json.dumps(kit, indent=1, default=str) + "\n")
    made = []
    if not kit["problems"]:
        import trimesh  # noqa: PLC0415

        for name, pose, variants in figures(kit):
            r = compose(kit, out / "store", out, variants, pose, fuse, None, engine, name=f"{breed}__{name}")
            ext = trimesh.load(r["outputs"]["glb"], force="mesh").extents
            made.append({"glb": r["outputs"]["glb"], "pose": pose, "variants": r["variants"], "size_mm": [round(float(x), 1) for x in ext]})
    return {"breed_id": breed, "kit": str(out / f"{breed}.draft-kit.json"), "figures": made, "notes": notes, "problems": kit["problems"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--files", type=Path, required=True, help="a folder of part GLBs: the breed's, and shared__* ones")
    ap.add_argument("--shared", type=Path, help="another folder of shared__<kind>__<variant>.glb parts")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--species", default="dog", choices=["dog", "cat"])
    ap.add_argument("--breed", help="the breed id, when the file names' breed is not it")
    ap.add_argument("--front", default="+z", choices=list(FRONT), help="the exports' front (the kit frame's is +z)")
    ap.add_argument("--keep-scale", action="store_true", help="the parts are already in proportion (split from one figure)")
    ap.add_argument("--fuse", action="store_true")
    ap.add_argument("--engine", choices=["auto", "bpy", "trimesh"], default="auto")
    a = ap.parse_args()
    files = sorted(a.files.glob("*.glb")) + (sorted(a.shared.glob("*.glb")) if a.shared else [])
    r = draft(files, a.out, a.species, a.breed, a.front, not a.keep_scale, a.fuse, a.engine)
    for n in r["notes"]:
        print("  " + n)
    for p in r["problems"]:
        print("  problem: " + p)
    for f in r["figures"]:
        w, h, d = f["size_mm"]
        print(f"{f['glb']}: {h:.0f} mm tall, {d:.0f} mm nose to tail, {w:.0f} mm wide  ({f['pose']}) {f['variants']}")
    print(f"draft kit: {r['kit']}")


if __name__ == "__main__":
    main()
