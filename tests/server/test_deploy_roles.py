"""Split deployments (decision 124): a cloud backend and a studio backend side by side in one process, the studio's sync
agent talking to the cloud through a test client. Releases go up, bespoke requests come down and their results go
back, finished orders' print bundles land in the shop's fulfilment folder; each role refuses the other's routes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.api import models as m
from backend.api.app import create_app
from backend.api.db import ArtefactRow, CompositionRow, JobRow, utcnow
from backend.core.config import settings

TOKEN = "sync-test-token"


@pytest.fixture
def pair(monkeypatch, tmp_path):
    for k, v in {"PETPOP_MOCK_SPEED": "0", "PETPOP_STAFF_TOKEN": "staff", "PETPOP_STUDIO_PASSWORD": "pw", "KIOSK_BESPOKE": "1",
                 "GENAI_PROFILE": "mock", "PETPOP_QUALITY": "test", "PETPOP_SYNC_TOKEN": TOKEN}.items():
        monkeypatch.setenv(k, v)
    for k in ("PETPOP_RELEASE_INBOX", "PETPOP_PUBLIC_URL", "PETPOP_CLOUD_URL", "PETPOP_FULFIL_DIR", "DATABASE_URL", "S3_ENDPOINT"):
        monkeypatch.delenv(k, raising=False)

    def make(role: str, **extra) -> TestClient:
        monkeypatch.setenv("PETPOP_VAR", str(tmp_path / role))
        monkeypatch.setenv("PETPOP_SECRET", f"{role}-secret")  # each box its own secret: links are signed where served
        monkeypatch.setenv("PETPOP_DEPLOY", role)
        return TestClient(create_app(embed_worker=False, s=settings(), **extra))

    cloud = make("cloud")
    studio = make("studio", sync_client=TestClient(cloud.app))  # its own client: the agent sets its token on it
    agent = studio.app.state.sync_agent
    with cloud, studio:
        agent.stop()  # the test drives each round itself
        yield cloud, studio, agent


def staff(c: TestClient, who: str = "admin") -> dict[str, str]:
    tok = c.post("/api/v1/studio/auth/login", json={"username": who, "password": "pw"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_each_role_serves_its_own_half(pair):
    cloud, studio, _ = pair
    assert cloud.post("/api/v1/kiosk/sessions", json={}).status_code == 201
    assert cloud.post("/api/v1/studio/auth/login", json={"username": "admin", "password": "pw"}).status_code == 404
    assert studio.post("/api/v1/kiosk/sessions", json={}).status_code == 404
    assert studio.get("/api/v1/studio/me", headers=staff(studio)).status_code == 200
    assert studio.get("/", follow_redirects=False).headers["location"] == "/studio/"
    # the /sync routes: the cloud only, and only with the shared token
    assert cloud.get("/api/v1/sync/prints").status_code == 401
    assert cloud.get("/api/v1/sync/prints", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert studio.get("/api/v1/sync/prints", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 404
    assert "/api/v1/sync/prints" not in cloud.get("/api/v1/openapi.json").json()["paths"]  # not the app contract


def test_a_release_packed_in_the_shop_reaches_the_cloud_kiosks(pair):
    cloud, studio, agent = pair
    before = cloud.get("/api/v1/kiosk/library/dog").json()["release_version"]
    r = studio.post("/api/v1/studio/releases", json={"species": "dog"}, headers=staff(studio))
    assert r.status_code == 201, r.text
    version = r.json()["release_version"]
    assert version != before
    assert agent.push_releases() == [version]
    assert cloud.get("/api/v1/kiosk/library/dog").json()["release_version"] == version
    assert agent.push_releases() == []  # idempotent: nothing to send twice


def _composition(cloud: TestClient) -> tuple[str, str]:
    sid = cloud.post("/api/v1/kiosk/sessions", json={}).json()["session_id"]
    lib = cloud.get("/api/v1/kiosk/library/dog").json()["manifest"]
    fam = lib["families"][0]
    body = {"composition_version": "2.0", "species": "dog", "release_version": lib["release_version"], "mesh_id": fam["mesh_id"],
            "family_id": fam["id"], "breed_id": "corgi_pembroke", "parts": {}, "base_colour": "#C8763A", "eye_colour": "#2B1B12",
            "nose_colour": "#1E1B1A", "layers": [], "stamps": [], "shells": [], "pet_name": "Rex"}
    r = cloud.post("/api/v1/kiosk/compositions", json={"session_id": sid, "composition": body})
    assert r.status_code == 201, r.text
    return sid, r.json()["composition_id"]


def test_a_bespoke_request_is_made_in_the_shop_and_its_result_page_stays_on_the_cloud(pair):
    cloud, studio, agent = pair
    _, cid = _composition(cloud)
    acc = cloud.post(f"/api/v1/kiosk/compositions/{cid}/bespoke", json={"contact": "rex@example.com"}).json()
    job_id = acc["request_id"]
    assert agent.pull_bespoke() == [job_id]
    assert agent.pull_bespoke() == []  # claimed: the cloud no longer offers it
    impl = studio.app.state.impl
    with impl.db() as db:
        job = db.get(JobRow, job_id)
        assert (job.origin, job.kind, job.contact, job.ticket) == ("cloud", "bespoke", "rex@example.com", acc["ticket"])
        # the studio worker would run the pipeline; here the job just finishes with its customer-facing files
        for name, kind in (("figure.glb", "glb"), ("thumbnail.png", "thumbnail")):
            key = f"jobs/{job_id}/{name}"
            impl.store.put(key, b"glb-bytes" if kind == "glb" else b"png-bytes")
            db.add(ArtefactRow(job_id=job_id, stage="F", kind=kind, name=name, object_key=key, bytes=9))
        job.status, job.finished_at = "done", utcnow()
        db.commit()
    assert agent.push_results() == [job_id]
    assert agent.push_results() == []
    with impl.db() as db:
        url = db.get(JobRow, job_id).remote_result_url
    assert url and "/r/" in url
    # the customer's result page is the cloud's, and Studio shows that link
    page = cloud.get(f"/api/v1/r/{url.rsplit('/r/', 1)[1]}")
    assert page.status_code == 200 and page.json()["pet_name"] == "Rex"
    assert studio.get(f"/api/v1/studio/jobs/{job_id}", headers=staff(studio, "operator")).json()["result_url"] == url


def test_a_failed_bespoke_request_is_reported_back(pair):
    cloud, studio, agent = pair
    _, cid = _composition(cloud)
    job_id = cloud.post(f"/api/v1/kiosk/compositions/{cid}/bespoke", json={}).json()["request_id"]
    agent.pull_bespoke()
    impl = studio.app.state.impl
    with impl.db() as db:
        job = db.get(JobRow, job_id)
        job.status, job.error = "failed", "Stage D timed out"
        db.commit()
    assert agent.push_results() == [job_id]
    with cloud.app.state.impl.db() as db:
        assert db.get(JobRow, job_id).status == "failed"


def test_a_finished_order_is_printed_in_the_shop_once(pair):
    cloud, studio, agent = pair
    _, cid = _composition(cloud)
    acc = cloud.post(f"/api/v1/kiosk/compositions/{cid}/export").json()
    assert agent.pull_prints() == []  # still exporting
    impl = cloud.app.state.impl
    with impl.db() as db:  # the kiosk worker's Stage F, stood in for: the print bundle in the store, the job done
        for name in ("figure.3mf", "albedo.png", "composition.json"):
            impl.store.put(f"jobs/{acc['job_id']}/{name}", name.encode())
        db.get(JobRow, acc["job_id"]).status = "done"
        db.commit()
    assert agent.pull_prints() == [acc["ticket"]]
    folder = studio.app.state.impl.s.fulfil_dir / f"{acc['ticket']}_{acc['job_id']}"
    assert sorted(p.name for p in folder.iterdir()) == ["albedo.png", "composition.json", "figure.3mf"]
    assert agent.pull_prints() == []  # acknowledged
    # a reprint from the kiosk ops panel sends it to the shop again
    assert cloud.post(f"/api/v1/kiosk/ops/orders/{cid}/reprint", headers={"X-Staff-Token": "staff"}).status_code == 200
    assert agent.pull_prints() == [acc["ticket"]]
    with impl.db() as db:
        assert db.scalar(select(CompositionRow).where(CompositionRow.id == cid)).collected_at is not None


def test_a_round_survives_an_unreachable_cloud(pair, monkeypatch):
    _, _, agent = pair

    def down(*_a, **_k):
        raise ConnectionError("cloud unreachable")

    monkeypatch.setattr(agent.client, "get", down)
    out = agent.run_once()
    assert all(str(v).startswith("error") or v == [] for v in out.values())
    assert m.API_VERSION  # the app contract is untouched by the sync protocol
