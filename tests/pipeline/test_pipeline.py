"""Pipeline behaviour in mock mode (BRIEF Sections 5, 6, 11, 12): fallbacks by fault injection, resume from
the store, determinism, and one topology/UV layout per species. Uses the 'test' quality profile."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from backend.api.store import LocalStore
from backend.core.config import settings
from petpop_core.schemas import manifest_errors
from petpop_core.spec import default_spec
from backend.worker.local_run import run_pipeline
from backend.worker.runner import JobFailed


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("PETPOP_MOCK_SPEED", "0")
    monkeypatch.setenv("PETPOP_QUALITY", "test")
    monkeypatch.setenv("PETPOP_VAR", str(tmp_path / "var"))
    monkeypatch.delenv("PETPOP_FAIL_STAGE", raising=False)


def run(store, job_id, spec):
    return run_pipeline(job_id, spec, store, settings()).data


def sha(store, key):
    return hashlib.sha256(store.get(key)).hexdigest()


def test_full_run_outputs_and_metrics(tmp_path):
    store = LocalStore(tmp_path / "s")
    spec = default_spec("cat", "maine_coon", seed=77, pet_name="Bear")
    spec["accessories"] = [{"type": "hat", "colour_hex": "#F2C230"}]
    m = run(store, "j_full", spec)
    assert manifest_errors(m) == []
    assert m["fallback"] == "none" and m["fidelity"] == "high"
    names = {f["name"] for f in m["files"]}
    for n in ("spec.json", "concept.png", "views/front.png", "shape.glb", "figure_mesh.npz", "albedo.png", "parts.png",
              "figure_uv.obj", "figure.stl", "figure.3mf", "paint_mask.png", "figure.glb", "thumbnail.png"):
        assert n in names, n
    met = m["metrics"]
    assert met["print_watertight"] and met["segmentation_valid"] and met["iou_mean"] >= 0.85
    assert met["mesh_id"].startswith("m_") and met["segmentation_version"] == "seg-1"
    assert [s["stage"] for s in m["stages"]] == ["A", "control", "B", "C", "D", "E", "F"]


def test_fault_injection_D_ships_parametric_figure(tmp_path, monkeypatch):
    monkeypatch.setenv("PETPOP_FAIL_STAGE", "D")
    store = LocalStore(tmp_path / "s")
    m = run(store, "j_d", default_spec("dog", "beagle", seed=5))
    assert m["fallback"] == "parametric"
    d = next(s for s in m["stages"] if s["stage"] == "D")
    assert d["status"] == "fallback" and d["attempts"] == 3  # multi-view twice, then single view
    assert "shape.glb" not in {f["name"] for f in m["files"]}
    assert m["metrics"]["print_watertight"]


def test_fault_injection_E_ships_unwrapped(tmp_path, monkeypatch):
    monkeypatch.setenv("PETPOP_FAIL_STAGE", "E")
    m = run(LocalStore(tmp_path / "s"), "j_e", default_spec("dog", "pug", seed=6))
    assert m["fallback"] == "unwrapped" and m["metrics"]["segmentation_valid"] is False


@pytest.mark.parametrize("stage", ["B", "F"])
def test_fault_injection_fails_job_with_stage_name(tmp_path, monkeypatch, stage):
    monkeypatch.setenv("PETPOP_FAIL_STAGE", stage)
    with pytest.raises(JobFailed) as exc:
        run(LocalStore(tmp_path / "s"), "j_fail", default_spec("cat", "siamese", seed=8))
    assert exc.value.stage == stage


def test_resume_from_store_and_determinism(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / "s")
    spec = default_spec("dog", "corgi_pembroke", seed=918273, pet_name="Biscuit")
    monkeypatch.setenv("PETPOP_FAIL_STAGE", "F")
    with pytest.raises(JobFailed):
        run(store, "j_r", spec)
    partial = json.loads(store.get("jobs/j_r/manifest.json"))
    done_before = {s["stage"]: s["ms"] for s in partial["stages"] if s["status"] == "ok"}
    assert set(done_before) == {"A", "control", "B", "C", "D", "E"}
    monkeypatch.delenv("PETPOP_FAIL_STAGE")
    m = run(store, "j_r", spec)  # retry restarts at F
    assert {s["stage"]: s["ms"] for s in m["stages"] if s["stage"] in done_before} == done_before
    # Same spec + seed on a fresh store: identical geometry and print layout.
    other = LocalStore(tmp_path / "s2")
    run(other, "j_r2", spec)
    for name in ("figure_uv.obj", "albedo.png", "parts.png"):
        assert sha(store, f"jobs/j_r/{name}") == sha(other, f"jobs/j_r2/{name}"), name
    assert m["metrics"]["mesh_id"] == json.loads(other.get("jobs/j_r2/manifest.json"))["metrics"]["mesh_id"]


def test_each_breed_keeps_its_own_mesh_labelled_to_one_schema(tmp_path):
    """Decision 116: different breeds get different meshes (no shared topology), every one segmented to the
    species schema, with its own UVs, a part label per texel and landmarks inside their parts."""
    from petpop_library import figure

    store = LocalStore(tmp_path / "s")
    a = run(store, "j_a", default_spec("dog", "dachshund", seed=1))
    b = run(store, "j_b", default_spec("dog", "samoyed", seed=2))
    assert a["metrics"]["mesh_id"] != b["metrics"]["mesh_id"]
    assert a["metrics"]["topology_hash"] != b["metrics"]["topology_hash"]
    assert a["metrics"]["segmentation_version"] == b["metrics"]["segmentation_version"] == "seg-1"
    sch = figure.schema("dog")
    for job in ("j_a", "j_b"):
        mesh = figure.load(store.get(f"jobs/{job}/figure_mesh.npz"))
        assert mesh.source == "generated" and sorted(mesh.group_names) == sorted(p["name"] for p in sch["parts"])
        labels = mesh.group_names
        dominant = mesh.groups.argmax(axis=0)
        for lm, allowed in sch["landmarks"].items():
            assert labels[dominant[mesh.landmarks[lm]]] in allowed, (job, lm)
        import io

        from PIL import Image

        parts = np.asarray(Image.open(io.BytesIO(store.get(f"jobs/{job}/parts.png"))))
        assert set(np.unique(parts)) - {0} == set(range(1, len(sch["parts"]) + 1)), job

    def layout(job):
        lines = store.get(f"jobs/{job}/figure_uv.obj").decode().splitlines()
        return [ln for ln in lines if ln.startswith(("vt ", "f "))]

    assert layout("j_a") != layout("j_b")  # each figurine ships its own mesh and UVs to the painter
