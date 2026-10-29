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


def test_fixture_topology_identical_per_species():
    index = json.loads((FIXTURES / "index.json").read_text())["pets"]
    by_species: dict[str, set] = {}
    for pet in index:
        m = json.loads((FIXTURES / pet["id"] / "manifest.json").read_text())["metrics"]
        by_species.setdefault(pet["species"], set()).add((m["topology_hash"], m["uv_layout_hash"]))
    assert all(len(v) == 1 for v in by_species.values())
