"""Guessed part sizes (decision 128): the breed database's proportions read right, the table is current, and an
uploaded part is scaled to its guess with its texture kept (a mirrored right leg too)."""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from backend.api import part_library as L
from petpop_library import part_sizes as S
from petpop_library import parts as P

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/breeds/dog_pebbles_simple.json"


def test_phrases():
    assert S.torso_ratio("a single horizontal lozenge, about 1.35 times as long as it is tall and broad") == 1.35
    assert S.torso_ratio("about twice as long as it is tall and moderately full") == 2.0
    assert S.torso_ratio("about three times as long as it is tall") == 3.0
    assert S.torso_ratio("about as long as it is tall and fairly narrow") == 1.0
    assert S.torso_ratio("only slightly longer than it is tall and broad and full") == 1.1
    assert S.torso_width("only slightly longer than it is tall and broad and full from side to side") == 0.9
    assert S.torso_width("about 1.3 times as long as it is tall and very broad and heavy from side to side") == 1.05
    assert S.leg_ratio("a thick, stout tube, barely taller than it is wide") == 1.15
    assert S.leg_ratio("a slender tube, about three times as tall as it is wide") == 3.0
    assert S.leg_ratio("a squat, rounded triangle, about as tall as it is wide") == 1.0
    assert S.leg_ratio("a rounded triangle, about one and a half times as tall as it is wide") == 1.5
    assert S.leg_ratio("about two and a half times as tall as it is wide") == 2.5


def test_table_is_current_and_sane():
    db = json.loads(DB.read_text())
    table = json.loads(S.table_path("dog").read_text())
    fresh = S.build_table(db)
    assert {k: v["parts"] for k, v in table["breeds"].items()} == {k: v["parts"] for k, v in fresh["breeds"].items()}, \
        "data/breeds/dog_part_sizes.json is stale: python scripts/guess_part_sizes.py"
    assert len(table["breeds"]) == len(db["breeds"])
    for b in table["breeds"].values():
        assert b["figure_mm"]["height"] <= S.FIGURE_MM + 0.1 and b["figure_mm"]["length"] <= S.LENGTH_MM + 0.1
        for p in b["parts"].values():
            assert all(x > 0 for x in p["size_mm"])
    corgi, dane = table["breeds"]["corgi_pembroke"]["parts"], table["breeds"]["great_dane"]["parts"]
    tx, ty, tz = corgi["torso/default"]["size_mm"]
    assert 1.8 < tz / ty < 2.2  # "about twice as long as it is tall"
    fx, fy, _ = corgi["front_leg/default"]["size_mm"]
    assert 1.0 < fy / fx < 1.3  # "barely taller than it is wide"
    assert dane["front_leg/default"]["size_mm"][1] > 1.5 * fy  # long legs against short ones
    # the size class shows in the head: a chihuahua's head is bigger against its torso than a mastiff's
    rel = lambda b: table["breeds"][b]["parts"]["head/default"]["size_mm"][0] / table["breeds"][b]["parts"]["torso/default"]["size_mm"][1]  # noqa: E731
    assert rel("chihuahua") > rel("mastiff")


def test_target_falls_back():
    assert S.target("dog", "corgi_pembroke", "hind_leg", "sitting")[1] == "corgi_pembroke size guess"
    size, src = S.target("dog", "corgi_pembroke", "torso", "stocky")  # a variant without a row: its kind's default
    assert size == S.table("dog")["breeds"]["corgi_pembroke"]["parts"]["torso/default"]["size_mm"]
    assert S.target("dog", "no_such_breed", "head", "default")[1].startswith("median")
    assert S.target("cat", "anything", "head", "default") is None  # no cat table yet


def test_fit_scales_every_part_to_its_guess():
    v = np.array([[0, 0, 0], [0.9, 1.0, 0.9]], float)
    out, s, notes = S.fit(v, [17.0, 19.0, 17.0])
    assert s == pytest.approx(19.0) and np.ptp(out[:, 1]) == pytest.approx(19.0) and not notes
    assert S.fit(v * 40, [17.0, 19.0, 17.0])[1] == pytest.approx(19.0 / 40)  # exported in mm, at its own size: still fitted
    assert "thinnest side" in S.fit(v * [0.2, 1, 0.2], [17.0, 19.0, 17.0])[2][0]
    assert S.normalise("dog", "corgi_pembroke", "head", "default", v, scale=False)[0] is None  # in proportion already
    assert "no size guess" in S.normalise("cat", "x", "head", "default", v)[2][0]


def test_names():
    assert P.parse_name("corgi_pembroke__fore_leg.glb") == ("corgi_pembroke", "front_leg", "default")
    assert P.parse_name("corgi_pembroke__hind_leg_sitting.glb") == ("corgi_pembroke", "hind_leg", "sitting")
    assert P.parse_name("corgi_pembroke__hind_leg_sitting__fluffy.glb") == ("corgi_pembroke", "hind_leg", "sitting_fluffy")
    assert P.parse_name("corgi_pembroke__hind_leg__long.glb") == ("corgi_pembroke", "hind_leg", "long")
    assert P.parse_name("corgi_pembroke__paw.glb") is None


def textured_part(centre_x: float) -> bytes:
    """A unit-sized textured box (what a generator returns), off to one side."""
    box = trimesh.creation.box(extents=[0.4, 1.0, 0.4])
    box.apply_translation([centre_x, 0, 0])
    uv = np.c_[box.vertices[:, 0] + 0.5, box.vertices[:, 1] + 0.5]
    tex = np.zeros((4, 4, 3), np.uint8)
    tex[..., 0] = 200
    from PIL import Image  # noqa: PLC0415

    box.visual = trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.PBRMaterial(baseColorTexture=Image.fromarray(tex)))
    return trimesh.Scene([box]).export(file_type="glb")


@pytest.mark.parametrize("scale", [True, False])
def test_normalise_keeps_texture(scale):
    """Scaled (a part exported on its own, off its origin: still a left leg) or not (a right leg split in place:
    mirrored), the texture and UVs come through and the outside stays out."""
    data = textured_part(-0.5)
    v, _ = L.read_glb(data)
    matrix, mirrored, notes = S.normalise("dog", "corgi_pembroke", "front_leg", "default", v, scale=scale)
    assert mirrored is (not scale)
    out = S.transform_glb(data, matrix)
    mesh = trimesh.load(io.BytesIO(out), file_type="glb").dump()[0]
    assert mesh.visual.material.baseColorTexture is not None and mesh.visual.uv.shape == (len(mesh.vertices), 2)
    assert mesh.volume > 0
    if scale:
        want = S.target("dog", "corgi_pembroke", "front_leg", "default")[0]
        assert np.ptp(mesh.vertices, axis=0).max() == pytest.approx(max(want), rel=1e-3) and any("scaled" in n for n in notes)
    else:
        assert mesh.vertices[:, 0].mean() > 0 and any("mirrored" in n for n in notes)  # moved to the pet's left
