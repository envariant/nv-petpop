"""Drafting a figure from parts exported one at a time (decision 128, scripts/draft_parts.py): every part fitted to
its size guess about the centre line, every joint guessed from shape, every leg on the floor, a figure per variant."""
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


@pytest.fixture
def exports(tmp_path):
    """A corgi's parts as a generator returns them: each at its own scale, about its own origin."""
    rng = np.random.default_rng(7)
    d = tmp_path / "in"
    d.mkdir()
    for (name, ext), scale in zip(PEBBLES.items(), [1.0, 0.5, 2.0, 300.0, 1.0, 0.1]):
        m = trimesh.creation.icosphere(subdivisions=2)
        m.apply_scale(np.array(ext) / 2 * scale)
        m.apply_translation(rng.normal(0, scale, 3))
        m.export(d / f"corgi_pembroke__{name}.glb")
    return d


def test_draft(exports, tmp_path):
    out = tmp_path / "draft"
    r = D.draft(sorted(exports.glob("*.glb")), out, engine="trimesh")
    assert r["breed_id"] == "corgi_pembroke" and len(r["figures"]) == 2  # the defaults, and the sitting hind leg
    assert sum("scaled" in n for n in r["notes"]) == 6
    kit = json.loads(Path(r["kit"]).read_text())
    assert kit["version"] == 0 and kit["draft"] and kit["defaults"]["hind_leg"] == "default"
    by = {(p["kind"], p["variant"]): p for p in kit["parts"]}
    assert by[("torso", "default")]["guess"]["front_left"]["method"] == "box"  # from the torso's shape, not the leg's origin
    assert by[("hind_leg", "sitting")]["guess"]["joint"]["method"].endswith("grounded")
    for name in ("torso", "head", "front_leg", "hind_leg", "hind_leg__sitting", "tail"):
        m = trimesh.load(out / "parts" / f"corgi_pembroke__{name}.glb", force="mesh")
        kind, _, variant = name.partition("__")
        assert m.extents.max() == pytest.approx(max(S.target("dog", "corgi_pembroke", kind, variant or "default")[0]), rel=1e-3)
    for f in r["figures"]:
        plan = json.loads(Path(f["glb"]).with_suffix(".plan.json").read_text())
        fig = trimesh.load(f["glb"], force="mesh")
        assert abs(fig.bounds.mean(axis=0)[0]) < 1.0  # on the centre line
        assert 60 < fig.extents[1] < 100 and fig.extents[0] < fig.extents[2]  # about the mandrel's height, longer than wide
        for e, path in zip(plan["parts"], plan["files"]):
            if e["kind"].endswith("_leg"):
                v = trimesh.load(path, force="mesh").vertices
                placed = np.c_[v, np.ones(len(v))] @ np.asarray(e["matrix"]).T
                assert placed[:, 1].min() == pytest.approx(0.0, abs=0.5), (f["glb"], e["slot"])  # on the floor
