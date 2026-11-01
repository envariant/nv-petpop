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
    assert any(ln.startswith("breeds on a generated mesh: 2/") for ln in lines)
