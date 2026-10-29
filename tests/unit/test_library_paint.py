"""Library painting (BRIEF Section 16): stamps cross UV seams correctly, coverage grows smoothly, the golden the
kiosk is checked against is current, and release bundles are signed and verified."""
from __future__ import annotations

import json

import numpy as np
import pytest

from backend.core.paths import ROOT
from petpop_library import paint, release
from petpop_library.atlas import texel_map, texel_positions
from petpop_library.meshkit import load_base

SIZE = 1024


def seam_vertex(base, near: str) -> int:
    """A vertex on a UV seam (its loops carry different UVs) close to a landmark."""
    corners = base.uv[base.tri_loops].reshape(-1, 2)
    verts = base.tri_verts.ravel()
    seen: dict[int, set] = {}
    for v, uv in zip(verts, map(tuple, np.round(corners, 5))):
        seen.setdefault(int(v), set()).add(uv)
    seam = np.array([v for v, uvs in seen.items() if len(uvs) > 1 and base.shell[v] == 0])
    d = np.linalg.norm(base.co[seam] - base.co[base.landmarks[near]], axis=1)
    return int(seam[np.argmin(d)])


def islands(mask: np.ndarray) -> int:
    from scipy import ndimage

    _, n = ndimage.label(mask)
    return int(n)


@pytest.mark.parametrize("species,near", [("dog", "chin"), ("dog", "back_of_head"), ("cat", "chin")])
def test_stamp_crosses_a_seam_correctly(species, near):
    base = load_base(species)
    tm = texel_map(species, SIZE)
    v = seam_vertex(base, near)
    p = base.co[v].astype(float).tolist()
    r = 4.0
    layer = paint.stamp_layer(base, tm, [{"p": p, "r": r, "colour": "#2266FF"}])
    painted = layer[..., 3] >= 128
    pos = texel_positions(base, tm)
    d = np.linalg.norm(pos - np.array(p), axis=-1)
    # Every painted texel is on the surface within the radius (plus the soft edge)...
    assert painted.any() and d[painted].max() <= r + paint.FEATHER_MM
    # ...it spans more than one UV island (the stamp crosses the seam and lands on both sides)...
    assert islands(painted) >= 2
    # ...and no texel within the radius is missed on either side of the seam.
    inside = tm.covered & (d <= r - paint.FEATHER_MM)
    assert (painted[inside]).all()


def test_coverage_grows_smoothly_and_monotonically():
    base = load_base("dog")
    m, files = release.read((ROOT / "fixtures/library/release-dog-1.tar").read_bytes())
    masks = paint.read_masks([files[f] for f in m["atlas"]["mask_files"]])
    ch = {p["id"]: p["channel"] for p in m["pattern_layers"]}
    stamps = paint.stamp_layer(base, texel_map("dog", SIZE), [])
    covered = []
    for cov in np.linspace(0.05, 1.0, 20):
        comp = {"base_colour": "#000000", "layers": [{"pattern_id": "pattern_chest", "coverage": float(cov), "colour": "#FFFFFF"}],
                "eye_colour": "#000000", "nose_colour": "#000000"}
        covered.append(int((paint.composite(masks, m["atlas"]["channels"], comp, ch, stamps)[..., 0] > 127).sum()))
    steps = np.diff(covered)
    assert (steps >= 0).all()  # markings grow, never jump back
    assert steps.max() < 0.15 * covered[-1]  # and grow in small steps, not by snapping between presets


def test_golden_is_current():
    import importlib.util

    spec = importlib.util.spec_from_file_location("golden", ROOT / "scripts/make_library_golden.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert json.loads((ROOT / "fixtures/library/golden.json").read_text()) == json.loads(json.dumps(mod.build()))


def test_release_signature_and_hashes_are_checked(tmp_path):
    bundle = (ROOT / "fixtures/library/release-cat-1.tar").read_bytes()
    manifest, files = release.read(bundle, key=release.DEV_RELEASE_KEY.encode())
    assert manifest["species"] == "cat" and release.release_errors(manifest) == []
    with pytest.raises(release.ReleaseError, match="signature"):
        release.read(bundle, key=b"another-key")
    target = "deltas/family_stocky.f16"
    tampered = bytearray(files[target])
    tampered[10] ^= 0xFF
    manifest2 = {k: v for k, v in manifest.items() if k != "files"}
    good = release.pack(manifest2, files, key=b"k")
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(good)) as src, tarfile.open(fileobj=buf, mode="w") as dst:
        for mem in src.getmembers():
            data = src.extractfile(mem).read()
            if mem.name == target:
                data = bytes(tampered)
            info = tarfile.TarInfo(mem.name)
            info.size = len(data)
            dst.addfile(info, io.BytesIO(data))
    with pytest.raises(release.ReleaseError, match="sha256"):
        release.read(buf.getvalue(), key=b"k")


def test_store_keeps_two_and_switches_atomically(tmp_path):
    store = release.ReleaseStore(tmp_path, base_topology={"dog": load_base("dog").topology_hash()})
    manifest, files = release.read((ROOT / "fixtures/library/release-dog-1.tar").read_bytes())
    bare = {k: v for k, v in manifest.items() if k != "files"}
    for n in (1, 2, 3):
        m = {**bare, "number": n, "release_version": f"release-dog-{n}"}
        assert store.install(release.pack(m, files)).version == f"release-dog-{n}"
        assert store.active("dog").version == f"release-dog-{n}"
    assert store.installed("dog") == ["release-dog-2", "release-dog-3"]
    wrong = {**bare, "number": 4, "release_version": "release-dog-4", "base_topology": "0" * 16}
    with pytest.raises(release.ReleaseError, match="base topology"):
        store.install(release.pack(wrong, files))
    assert store.active("dog").version == "release-dog-3"  # a refused bundle never replaces the active one
