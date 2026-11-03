"""Part kits (decision 127): joint frames, assembly, mirroring, leg twists and head angles, the automatic first guess on
the proxy parts (fixtures/parts, cut from the labelled templates), and what stops a kit from being committed."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from petpop_library import parts as P

ROOT = Path(__file__).resolve().parents[2]


def kit_meshes(species: str = "dog") -> dict[str, tuple[np.ndarray, np.ndarray]]:
    out = {}
    for p in sorted((ROOT / "fixtures" / "parts" / species).glob("*.glb")):
        _, kind, *var = p.stem.split("__")
        m = trimesh.load(p, force="mesh", process=False)
        out[f"{kind}/{var[0] if var else 'default'}"] = (np.asarray(m.vertices), np.asarray(m.faces))
    return out


@pytest.fixture(scope="module")
def dog():
    meshes = kit_meshes("dog")
    rig = P.auto_rig({k: v for k, v in meshes.items() if not k.startswith("torso/")}, meshes["torso/default"])
    return meshes, rig


def joints(rig, kind: str, slot: str):
    j, a = rig.joints[f"{kind}/default"], rig.attachments[slot]
    return P.Joint(j["pivot"], j["axis"]), P.Joint(a["position"], a["axis"])


def test_frames_are_right_handed_and_twist_turns_the_ref():
    j = P.Joint(np.zeros(3), np.array([0.2, -1.0, 0.3]), 0.0)
    f = j.frame()
    assert np.allclose(f.T @ f, np.eye(3), atol=1e-9) and np.isclose(np.linalg.det(f), 1.0)
    g = P.Joint(np.zeros(3), j.axis, 90.0).frame()
    assert np.allclose(g[:, 0], f[:, 0]) and abs(float(f[:, 1] @ g[:, 1])) < 1e-9  # ref turned a quarter about the axis
    up = P.Joint(np.zeros(3), np.array([0, 0, 1.0])).frame()  # axis along the front: ref falls back to up
    assert np.allclose(up[:, 1], [0, 1, 0])


def test_the_automatic_guess_finds_each_cut(dog):
    _, rig = dog
    for key in ("head/default", "front_leg/default", "hind_leg/default"):
        assert rig.joints[key]["method"] == "in place, cut" and rig.joints[key]["confidence"] >= 0.9, key
    assert rig.joints["tail/default"]["method"].startswith("in place")
    a = rig.attachments
    assert a["front_right"]["position"][0] == pytest.approx(-a["front_left"]["position"][0])
    assert a["head"]["axis"][1] > 0.8 and a["tail"]["axis"][2] < -0.8  # the neck points up, the tail back
    assert a["front_left"]["axis"][1] < -0.5 and a["hind_left"]["axis"][1] < 0  # legs point down


def test_parts_split_in_place_go_back_where_they_were_cut(dog):
    meshes, rig = dog
    for slot in ("head", "front_left", "hind_left", "tail"):
        kind = P.SLOT_KIND[slot]
        v, f = meshes[f"{kind}/default"]
        part, att = joints(rig, kind, slot)
        pv, _ = P.place(v, f, part, att, slot)
        assert np.allclose(pv, v, atol=1e-6), slot


def test_right_legs_are_the_mirror_of_the_left(dog):
    meshes, rig = dog
    for left, kind in (("front_left", "front_leg"), ("hind_left", "hind_leg")):
        right = P.PAIRS[left]
        v, f = meshes[f"{kind}/default"]
        part, att_l = joints(rig, kind, left)
        att_r = P.Joint(rig.attachments[right]["position"], rig.attachments[right]["axis"])
        for k in (0, 1, 2):
            pose = {"legs": {left: k, right: k}}
            lv, lf = P.place(v, f, part, att_l, left, pose)
            rv, rf = P.place(v, f, part, att_r, right, pose)
            assert np.allclose(rv, lv * [-1, 1, 1], atol=1e-6), (left, k)  # a symmetric pose is symmetric
            assert (rf == lf[:, ::-1]).all()  # winding flipped: normals still point out


def test_a_leg_twists_in_thirds_about_its_socket(dog):
    meshes, rig = dog
    v, f = meshes["front_leg/default"]
    part, att = joints(rig, "front_leg", "front_left")
    rest, _ = P.place(v, f, part, att, "front_left")
    turned, _ = P.place(v, f, part, att, "front_left", {"legs": {"front_left": 1}})
    full, _ = P.place(v, f, part, att, "front_left", {"legs": {"front_left": 3}})
    assert np.allclose(full, rest, atol=1e-6)  # three thirds: back to the start
    r_rest, r_turn = rest - att.point, turned - att.point
    assert np.allclose(np.linalg.norm(r_rest, axis=1), np.linalg.norm(r_turn, axis=1), atol=1e-6)  # turns about the socket
    assert np.allclose(r_rest @ att.axis, r_turn @ att.axis, atol=1e-6)  # ...about its axis
    perp = lambda r: r - np.outer(r @ att.axis, att.axis)  # noqa: E731 - off the axis (the centre lies on it)
    i = int(np.argmax(np.linalg.norm(perp(r_rest), axis=1)))  # the vertex farthest from the axis
    p0, p1 = perp(r_rest)[i], perp(r_turn)[i]
    cos = float(p0 @ p1) / float(np.linalg.norm(p0) * np.linalg.norm(p1))
    assert cos == pytest.approx(-0.5, abs=1e-6)  # 120 degrees


def test_the_head_turns_about_its_pivot_within_limits(dog):
    meshes, rig = dog
    v, f = meshes["head/default"]
    part, att = joints(rig, "head", "head")
    rest, _ = P.place(v, f, part, att, "head")
    yawed, _ = P.place(v, f, part, att, "head", {"head": {"yaw": 30, "pitch": -10, "roll": 5}})
    assert np.allclose(np.linalg.norm(rest - att.point, axis=1), np.linalg.norm(yawed - att.point, axis=1), atol=1e-6)
    assert not np.allclose(rest, yawed)
    assert P.clamp_head({"head": {"yaw": 30}}, P.DEFAULT_HEAD_LIMITS) == []
    assert P.clamp_head({"head": {"yaw": 50}}, P.DEFAULT_HEAD_LIMITS) == ["head yaw 50 is outside -35..35"]


def test_a_right_leg_is_kept_as_a_left_one(dog):
    meshes, _ = dog
    v, f = meshes["front_leg/default"]
    rv, rf = P.mirror_vertices(v, f)
    lv, lf, flipped = P.as_left("front_leg", rv, rf)
    assert flipped and np.allclose(lv, v) and (lf == f).all()
    assert P.as_left("head", rv, rf)[2] is False


def test_what_stops_a_kit_from_being_committed():
    j = {"pivot": [0, 0, 0], "axis": [0, -1, 0], "twist": 0}
    att = {s: {"position": [0, 0, 0], "axis": [0, -1, 0], "twist": 0} for s in P.SLOTS}
    kit = {"defaults": {k: "default" for k in P.KINDS},
           "parts": [{"kind": "torso", "variant": "default", "attachments": att}]
           + [{"kind": k, "variant": "default", "joint": j, "limits": P.DEFAULT_HEAD_LIMITS} for k in ("head", "front_leg", "hind_leg", "tail")],
           "poses": [{"pose_id": "sit", "legs": {"front_left": 0}, "head": {"yaw": 0}}], "default_pose": "sit"}
    assert P.kit_problems(kit) == []
    bad = {**kit, "parts": kit["parts"][1:], "poses": [{"pose_id": "x", "legs": {"front_left": 5}, "head": {"yaw": 90}}]}
    problems = P.kit_problems(bad)
    assert "no torso part" in problems
    assert any("must be 0, 1 or 2" in p for p in problems) and any("outside" in p for p in problems)
    assert "the default pose is not in the allowed list" in problems


def test_heads_have_their_breeds_own_texture_template():
    """Decision 129: a head's layout (and masks) is its breed's; other kinds share one layout across breeds."""
    import jsonschema  # noqa: PLC0415

    from petpop_core.schemas import load_schema  # noqa: PLC0415

    assert P.uv_layout("dog", "corgi_pembroke", "head") == "dog-corgi_pembroke-head-1"
    assert P.uv_layout("dog", "corgi_pembroke", "torso") == P.uv_layout("dog", "pug", "torso") == "dog-torso-1"
    prop = load_schema("part_kit.schema.json")["properties"]["parts"]["items"]["properties"]["uv_layout"]
    for ok in ("dog-corgi_pembroke-head-1", "cat-hind_leg-1"):
        jsonschema.validate(ok, prop)
    for bad in ("dog-head-1", "dog-corgi-paw-1"):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, prop)
