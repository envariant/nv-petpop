"""Compose figures from a committed part kit (decision 127, docs/PARTS.md section 3): every part on its slot in a pose,
the right legs mirrored, joined, optionally fused into one watertight surface, then your own final edits.

    python scripts/compose_parts.py --kit kit-3.json --files ~/kits/corgi --out out/ [--variants torso=long_low] [--preset stocky]
        [--pose standing | --all-poses] [--fuse] [--modify my_edits.py] [--engine auto|bpy|trimesh]

--kit       a committed kit (Studio, Parts, Commit; the store's kits/<species>/<breed>/kit-<n>.json)
--files     where the part GLBs are: a folder (matched by the kit's file names or <breed>__<kind>[__<variant>].glb),
            or the artefact store root (var/artefacts) holding the kit's keys
--modify    a Python file with modify(obj, job): runs in Blender on the joined figure, the last authoring step
Writes <out>/<breed>__<pose>.glb (and .stl), stood on the floor (y = 0), and <out>/<breed>__<pose>.plan.json (what went where). Blender's bpy
(PETPOP_BPY_PYTHON) does the work when it is there; a trimesh stand-in otherwise (no voxel fuse, no --modify).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages/core/python"), str(ROOT / "packages/library/python")]

from petpop_library import parts as P  # noqa: E402


def resolve(entry: dict, kit: dict, files: Path) -> Path:
    key = entry["file"]
    candidates = [files / key, files / Path(key).name,
                  files / (f"{kit['breed_id']}__{entry['kind']}" + ("" if entry["variant"] == "default" else f"__{entry['variant']}") + ".glb")]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    # Studio's keys carry a hash suffix: <kind>__<variant>__<sha12>.glb; a local folder may hold the plain name
    stem = Path(key).name.rsplit("__", 1)[0]
    for c in sorted(files.glob(f"*{stem}*.glb")):
        return c.resolve()
    raise FileNotFoundError(f"no GLB for {entry['kind']} {entry['variant']} ({key}) under {files}")


def compose_trimesh(plan: dict, paths: list[Path], out_glb: Path, out_stl: Path | None, fuse: bool) -> dict:
    import trimesh  # noqa: PLC0415

    meshes = []
    for entry, path in zip(plan["parts"], paths):
        m = trimesh.load(path, force="mesh", process=False)
        v = np.c_[m.vertices, np.ones(len(m.vertices))] @ np.asarray(entry["matrix"]).T
        f = np.asarray(m.faces)
        meshes.append(trimesh.Trimesh(v[:, :3], f[:, ::-1] if entry["mirrored"] else f, process=False))
    fig = trimesh.util.concatenate(meshes)
    lift = -float(fig.bounds[0][1])  # stand the figure on the floor (y = 0): a breed's stretch moves its feet
    fig.apply_translation([0.0, lift, 0.0])
    meshes = [m.apply_translation([0.0, lift, 0.0]) for m in meshes]
    note = None
    if fuse:
        if all(m.is_watertight for m in meshes):
            fig = trimesh.boolean.union(meshes, engine="manifold")
        else:
            note = "not fused: some parts are open (trimesh needs closed parts; Blender's voxel fuse does not)"
    fig.export(out_glb)
    if out_stl:
        fig.export(out_stl)
    return {"vertices": int(len(fig.vertices)), "faces": int(len(fig.faces)), "engine": "trimesh", "floor_mm": round(lift, 3),
            **({"note": note} if note else {})}


def compose(kit: dict, files: Path, out: Path, variants: dict | None = None, pose_id: str | None = None, fuse: bool = False,
            modify: Path | None = None, engine: str = "auto", stl: bool = True, name: str | None = None,
            preset_id: str | None = None) -> dict:
    plan = P.compose_plan(kit, variants, pose_id, preset_id)
    paths = [resolve(e, kit, files) for e in plan["parts"]]
    out.mkdir(parents=True, exist_ok=True)
    stem = name or f"{kit['breed_id']}__{plan['pose_id']}" + ("" if plan["preset_id"] == "default" else f"__{plan['preset_id']}")
    out_glb, out_stl = out / f"{stem}.glb", (out / f"{stem}.stl" if stl else None)
    python = os.environ.get("PETPOP_BPY_PYTHON", "/opt/bpy/bin/python")
    from backend.worker import blender  # noqa: PLC0415

    use_bpy = engine == "bpy" or (engine == "auto" and blender.available(python))
    if engine == "bpy" and not blender.available(python):
        raise SystemExit(f"no bpy at {python} (PETPOP_BPY_PYTHON)")
    if modify and not use_bpy:
        raise SystemExit("--modify runs in Blender: set PETPOP_BPY_PYTHON to a Python with bpy")
    if use_bpy:
        job = {"parts": [{**e, "path": str(p)} for e, p in zip(plan["parts"], paths)], "out_glb": str(out_glb),
               "out_stl": str(out_stl) if out_stl else None, "fuse": fuse, "voxel_mm": 0.35, "modify": str(modify.resolve()) if modify else None}
        result = blender.run(python, ["compose_parts"], job, timeout=600)
        result = {k: result[k] for k in ("vertices", "faces", "engine", "floor_mm") if k in result}
    else:
        result = compose_trimesh(plan, paths, out_glb, out_stl, fuse)
    for e in plan["parts"]:  # the plan as written: every matrix includes the move onto the floor
        e["matrix"][1][3] += result.get("floor_mm", 0.0)
    record = {**plan, "files": [str(p) for p in paths], "outputs": {"glb": str(out_glb), "stl": str(out_stl) if out_stl else None},
              "fused": fuse, "result": result}
    (out / f"{stem}.plan.json").write_text(json.dumps(record, indent=1) + "\n")
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kit", type=Path, required=True)
    ap.add_argument("--files", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--variants", nargs="*", default=[], help="kind=variant ...")
    ap.add_argument("--preset", help="the torso preset, the shape (decision 131); the default otherwise")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pose")
    g.add_argument("--all-poses", action="store_true")
    ap.add_argument("--fuse", action="store_true")
    ap.add_argument("--modify", type=Path)
    ap.add_argument("--engine", choices=["auto", "bpy", "trimesh"], default="auto")
    a = ap.parse_args()
    kit = json.loads(a.kit.read_text())
    variants = dict(v.split("=", 1) for v in a.variants)
    poses = [p["pose_id"] for p in kit["poses"]] if a.all_poses else [a.pose]
    for pose in poses:
        r = compose(kit, a.files, a.out, variants, pose, a.fuse, a.modify, a.engine, preset_id=a.preset)
        print(f"{r['breed_id']} {r['pose_id']}: {r['result']} -> {r['outputs']['glb']}")


if __name__ == "__main__":
    main()
