"""scripts/library_coverage.py: the coverage half of gate 9 (docs/HANDOFF-M9.md)."""
import importlib.util

from backend.core.paths import ROOT
from petpop_library import release

spec = importlib.util.spec_from_file_location("library_coverage", ROOT / "scripts/library_coverage.py")
cov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cov)


def test_proxy_release_is_not_coverage():
    manifest, _ = release.read((ROOT / "fixtures/library/release-dog-1.tar").read_bytes())
    lines, ok = cov.report(manifest)
    assert not ok and any("only on the proxy template" in ln for ln in lines)
    assert lines[-1].endswith("yes")  # the proxy release has every pattern layer


def test_a_generated_mesh_shared_by_two_breeds_covers_them():
    manifest, _ = release.read((ROOT / "fixtures/library/release-dog-1.tar").read_bytes())
    mesh = dict(manifest["meshes"][0], id="m_0000000000000001", source="generated", name="Hound", breeds=["beagle", "dachshund"])
    fam = dict(manifest["families"][0], id="family_hound", mesh_id=mesh["id"], breeds=["beagle", "dachshund"])
    lines, _ = cov.report({**manifest, "meshes": [*manifest["meshes"], mesh], "families": [*manifest["families"], fam]})
    assert "shared mesh Hound: beagle, dachshund" in "\n".join(lines)
    assert any(ln.startswith("breeds covered: 3/") and "2 on a generated mesh" in ln for ln in lines)  # and the labrador kit


def test_a_kit_covers_its_breed_and_its_texture_needs_its_masks():
    """A breed with a part kit is covered (decisions 127 to 139); each marking its default texture names needs a mask
    on one of its parts."""
    manifest, _ = release.read((ROOT / "fixtures/library/release-dog-1.tar").read_bytes())
    lines, ok, data = cov.summary(manifest)
    assert data["kits"] == ["labrador"] and "labrador" not in data["proxy_only"] and not data["kit_mask_gaps"]
    kit = manifest["kits"][0]
    named = {**kit, "texture": {**kit["texture"], "markings": [*kit["texture"]["markings"], "dark_mask"]}}
    lines, ok, data = cov.summary({**manifest, "kits": [named]})
    assert not ok and data["kit_mask_gaps"] == {"labrador": ["dark_mask"]}
    assert "  kit labrador: no mask for dark_mask (named by its default texture)" in lines


def test_a_library_of_kits_needs_no_pattern_layers():
    manifest, _ = release.read((ROOT / "fixtures/library/release-dog-1.tar").read_bytes())
    kit = manifest["kits"][0]
    breeds = [b["id"] for b in cov.all_breeds("dog") if b["id"] != "mixed"]
    kits = [{**kit, "breed_id": b} for b in breeds]
    lines, ok, data = cov.summary({**manifest, "kits": kits, "families": [], "pattern_layers": []})
    assert ok and data["complete"] and len(data["kits"]) == len(breeds), lines
