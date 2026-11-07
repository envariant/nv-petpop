"""Painting a figure of part kits (decisions 135, 139): masks sampled at texel centres, stamps that belong to a slot and
sit in its part's own frame, a tile of their own for slots with stamps, the mirror rule, extras and bespoke."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from petpop_core.schemas import composition_errors, spec_errors
from petpop_library import kit_figure as KF
from petpop_library.composition import check_ids, sample_kit, to_spec
from petpop_library.release import Release, read

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def rel():
    manifest, files = read((ROOT / "fixtures/library/release-dog-1.tar").read_bytes())

    class Mem(Release):
        def file(self, path: str) -> bytes:
            return files[path]

    return Mem(manifest, Path("."))


def comp_of(rel, **extra):
    return {**sample_kit(rel.manifest), **extra}


def test_masks_are_sampled_at_texel_centres():
    m = (np.arange(16, dtype=np.uint8).reshape(4, 4) * 16)
    assert KF.sample_mask(m, 4) == pytest.approx(m / 255.0)  # one texel per pixel: the mask itself
    half = KF.sample_mask(m, 2)  # texel centres fall between four pixels: their mean
    assert half[0, 0] == pytest.approx(m[0:2, 0:2].mean() / 255.0)
    assert KF.sample_mask(np.full((3, 5), 255, np.uint8), 7) == pytest.approx(np.ones((7, 7)))


def test_a_stamp_paints_its_slot_and_only_its_slot(rel):
    kit = rel.kit(sample_kit(rel.manifest)["breed_id"])
    plain = KF.slot_tiles("dog", kit, comp_of(rel), None, rel.file, rel.mask_file, 64)
    assert plain["front_left"][0] == plain["front_right"][0]  # a mirrored leg shares its left leg's tile
    head_file = plain["head"][0]
    v, _, _ = KF.read_part(rel.file(head_file))
    p = [round(float(x), 3) for x in v[np.argmax(v[:, 2])]]  # the nose, in the head's own frame
    comp = comp_of(rel, stamps=[{"slot": "head", "p": p, "r": 6.0, "colour": "#FFFFFF"},
                                {"slot": "front_right", "p": [0, 0, 0], "r": 20.0, "colour": "#00FF00"}])
    assert not composition_errors(comp)
    tiles = KF.slot_tiles("dog", kit, comp, None, rel.file, rel.mask_file, 64)
    assert tiles["head"][0] == f"{head_file}#head" and tiles["front_left"][0] != tiles["front_right"][0]
    changed = np.abs(tiles["head"][1].astype(int) - plain["head"][1].astype(int)).max(axis=2) > 0
    assert 0 < changed.mean() < 0.5  # a spot, not the whole head
    assert (tiles["head"][1][changed] == 255).all(axis=1).any()  # white at its centre
    assert (tiles["front_left"][1] == plain["front_left"][1]).all()  # the other leg keeps its tile
    assert (tiles["front_right"][1][..., 1] > tiles["front_right"][1][..., 0]).any()  # green on the right leg
    mesh, co, atlas = KF.build("dog", kit, comp, rel.file, rel.mask_file, tile=64)
    assert atlas.shape[0] * atlas.shape[1] >= 64 * 64 * len({k for k, _ in tiles.values()})


def test_the_mirror_rule():
    s = {"p": [3.0, 4.0, 5.0], "r": 2.0, "colour": "#000000"}
    assert KF.mirror_stamp("front_left", s) == ("front_right", s)
    assert KF.mirror_stamp("hind_right", s) == ("hind_left", s)
    assert KF.mirror_stamp("head", s) == ("head", {**s, "p": [-3.0, 4.0, 5.0]})


def test_extras_and_stamps_are_checked(rel):
    collar = next(s for s in rel.manifest["shell_parts"] if s["kind"] == "collar")
    ok = comp_of(rel, shells=[{"part_id": collar["id"], "colour": "#DD3333"}])
    assert not composition_errors(ok) and not check_ids(rel.manifest, ok)
    assert check_ids(rel.manifest, comp_of(rel, shells=[{"part_id": "shell_cape", "colour": "#DD3333"}])) == ["shells: unknown shell_cape"]
    assert composition_errors(comp_of(rel, stamps=[{"slot": "wing", "p": [0, 0, 0], "r": 2, "colour": "#000000"}]))


def test_bespoke_starts_from_a_figure_of_parts(rel):
    collar = next(s for s in rel.manifest["shell_parts"] if s["kind"] == "collar")
    comp = comp_of(rel, shells=[{"part_id": collar["id"], "colour": "#dd3333"}])
    comp["texture"] = {**comp["texture"], "base": {"name": None, "hex": "#aa5500"}, "secondary": {"name": None, "hex": "#ffffff"},
                       "pattern": "bicolour", "markings": ["white_chest", "saddle_patch"]}
    spec = to_spec(rel.manifest, comp, 7)
    assert not spec_errors(spec), spec_errors(spec)
    assert spec["colour"]["base"]["hex"] == "#AA5500" and spec["colour"]["secondary"]["hex"] == "#FFFFFF"
    assert spec["colour"]["pattern"] == "bicolour" and spec["colour"]["markings"] == ["white_chest"]  # those a PetSpec names
    assert [(a["type"], a["colour_hex"]) for a in spec["accessories"]] == [("collar", "#DD3333")]
    assert spec["eyes"]["hex"] == comp["eye_colour"]
