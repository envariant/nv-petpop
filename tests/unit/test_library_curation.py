"""M8 curation maths (BRIEF Section 16): delta extraction and the QC metrics, on figurines from the real pipeline
(the fixture pack's wrapped meshes)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from backend.core.paths import ROOT
from petpop_library import qc
from petpop_library.deltas import REGIONS, compose
from petpop_library.extract import extract, normalised_weights
from petpop_library.meshkit import load_base

PETS = ROOT / "fixtures" / "pets"


def wrapped(pet: str) -> tuple[str, np.ndarray]:
    species = json.loads((PETS / pet / "spec.json").read_text())["species"]
    rows = [line.split()[1:4] for line in (PETS / pet / "figure_uv.obj").read_text().splitlines() if line.startswith("v ")]
    return species, np.array(rows, dtype=np.float64)


@pytest.mark.parametrize("pet", ["biscuit", "luna"])
def test_family_plus_parts_recompose_the_figurine(pet):
    species, co = wrapped(pet)
    base = load_base(species)
    ps = extract(base, co)
    assert set(ps.parts) == set(REGIONS)
    assert np.abs(ps.compose(base) - co).max() < 0.01  # mm: float16 storage only
    # The kiosk composes the same arrays the same way.
    assert np.allclose(compose(base, ps.family, list(ps.parts.values())), ps.compose(base))
    # Each part lives in its region: outside it, the offsets are zero.
    for region, d in ps.parts.items():
        outside = normalised_weights(base)[region] == 0
        assert np.abs(d[outside]).max() == 0, region


def test_weights_never_double_count():
    base = load_base("dog")
    total = sum(normalised_weights(base).values())
    assert total.max() <= 1.0 + 1e-9


def test_symmetric_delta_has_no_symmetry_error():
    base = load_base("dog")
    d = base.morph_deltas[0].astype(np.float64)  # shape keys are authored symmetric
    w = np.ones(len(base.co))
    assert qc.symmetry_error(base, d, w) < 0.05
    lopsided = d.copy()
    lopsided[base.co[:, 0] > 0] += [0.0, 0.0, 5.0]
    assert qc.symmetry_error(base, lopsided, w) > 2.0


def test_base_mesh_has_no_new_crossings_and_a_fold_is_found():
    base = load_base("dog")
    assert not qc.self_intersecting_triangles(base, base.co.astype(np.float64)).any()
    folded = base.co.astype(np.float64).copy()
    head = base.group("muzzle") > 0.5
    centre = folded[head].mean(axis=0)
    folded[head] = centre + (folded[head] - centre) * np.array([1.0, -1.0, 1.0])  # turn the muzzle inside out
    assert qc.self_intersecting_triangles(base, folded).sum() > 0


def test_boundary_strain_grows_with_a_part_that_pulls_at_its_seam():
    base = load_base("dog")
    w = normalised_weights(base)["ears"]
    w_band = normalised_weights(base)["muzzle"]
    gentle = np.zeros_like(base.co, dtype=np.float64)
    gentle[:, 1] = 0.2 * w_band
    harsh = np.zeros_like(gentle)
    harsh[:, 1] = 15.0 * w_band
    assert qc.boundary_strain(base, gentle, w_band) < qc.boundary_strain(base, harsh, w_band)
    assert qc.boundary_strain(base, np.zeros_like(gentle), w) == 0.0


def test_qc_passes_clean_figurines_and_rejects_folded_regions():
    """Calibration on the fixture pack: clean pets pass every region; a folded brachy muzzle is auto-rejected."""
    species, co = wrapped("biscuit")
    base = load_base(species)
    report = qc.evaluate(base, extract(base, co))
    assert report["passed_regions"] == [*REGIONS, "family"]
    species, co = wrapped("gus")
    base = load_base(species)
    report = qc.evaluate(base, extract(base, co))
    assert "muzzle" not in report["passed_regions"]
    assert any("self-intersecting" in r for r in report["regions"]["muzzle"]["reasons"])
    bad_wrap = qc.evaluate(base, extract(base, co), wrap_valid=False)
    assert bad_wrap["passed_regions"] == []


def test_pets_exist():
    assert all((PETS / p / "figure_uv.obj").exists() for p in ("biscuit", "luna", "gus"))
    assert Path(PETS).is_dir()
