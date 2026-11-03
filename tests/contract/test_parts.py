"""The Studio part library (decision 127, API 3.11.0) against both servers: labelled GLBs in, the first guess at every
joint, workbench edits, poses and defaults, and a commit that refuses an incomplete kit."""
from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

from petpop_library import parts as P

from .oas import check

ROOT = Path(__file__).resolve().parents[2]
S = "/api/v1/studio"


def staff(client, who: str) -> dict:
    tok = client.post(f"{S}/auth/login", json={"username": who, "password": "test-studio"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def glbs(names=None) -> list:
    d = ROOT / "fixtures" / "parts" / "dog"
    files = sorted(d.glob("*.glb"))
    return [("files", (p.name, p.read_bytes(), "model/gltf-binary")) for p in files if names is None or p.name in names]


def test_upload_guess_edit_pose_commit(client):
    cur, op = staff(client, "curator"), staff(client, "operator")
    assert client.post(f"{S}/parts/dog/upload?scale=false", files=glbs(), headers=op).status_code == 403  # curators upload
    r = client.post(f"{S}/parts/dog/upload?scale=false", files=glbs() + [("files", ("notes.txt", b"x", "text/plain"))], headers=cur)
    assert r.status_code == 201, r.text
    up = check(f"{S}/parts/{{species}}/upload", "post", r)
    assert up["breeds"] == ["mixed"] and len(up["items"]) == 10
    assert any("notes.txt" in s for s in up["skipped"])

    kits = check(f"{S}/parts/{{species}}", "get", client.get(f"{S}/parts/dog", headers=op))
    assert kits["items"][0]["breed_id"] == "mixed" and kits["items"][0]["kinds"] == list(P.KINDS)

    kit = check(f"{S}/parts/{{species}}/{{breed_id}}", "get", client.get(f"{S}/parts/dog/mixed", headers=op))
    assert kit["version"] == 0 and kit["dirty"] and kit["problems"] == []
    assert kit["defaults"] == {k: "default" for k in P.KINDS}
    by = {(p["kind"], p["variant"]): p for p in kit["parts"]}
    torso, leg = by[("torso", "default")], by[("front_leg", "default")]
    assert set(torso["attachments"]) == set(P.SLOTS) and torso["guess"]["head"]["method"].startswith("in place")
    assert leg["guess"]["joint"]["method"] == "in place, cut" and leg["guess"]["joint"]["confidence"] >= 0.9
    assert by[("head", "default")]["limits"]["yaw"] == [-35.0, 35.0]
    assert client.get(leg["mesh_url"]).status_code == 200

    # move the front leg's pivot and turn the torso's front-left socket; both are marked edited
    j = {**leg["joint"], "pivot": [7.0, 16.0, 10.0], "twist": 30}
    r = client.patch(f"{S}/parts/dog/mixed/parts/{leg['part_id']}", json={"joint": j}, headers=cur)
    kit = check(f"{S}/parts/{{species}}/{{breed_id}}/parts/{{part_id}}", "patch", r)
    leg2 = next(p for p in kit["parts"] if p["part_id"] == leg["part_id"])
    assert leg2["edited"] and leg2["joint"]["pivot"] == [7.0, 16.0, 10.0] and leg2["joint"]["twist"] == 30
    att = {"front_left": {**torso["attachments"]["front_left"], "axis": [0, -1, 0]}}
    kit = client.patch(f"{S}/parts/dog/mixed/parts/{torso['part_id']}", json={"attachments": att}, headers=cur).json()
    t2 = next(p for p in kit["parts"] if p["part_id"] == torso["part_id"])
    assert t2["attachments"]["front_left"]["axis"] == [0.0, -1.0, 0.0] and t2["attachments"]["head"] == torso["attachments"]["head"]
    bad = client.patch(f"{S}/parts/dog/mixed/parts/{leg['part_id']}", json={"attachments": att}, headers=cur)
    assert bad.status_code == 422  # a leg has no attachments
    zero = client.patch(f"{S}/parts/dog/mixed/parts/{leg['part_id']}", json={"joint": {**j, "axis": [0, 0, 0]}}, headers=cur)
    assert zero.status_code == 422
    # back to the first guess
    r = client.post(f"{S}/parts/dog/mixed/parts/{leg['part_id']}/guess", headers=cur)
    kit = check(f"{S}/parts/{{species}}/{{breed_id}}/parts/{{part_id}}/guess", "post", r)
    assert not next(p for p in kit["parts"] if p["part_id"] == leg["part_id"])["edited"]

    # poses: a head turned past its limit stops the commit
    poses = [{"pose_id": "standing", "label": "Standing"},
             {"pose_id": "looking", "label": "Looking up", "legs": {"front_left": 1, "front_right": 1}, "head": {"pitch": 40}}]
    r = client.put(f"{S}/parts/dog/mixed/setup", json={"poses": poses, "default_pose": "looking", "defaults": {"torso": "stocky"}}, headers=cur)
    kit = check(f"{S}/parts/{{species}}/{{breed_id}}/setup", "put", r)
    assert kit["default_pose"] == "looking" and kit["defaults"]["torso"] == "stocky"
    assert any("pitch 40" in p for p in kit["problems"])
    r = client.post(f"{S}/parts/dog/mixed/commit", headers=cur)
    assert r.status_code == 409
    assert client.put(f"{S}/parts/dog/mixed/setup", json={"defaults": {"torso": "nope"}}, headers=cur).status_code == 422
    poses[1]["head"] = {"pitch": 20}
    client.put(f"{S}/parts/dog/mixed/setup", json={"poses": poses}, headers=cur)
    r = client.post(f"{S}/parts/dog/mixed/commit", headers=cur)
    kit = check(f"{S}/parts/{{species}}/{{breed_id}}/commit", "post", r)
    assert kit["version"] == 1 and not kit["dirty"] and kit["committed_by"] == "curator"
    # any edit makes it dirty again; the next commit is version 2
    client.patch(f"{S}/parts/dog/mixed/parts/{leg['part_id']}", json={"label": "Short"}, headers=cur)
    assert client.get(f"{S}/parts/dog/mixed", headers=op).json()["dirty"]
    assert client.post(f"{S}/parts/dog/mixed/commit", headers=cur).json()["version"] == 2


def test_a_right_leg_is_kept_as_a_left_one_and_parts_can_be_removed(client):
    cur = staff(client, "curator")
    d = ROOT / "fixtures" / "parts" / "cat"
    leg = trimesh.load(d / "mixed__front_leg.glb", force="mesh", process=False)
    v, f = P.mirror_vertices(leg.vertices, leg.faces)
    right = trimesh.Trimesh(v, f, process=False).export(file_type="glb")
    files = [("files", ("tabby__front_leg.glb", right, "model/gltf-binary")),
             ("files", ("tabby__torso.glb", (d / "mixed__torso.glb").read_bytes(), "model/gltf-binary"))]
    up = client.post(f"{S}/parts/cat/upload?scale=false", files=files, headers=cur).json()  # split in place
    legs = [p for p in up["items"] if p["kind"] == "front_leg"]
    assert legs[0]["mirrored"]
    kit = client.get(f"{S}/parts/cat/tabby", headers=cur).json()
    assert "no head part" in kit["problems"] and "no tail part" in kit["problems"]
    r = client.delete(f"{S}/parts/cat/tabby/parts/{legs[0]['part_id']}", headers=cur)
    kit = check(f"{S}/parts/{{species}}/{{breed_id}}/parts/{{part_id}}", "delete", r)
    assert [p["kind"] for p in kit["parts"]] == ["torso"]
    assert client.get(f"{S}/parts/cat/nobody", headers=cur).status_code == 404


def test_generated_parts_are_scaled_to_their_size_guess(client):
    """Parts a generator made one at a time (unit-sized, the breed database's names) arrive scaled to the breed's
    size guess (decision 128), each with a note saying so; legs are taken as left legs wherever their origin is."""
    import io  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    from petpop_library import part_sizes as SZ  # noqa: PLC0415

    cur = staff(client, "curator")
    files = []
    for name, ext, x in [("torso", (0.4, 0.5, 1.0), 0), ("head", (0.8, 1.0, 0.9), 0), ("fore_leg", (0.9, 1.0, 0.9), -2),
                         ("hind_leg", (0.5, 1.0, 1.0), 2), ("hind_leg_sitting", (0.55, 0.55, 1.0), 2), ("tail", (0.9, 1.0, 1.0), 0)]:
        box = trimesh.creation.box(extents=ext)
        box.apply_translation([x, 0, 0])
        files.append(("files", (f"corgi_pembroke__{name}.glb", box.export(file_type="glb"), "model/gltf-binary")))
    r = client.post(f"{S}/parts/dog/upload", files=files, headers=cur)
    up = check(f"{S}/parts/{{species}}/upload", "post", r)
    assert up["breeds"] == ["corgi_pembroke"] and len(up["items"]) == 6 and not up["skipped"]
    assert sum("scaled" in n for n in up["notes"]) == 6 and not any("mirrored" in n for n in up["notes"])
    kit = client.get(f"{S}/parts/dog/corgi_pembroke", headers=cur).json()
    assert kit["breed_label"] == "Pembroke Welsh Corgi"
    by = {(p["kind"], p["variant"]): p for p in kit["parts"]}
    assert ("hind_leg", "sitting") in by and not by[("front_leg", "default")]["mirrored"]
    # guessed from shape: the torso's sockets from its own shape, each leg slid to stand on the floor
    assert by[("torso", "default")]["guess"]["front_left"]["method"] == "box"
    assert by[("hind_leg", "sitting")]["guess"]["joint"]["method"].endswith("grounded")
    for (kind, variant), p in by.items():
        mesh = trimesh.load(io.BytesIO(client.get(p["mesh_url"]).content), file_type="glb", force="mesh")
        want = SZ.target("dog", "corgi_pembroke", kind, variant)[0]
        assert float(np.ptp(mesh.vertices, axis=0).max()) == pytest.approx(max(want), rel=1e-3), (kind, variant)
