"""Manual mode end to end on the backend (decision 111): a Studio job on the tripo-manual profile waits for the
operator twice (concept image, then the 3D model), each time with the exact request the Tripo API would have got;
uploading each output through the Studio API resumes it, and it finishes with the operator's model, textured."""
from __future__ import annotations

import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from petpop_core.spec import default_spec
from tests.fakes.tripo_api import FakeTripo

S = "/api/v1/studio"


@pytest.fixture
def studio(monkeypatch, tmp_path):
    monkeypatch.setenv("GENAI_PROFILE", "tripo-manual")
    monkeypatch.setenv("PETPOP_QUALITY", "test")
    monkeypatch.setenv("PETPOP_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("PETPOP_STUDIO_PASSWORD", "manual-test")
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)  # manual mode needs no key
    from backend.api.app import create_app
    from backend.core.config import settings
    from backend.worker.service import Worker

    with TestClient(create_app(embed_worker=False)) as c:
        token = c.post(f"{S}/auth/login", json={"username": "operator", "password": "manual-test"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c, Worker(settings(), queue="studio")


def fetch(client: TestClient, url: str) -> bytes:
    path = httpx.URL(url).raw_path.decode()
    r = client.get(path)
    assert r.status_code == 200, r.text
    return r.content


def test_a_job_waits_for_the_operator_and_resumes(studio):
    c, worker = studio
    job_id = c.post(f"{S}/jobs", json={"spec": default_spec("dog", "beagle", seed=42, pet_name="Manny")}).json()["job_id"]

    assert worker.run_job(job_id) == "waiting"
    job = c.get(f"{S}/jobs/{job_id}").json()
    assert job["status"] == "waiting" and job["stage"] == "B" and "Concept image" in job["message"]
    inbox = c.get(f"{S}/manual").json()
    assert inbox["pending"] == 1
    concept = inbox["items"][0]
    assert concept["capability"] == "text_to_image" and concept["job_id"] == job_id
    assert concept["prompt"].startswith("a chibi vinyl collectible figurine of a Beagle") and concept["negative_prompt"]
    assert concept["route"] == "POST /v3/generation/text-to-image" and concept["manifest"] == "tripo-v3 v1"
    assert concept["pet_name"] == "Manny" and concept["instructions"]

    bad = c.post(f"{S}/manual/{concept['task_id']}/result", files={"file": ("concept.glb", b"x", "model/gltf-binary")})
    assert bad.status_code == 422  # an image is expected here
    up = c.post(f"{S}/manual/{concept['task_id']}/result", files={"file": ("concept.jpg", FakeTripo.figure(), "image/jpeg")})
    assert up.status_code == 200 and up.json()["status"] == "submitted"
    assert c.get(f"{S}/jobs/{job_id}").json()["status"] == "queued"

    assert worker.run_job(job_id) == "waiting"  # resumed past B, now waits for the 3D model
    model = c.get(f"{S}/manual").json()["items"][0]
    assert model["capability"] == "image_to_model" and model["expects"] == {"kind": "model", "accept": [".glb"]}
    assert model["request"]["model"] == "v3.1-20260211" and model["request"]["texture"] is True
    assert model["request"]["input"] == "<upload input.png>" and "face_limit: 200000" in model["settings"]
    matted = fetch(c, model["inputs"][0]["url"])  # the matted concept the operator uploads to Tripo Studio
    assert Image.open(io.BytesIO(matted)).mode == "RGBA"
    glb = FakeTripo.textured_hull(matted)
    assert c.post(f"{S}/manual/{model['task_id']}/result", files={"file": ("figure.glb", glb, "model/gltf-binary")}).status_code == 200

    assert worker.run_job(job_id) == "done"
    job = c.get(f"{S}/jobs/{job_id}").json()
    assert job["status"] == "done" and job["fallback"] in ("none", "unwrapped")
    notes = {t["stage"]: t["status"] for t in job["timings"]}
    assert notes.get("D") == "ok" and c.get(f"{S}/manual").json()["pending"] == 0
    assert any(a["kind"] == "glb" for a in job["artefacts"])


def test_one_worker_runs_each_job_on_its_own_profile(monkeypatch, tmp_path):
    """Decision 113: GENAI_PROFILE is the default; Studio picks per job from PETPOP_STUDIO_PROFILES; one worker
    builds each profile's adapters on first use, so a mock job and a manual-mode job run side by side."""
    monkeypatch.setenv("GENAI_PROFILE", "mock")
    monkeypatch.setenv("PETPOP_STUDIO_PROFILES", "tripo-manual")
    monkeypatch.setenv("PETPOP_QUALITY", "test")
    monkeypatch.setenv("PETPOP_MOCK_SPEED", "0")
    monkeypatch.setenv("PETPOP_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("PETPOP_STUDIO_PASSWORD", "pick-test")
    from backend.api.app import create_app
    from backend.core.config import settings
    from backend.worker.service import Worker

    with TestClient(create_app(embed_worker=False)) as c:
        c.headers["Authorization"] = "Bearer " + c.post(f"{S}/auth/login", json={"username": "operator", "password": "pick-test"}).json()["token"]
        offered = c.get(f"{S}/profiles").json()
        assert offered["default"] == "mock" and [p["name"] for p in offered["items"]] == ["mock", "tripo-manual"]
        assert all(p["ready"] for p in offered["items"])  # manual mode needs no key
        spec = default_spec("cat", "siamese", seed=8)
        plain = c.post(f"{S}/jobs", json={"spec": spec}).json()["job_id"]
        manual = c.post(f"{S}/jobs", json={"spec": spec, "genai_profile": "tripo-manual"}).json()["job_id"]
        assert c.post(f"{S}/jobs", json={"spec": spec, "genai_profile": "tripo"}).status_code == 422  # not offered
        worker = Worker(settings(), queue="studio")
        assert worker.run_job(plain) == "done"
        assert worker.run_job(manual) == "waiting"
        jobs = {j: c.get(f"{S}/jobs/{j}").json() for j in (plain, manual)}
        assert jobs[plain]["genai_profile"] == "mock" and jobs[manual]["genai_profile"] == "tripo-manual"
        assert [t["job_id"] for t in c.get(f"{S}/manual").json()["items"]] == [manual]
        # the profile is recorded at creation: changing the server default later does not move a waiting job
        retried = c.post(f"{S}/jobs/{manual}/retry").json()["job_id"]
        assert c.get(f"{S}/jobs/{retried}").json()["genai_profile"] == "tripo-manual"


def test_an_unknown_studio_profile_is_a_configuration_error(monkeypatch):
    from backend.core.genai import ProfileError, studio_profiles

    monkeypatch.setenv("PETPOP_STUDIO_PROFILES", "tripo,no-such-profile")
    with pytest.raises(ProfileError, match="no-such-profile"):
        studio_profiles()
