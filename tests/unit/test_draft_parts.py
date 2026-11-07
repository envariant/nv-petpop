"""Drafting a figure from parts exported one at a time (decisions 128, 130; scripts/draft_parts.py): every part fitted
to its size guess about the centre line, joints guessed from shape, shared parts stretched to the breed, the sitting
pose once the sitting hind leg is there, every figure standing on the floor."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import draft_parts as D  # noqa: E402

from petpop_library import part_sizes as S  # noqa: E402

PEBBLES = {"torso": [0.8, 1.0, 2.0], "head": [0.9, 1.1, 1.0], "fore_leg": [0.9, 1.0, 0.9], "hind_leg": [0.5, 1.0, 1.0],
           "hind_leg_sitting": [0.55, 0.55, 1.0], "tail": [0.9, 1.0, 1.0]}


def pebble(path: Path, ext, scale: float, rng) -> None:
    """A part as a generator returns it: at its own scale, about its own origin."""
    m = trimesh.creation.icosphere(subdivisions=2)
    m.apply_scale(np.array(ext) / 2 * scale)
    m.apply_translation(rng.normal(0, scale, 3))
    m.export(path)


def check_figures(r: dict) -> None:
    for f in r["figures"]:
        plan = json.loads(Path(f["glb"]).with_suffix(".plan.json").read_text())
        fig = trimesh.load(f["glb"], force="mesh")
        assert abs(fig.bounds.mean(axis=0)[0]) < 1.0  # on the centre line
        assert fig.bounds[0][1] == pytest.approx(0.0, abs=1e-3)  # on the floor
        assert 50 < fig.extents[1] < 100 and fig.extents[0] < fig.extents[2]  # about the mandrel's height, longer than wide
        feet = []
        for e, path in zip(plan["parts"], plan["files"]):
            if e["kind"].endswith("_leg"):
                v = trimesh.load(path, force="mesh").vertices
                M = np.asarray(e["matrix"])
                feet.append(float((v @ M[:3, :3].T + M[:3, 3])[:, 1].min()))
        assert max(feet) < 3.0, (f["glb"], feet)  # every leg reaches the floor


def test_a_breed_of_its_own_parts(tmp_path):
    rng = np.random.default_rng(7)
    d = tmp_path / "in"
    d.mkdir()
    for (name, ext), scale in zip(PEBBLES.items(), [1.0, 0.5, 2.0, 300.0, 1.0, 0.1]):
        pebble(d / f"corgi_pembroke__{name}.glb", ext, scale, rng)
    r = D.draft(sorted(d.glob("*.glb")), tmp_path / "draft", engine="trimesh")
    assert r["breed_id"] == "corgi_pembroke" and not r["problems"]
    assert sum("scaled" in n for n in r["notes"]) == 6
    kit = json.loads(Path(r["kit"]).read_text())
    assert kit["version"] == 0 and kit["kit_version"] == "kit-3" and kit["default_pose"] == "sitting"
    assert [p["pose_id"] for p in kit["poses"]] == ["standing", "sitting"] and kit["poses"][1]["variants"] == {"hind_leg": "sitting_fold"}
    assert kit["texture"]["base"]["hex"] == "#C8763A"  # the breed's default texture, from the breed database
    by = {(p["kind"], p["variant"]): p for p in kit["parts"]}
    assert by[("head", "default")]["uv_layout"] == "dog-corgi_pembroke-head-1" and by[("tail", "default")]["uv_layout"] == "dog-tail-1"
    assert not any(p["shared"] for p in kit["parts"]) and all(p["stretch"] == [1.0, 1.0, 1.0] for p in kit["parts"])
    assert {f["pose"] for f in r["figures"]} == {"standing", "sitting"}
    check_figures(r)


def test_a_breed_on_the_shared_library(tmp_path):
    """Shared torsos, legs and tails (each fitted to the median of the breeds using it) and a corgi head: the corgi's
    kit takes its own part types, stretched to its proportions."""
    rng = np.random.default_rng(3)
    d = tmp_path / "in"
    d.mkdir()
    for name, ext, scale in [("torso__long_low", [0.8, 1.0, 2.0], 1.0), ("torso__standard", [0.8, 1.0, 1.35], 3.0),
                             ("fore_leg__paw", [0.9, 1.0, 0.9], 2.0), ("fore_leg__boot", [0.4, 1.0, 0.4], 0.5),
                             ("hind_leg__bean", [0.5, 1.0, 1.0], 300.0), ("hind_leg_sitting__sitting_fold", [0.55, 0.55, 1.0], 1.0),
                             ("tail__bob", [0.9, 1.0, 1.0], 0.1), ("tail__straight", [0.3, 0.35, 1.0], 1.0)]:
        pebble(d / f"shared__{name}.glb", ext, scale, rng)
    pebble(d / "corgi_pembroke__head.glb", [0.9, 1.1, 1.0], 0.5, rng)
    r = D.draft(sorted(d.glob("*.glb")), tmp_path / "draft", engine="trimesh")
    assert r["breed_id"] == "corgi_pembroke" and not r["problems"], r["problems"]
    kit = json.loads(Path(r["kit"]).read_text())
    assert kit["defaults"] == {"head": "default", "torso": "long_low", "front_leg": "paw", "hind_leg": "bean", "tail": "bob"}
    assert kit["allowed"]["front_leg"] == ["paw"] and kit["allowed"]["hind_leg"] == ["bean", "sitting_fold"]
    assert {(p["kind"], p["variant"]) for p in kit["parts"]} == {("head", "default"), ("torso", "long_low"), ("front_leg", "paw"),
                                                               ("hind_leg", "bean"), ("hind_leg", "sitting_fold"), ("tail", "bob")}
    by = {(p["kind"], p["variant"]): p for p in kit["parts"]}
    assert by[("front_leg", "paw")]["shared"] and not by[("head", "default")]["shared"]
    assert by[("front_leg", "paw")]["stretch"][1] < 0.8  # a corgi's legs are shorter than the median paw
    paw = trimesh.load(tmp_path / "draft" / "store" / by[("front_leg", "paw")]["mesh"]["file"], force="mesh")
    assert paw.extents.max() == pytest.approx(max(S.target("dog", S.SHARED, "front_leg", "paw")[0]), rel=1e-3)
    stretched = paw.extents * np.asarray(by[("front_leg", "paw")]["stretch"])
    assert stretched == pytest.approx(S.target("dog", "corgi_pembroke", "front_leg", "paw")[0], rel=0.01)  # the corgi's box
    assert [p["pose_id"] for p in kit["poses"]] == ["standing", "sitting"]
    check_figures(r)


def test_a_breed_entry_with_torso_presets(tmp_path, monkeypatch):
    """A breed's entry in the per-breed parts file (decision 131) with a second torso preset: drafted as its own figure,
    the torso stretched and the legs on its moved sockets."""
    from petpop_library import breed_parts as B  # noqa: PLC0415

    table = json.loads(B.path("dog").read_text())
    entry = table["breeds"]["corgi_pembroke"]
    entry["parts"]["torso"]["offer"]["default"] = {"presets": [B.default_preset(), {
        "preset_id": "stocky", "label": "Stocky", "stretch": [1.3, 1.0, 0.9],
        "sockets": {"front_left": {"translate": [2, 0, 0]}, "front_right": {"translate": [-2, 0, 0]}}}]}
    alt = tmp_path / "parts.json"
    alt.write_text(json.dumps(table))
    monkeypatch.setattr(B, "path", lambda species: alt)
    B.clear()
    try:
        rng = np.random.default_rng(5)
        d = tmp_path / "in"
        d.mkdir()
        for (name, ext), scale in zip(PEBBLES.items(), [1.0, 0.5, 2.0, 300.0, 1.0, 0.1]):
            pebble(d / f"corgi_pembroke__{name}.glb", ext, scale, rng)
        r = D.draft(sorted(d.glob("*.glb")), tmp_path / "draft", engine="trimesh")
    finally:
        B.clear()
    kit = json.loads(Path(r["kit"]).read_text())
    torso = next(p for p in kit["parts"] if p["kind"] == "torso")
    assert [x["preset_id"] for x in torso["presets"]] == ["default", "stocky"]
    stocky = next(f for f in r["figures"] if f["preset"] == "stocky")
    plain = next(f for f in r["figures"] if f["preset"] == "default" and f["pose"] == kit["default_pose"])
    assert stocky["size_mm"][0] > plain["size_mm"][0] * 1.1  # wider: the torso and the legs set further out
    check_figures(r)


def box_obj(ext, scale: float, at, mtl: str | None = None) -> bytes:
    """A box of quads, as a modeller exports it: at its own scale and origin, UVs on, its MTL named."""
    hx, hy, hz = (np.asarray(ext) / 2 * scale).tolist()
    lines = [f"mtllib {mtl}"] if mtl else []
    lines += [f"v {at[0] + sx * hx} {at[1] + sy * hy} {at[2] + sz * hz}" for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    lines += ["vt 0 0", "vt 1 0", "vt 1 1", "vt 0 1"] + (["usemtl skin"] if mtl else [])
    for face in [(1, 2, 4, 3), (5, 7, 8, 6), (1, 5, 6, 2), (3, 4, 8, 7), (1, 3, 7, 5), (2, 6, 8, 4)]:
        lines.append("f " + " ".join(f"{i}/{k + 1}" for k, i in enumerate(face)))
    return ("\n".join(lines) + "\n").encode()


def test_obj_parts_keep_their_quads_for_blender(tmp_path):
    """Decision 138: parts exported as OBJs (quads, an MTL, a texture), facing -Z: triangulated and fitted for Studio
    and the app, the original kept beside the GLB with the matrix that fits it, so Blender composes the quads."""
    import io  # noqa: PLC0415
    import zipfile  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    rng = np.random.default_rng(11)
    d = tmp_path / "in"
    d.mkdir()
    for (name, ext), scale in zip(PEBBLES.items(), [1.0, 0.5, 2.0, 300.0, 1.0, 0.1]):
        if name in ("torso", "tail"):
            (d / f"corgi_pembroke__{name}.obj").write_bytes(box_obj(ext, scale, rng.normal(0, scale, 3),
                                                                     "skin.mtl" if name == "torso" else None))
        else:
            pebble(d / f"corgi_pembroke__{name}.glb", ext, scale, rng)
    (d / "skin.mtl").write_text("newmtl skin\nKd 1 1 1\nmap_Kd skin.png\n")
    Image.fromarray((rng.random((8, 8, 3)) * 255).astype("uint8")).save(d / "skin.png")
    files = [p for p in sorted(d.iterdir()) if p.suffix in (".glb", ".obj")]
    r = D.draft(files, tmp_path / "draft", front="+z", engine="trimesh")
    assert not r["problems"], r["problems"]
    assert any("6 quads" in n for n in r["notes"]) and not any("skin" in n for n in r["notes"]), r["notes"]
    kit = json.loads(Path(r["kit"]).read_text())
    by = {p["kind"]: p for p in kit["parts"]}
    assert "source" not in by["head"] and by["torso"]["source"]["format"] == "obj"
    store = tmp_path / "draft" / "store"
    with zipfile.ZipFile(store / by["torso"]["source"]["file"]) as z:
        assert sorted(z.namelist()) == ["corgi_pembroke__torso.obj", "skin.mtl", "skin.png"]
        raw = trimesh.load(io.BytesIO(z.read("corgi_pembroke__torso.obj")), file_type="obj", process=False)
    glb = trimesh.load(store / by["torso"]["mesh"]["file"], force="mesh", process=False)
    assert glb.visual.material.baseColorTexture is not None  # the texture came through the MTL
    M = np.asarray(by["torso"]["source"]["matrix"])
    assert (raw.vertices @ M[:3, :3].T + M[:3, 3]).min(axis=0) == pytest.approx(glb.vertices.min(axis=0), abs=1e-3)
    check_figures(r)


@pytest.mark.skipif(not Path(os.environ.get("PETPOP_BPY_PYTHON", "/opt/bpy/bin/python")).exists(), reason="no bpy")
def test_blender_composes_obj_parts_from_their_quads(tmp_path):
    from compose_parts import compose  # noqa: PLC0415

    rng = np.random.default_rng(13)
    d = tmp_path / "in"
    d.mkdir()
    for (name, ext), scale in zip(PEBBLES.items(), [1.0, 0.5, 2.0, 300.0, 1.0, 0.1]):
        if name in ("torso", "fore_leg"):
            (d / f"corgi_pembroke__{name}.obj").write_bytes(box_obj(ext, scale, rng.normal(0, scale, 3)))
        else:
            pebble(d / f"corgi_pembroke__{name}.glb", ext, scale, rng)
    # exports facing -Z: the same turn for the GLB and, through the source matrix, for the OBJ original
    r = D.draft(sorted(d.iterdir()), tmp_path / "draft", front="-z", engine="trimesh")
    kit = json.loads(Path(r["kit"]).read_text())
    store = tmp_path / "draft" / "store"
    tm = compose(kit, store, tmp_path / "t", engine="trimesh")
    bp = compose(kit, store, tmp_path / "b", engine="bpy")
    assert bp["result"]["quads"] == 6 * 3  # the torso's and both front legs' quads, as authored
    a = trimesh.load(tm["outputs"]["glb"], force="mesh")
    b = trimesh.load(bp["outputs"]["glb"], force="mesh")
    assert b.bounds == pytest.approx(a.bounds, abs=0.05)  # the same figure as the triangulated parts make
