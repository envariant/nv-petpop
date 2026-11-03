"""Draft a breed's figure from parts exported one at a time (decision 128, docs/PARTS.md section 1a).

    python scripts/draft_parts.py --files ~/exports/corgi --out var/drafts/corgi_pembroke [--breed corgi_pembroke]
        [--species dog] [--front +z|-z|+x|-x] [--keep-scale] [--fuse]

Each part a generator makes on its own comes at its own scale, about its own origin, so nothing in the files says
how the parts fit together. This guesses it:
  1. names   <breed>__<kind>[__<variant>].glb, the breed database's names too (fore_leg, hind_leg_sitting)
  2. facing  every part turned about +Y so the pet faces +Z (--front: where the exports' front is)
  3. size    every part scaled to its breed's size guess (petpop_library.part_sizes, data/breeds/<species>_part_sizes.json),
             textures kept; --keep-scale for parts already in proportion
  4. rig     the first guess at every joint and torso socket (petpop_library.parts.auto_rig)
  5. compose the draft figure in the standing pose, once with the default variants and once per other variant
Writes <out>/parts/*.glb (the fitted parts), <out>/<breed>.draft-kit.json (a kit-1 document, version 0) and
<out>/<breed>__draft*.glb (+ .stl, .plan.json). Final authoring starts from there: upload <out>/parts to Studio
(Parts, with "Scale to size guess" off: they are fitted already) to rig and commit, then compose the committed kit
with your own edits (make compose-parts ... ARGS="--modify my_edits.py").
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "packages/core/python"), str(ROOT / "packages/library/python")]

from compose_parts import compose  # noqa: E402
from petpop_library import part_sizes as S  # noqa: E402
from petpop_library import parts as P  # noqa: E402

FRONT = {"+z": 0.0, "-z": 180.0, "+x": -90.0, "-x": 90.0}  # degrees about +Y that bring that axis to +Z
STANDING = {"pose_id": "standing", "label": "Standing", "legs": {s: 0 for s in P.LEG_SLOTS}, "head": {"yaw": 0, "pitch": 0, "roll": 0}}


def mesh_of(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    import trimesh  # noqa: PLC0415

    m = trimesh.load(io.BytesIO(data), file_type="glb", force="mesh", process=False)
    return np.asarray(m.vertices, float), np.asarray(m.faces, int)


def file_name(breed: str, kind: str, variant: str) -> str:
    return f"{breed}__{kind}" + ("" if variant == "default" else f"__{variant}") + ".glb"


def fit_parts(files: list[Path], species: str, breed: str | None, front: str, scale: bool, out: Path) -> tuple[str, dict, list[str]]:
    """Steps 1 to 3: the fitted parts written to `out`; returns the breed, {(kind, variant): (file, v, f)} and notes."""
    turn = np.eye(4)
    turn[:3, :3] = P.rot([0, 1, 0], FRONT[front])
    got: dict[tuple[str, str], tuple[str, np.ndarray, np.ndarray]] = {}
    notes: list[str] = []
    breeds = set()
    out.mkdir(parents=True, exist_ok=True)
    for path in sorted(files):
        parsed = P.parse_name(path.name)
        if not parsed:
            notes.append(f"{path.name}: skipped, expected <breed>__<kind>[__<variant>].glb")
            continue
        b, kind, variant = parsed
        b = breed or b
        breeds.add(b)
        data = path.read_bytes()
        v, _ = mesh_of(data)
        v = v @ turn[:3, :3].T
        matrix, _, what = S.normalise(species, b, kind, variant, v, scale)
        m = (matrix if matrix is not None else np.eye(4)) @ turn
        if not np.allclose(m, np.eye(4)):
            data = S.transform_glb(data, m)
        notes += [f"{path.name}: {w}" for w in what]
        name = file_name(b, kind, variant)
        (out / name).write_bytes(data)
        nv, nf = mesh_of(data)
        got[(kind, variant)] = (name, nv, nf)
    if len(breeds) != 1:
        raise SystemExit(f"expected the parts of one breed, found {sorted(breeds) or 'none'} (--breed sets it)")
    return breeds.pop(), got, notes


def draft_kit(species: str, breed: str, got: dict, in_place: bool = False) -> dict:
    """Step 4: the first guess as a kit-1 document (version 0: a draft, never committed)."""
    defaults = {}
    for kind in P.KINDS:
        variants = sorted(v for k, v in got if k == kind)
        if not variants:
            raise SystemExit(f"no {kind} part: a draft needs all of {', '.join(P.KINDS)}")
        defaults[kind] = "default" if "default" in variants else variants[0]
    _, tv, tf = got[("torso", defaults["torso"])]
    rig = P.auto_rig({f"{k}/{v}": (pv, pf) for (k, v), (_, pv, pf) in got.items() if k != "torso"}, (tv, tf), in_place,
                     ground=None if in_place else 0.0)
    flt = lambda xs: [round(float(x), 4) for x in xs]  # noqa: E731
    parts = []
    for (kind, variant), (name, _, pf) in sorted(got.items()):
        p = {"part_id": f"draft_{kind}_{variant}", "kind": kind, "variant": variant, "label": variant.replace("_", " ").title(),
             "mesh": {"file": name, "sha256": "0" * 64, "tris": int(len(pf))}, "uv_layout": f"{species}-{kind}-1"}
        if kind == "torso":
            p["attachments"] = {s: {"position": flt(a["position"]), "axis": flt(a["axis"]), "twist": 0.0} for s, a in rig.attachments.items()}
            p["guess"] = {s: {"method": a["method"], "confidence": a["confidence"]} for s, a in rig.attachments.items()}
        else:
            j = rig.joints[f"{kind}/{variant}"]
            p["joint"] = {"pivot": flt(j["pivot"]), "axis": flt(j["axis"]), "twist": 0.0}
            p["guess"] = {"joint": {"method": j["method"], "confidence": j["confidence"]}}
        if kind == "head":
            p["limits"] = P.DEFAULT_HEAD_LIMITS
        parts.append(p)
    return {"kit_version": "kit-1", "species": species, "breed_id": breed, "version": 0, "draft": True, "parts": parts,
            "defaults": defaults, "poses": [STANDING], "default_pose": "standing", "notes": rig.notes}


def figures(kit: dict) -> list[tuple[str, dict]]:
    """Step 5's figures: the defaults, then each other variant swapped in on its own."""
    out = [("draft", {})]
    for p in kit["parts"]:
        if p["variant"] != kit["defaults"][p["kind"]]:
            out.append((f"draft__{p['kind']}-{p['variant']}", {p["kind"]: p["variant"]}))
    return out


def draft(files: list[Path], out: Path, species: str = "dog", breed: str | None = None, front: str = "+z",
          scale: bool = True, fuse: bool = False, engine: str = "auto") -> dict:
    breed, got, notes = fit_parts(files, species, breed, front, scale, out / "parts")
    kit = draft_kit(species, breed, got, in_place=not scale)
    kit["notes"] = notes + kit["notes"]
    (out / f"{breed}.draft-kit.json").write_text(json.dumps(kit, indent=1) + "\n")
    made = []
    for name, variants in figures(kit):
        r = compose(kit, out / "parts", out, variants, "standing", fuse, None, engine, name=f"{breed}__{name}")
        import trimesh  # noqa: PLC0415

        ext = trimesh.load(r["outputs"]["glb"], force="mesh").extents
        made.append({"glb": r["outputs"]["glb"], "variants": r["variants"], "size_mm": [round(float(x), 1) for x in ext]})
    return {"breed_id": breed, "kit": str(out / f"{breed}.draft-kit.json"), "figures": made, "notes": kit["notes"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--files", type=Path, required=True, help="a folder of part GLBs (or one GLB per --files ... use a folder)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--species", default="dog", choices=["dog", "cat"])
    ap.add_argument("--breed", help="the breed id, when the file names' breed is not it")
    ap.add_argument("--front", default="+z", choices=list(FRONT), help="the exports' front (the kit frame's is +z)")
    ap.add_argument("--keep-scale", action="store_true", help="the parts are already in proportion (split from one figure)")
    ap.add_argument("--fuse", action="store_true")
    ap.add_argument("--engine", choices=["auto", "bpy", "trimesh"], default="auto")
    a = ap.parse_args()
    r = draft(sorted(a.files.glob("*.glb")), a.out, a.species, a.breed, a.front, not a.keep_scale, a.fuse, a.engine)
    for n in r["notes"]:
        print("  " + n)
    for f in r["figures"]:
        w, h, d = f["size_mm"]
        print(f"{f['glb']}: {h:.0f} mm tall, {d:.0f} mm nose to tail, {w:.0f} mm wide  {f['variants']}")
    print(f"draft kit: {r['kit']}")


if __name__ == "__main__":
    main()
