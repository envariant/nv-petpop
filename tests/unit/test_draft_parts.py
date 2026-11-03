"""Drafting a figure from parts exported one at a time (decisions 128, 130; scripts/draft_parts.py): every part fitted
to its size guess about the centre line, joints guessed from shape, shared parts stretched to the breed, the sitting
pose once the sitting hind leg is there, every figure standing on the floor."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import draft_parts as D  # noqa: E402

from petpop_library import part_sizes as S  # noqa: E402

PEBBLES = {"torso": [0.8, 1.0, 2.0], "head": [0.9, 1.1, 1.0], "fore_leg": [0.9, 1.0, 0.9], "hind_leg": [0.5, 1.0, 1.0],
           "hind_leg_sitting": [0.55, 0.55, 1.0], "tail": [0.9, 1.0, 1.0]}


def pebble(path: Path, ext, scale: float, rng) -> None:
    """A part as a generator returns it: at its own scale, about its own origin."""
    m = trimesh.creation.icosphere(subdivisions=2)
    m.apply_scale(np.array(ext) / 2 * scale)
    m.apply_translation(rng.normal(0, scale, 3))
    m.export(path)


def check_figures(r: dict) -> None:
    for f in r["figures"]:
        plan = json.loads(Path(f["glb"]).with_suffix(".plan.json").read_text())
        fig = trimesh.load(f["glb"], force="mesh")
        assert abs(fig.bounds.mean(axis=0)[0]) < 1.0  # on the centre line
        assert fig.bounds[0][1] == pytest.approx(0.0, abs=1e-3)  # on the floor
        assert 50 < fig.extents[1] < 100 and fig.extents[0] < fig.extents[2]  # about the mandrel's height, longer than wide
        feet = []
        for e, path in zip(plan["parts"], plan["files"]):
            if e["kind"].endswith("_leg"):
                v = trimesh.load(path, force="mesh").vertices
                M = np.asarray(e["matrix"])
                feet.append(float((v @ M[:3, :3].T + M[:3, 3])[:, 1].min()))
        assert max(feet) < 3.0, (f["glb"], feet)  # every leg reaches the floor


def test_a_breed_of_its_own_parts(tmp_path):
    rng = np.random.default_rng(7)
    d = tmp_path / "in"
    d.mkdir()
    for (name, ext), scale in zip(PEBBLES.items(), [1.0, 0.5, 2.0, 300.0, 1.0, 0.1]):
        pebble(d / f"corgi_pembroke__{name}.glb", ext, scale, rng)
    r = D.draft(sorted(d.glob("*.glb")), tmp_path / "draft", engine="trimesh")
    assert r["breed_id"] == "corgi_pembroke" and not r["problems"]
    assert sum("scaled" in n for n in r["notes"]) == 6
    kit = json.loads(Path(r["kit"]).read_text())
    assert kit["version"] == 0 and kit["kit_version"] == "kit-2" and kit["default_pose"] == "sitting"
    assert [p["pose_id"] for p in kit["poses"]] == ["standing", "sitting"] and kit["poses"][1]["variants"] == {"hind_leg": "sitting_fold"}
    assert kit["texture"]["base"]["hex"] == "#C8763A"  # the breed's default texture, from the breed database
    by = {(p["kind"], p["variant"]): p for p in kit["parts"]}
    assert by[("head", "default")]["uv_layout"] == "dog-corgi_pembroke-head-1" and by[("tail", "default")]["uv_layout"] == "dog-tail-1"
    assert not any(p["shared"] for p in kit["parts"]) and all(p["stretch"] == [1.0, 1.0, 1.0] for p in kit["parts"])
    assert {f["pose"] for f in r["figures"]} == {"standing", "sitting"}
    check_figures(r)


def test_a_breed_on_the_shared_library(tmp_path):
    """Shared torsos, legs and tails (each fitted to the median of the breeds using it) and a corgi head: the corgi's
    kit takes its own part types, stretched to its proportions."""
    rng = np.random.default_rng(3)
    d = tmp_path / "in"
    d.mkdir()
    for name, ext, scale in [("torso__long_low", [0.8, 1.0, 2.0], 1.0), ("torso__standard", [0.8, 1.0, 1.35], 3.0),
                             ("fore_leg__paw", [0.9, 1.0, 0.9], 2.0), ("fore_leg__boot", [0.4, 1.0, 0.4], 0.5),
                             ("hind_leg__bean", [0.5, 1.0, 1.0], 300.0), ("hind_leg_sitting__sitting_fold", [0.55, 0.55, 1.0], 1.0),
                             ("tail__bob", [0.9, 1.0, 1.0], 0.1), ("tail__straight", [0.3, 0.35, 1.0], 1.0)]:
        pebble(d / f"shared__{name}.glb", ext, scale, rng)
    pebble(d / "corgi_pembroke__head.glb", [0.9, 1.1, 1.0], 0.5, rng)
    r = D.draft(sorted(d.glob("*.glb")), tmp_path / "draft", engine="trimesh")
    assert r["breed_id"] == "corgi_pembroke" and not r["problems"], r["problems"]
    kit = json.loads(Path(r["kit"]).read_text())
    assert kit["defaults"] == {"head": "default", "torso": "long_low", "front_leg": "paw", "hind_leg": "bean", "tail": "bob"}
    assert kit["allowed"]["front_leg"] == ["paw"] and kit["allowed"]["hind_leg"] == ["bean", "sitting_fold"]
    assert {(p["kind"], p["variant"]) for p in kit["parts"]} == {("head", "default"), ("torso", "long_low"), ("front_leg", "paw"),
                                                               ("hind_leg", "bean"), ("hind_leg", "sitting_fold"), ("tail", "bob")}
    by = {(p["kind"], p["variant"]): p for p in kit["parts"]}
    assert by[("front_leg", "paw")]["shared"] and not by[("head", "default")]["shared"]
    assert by[("front_leg", "paw")]["stretch"][1] < 0.8  # a corgi's legs are shorter than the median paw
    paw = trimesh.load(tmp_path / "draft" / "store" / by[("front_leg", "paw")]["mesh"]["file"], force="mesh")
    assert paw.extents.max() == pytest.approx(max(S.target("dog", S.SHARED, "front_leg", "paw")[0]), rel=1e-3)
    stretched = paw.extents * np.asarray(by[("front_leg", "paw")]["stretch"])
    assert stretched == pytest.approx(S.target("dog", "corgi_pembroke", "front_leg", "paw")[0], rel=0.01)  # the corgi's box
    assert [p["pose_id"] for p in kit["poses"]] == ["standing", "sitting"]
    check_figures(r)
