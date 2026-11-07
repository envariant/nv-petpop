"""A figure of part kits end to end on the backend (decisions 133 to 135): parts and a mask uploaded in Studio, the
kit committed and released, a composition 3.0 ordered at the kiosk, and the kiosk worker's export: the parts placed,
painted per part (the mask in colour B, the rest in colour A) and printed."""
from __future__ import annotations

import io
import json
import os

import httpx
import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image

S, K = "/api/v1/studio", "/api/v1/kiosk"
A, B = "#E04020", "#2040E0"


def uv_part(ext) -> bytes:
    """A pebble with spherical UVs (and a texture, as a generator's part has)."""
    m = trimesh.creation.icosphere(subdivisions=2)
    v = m.vertices
    uv = np.stack([0.5 + np.arctan2(v[:, 0], v[:, 2]) / (2 * np.pi), 0.5 + np.arcsin(np.clip(v[:, 1], -1, 1)) / np.pi], axis=1)
    m.apply_scale(np.array(ext) / 2)
    m.visual = trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.PBRMaterial(
        baseColorTexture=Image.new("RGB", (8, 8), (90, 90, 90))))
    return trimesh.Scene([m]).export(file_type="glb")


def png(value: int) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (128, 128), value).save(buf, format="PNG")
    return buf.getvalue()


BPY = os.environ.get("PETPOP_BPY_PYTHON", "/opt/bpy/bin/python")


@pytest.fixture(params=["cpu", "blender"])
def backend(request, monkeypatch, tmp_path):
    if request.param == "blender" and not os.path.exists(BPY):
        pytest.skip("no Blender (PETPOP_BPY_PYTHON)")
    monkeypatch.setenv("GENAI_PROFILE", "mock")
    monkeypatch.setenv("PETPOP_QUALITY", "test")
    monkeypatch.setenv("PETPOP_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("PETPOP_RELEASE_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("PETPOP_STUDIO_PASSWORD", "kit-test")
    # the CPU fallback (quick, the same painting) and Blender (the kiosk's print path)
    monkeypatch.setenv("PETPOP_BPY_PYTHON", BPY if request.param == "blender" else str(tmp_path / "no-blender"))
    from backend.api.app import create_app
    from backend.core.config import settings
    from backend.worker.service import Worker

    with TestClient(create_app(embed_worker=False)) as c:
        yield c, Worker(settings(), queue="kiosk")


def login(c: TestClient, who: str) -> dict:
    return {"Authorization": f"Bearer {c.post(f'{S}/auth/login', json={'username': who, 'password': 'kit-test'}).json()['token']}"}


def test_a_figure_of_part_kits_is_ordered_and_printed(backend):
    c, worker = backend
    cur, adm = login(c, "curator"), login(c, "admin")
    files = [("files", (f"beagle__{n}.glb", uv_part(e), "model/gltf-binary")) for n, e in
             [("torso", (0.8, 1, 1.4)), ("head", (1, 1, 1)), ("fore_leg", (0.4, 1, 0.4)), ("hind_leg", (0.5, 1, 1)), ("tail", (0.2, 0.2, 1))]]
    files.append(("files", ("dog-torso-1__white_chest.png", png(255), "image/png")))  # the whole torso is "chest"
    up = c.post(f"{S}/parts/dog/upload", files=files, headers=cur)
    assert up.status_code == 201, up.text
    texture = {"base": {"name": "red", "hex": A}, "secondary": {"name": "blue", "hex": B}, "tertiary": None, "pattern": "solid",
               "markings": ["white_chest"]}
    assert c.put(f"{S}/parts/dog/beagle/setup", json={"texture": texture}, headers=cur).status_code == 200
    assert c.post(f"{S}/parts/dog/beagle/commit", headers=cur).status_code == 200
    r = c.post(f"{S}/releases", json={"species": "dog"}, headers=adm)
    assert r.status_code == 201, r.text

    rel = c.get(f"{K}/library/dog").json()
    assert any(k["breed_id"] == "beagle" for k in rel["manifest"]["kits"])
    from petpop_library.composition import sample_kit

    comp = sample_kit(rel["manifest"], "beagle", pet_name="Kit")
    assert comp["texture"]["markings"] == ["white_chest"] and comp["texture"]["secondary"]["hex"] == B
    sid = c.post(f"{K}/sessions", json={"kiosk_id": "kit-test"}).json()["session_id"]
    st = c.post(f"{K}/compositions", json={"session_id": sid, "composition": comp})
    assert st.status_code == 201, st.text
    cid = st.json()["composition_id"]
    acc = c.post(f"{K}/compositions/{cid}/export", json={"contact": {"email": "kit@example.com"}})
    assert acc.status_code in (200, 201, 202), acc.text
    job_id = acc.json()["job_id"]
    assert worker.run_job(job_id) == "done"
    assert c.get(f"{K}/compositions/{cid}").json()["status"] == "ready"

    from backend.core.config import settings
    from backend.api.store import LocalStore

    store = LocalStore(settings().var / "artefacts")
    manifest = json.loads(store.get(f"jobs/{job_id}/manifest.json"))
    assert manifest["source"]["breed_id"] == "beagle" and manifest["source"]["kit_version"] == 1
    assert manifest["metrics"]["print_watertight"]
    assert manifest["fidelity"] == ("high" if os.environ["PETPOP_BPY_PYTHON"] == BPY else "low")
    # the albedo: a tile per distinct part; the torso's is all colour B (its mask is white everywhere), the others A
    albedo = np.asarray(Image.open(io.BytesIO(store.get(f"jobs/{job_id}/albedo.png"))).convert("RGB"))
    colours = {tuple(int(x) for x in px) for px in albedo.reshape(-1, 3)[:: 97]}
    rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # noqa: E731
    assert rgb(A) in colours and rgb(B) in colours
    stl = trimesh.load(io.BytesIO(store.get(f"jobs/{job_id}/figure.stl")), file_type="stl")
    assert 40 < stl.extents[2] < 110  # about the mandrel's height, standing on its base
    _ = httpx  # (kept for parity with the other server tests)

    # every vertex samples its own part's tile: the torso's colour B, the head's colour A
    from backend.worker.export import find_release, release_store
    from petpop_library import kit_figure

    rel_obj = find_release(release_store(settings()), comp)
    mesh, co, atlas = kit_figure.build("dog", rel_obj.kit("beagle"), comp, rel_obj.file, rel_obj.mask_file, tile=64)
    h, w, _ = atlas.shape
    corner = mesh.uv.reshape(-1, 3, 2)
    for group, want in (("body", B), ("head", A), ("leg_FR", A)):
        faces = mesh.groups[mesh.group_names.index(group)][mesh.tri_verts[:, 0]] > 0.5
        uv = corner[faces].reshape(-1, 2)
        px = atlas[np.clip(((1 - uv[:, 1]) * h).astype(int), 0, h - 1), np.clip((uv[:, 0] * w).astype(int), 0, w - 1)]
        assert (np.abs(px.astype(int) - rgb(want)).max(axis=1) <= 2).mean() > 0.98, group
    assert co[:, 2].min() == pytest.approx(0.0) and np.ptp(co[:, 2]) > np.ptp(co[:, 0])  # Z up, on the floor, taller than wide
