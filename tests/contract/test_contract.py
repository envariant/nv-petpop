"""The contract test (BRIEF Section 13): every implementation must pass it unchanged.

Runs the full job flow against each implementation in tests/contract/impls.py, validating every response
against data/schema/openapi.json and every manifest and artefact against the JSON Schemas.
"""
from __future__ import annotations

import hashlib
import json
import time

import pytest

from backend.core.contract import openapi_text
from backend.core.paths import SCHEMA_DIR
from backend.core.schemas import manifest_errors, spec_errors
from backend.core.spec import default_spec

from .oas import check, doc, schema_validator

P = "/api/v1"
TERMINAL = {"done", "failed", "fulfilled"}


def new_session(client) -> str:
    r = client.post(f"{P}/sessions", json={"kiosk_id": "test-kiosk"})
    assert r.status_code == 201
    return check(f"{P}/sessions", "post", r)["session_id"]


def submit(client, sid: str, spec: dict) -> dict:
    r = client.post(f"{P}/jobs", json={"session_id": sid, "spec": spec})
    assert r.status_code == 201, r.text
    return check(f"{P}/jobs", "post", r)


def wait_terminal(client, job_id: str, timeout: float = 600) -> dict:
    t0 = time.time()
    while True:
        r = client.get(f"{P}/jobs/{job_id}")
        body = check(f"{P}/jobs/{{job_id}}", "get", r)
        if body["status"] in TERMINAL:
            return body
        assert time.time() - t0 < timeout, f"job {job_id} stuck in {body['stage']}"
        time.sleep(0.2)


def test_openapi_matches_committed(client):
    assert openapi_text(client.app) == (SCHEMA_DIR / "openapi.json").read_text()


def test_health(client):
    body = check(f"{P}/health", "get", client.get(f"{P}/health"))
    if client.impl_name == "mock":
        assert body["mode"] == "mock"
    else:  # the backend reports its GenAI profile's mode: mock by default, real on a GenAI host (gates 3 to 6)
        from backend.core.config import settings

        assert body["mode"] == settings().mode


def test_breeds(client):
    dogs = check(f"{P}/breeds", "get", client.get(f"{P}/breeds", params={"species": "dog"}))
    cats = check(f"{P}/breeds", "get", client.get(f"{P}/breeds", params={"species": "cat"}))
    assert dogs["total"] >= 55 and cats["total"] >= 22
    assert dogs["items"][-1]["id"] == "mixed"
    hit = check(f"{P}/breeds", "get", client.get(f"{P}/breeds", params={"species": "dog", "q": "cor"}))
    assert any(b["id"].startswith("corgi") for b in hit["items"][:3])
    assert client.get(f"{P}/breeds", params={"species": "horse"}).status_code == 422


def test_parse(client):
    spec = default_spec("dog", "mixed", seed=5)
    r = client.post(f"{P}/spec/parse", json={"species": "dog", "current_spec": spec,
                                             "text": "A chunky corgi with floppy ears and blue eyes, loves socks",
                                             "tapped_fields": ["ears.shape"]})
    body = check(f"{P}/spec/parse", "post", r)
    assert body["patch"]["breed"]["id"] == "corgi_pembroke"
    assert "ears.shape" not in body["changed_fields"]  # a tap always wins
    assert body["patch"]["eyes"]["colour"] == "blue"
    assert "loves socks" in body["personality"]
    assert body["ms"] < 3000


def test_job_flow(client):
    sid = new_session(client)
    spec = default_spec("dog", "corgi_pembroke", seed=918273, pet_name="Biscuit")
    created = submit(client, sid, spec)
    assert created["generations_left"] == 2
    job_id = created["job_id"]
    # WebSocket progress stream ends at a terminal status, every frame a ProgressEvent.
    v = schema_validator("ProgressEvent")
    events = []
    with client.websocket_connect(f"{P}/jobs/{job_id}/events") as ws:
        while True:
            try:
                ev = json.loads(ws.receive_text())
            except Exception:
                break
            assert not list(v.iter_errors(ev)), ev
            events.append(ev)
            if ev["status"] in TERMINAL:
                break
    assert events and events[-1]["status"] == "done"
    assert [e for e in events if e.get("preview_kind") == "concept"]
    job = wait_terminal(client, job_id)
    assert job["status"] == "done" and job["pct"] == 100
    assert job["result_url"] and "/r/" in job["result_url"]
    kinds = {a["kind"] for a in job["artefacts"]}
    for k in ("concept", "view", "glb", "albedo", "uv_obj", "3mf", "stl", "mask", "manifest"):
        assert k in kinds, f"missing artefact kind {k}"
    # Artefacts download through signed URLs and match the manifest.
    manifest_url = next(a["url"] for a in job["artefacts"] if a["kind"] == "manifest")
    manifest = client.get(manifest_url).json()
    assert manifest_errors(manifest) == []
    assert manifest["seed"] == spec["seed"]
    by_name = {f["name"]: f for f in manifest["files"]}
    for a in job["artefacts"]:
        if a["kind"] == "manifest":
            continue
        r = client.get(a["url"])
        assert r.status_code == 200, a["name"]
        if a["name"] in by_name and "sha256" in by_name[a["name"]]:
            assert hashlib.sha256(r.content).hexdigest() == by_name[a["name"]]["sha256"], a["name"]
    spec_art = next((a for a in job["artefacts"] if a["kind"] == "spec"), None)
    if spec_art:
        assert spec_errors(client.get(spec_art["url"]).json()) == []
    # Tampered signature is refused.
    bad = manifest_url.replace("sig=", "sig=0")
    assert client.get(bad).status_code == 403
    # Public result page.
    token = job["result_url"].rsplit("/r/", 1)[1]
    page = check(f"{P}/r/{{token}}", "get", client.get(f"{P}/r/{token}"))
    assert page["job_id"] == job_id and client.get(page["glb_url"]).status_code == 200
    assert client.get(f"{P}/r/{token}x").status_code in (404, 410)
    # Tweak keeps the seed.
    tw = client.post(f"{P}/jobs/{job_id}/tweak", json={"session_id": sid, "patch": {"ears": {"shape": "drop"}}})
    tweaked = check(f"{P}/jobs/{{job_id}}/tweak", "post", tw)
    tjob = wait_terminal(client, tweaked["job_id"])
    assert tjob["seed"] == spec["seed"] and tjob["spec"]["ears"]["shape"] == "drop"
    # Fulfil returns a ticket; the job becomes fulfilled.
    ful = check(f"{P}/jobs/{{job_id}}/fulfil", "post", client.post(f"{P}/jobs/{job_id}/fulfil"))
    assert ful["ticket"] and "figure.3mf" in ful["files"]
    assert check(f"{P}/jobs/{{job_id}}", "get", client.get(f"{P}/jobs/{job_id}"))["status"] == "fulfilled"


def test_session_cap_and_validation(client):
    sid = new_session(client)
    spec = default_spec("cat", "siamese", seed=7, pet_name="Luna")
    bad = dict(spec, ears={"shape": "antenna", "size": "small", "tip": "pointed"})
    r = client.post(f"{P}/jobs", json={"session_id": sid, "spec": bad})
    assert r.status_code == 422
    ids = [submit(client, sid, spec)["job_id"] for _ in range(3)]
    r = client.post(f"{P}/jobs", json={"session_id": sid, "spec": spec})
    assert r.status_code == 409
    check(f"{P}/jobs", "post", r)
    for j in ids:
        wait_terminal(client, j)
    assert client.get(f"{P}/jobs/nope").status_code == 404
    assert client.post(f"{P}/jobs/nope/fulfil").status_code == 404


def test_staff(client):
    assert client.get(f"{P}/staff/queue").status_code == 403
    sid = new_session(client)
    job = submit(client, sid, default_spec("dog", "pug", seed=3, pet_name="Mochi"))
    wait_terminal(client, job["job_id"])
    q = check(f"{P}/staff/queue", "get", client.get(f"{P}/staff/queue", headers={"X-Staff-Token": "test-staff"}))
    assert any(j["job_id"] == job["job_id"] for j in q["recent"])
    r = client.post(f"{P}/staff/jobs/{job['job_id']}/retry", headers={"X-Staff-Token": "test-staff"})
    retried = check(f"{P}/staff/jobs/{{job_id}}/retry", "post", r)
    wait_terminal(client, retried["job_id"])


def test_every_documented_path_is_exercised():
    exercised = {"/api/v1/health", "/api/v1/sessions", "/api/v1/breeds", "/api/v1/spec/parse", "/api/v1/jobs",
                 "/api/v1/jobs/{job_id}", "/api/v1/jobs/{job_id}/events", "/api/v1/jobs/{job_id}/tweak",
                 "/api/v1/jobs/{job_id}/fulfil", "/api/v1/r/{token}", "/api/v1/files/{key}",
                 "/api/v1/staff/queue", "/api/v1/staff/jobs/{job_id}/retry"}
    assert set(doc()["paths"]) == exercised


@pytest.mark.parametrize("species", ["dog", "cat"])
def test_specs_for_every_breed_validate(species):
    from backend.core.breeds import all_breeds

    for b in all_breeds(species):
        assert spec_errors(default_spec(species, b["id"], seed=1)) == [], b["id"]
