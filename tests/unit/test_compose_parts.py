"""Composing a figure from a part kit (decision 127): the plan (what goes where), the trimesh stand-in, and Blender
(bpy, when PETPOP_BPY_PYTHON has it): the same figure, a voxel fuse into one watertight print, and the modify hook."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

from petpop_library import parts as P

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from compose_parts import compose  # noqa: E402

FILES = ROOT / "fixtures" / "parts" / "dog"
BPY = os.environ.get("PETPOP_BPY_PYTHON", "/opt/bpy/bin/python")


def kit() -> dict:
    """The dog proxy kit, committed: the first-guess rig (fixtures/parts/golden.json) and two poses."""
    g = json.loads((ROOT / "fixtures" / "parts" / "golden.json").read_text())
    parts = [{"part_id": f"pt_{p['kind']}_{p['variant']}", "kind": p["kind"], "variant": p["variant"], "label": p["variant"],
              "mesh": {"file": p["file"], "sha256": "", "tris": p["tris"]},
              **({"attachments": p["attachments"]} if p["kind"] == "torso" else {"joint": p["joint"]}),
              **({"limits": p["limits"]} if p["kind"] == "head" else {})} for p in g["parts"]]
    return {"kit_version": "kit-1", "species": "dog", "breed_id": "mixed", "version": 1, "parts": parts,
            "defaults": {k: "default" for k in P.KINDS}, "default_pose": "standing",
            "poses": [{"pose_id": "standing", "label": "Standing"},
                      {"pose_id": "curious", "label": "Curious", "legs": {"front_left": 1, "front_right": 1}, "head": {"yaw": 20}}]}


def load(path: Path) -> trimesh.Trimesh:
    return trimesh.load(path, force="mesh", process=False)


def test_the_plan_places_seven_instances_and_mirrors_the_right_legs():
    plan = P.compose_plan(kit(), {"torso": "slim"}, "curious")
    assert [e["slot"] for e in plan["parts"]] == ["torso", *P.SLOTS]
    assert plan["variants"]["torso"] == "slim" and plan["pose_id"] == "curious"
    dets = {e["slot"]: np.linalg.det(np.asarray(e["matrix"])[:3, :3]) for e in plan["parts"]}
    assert dets["front_right"] < 0 < dets["front_left"]
    with pytest.raises(ValueError, match="no torso huge"):
        P.compose_plan(kit(), {"torso": "huge"})
    with pytest.raises(ValueError, match="allowed list"):
        P.compose_plan(kit(), pose_id="dancing")


def test_trimesh_composes_the_figure_where_it_was_cut(tmp_path):
    r = compose(kit(), FILES, tmp_path, engine="trimesh")
    fig = load(Path(r["outputs"]["glb"]))
    n = {k: len(load(FILES / f"mixed__{k}.glb").vertices) for k in P.KINDS}
    assert len(fig.vertices) == n["torso"] + n["head"] + n["tail"] + 2 * (n["front_leg"] + n["hind_leg"])
    assert fig.bounds[0][0] == pytest.approx(-fig.bounds[1][0], abs=0.5)  # left and right legs: symmetric
    assert Path(r["outputs"]["stl"]).is_file() and Path(tmp_path / "mixed__standing.plan.json").is_file()


@pytest.mark.skipif(not Path(BPY).exists(), reason="no bpy (PETPOP_BPY_PYTHON)")
def test_blender_composes_the_same_figure_fuses_it_and_runs_the_modify_hook(tmp_path):
    ref = load(Path(compose(kit(), FILES, tmp_path / "t", engine="trimesh")["outputs"]["glb"]))
    r = compose(kit(), FILES, tmp_path / "b", engine="bpy")
    fig = load(Path(r["outputs"]["glb"]))
    assert r["result"]["engine"] == "bpy"
    assert np.allclose(fig.bounds, ref.bounds, atol=0.05)  # the same figure, through Blender's Y-up/Z-up round trip
    fused = compose(kit(), FILES, tmp_path / "f", pose_id="curious", fuse=True, engine="bpy")
    stl = trimesh.load(fused["outputs"]["stl"], force="mesh")
    assert stl.is_watertight  # one closed surface: no walls inside the joints
    hook = tmp_path / "edits.py"
    hook.write_text("def modify(obj, job):\n    obj.data.transform(__import__('mathutils').Matrix.Translation((0, 0, 100)))\n")
    moved = load(Path(compose(kit(), FILES, tmp_path / "m", modify=hook, engine="bpy")["outputs"]["glb"]))
    assert moved.bounds[0][1] == pytest.approx(ref.bounds[0][1] + 100, abs=0.05)  # Blender +Z is glTF +Y
