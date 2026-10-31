"""The fixture pack: 10 PetSpecs with mock outputs, all valid and self-consistent."""
import hashlib
import json

from backend.core.paths import FIXTURES
from petpop_core.schemas import manifest_errors, spec_errors


def test_fixture_pack():
    index = json.loads((FIXTURES / "index.json").read_text())["pets"]
    assert len(index) == 10
    assert {p["species"] for p in index} == {"dog", "cat"}
    for pet in index:
        d = FIXTURES / pet["id"]
        assert spec_errors(json.loads((d / "spec.json").read_text())) == [], pet["id"]
        manifest = json.loads((d / "manifest.json").read_text())
        assert manifest_errors(manifest) == [], pet["id"]
        kinds = {f["kind"] for f in manifest["files"]}
        assert {"spec", "concept", "view", "shape", "glb", "albedo", "uv_obj", "3mf", "stl", "mask"} <= kinds
        for f in manifest["files"]:
            data = (d / f["name"]).read_bytes()
            assert len(data) == f["bytes"] and hashlib.sha256(data).hexdigest() == f["sha256"], f["name"]
        assert manifest["metrics"]["print_watertight"] is True


def test_fixture_pets_have_own_meshes_on_one_schema():
    """Decision 116: every fixture pet is its own mesh (no shared topology), all labelled to one schema."""
    index = json.loads((FIXTURES / "index.json").read_text())["pets"]
    ids, schemas = set(), set()
    for pet in index:
        m = json.loads((FIXTURES / pet["id"] / "manifest.json").read_text())["metrics"]
        ids.add(m["mesh_id"])
        schemas.add(m["segmentation_version"])
        assert (FIXTURES / pet["id"] / "figure_mesh.npz").exists()
    assert len(ids) == len(index) and schemas == {"seg-1"}
