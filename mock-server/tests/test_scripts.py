"""Every mock script drives the kiosk into the state it promises (slow queue, failed stage, fallback)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "mock-server")]

from mock_server.app import create_app, load_scripts  # noqa: E402

from backend.core.spec import default_spec  # noqa: E402

P = "/api/v1"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PETPOP_MOCK_SPEED", "0.01")
    with TestClient(create_app()) as c:
        yield c


def run(client, name: str) -> tuple[list[dict], dict]:
    sid = client.post(f"{P}/sessions", json={}).json()["session_id"]
    spec = default_spec("dog", "beagle", seed=11, pet_name=name)
    job = client.post(f"{P}/jobs", json={"session_id": sid, "spec": spec}).json()
    events = []
    with client.websocket_connect(f"{P}/jobs/{job['job_id']}/events") as ws:
        while True:
            ev = json.loads(ws.receive_text())
            events.append(ev)
            if ev["status"] in ("done", "failed"):
                break
    return events, client.get(f"{P}/jobs/{job['job_id']}").json()


def test_scripts_are_well_formed():
    scripts = load_scripts()
    assert {"normal", "slow_queue", "failed_stage", "fallback_figurine"} <= set(scripts)
    for s in scripts.values():
        at = [st["at_s"] for st in s["steps"]]
        assert at == sorted(at), s["name"]
        assert s["steps"][-1]["stage"] in ("done", "D")


def test_normal_previews_in_order(client):
    events, job = run(client, "Biscuit")
    kinds = [e["preview_kind"] for e in events if e.get("preview_kind")]
    assert kinds[0] == "concept" and kinds[-1] == "glb" and "shape" in kinds
    assert job["status"] == "done" and job["fallback"] == "none"


def test_slow_queue_counts_down(client):
    events, job = run(client, "Slowpoke")
    queued = [e["queue_position"] for e in events if e["status"] == "queued"]
    assert queued and queued[0] >= 2 and queued == sorted(queued, reverse=True)
    assert job["status"] == "done"


def test_failed_stage(client):
    events, job = run(client, "Oops")
    assert events[-1]["status"] == "failed" and job["status"] == "failed"
    assert "Stage D" in job["error"]
    assert not [a for a in job["artefacts"] if a["kind"] == "glb"]
    assert any(t["status"] == "failed" and t["stage"] == "D" for t in job["timings"])


def test_fallback_figurine(client):
    events, job = run(client, "Plan B")
    assert job["status"] == "done" and job["fallback"] == "parametric"
    assert not [e for e in events if e.get("preview_kind") == "shape"]
    assert any(a["kind"] == "glb" for a in job["artefacts"])
    assert any(t["stage"] == "D" and t["status"] == "fallback" for t in job["timings"])


def test_queue_serialises_jobs(client):
    sid = client.post(f"{P}/sessions", json={}).json()["session_id"]
    spec = default_spec("cat", "persian", seed=2, pet_name="Fluff")
    a = client.post(f"{P}/jobs", json={"session_id": sid, "spec": spec}).json()
    b = client.post(f"{P}/jobs", json={"session_id": sid, "spec": spec}).json()
    assert a["queue_position"] == 0 and b["status"] == "queued" and b["queue_position"] >= 1
    time.sleep(0.05)
