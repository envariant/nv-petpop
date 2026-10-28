#!/usr/bin/env python3
"""End-to-end smoke test of a running PetPop stack (make up): session, job through the queue and worker,
progress over WebSocket, artefacts from the store via signed URLs, manifest, fulfil, staff panel, metrics.

    python scripts/smoke_stack.py --base http://127.0.0.1:8000 --staff-token "$PETPOP_STAFF_TOKEN"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.schemas import manifest_errors  # noqa: E402
from backend.core.spec import default_spec  # noqa: E402


def ok(msg: str) -> None:
    print(f"  [PASS] {msg}", flush=True)


async def events(base: str, job_id: str, timeout: float) -> list[dict]:
    url = base.replace("http", "ws", 1) + f"/api/v1/jobs/{job_id}/events"
    out = []
    async with websockets.connect(url, open_timeout=30) as ws:
        t0 = time.time()
        while time.time() - t0 < timeout:
            ev = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            out.append(ev)
            if ev["status"] in ("done", "failed", "fulfilled"):
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--staff-token", required=True)
    ap.add_argument("--timeout", type=float, default=900)
    a = ap.parse_args()
    c = httpx.Client(base_url=a.base, timeout=60)
    health = c.get("/api/v1/health").json()
    ok(f"API healthy ({health['server']}, mode {health['mode']})")
    assert "<div id=\"root\">" in c.get("/").text
    ok("SPA served from the API origin")
    sid = c.post("/api/v1/sessions", json={"kiosk_id": "smoke"}).json()["session_id"]
    spec = default_spec("dog", "corgi_pembroke", seed=918273, pet_name="Biscuit")
    spec["accessories"] = [{"type": "collar", "colour_hex": "#DD3333", "tag": True}]
    job = c.post("/api/v1/jobs", json={"session_id": sid, "spec": spec}).json()
    ok(f"job {job['job_id']} enqueued (queue position {job['queue_position']})")
    t0 = time.time()
    evs = asyncio.run(events(a.base, job["job_id"], a.timeout))
    assert evs and evs[-1]["status"] == "done", evs[-3:]
    ok(f"{len(evs)} progress events over WebSocket, done in {time.time() - t0:.0f} s "
       f"(previews: {sorted({e['preview_kind'] for e in evs if e.get('preview_kind')})})")
    j = c.get(f"/api/v1/jobs/{job['job_id']}").json()
    kinds = {x["kind"] for x in j["artefacts"]}
    assert {"concept", "view", "shape", "glb", "albedo", "uv_obj", "stl", "3mf", "mask", "manifest"} <= kinds, kinds
    for art in j["artefacts"]:
        r = c.get(art["url"])
        assert r.status_code == 200 and len(r.content) == art["bytes"], art["name"]
    ok(f"{len(j['artefacts'])} artefacts downloaded from the object store through signed URLs")
    manifest = c.get(next(x["url"] for x in j["artefacts"] if x["kind"] == "manifest")).json()
    assert not manifest_errors(manifest), manifest_errors(manifest)
    ok(f"manifest valid: GenAI profile {manifest['genai']['profile']}, adapters {manifest['genai']['adapters']}, "
       f"watertight {manifest['metrics']['print_watertight']}")
    ful = c.post(f"/api/v1/jobs/{job['job_id']}/fulfil").json()
    ok(f"fulfilled, ticket {ful['ticket']} ({len(ful['files'])} files)")
    q = c.get("/api/v1/staff/queue", headers={"X-Staff-Token": a.staff_token}).json()
    assert q["recent"] and q["recent"][0]["job_id"] == job["job_id"]
    ok("staff queue lists the job")
    assert 'petpop_jobs{status="fulfilled"}' in c.get("/metrics").text
    ok("Prometheus metrics")
    page = c.get(f"/api/v1/r/{j['result_url'].rsplit('/r/', 1)[1]}").json()
    assert c.get(page["glb_url"]).content[:4] == b"glTF"
    ok("QR result page and GLB")
    print("STACK SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
