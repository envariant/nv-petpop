"""Contract 1, the library release (BRIEF Section 17), and Contract 2, the composition (Section 16).

The release is the only thing the kiosk reads from Studio: a signed, versioned `release-<species>-<n>.tar` whose
manifest satisfies data/schema/release.schema.json and whose every file is listed with its sha256. This test holds
any bundle to that contract: the committed proxy releases now, the bundles Studio packs in M8. A composition is the
only input to a library export; every id in it must exist in the release it names.
"""
from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.core.paths import ROOT
from petpop_core.schemas import composition_errors
from petpop_library import figure, release
from petpop_library.basebin import read_base_bin
from petpop_library.composition import check_ids, errors, sample
from petpop_library.deltas import REGIONS, decode

BUNDLES = sorted((ROOT / "fixtures" / "library").glob("release-*.tar"))


def bundles() -> list[Path]:
    return BUNDLES


@pytest.fixture(params=bundles(), ids=lambda p: p.stem)
def bundle(request) -> tuple[Path, dict, dict]:
    path = request.param
    manifest, files = release.read(path.read_bytes())
    return path, manifest, files


def test_both_species_have_a_release():
    assert {p.name.split("-")[1] for p in BUNDLES} == {"dog", "cat"}


def test_bundle_is_signed_schema_valid_and_complete(bundle):
    path, manifest, files = bundle
    assert release.release_errors(manifest) == []
    assert path.name == f"{manifest['release_version']}.tar"
    assert manifest["release_version"] == f"release-{manifest['species']}-{manifest['number']}"
    assert {f["path"] for f in manifest["files"]} == set(files)
    with tarfile.open(path) as tar:
        names = set(tar.getnames())
    assert {"manifest.json", "manifest.sig"} <= names  # signature beside the manifest, nothing unlisted
    assert names - {"manifest.json", "manifest.sig"} == set(files)


def test_every_mesh_is_labelled_to_the_schema_and_lists_who_shares_it(bundle):
    """Decision 118: each release mesh is its own (content-hashed) mesh on the species' segmentation schema; its
    viewer binary, info and figure package agree; and it lists every breed of every family built on it."""
    _, manifest, files = bundle
    sch = figure.schema(manifest["species"])
    assert manifest["segmentation_version"] == sch["schema_version"]
    for me in manifest["meshes"]:
        mesh = figure.load(files[me["package"]])
        assert mesh.mesh_id == me["id"] and mesh.schema_version == manifest["segmentation_version"]
        assert sorted(mesh.group_names) == sorted(p["name"] for p in sch["parts"])
        assert sorted(mesh.landmarks) == sorted(sch["landmarks"])
        bb = read_base_bin(files[me["bin"]])
        assert np.allclose(bb["co"], mesh.co, atol=1e-4) and (bb["tri"] == mesh.tri_verts).all()
        info = json.loads(files[me["info"]])
        assert info["mesh_id"] == me["id"] and info["topology"] == mesh.topology_hash()
        sharing = {b for f in manifest["families"] if f["mesh_id"] == me["id"] for b in f["breeds"]}
        assert sharing <= set(me["breeds"])
        size = me["atlas"]["size"]
        for f in me["atlas"]["mask_files"]:
            assert Image.open(io.BytesIO(files[f])).size == (size, size)
        channels = 4 * len(me["atlas"]["mask_files"])
        assert {p["channel"] for p in manifest["pattern_layers"]} | {me["atlas"]["channels"]["eye"],
                                                                     me["atlas"]["channels"]["nose"]} <= set(range(channels))


def test_every_item_resolves(bundle):
    _, manifest, files = bundle
    meshes = {me["id"]: figure.load(files[me["package"]]) for me in manifest["meshes"]}
    ids = [it["id"] for kind in ("families", "region_deltas", "shell_parts", "pattern_layers") for it in manifest[kind]]
    assert len(ids) == len(set(ids)), "ids are unique across the release"
    deltas = {d["id"]: d for d in manifest["region_deltas"]}
    for fam in manifest["families"]:
        n = len(meshes[fam["mesh_id"]].co)
        if fam["delta"]:
            assert np.isfinite(decode(files[fam["delta"]], n)).all()
        for region, pid in fam["default_parts"].items():
            assert deltas[pid]["region"] == region, (fam["id"], region)
            assert deltas[pid]["mesh_id"] == fam["mesh_id"], "a family's default parts are on its own mesh"
        assert fam["thumbnail"] in files
    for d in manifest["region_deltas"]:
        assert d["region"] in REGIONS
        assert np.abs(decode(files[d["delta"]], len(meshes[d["mesh_id"]].co))).max() < 100.0  # mm, float16 range kept sane
    for sh in manifest["shell_parts"]:
        assert files[sh["mesh"]][:4] == b"glTF" and sh["socket"] in ("neck", "head", "face")
    for p in manifest["pattern_layers"]:
        cov = p["coverage"]
        assert 0 <= cov["min"] <= cov["default"] <= cov["max"] <= 1


def test_tampered_or_foreign_bundles_are_refused(bundle):
    path, manifest, files = bundle
    raw = path.read_bytes()
    with pytest.raises(release.ReleaseError, match="signature"):
        release.read(raw, key=b"not-the-release-key")
    # A changed file breaks its sha256; a changed manifest breaks the signature.
    victim = next(f["path"] for f in manifest["files"] if f["path"].endswith(".f16") and any(files[f["path"]]))
    altered = dict(files)
    altered[victim] = bytes([files[victim][0] ^ 0xFF]) + files[victim][1:]
    forged = _repack(raw, altered)
    with pytest.raises(release.ReleaseError, match="sha256"):
        release.read(forged)
    with pytest.raises(release.ReleaseError):
        release.read(b"not a tar")


def _repack(raw: bytes, files: dict[str, bytes]) -> bytes:
    """The same bundle with different file bytes but the original manifest and signature."""
    src = tarfile.open(fileobj=io.BytesIO(raw))
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        for member in src.getmembers():
            data = files.get(member.name) or src.extractfile(member).read()
            info = tarfile.TarInfo(member.name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


def test_a_release_loads_on_a_clean_kiosk(tmp_path):
    """Contract 1 end to end: a fresh store installs each species' release and serves it."""
    store = release.ReleaseStore(tmp_path / "releases", segmentation={sp: figure.schema(sp)["schema_version"] for sp in ("dog", "cat")})
    assert store.active("dog") is None
    installed = store.install_newer(BUNDLES)
    assert sorted(installed) == sorted(p.stem for p in BUNDLES)
    for path in BUNDLES:
        manifest, files = release.read(path.read_bytes())
        active = store.active(manifest["species"])
        assert active.version == manifest["release_version"]
        assert all(active.file(p) == data for p, data in files.items())


def test_compositions_name_ids_that_exist(bundle):
    _, manifest, _ = bundle
    comp = sample(manifest, layers=10, stamps=20)
    assert composition_errors(comp) == [] and errors(manifest, comp) == []
    bad = json.loads(json.dumps(comp))
    region, pid = next(iter(bad["parts"].items()))
    other = next(r for r in bad["parts"] if r != region)
    bad["parts"][other] = pid  # a part in the wrong region
    bad["layers"][0]["pattern_id"] = "pattern_nope"
    bad["shells"] = [{"part_id": "shell_nope", "colour": "#FFFFFF"}]
    errs = check_ids(manifest, bad)
    assert any(e.startswith(f"parts.{other}") for e in errs)
    assert check_ids(manifest, dict(comp, mesh_id="m_0000000000000000")) != []  # a mesh the release does not hold
    assert "layers: unknown pattern_nope" in errs and "shells: unknown shell_nope" in errs
    assert composition_errors(dict(comp, stamps=[{"p": [0, 0, 0], "r": 50, "colour": "#000000"}]))  # radius out of range
    assert composition_errors(dict(comp, layers=comp["layers"] * 2))  # more than 10 layers
