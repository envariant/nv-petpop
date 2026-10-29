"""The contract test (BRIEF Section 13): every implementation must pass it unchanged.

Runs the full job flow against each implementation in tests/contract/impls.py, validating every response
against data/schema/openapi.json and every manifest and artefact against the JSON Schemas.
"""
from __future__ import annotations

import hashlib
import json
import time

import pytest

from backend.api.contract import openapi_text
from backend.core.paths import SCHEMA_DIR
from petpop_core.schemas import manifest_errors, spec_errors
from petpop_core.spec import default_spec

from .oas import check, doc, schema_validator

P = "/api/v1"
K = f"{P}/kiosk"
S = f"{P}/studio"
TERMINAL = {"done", "failed", "fulfilled"}


def new_session(client) -> str:
    r = client.post(f"{K}/sessions", json={"kiosk_id": "test-kiosk"})
    assert r.status_code == 201
    return check(f"{K}/sessions", "post", r)["session_id"]


def login(client, username: str = "operator") -> dict:
    r = client.post(f"{S}/auth/login", json={"username": username, "password": "test-studio"})
    body = check(f"{S}/auth/login", "post", r)
    return {"Authorization": f"Bearer {body['token']}"}


def submit(client, auth: dict, spec: dict) -> dict:
    r = client.post(f"{S}/jobs", json={"spec": spec}, headers=auth)
    assert r.status_code == 201, r.text
    return check(f"{S}/jobs", "post", r)


def wait_terminal(client, auth: dict, job_id: str, timeout: float = 600) -> dict:
    t0 = time.time()
    while True:
        r = client.get(f"{S}/jobs/{job_id}", headers=auth)
        body = check(f"{S}/jobs/{{job_id}}", "get", r)
        if body["status"] in TERMINAL:
            return body
        assert time.time() - t0 < timeout, f"job {job_id} stuck in {body['stage']}"
        time.sleep(0.2)


def test_openapi_matches_committed(client):
    assert openapi_text(client.app) == (SCHEMA_DIR / "openapi.json").read_text()


def test_health(client):
    body = check(f"{P}/health", "get", client.get(f"{P}/health"))
    assert body["mode"] == "mock"


def test_breeds(client):
    dogs = check(f"{K}/breeds", "get", client.get(f"{K}/breeds", params={"species": "dog"}))
    cats = check(f"{K}/breeds", "get", client.get(f"{K}/breeds", params={"species": "cat"}))
    assert dogs["total"] >= 55 and cats["total"] >= 22
    assert dogs["items"][-1]["id"] == "mixed"
    hit = check(f"{K}/breeds", "get", client.get(f"{K}/breeds", params={"species": "dog", "q": "cor"}))
    assert any(b["id"].startswith("corgi") for b in hit["items"][:3])
    assert client.get(f"{K}/breeds", params={"species": "horse"}).status_code == 422
    auth = login(client)
    same = check(f"{S}/breeds", "get", client.get(f"{S}/breeds", params={"species": "cat"}, headers=auth))
    assert same == cats


def test_studio_auth(client):
    assert check(f"{S}/auth/login", "post", client.post(f"{S}/auth/login", json={"username": "operator", "password": "nope"})) \
        is not None
    assert client.post(f"{S}/auth/login", json={"username": "operator", "password": "nope"}).status_code == 401
    for role in ("operator", "curator", "admin"):
        me = check(f"{S}/auth/me", "get", client.get(f"{S}/auth/me", headers=login(client, role)))
        assert me == {"username": role, "role": role}
    assert client.get(f"{S}/auth/me").status_code == 401
    assert client.get(f"{S}/auth/me", headers={"Authorization": "Bearer operator.admin.9999999999.forged"}).status_code == 401
    assert client.get(f"{S}/queue").status_code == 401
    assert client.post(f"{S}/jobs", json={"spec": default_spec("dog", "pug", seed=1)}).status_code == 401


def test_kiosk_session_bespoke_and_ops(client):
    sid = new_session(client)
    spec = default_spec("dog", "beagle", seed=11, pet_name="Rocket")
    r = client.post(f"{K}/bespoke", json={"session_id": sid, "spec": spec, "contact": "07700 900123"})
    accepted = check(f"{K}/bespoke", "post", r)
    assert r.status_code == 201 and accepted["ticket"].startswith("PP-") and "message" in accepted["message"]
    again = client.post(f"{K}/bespoke", json={"session_id": sid, "spec": spec})
    assert again.status_code == 409  # one one-off request per session
    check(f"{K}/bespoke", "post", again)
    # The request is a studio job, visible to staff, never on the kiosk queue.
    auth = login(client)
    job = wait_terminal(client, auth, accepted["request_id"])
    assert job["kind"] == "bespoke" and job["session_id"] == sid and job["requested_by"].startswith("kiosk:")
    assert client.get(f"{K}/ops").status_code == 403
    ops = check(f"{K}/ops", "get", client.get(f"{K}/ops", headers={"X-Staff-Token": "test-staff"}))
    assert ops["bespoke_enabled"] is True and ops["exports_queued"] == 0


def test_parse(client):
    spec = default_spec("dog", "mixed", seed=5)
    r = client.post(f"{S}/spec/parse", json={"species": "dog", "current_spec": spec,
                                             "text": "A chunky corgi with floppy ears and blue eyes, loves socks",
                                             "tapped_fields": ["ears.shape"]}, headers=login(client))
    body = check(f"{S}/spec/parse", "post", r)
    assert body["patch"]["breed"]["id"] == "corgi_pembroke"
    assert "ears.shape" not in body["changed_fields"]  # a tap always wins
    assert body["patch"]["eyes"]["colour"] == "blue"
    assert "loves socks" in body["personality"]
    assert body["ms"] < 3000


def test_job_flow(client):
    auth = login(client)
    token = auth["Authorization"].split()[1]
    spec = default_spec("dog", "corgi_pembroke", seed=918273, pet_name="Biscuit")
    created = submit(client, auth, spec)
    job_id = created["job_id"]
    # WebSocket progress stream ends at a terminal status, every frame a ProgressEvent.
    v = schema_validator("ProgressEvent")
    events = []
    with client.websocket_connect(f"{S}/jobs/{job_id}/events?token={token}") as ws:
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
    job = wait_terminal(client, auth, job_id)
    assert job["status"] == "done" and job["pct"] == 100
    assert job["kind"] == "pipeline" and job["requested_by"] == "operator" and job["session_id"] is None
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
    tw = client.post(f"{S}/jobs/{job_id}/tweak", json={"patch": {"ears": {"shape": "drop"}}}, headers=auth)
    tweaked = check(f"{S}/jobs/{{job_id}}/tweak", "post", tw)
    tjob = wait_terminal(client, auth, tweaked["job_id"])
    assert tjob["seed"] == spec["seed"] and tjob["spec"]["ears"]["shape"] == "drop"
    # Fulfil returns a ticket; the job becomes fulfilled.
    ful = check(f"{S}/jobs/{{job_id}}/fulfil", "post", client.post(f"{S}/jobs/{job_id}/fulfil", headers=auth))
    assert ful["ticket"] and "figure.3mf" in ful["files"]
    assert check(f"{S}/jobs/{{job_id}}", "get", client.get(f"{S}/jobs/{job_id}", headers=auth))["status"] == "fulfilled"
    # A WebSocket without a valid staff token is refused.
    with pytest.raises(Exception):
        with client.websocket_connect(f"{S}/jobs/{job_id}/events") as ws:
            ws.receive_text()


def test_validation(client):
    auth = login(client)
    spec = default_spec("cat", "siamese", seed=7, pet_name="Luna")
    bad = dict(spec, ears={"shape": "antenna", "size": "small", "tip": "pointed"})
    r = client.post(f"{S}/jobs", json={"spec": bad}, headers=auth)
    assert r.status_code == 422
    check(f"{S}/jobs", "post", r)
    assert client.get(f"{S}/jobs/nope", headers=auth).status_code == 404
    assert client.post(f"{S}/jobs/nope/fulfil", headers=auth).status_code == 404


def test_studio_queue_and_retry(client):
    auth = login(client, "curator")
    job = submit(client, auth, default_spec("dog", "pug", seed=3, pet_name="Mochi"))
    wait_terminal(client, auth, job["job_id"])
    q = check(f"{S}/queue", "get", client.get(f"{S}/queue", headers=auth))
    assert any(j["job_id"] == job["job_id"] and j["requested_by"] == "curator" for j in q["recent"])
    r = client.post(f"{S}/jobs/{job['job_id']}/retry", headers=auth)
    retried = check(f"{S}/jobs/{{job_id}}/retry", "post", r)
    wait_terminal(client, auth, retried["job_id"])


def test_every_documented_path_is_exercised():
    exercised = {f"{P}/health", f"{P}/r/{{token}}", f"{P}/files/{{key}}",
                 f"{K}/sessions", f"{K}/breeds", f"{K}/bespoke", f"{K}/ops",
                 f"{S}/auth/login", f"{S}/auth/me", f"{S}/breeds", f"{S}/spec/parse", f"{S}/jobs", f"{S}/jobs/{{job_id}}",
                 f"{S}/jobs/{{job_id}}/events", f"{S}/jobs/{{job_id}}/tweak", f"{S}/jobs/{{job_id}}/fulfil",
                 f"{S}/jobs/{{job_id}}/retry", f"{S}/queue"}
    assert set(doc()["paths"]) == exercised


@pytest.mark.parametrize("species", ["dog", "cat"])
def test_specs_for_every_breed_validate(species):
    from petpop_core.breeds import all_breeds

    for b in all_breeds(species):
        assert spec_errors(default_spec(species, b["id"], seed=1)) == [], b["id"]
