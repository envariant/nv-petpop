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
from petpop_library.composition import sample
from petpop_library.release import release_errors

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


def library(client, species: str) -> dict:
    r = client.get(f"{K}/library/{species}")
    body = check(f"{K}/library/{{species}}", "get", r)
    assert release_errors(body["manifest"]) == []
    assert body["release_version"] == body["manifest"]["release_version"]
    return body


def new_composition(client, sid: str, comp: dict) -> dict:
    r = client.post(f"{K}/compositions", json={"session_id": sid, "composition": comp})
    assert r.status_code == 201, r.text
    return check(f"{K}/compositions", "post", r)


def wait_composition(client, cid: str, timeout: float = 300) -> dict:
    t0 = time.time()
    while True:
        body = check(f"{K}/compositions/{{composition_id}}", "get", client.get(f"{K}/compositions/{cid}"))
        if body["status"] in ("ready", "failed"):
            return body
        assert time.time() - t0 < timeout, f"export of {cid} stuck at {body['export']}"
        time.sleep(0.2)


@pytest.mark.parametrize("species", ["dog", "cat"])
def test_kiosk_library_listing(client, species):
    rel = library(client, species)
    fams = check(f"{K}/library/{{species}}/families", "get", client.get(f"{K}/library/{species}/families"))
    assert fams["items"] and all(f["delta_url"].startswith(rel["files_url"]) for f in fams["items"])
    ears = check(f"{K}/library/{{species}}/parts", "get", client.get(f"{K}/library/{species}/parts", params={"region": "ears"}))
    assert ears["items"] and {p["region"] for p in ears["items"]} == {"ears"}
    shells = check(f"{K}/library/{{species}}/parts", "get", client.get(f"{K}/library/{species}/parts", params={"region": "shells"}))
    assert shells["items"] and {p["kind"] for p in shells["items"]} == {"shell"}
    assert client.get(f"{K}/library/{species}/parts", params={"region": "wings"}).status_code == 422
    pats = check(f"{K}/library/{{species}}/patterns", "get", client.get(f"{K}/library/{species}/patterns"))
    assert len(pats["items"]) == 10
    for url in (pats["items"][0]["thumbnail_url"], ears["items"][0]["url"], rel["files_url"] + "base.bin"):
        r = client.get(url)
        assert r.status_code == 200 and r.content, url
    listed = {f["path"]: f for f in rel["manifest"]["files"]}
    data = client.get(rel["files_url"] + "base.bin").content
    assert hashlib.sha256(data).hexdigest() == listed["base.bin"]["sha256"]
    assert client.get(rel["files_url"] + "manifest.sig").status_code == 404  # only files the manifest lists
    assert client.get(rel["files_url"] + "nope.png").status_code == 404


def test_kiosk_order_from_composition(client):
    """Library mode end to end: a composition is the order record and the only input to a Stage-F-only export."""
    sid = new_session(client)
    rel = library(client, "dog")
    comp = sample(rel["manifest"], layers=4, stamps=12, pet_name="Rocket")
    created = new_composition(client, sid, comp)
    assert created["status"] == "draft" and created["ticket"] is None and created["composition"] == comp
    bad = dict(comp, parts=dict(comp["parts"], ears=comp["parts"]["tail"]))
    r = client.post(f"{K}/compositions", json={"session_id": sid, "composition": bad})
    assert r.status_code == 422
    check(f"{K}/compositions", "post", r)
    r = client.post(f"{K}/compositions", json={"session_id": sid, "composition": dict(comp, release_version="release-dog-999")})
    assert r.status_code == 422
    assert client.post(f"{K}/compositions", json={"session_id": "s_nope", "composition": comp}).status_code == 404
    assert client.get(f"{K}/compositions/c_nope").status_code == 404

    cid = created["composition_id"]
    r = client.post(f"{K}/compositions/{cid}/export")
    assert r.status_code == 202, r.text
    acc = check(f"{K}/compositions/{{composition_id}}/export", "post", r)
    assert acc["ticket"].startswith("PP-")
    again = check(f"{K}/compositions/{{composition_id}}/export", "post", client.post(f"{K}/compositions/{cid}/export"))
    assert again["ticket"] == acc["ticket"]  # idempotent
    done = wait_composition(client, cid)
    assert done["status"] == "ready", done["error"]
    names = {a["name"] for a in done["artefacts"]}
    assert {"figure.3mf", "figure.stl", "albedo.png", "figure.glb", "thumbnail.png", "composition.json"} <= names
    arts = {a["name"]: a for a in done["artefacts"]}
    assert json.loads(client.get(arts["composition.json"]["url"]).content) == comp
    if "manifest.json" in arts:
        man = json.loads(client.get(arts["manifest.json"]["url"]).content)
        assert manifest_errors(man) == []
        assert man["source"] == {"kind": "composition", "composition_id": cid, "release_version": comp["release_version"]}
    page = done["result_url"].split("/r/", 1)[1]
    res = check(f"{P}/r/{{token}}", "get", client.get(f"{P}/r/{page}"))
    assert res["pet_name"] == "Rocket" and client.get(res["glb_url"]).status_code == 200

    assert client.get(f"{K}/ops").status_code == 403
    staff = {"X-Staff-Token": "test-staff"}
    ops = check(f"{K}/ops", "get", client.get(f"{K}/ops", headers=staff))
    assert ops["releases"]["dog"] == rel["release_version"] and ops["orders"][0]["composition_id"] == cid
    r = client.post(f"{K}/ops/orders/{cid}/reprint", headers=staff)
    order = check(f"{K}/ops/orders/{{composition_id}}/reprint", "post", r)
    assert order["ticket"] == acc["ticket"] and order["status"] == "ready"
    assert client.post(f"{K}/ops/orders/{cid}/reprint").status_code == 403


def test_kiosk_bespoke_from_composition(client):
    sid = new_session(client)
    rel = library(client, "dog")
    comp = dict(sample(rel["manifest"], layers=2, pet_name="Mochi"), breed_id="pug")
    cid = new_composition(client, sid, comp)["composition_id"]
    r = client.post(f"{K}/compositions/{cid}/bespoke", json={"contact": "07700 900123"})
    accepted = check(f"{K}/compositions/{{composition_id}}/bespoke", "post", r)
    assert r.status_code == 201 and accepted["ticket"].startswith("PP-")
    again = client.post(f"{K}/compositions/{cid}/bespoke", json={})
    assert again.status_code == 409  # one one-off request per session
    check(f"{K}/compositions/{{composition_id}}/bespoke", "post", again)
    # The request is a studio job whose starting spec is the composition, never on the kiosk queue.
    auth = login(client)
    job = wait_terminal(client, auth, accepted["request_id"])
    assert job["kind"] == "bespoke" and job["session_id"] == sid and job["requested_by"].startswith("kiosk:")
    assert job["spec"]["breed"]["id"] == "pug" and job["spec"]["colour"]["base"]["hex"] == comp["base_colour"]
    assert [a["type"] for a in job["spec"]["accessories"]] == ["collar"]


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
                 f"{K}/sessions", f"{K}/breeds", f"{K}/ops", f"{K}/ops/orders/{{composition_id}}/reprint",
                 f"{K}/library/{{species}}", f"{K}/library/{{species}}/families", f"{K}/library/{{species}}/parts",
                 f"{K}/library/{{species}}/patterns", f"{K}/library/{{species}}/files/{{path}}", f"{K}/compositions",
                 f"{K}/compositions/{{composition_id}}", f"{K}/compositions/{{composition_id}}/export",
                 f"{K}/compositions/{{composition_id}}/bespoke",
                 f"{S}/auth/login", f"{S}/auth/me", f"{S}/breeds", f"{S}/spec/parse", f"{S}/jobs", f"{S}/jobs/{{job_id}}",
                 f"{S}/jobs/{{job_id}}/events", f"{S}/jobs/{{job_id}}/tweak", f"{S}/jobs/{{job_id}}/fulfil",
                 f"{S}/jobs/{{job_id}}/retry", f"{S}/queue"}
    assert set(doc()["paths"]) == exercised


@pytest.mark.parametrize("species", ["dog", "cat"])
def test_specs_for_every_breed_validate(species):
    from petpop_core.breeds import all_breeds

    for b in all_breeds(species):
        assert spec_errors(default_spec(species, b["id"], seed=1)) == [], b["id"]
