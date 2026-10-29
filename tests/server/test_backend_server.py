"""The backend as a real process (make dev mode): SPA and API from one origin, QR result page, signed
files, fulfilment folder, staff panel and Prometheus metrics. Requires apps/kiosk/dist (npm run build)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from backend.core.paths import ROOT
from backend.core.spec import default_spec

DIST = ROOT / "apps/kiosk/dist/index.html"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    if not DIST.exists():
        pytest.skip("SPA not built (cd apps/kiosk && npm run build)")
    var = tmp_path_factory.mktemp("var")
    port = free_port()
    env = {**os.environ, "PYTHONPATH": f"{ROOT}:{ROOT / 'mock-server'}", "PETPOP_VAR": str(var), "PETPOP_EMBED_WORKER": "1",
           "PETPOP_QUALITY": "test", "PETPOP_MOCK_SPEED": "0", "PETPOP_STAFF_TOKEN": "staff-smoke",
           "PETPOP_FULFIL_DIR": str(var / "fulfilment")}
    proc = subprocess.Popen([sys.executable, "-m", "backend.api", "--port", str(port)], env=env, cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/api/v1/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield base, var
    proc.terminate()
    proc.wait(10)


def test_one_origin_job_qr_fulfil_staff_metrics(server):
    base, var = server
    c = httpx.Client(base_url=base, timeout=30)
    assert "<div id=\"root\">" in c.get("/").text  # SPA from the API origin
    sid = c.post("/api/v1/sessions", json={}).json()["session_id"]
    job = c.post("/api/v1/jobs", json={"session_id": sid, "spec": default_spec("cat", "bengal", seed=9, pet_name="Tiger")}).json()
    for _ in range(600):
        j = c.get(f"/api/v1/jobs/{job['job_id']}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert j["status"] == "done", j.get("error")
    path = httpx.URL(j["result_url"]).path
    assert "<div id=\"root\">" in c.get(path).text  # the phone page route is served by the SPA
    page = c.get(f"/api/v1/r/{path.split('/r/')[1]}").json()
    assert page["pet_name"] == "Tiger" and c.get(page["glb_url"]).content[:4] == b"glTF"
    ful = c.post(f"/api/v1/jobs/{job['job_id']}/fulfil").json()
    folder = next(Path(var / "fulfilment").glob(f"{ful['ticket']}_*"))
    assert {"figure.3mf", "figure.stl", "albedo.png", "figure_uv.obj", "paint_mask.png", "manifest.json"} <= {p.name for p in folder.iterdir()}
    assert c.get("/api/v1/staff/queue").status_code == 403
    q = c.get("/api/v1/staff/queue", headers={"X-Staff-Token": "staff-smoke"}).json()
    assert q["recent"][0]["job_id"] == job["job_id"] and q["recent"][0]["thumbnail_url"]
    metrics = c.get("/metrics").text
    assert 'petpop_jobs{status="fulfilled"} 1' in metrics and "petpop_stage_ms_avg" in metrics
