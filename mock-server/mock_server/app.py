"""Standalone PetPop mock server (BRIEF Section 13, "Mock server, built first").

No database, queue or Blender. Implements the committed OpenAPI exactly via backend.core.contract:
breed search over the real preset files, /spec/parse with the rule-based parser, and jobs that follow a
script from mock-server/scripts/*.json using artefacts from the fixture pack.

Script selection: header-free so the kiosk can reach every state by pet name. A pet named after one of a
script's `trigger_names` (case-insensitive: "Slowpoke", "Oops", "Plan B") runs that script; otherwise
MOCK_SCRIPT (default "normal"). Timings are the script's real seconds x PETPOP_MOCK_SPEED.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import random
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi.responses import Response

from backend.core import models as m
from backend.core.breeds import breed_doc, search
from backend.core.contract import ApiError, check_sig, make_app, make_token, read_token, signed_file_url
from backend.core.parser import parse
from backend.core.paths import FIXTURES, ROOT, mock_speed
from backend.core.schemas import spec_errors
from backend.core.spec import apply_patch

SCRIPTS_DIR = ROOT / "mock-server" / "scripts"
PRINT_BUNDLE = ["figure.3mf", "figure.stl", "albedo.png", "figure_uv.obj", "paint_mask.png", "manifest.json"]
STAGE_ORDER = ["queued", "A", "control", "B", "C", "D", "E", "F", "done"]


def load_scripts() -> dict[str, dict[str, Any]]:
    return {p.stem: json.loads(p.read_text()) for p in sorted(SCRIPTS_DIR.glob("*.json"))}


def utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


@dataclass
class MockJob:
    job_id: str
    session_id: str
    spec: dict[str, Any]
    script: dict[str, Any]
    pet: str
    created: float
    start: float  # when the script's t=0 happens (after the queue)
    speed: float
    ticket: str | None = None
    manifest: dict[str, Any] = field(default_factory=dict)

    def scaled(self, s: float) -> float:
        return s * self.speed

    def queue_end(self) -> float:
        return self.start

    def end(self) -> float:
        return self.start + self.scaled(self.script["steps"][-1]["at_s"])

    def state(self, now: float) -> dict[str, Any]:
        """Status at wall time `now`: the last script step reached plus queue position."""
        if now < self.start:
            qlen = self.script.get("queue_job_s", 0) * self.speed
            ahead = 0
            if qlen > 0:
                ahead = int((self.start - now) // qlen) + 1
            return {"status": "queued", "stage": "queued", "pct": 0, "message": "Waiting for the studio",
                    "queue_position": max(ahead, 1), "step": -1}
        t = (now - self.start)
        idx = 0
        for i, step in enumerate(self.script["steps"]):
            if self.scaled(step["at_s"]) <= t + 1e-9:
                idx = i
        step = self.script["steps"][idx]
        last = idx == len(self.script["steps"]) - 1
        if last and self.script["outcome"] == "failed":
            status = "failed"
        elif last:
            status = "fulfilled" if self.ticket else "done"
        else:
            status = "running"
        return {"status": status, "stage": step["stage"] if status != "failed" else step["stage"],
                "pct": step["pct"], "message": step["message"], "queue_position": 0, "step": idx}


class MockApi:
    mode = "mock"
    server = "mock-server"

    def __init__(self) -> None:
        self.staff_token = os.environ.get("PETPOP_STAFF_TOKEN", "dev-staff-token")
        self.secret = os.environ.get("PETPOP_SECRET") or secrets.token_hex(16)
        self.scripts = load_scripts()
        self.default_script = os.environ.get("MOCK_SCRIPT", "normal")
        self.sessions: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, MockJob] = {}
        self.index = json.loads((FIXTURES / "index.json").read_text())["pets"]

    # ----------------------------------------------------------------- helpers
    def _pick_script(self, spec: dict[str, Any]) -> dict[str, Any]:
        name = (spec.get("pet_name") or "").strip().lower()
        for s in self.scripts.values():
            if name and name in [t.lower() for t in s.get("trigger_names", [])]:
                return s
        return self.scripts[self.default_script]

    def _pick_pet(self, spec: dict[str, Any]) -> str:
        same = [p for p in self.index if p["species"] == spec["species"]]
        exact = [p for p in same if p["breed"] == spec.get("breed", {}).get("id")]
        pool = exact or same or self.index
        return pool[int(spec.get("seed", 0)) % len(pool)]["id"]

    def _fixture_manifest(self, pet: str) -> dict[str, Any]:
        return json.loads((FIXTURES / pet / "manifest.json").read_text())

    def _job(self, job_id: str) -> MockJob:
        job = self.jobs.get(job_id)
        if not job:
            raise ApiError(404, f"unknown job {job_id}")
        return job

    def _url(self, job: MockJob, name: str, base: str = "") -> str:
        return signed_file_url(self.secret, f"jobs/{job.job_id}/{name}", base=base)

    def _enqueue(self, session_id: str, spec: dict[str, Any], script: dict[str, Any] | None = None) -> MockJob:
        now = time.time()
        speed = mock_speed()
        script = script or self._pick_script(spec)
        busy_until = max([j.end() for j in self.jobs.values()] + [now])  # one GPU: jobs run back to back
        start = max(now, busy_until) + script.get("queue_ahead", 0) * script.get("queue_job_s", 0) * speed
        job = MockJob(job_id="j_" + uuid.uuid4().hex[:12], session_id=session_id, spec=spec, script=script,
                      pet=self._pick_pet(spec), created=now, start=start, speed=speed)
        job.manifest = self._fixture_manifest(job.pet)
        self.jobs[job.job_id] = job
        return job

    def _reached_files(self, job: MockJob, step_idx: int) -> list[str]:
        """Files whose stage the script has passed. A failed job keeps what it had; fallbacks skip shape."""
        done = job.state(time.time())["status"] in ("done", "fulfilled")
        steps = job.script["steps"][: step_idx + 1]
        reached = {s["stage"] for s in steps}
        names = [f["name"] for f in job.manifest["files"]]
        out = []
        for f in job.manifest["files"]:
            st = f["stage"]
            if st in ("A", "control") and reached & {"control", "B", "C", "D", "E", "F", "done"}:
                out.append(f["name"])
            elif st == "B" and any(s.get("preview_kind") == "concept" for s in steps):
                out.append(f["name"])
            elif st == "C" and any(s.get("preview_kind") == "view_front" for s in steps):
                out.append(f["name"])
            elif st == "D" and any(s.get("preview_kind") == "shape" for s in steps):
                out.append(f["name"])
            elif st in ("E", "F") and done:
                out.append(f["name"])
        if done and "manifest.json" not in names:
            out.append("manifest.json")
        return out

    def _kind(self, job: MockJob, name: str) -> tuple[str, str, int]:
        if name == "manifest.json":
            return "manifest", "F", len(json.dumps(job.manifest))
        for f in job.manifest["files"]:
            if f["name"] == name:
                return f["kind"], f["stage"], f["bytes"]
        raise KeyError(name)

    def _session_left(self, session_id: str) -> int:
        s = self.sessions[session_id]
        return s["policy"].max_generations - s["count"]

    # ----------------------------------------------------------------- API
    async def create_session(self, body: m.SessionCreate) -> m.Session:
        sid = "s_" + uuid.uuid4().hex[:12]
        policy = m.IdlePolicy()
        self.sessions[sid] = {"kiosk_id": body.kiosk_id, "started": time.time(), "count": 0, "policy": policy}
        return m.Session(session_id=sid, kiosk_id=body.kiosk_id, started_at=utc(time.time()), idle_policy=policy,
                         generate_count=0, generations_left=policy.max_generations)

    async def breeds(self, species: str, q: str | None) -> m.BreedList:
        items = search(species, q)
        return m.BreedList(species=species, accent=breed_doc(species)["accent"], total=len(items),
                           items=[m.Breed(**b) for b in items])

    async def parse(self, req: m.ParseRequest) -> m.ParseResponse:
        r = parse(req.text, req.species, req.current_spec, req.tapped_fields)
        return m.ParseResponse(patch=r.patch, changed_fields=r.changed_fields, personality=r.personality,
                               free_text_unmapped=r.free_text_unmapped, parser="rules", llm_available=False,
                               flavour_only=bool(req.text.strip()) and not r.changed_fields, blocked=r.blocked,
                               ms=r.ms)

    def _check_spec(self, spec: dict[str, Any]) -> None:
        errs = spec_errors(spec)
        if errs:
            raise ApiError(422, {"spec": errs})

    async def create_job(self, body: m.JobCreate) -> m.JobCreated:
        if body.session_id not in self.sessions:
            raise ApiError(404, "unknown session")
        self._check_spec(body.spec)
        if self._session_left(body.session_id) <= 0:
            raise ApiError(409, "This session has used all of its figurines.")
        self.sessions[body.session_id]["count"] += 1
        job = self._enqueue(body.session_id, body.spec)
        st = job.state(time.time())
        return m.JobCreated(job_id=job.job_id, status=st["status"], queue_position=st["queue_position"],
                            generations_left=self._session_left(body.session_id))

    async def get_job(self, job_id: str, base: str) -> m.Job:
        job = self._job(job_id)
        now = time.time()
        st = job.state(now)
        files = self._reached_files(job, st["step"]) if st["step"] >= 0 else []
        artefacts = []
        for name in files:
            kind, stage, nbytes = self._kind(job, name)
            artefacts.append(m.Artefact(name=name, kind=kind, stage=stage, url=self._url(job, name), bytes=nbytes))
        previews: dict[str, str] = {}
        for step in job.script["steps"][: st["step"] + 1]:
            if step.get("preview"):
                previews[step["preview_kind"]] = self._url(job, step["preview"])
            for name, kind in step.get("also", []):
                previews[kind] = self._url(job, name)
        if st["status"] in ("done", "fulfilled"):
            previews["thumbnail"] = self._url(job, "thumbnail.png")
        timings = []
        steps = job.script["steps"]
        for stage in STAGE_ORDER[1:-1]:
            at = [s["at_s"] for s in steps if s["stage"] == stage]
            if not at:
                continue
            nxt = [s["at_s"] for s in steps if STAGE_ORDER.index(s["stage"]) > STAGE_ORDER.index(stage)]
            begin, end = min(at), (min(nxt) if nxt else max(at))
            if job.start + job.scaled(begin) > now:
                continue
            finished = job.start + job.scaled(end) <= now
            status = "ok" if finished else "running"
            if job.script["outcome"] == "failed" and stage == steps[-1]["stage"] and st["status"] == "failed":
                status = "failed"
            if job.script.get("fallback") == "parametric" and stage == "D" and finished:
                status = "fallback"
            timings.append(m.StageTiming(stage=stage, status=status, ms=int((end - begin) * 1000),
                                         started_at=utc(job.start + job.scaled(begin)),
                                         ended_at=utc(job.start + job.scaled(end)) if finished else None))
        done = st["status"] in ("done", "fulfilled")
        result_url = f"{base}/r/{make_token(self.secret, job.job_id)}" if done else None
        return m.Job(job_id=job.job_id, session_id=job.session_id, status=st["status"], stage=st["stage"],
                     pct=st["pct"], message=st["message"], queue_position=st["queue_position"],
                     seed=job.spec["seed"], species=job.spec["species"], pet_name=job.spec.get("pet_name"),
                     created_at=utc(job.created), finished_at=utc(job.end()) if done or st["status"] == "failed"
                     else None, error=job.script.get("error") if st["status"] == "failed" else None,
                     fallback=job.script.get("fallback", "none") if done else "none",
                     fidelity=job.manifest.get("fidelity", "low"), timings=timings, artefacts=artefacts,
                     previews=previews, result_url=result_url, ticket=job.ticket, spec=job.spec)

    async def job_events(self, job_id: str, base: str) -> AsyncIterator[m.ProgressEvent]:
        job = self._job(job_id)
        last_key = None
        sent_steps: set[int] = set()
        while True:
            now = time.time()
            st = job.state(now)
            # Emit every step passed since the last frame (speed 0 passes them all at once).
            first = max(sent_steps) + 1 if sent_steps else 0
            for i in range(first, st["step"] + 1):
                step = job.script["steps"][i]
                sent_steps.add(i)
                status = "running"
                if i == len(job.script["steps"]) - 1:
                    status = st["status"]
                yield m.ProgressEvent(job_id=job_id, status=status, stage=step["stage"], pct=step["pct"],
                                      message=step["message"], queue_position=0,
                                      preview_url=self._url(job, step["preview"]) if step.get("preview") else None,
                                      preview_kind=step.get("preview_kind"))
                for name, kind in step.get("also", []):
                    yield m.ProgressEvent(job_id=job_id, status="running", stage=step["stage"], pct=step["pct"],
                                          message=step["message"], preview_url=self._url(job, name),
                                          preview_kind=kind)
            if st["step"] < 0:
                key = ("queued", st["queue_position"])
                if key != last_key:
                    last_key = key
                    yield m.ProgressEvent(job_id=job_id, status="queued", stage="queued", pct=0,
                                          message=st["message"], queue_position=st["queue_position"])
            if st["status"] in ("done", "failed", "fulfilled"):
                return
            await asyncio.sleep(0.1)

    async def tweak(self, job_id: str, req: m.TweakRequest) -> m.JobCreated:
        old = self._job(job_id)
        spec, _ = apply_patch(old.spec, req.patch)
        spec["seed"] = old.spec["seed"]
        return await self.create_job(m.JobCreate(session_id=req.session_id, spec=spec))

    async def fulfil(self, job_id: str) -> m.FulfilResponse:
        job = self._job(job_id)
        st = job.state(time.time())["status"]
        if st not in ("done", "fulfilled"):
            raise ApiError(409, "job is not finished")
        if not job.ticket:
            job.ticket = f"PP-{random.randint(1000, 9999)}"
        return m.FulfilResponse(job_id=job_id, ticket=job.ticket, files=PRINT_BUNDLE)

    async def result(self, token: str, base: str) -> m.ResultPage:
        job_id, exp = read_token(self.secret, token)
        job = self._job(job_id)
        return m.ResultPage(job_id=job_id, pet_name=job.spec.get("pet_name"), species=job.spec["species"],
                            breed_label=job.spec["breed"]["label"], glb_url=self._url(job, "figure.glb"),
                            thumbnail_url=self._url(job, "thumbnail.png"), turntable_url=None,
                            created_at=utc(job.created), expires_at=utc(exp))

    async def file(self, key: str, exp: int, sig: str) -> Response:
        if not check_sig(self.secret, key, exp, sig):
            raise ApiError(403, "bad or expired signature")
        parts = key.split("/", 2)
        if len(parts) != 3 or parts[0] != "jobs":
            raise ApiError(404, "unknown file")
        job = self._job(parts[1])
        name = parts[2]
        if name == "manifest.json":
            return Response(json.dumps(job.manifest, indent=1), media_type="application/json")
        path = (FIXTURES / job.pet / name).resolve()
        if not str(path).startswith(str(FIXTURES.resolve())) or not path.is_file():
            raise ApiError(404, "unknown file")
        media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".glb":
            media = "model/gltf-binary"
        return Response(path.read_bytes(), media_type=media, headers={"Cache-Control": "private, max-age=3600"})

    def _staff_job(self, job: MockJob) -> m.StaffJob:
        st = job.state(time.time())
        done = st["status"] in ("done", "fulfilled", "failed")
        return m.StaffJob(job_id=job.job_id, status=st["status"], stage=st["stage"],
                          pet_name=job.spec.get("pet_name"), species=job.spec["species"],
                          created_at=utc(job.created), finished_at=utc(job.end()) if done else None,
                          fallback=job.script.get("fallback", "none"),
                          total_ms=int((job.end() - job.start) * 1000) if done else None,
                          thumbnail_url=self._url(job, "thumbnail.png") if st["status"] in ("done", "fulfilled")
                          else None, error=job.script.get("error") if st["status"] == "failed" else None)

    async def staff_queue(self, base: str) -> m.StaffQueue:
        now = time.time()
        jobs = sorted(self.jobs.values(), key=lambda j: j.created)
        states = [(j, j.state(now)["status"]) for j in jobs]
        running = next((self._staff_job(j) for j, s in states if s == "running"), None)
        queued = [self._staff_job(j) for j, s in states if s == "queued"]
        recent = [self._staff_job(j) for j, s in reversed(states) if s in ("done", "failed", "fulfilled")][:20]
        return m.StaffQueue(mode="mock", running=running, queued=queued, recent=recent,
                            gpu=m.GpuStatus(name="mock (no GPU)", temp_c=41.0, vram_used_mb=0, mock=True))

    async def staff_retry(self, job_id: str) -> m.JobCreated:
        old = self._job(job_id)
        job = self._enqueue(old.session_id, old.spec, self.scripts["normal"])
        st = job.state(time.time())
        return m.JobCreated(job_id=job.job_id, status=st["status"], queue_position=st["queue_position"],
                            generations_left=self._session_left(old.session_id))


def create_app():
    return make_app(MockApi(), title="PetPop mock server")

