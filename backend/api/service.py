"""The real backend's implementation of the /api/v1 contract (BRIEF Section 9).

The API never touches the GPU: it validates, writes jobs to the database, enqueues them, streams progress
from the bus and serves artefacts through signed URLs. Mounted on backend.core.contract like the mock.
"""
from __future__ import annotations

import asyncio
import mimetypes
import random
import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from fastapi.responses import Response
from sqlalchemy import func, select

from backend.core import models as m
from backend.core.breeds import breed_doc
from backend.core.config import Settings
from backend.core.contract import ApiError, check_sig, make_token, read_token, signed_file_url
from backend.core.schemas import spec_errors
from backend.core.spec import apply_patch, fill_colour_names

from .bus import make_bus
from .db import ArtefactRow, BreedRow, JobRow, SessionRow, StageTimingRow, seed_breeds, session_factory, utcnow
from .store import make_store

PRINT_BUNDLE = ["figure.3mf", "figure.stl", "albedo.png", "figure_uv.obj", "paint_mask.png", "manifest.json"]
TERMINAL = {"done", "failed", "fulfilled"}
POLICY = m.IdlePolicy()


def aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=UTC) if dt and dt.tzinfo is None else dt


class BackendApi:
    server = "backend"

    def __init__(self, s: Settings) -> None:
        self.s = s
        self.mode = s.mode
        self.staff_token = s.staff_token
        self.secret = s.secret
        self.db = session_factory(s.database_url)
        seed_breeds(self.db)
        self.bus = make_bus(s, self.db)
        self.store = make_store(s)

    # ------------------------------------------------------------------ helpers
    def _url(self, key: str) -> str:
        return signed_file_url(self.secret, key)

    def _job(self, db, job_id: str) -> JobRow:
        job = db.get(JobRow, job_id)
        if not job:
            raise ApiError(404, f"unknown job {job_id}")
        return job

    def _queue_position(self, db, job: JobRow) -> int:
        if job.status != "queued":
            return 0
        ahead = db.scalar(select(func.count()).select_from(JobRow).where(JobRow.status == "queued", JobRow.created_at < job.created_at)) or 0
        running = db.scalar(select(func.count()).select_from(JobRow).where(JobRow.status == "running")) or 0
        return int(ahead + running + 1) if (ahead + running) else 1

    def _left(self, sess: SessionRow) -> int:
        return POLICY.max_generations - sess.generate_count

    def _new_job(self, db, session_id: str, spec: dict) -> JobRow:
        job = JobRow(id="j_" + uuid.uuid4().hex[:12], session_id=session_id, pet_spec=spec, status="queued", stage="queued",
                     seed=int(spec["seed"]), created_at=utcnow())
        db.add(job)
        db.commit()
        self.bus.enqueue(job.id)
        return job

    def _check_spec(self, spec: dict) -> dict:
        spec = fill_colour_names(spec)
        errs = spec_errors(spec)
        if errs:
            raise ApiError(422, {"spec": errs})
        return spec

    def _public_base(self, base: str) -> str:
        return self.s.public_url.rstrip("/") or base

    # ------------------------------------------------------------------ kiosk
    async def create_session(self, body: m.SessionCreate) -> m.Session:
        with self.db() as db:
            row = SessionRow(id="s_" + uuid.uuid4().hex[:12], kiosk_id=body.kiosk_id, started_at=utcnow(), generate_count=0)
            db.add(row)
            db.commit()
            return m.Session(session_id=row.id, kiosk_id=row.kiosk_id, started_at=aware(row.started_at), idle_policy=POLICY,
                             generate_count=0, generations_left=POLICY.max_generations)

    async def breeds(self, species: str, q: str | None) -> m.BreedList:
        with self.db() as db:
            rows = db.scalars(select(BreedRow).where(BreedRow.species == species)).all()
        items = [{"id": r.id, "species": r.species, "label": r.label, "prompt_hint": r.prompt_hint, "preset": r.preset} for r in rows]
        if q:
            ql = q.strip().lower()
            items = [b for b in items if ql in b["label"].lower() or ql in b["id"]]
            items.sort(key=lambda b: (not b["label"].lower().startswith(ql),
                                      not any(w.startswith(ql) for w in b["label"].lower().split()), b["label"]))
        else:
            items.sort(key=lambda b: b["label"])
        items = [b for b in items if b["id"] != "mixed"] + [b for b in items if b["id"] == "mixed"]
        return m.BreedList(species=species, accent=breed_doc(species)["accent"], total=len(items), items=[m.Breed(**b) for b in items])

    async def parse(self, req: m.ParseRequest) -> m.ParseResponse:
        from backend.worker.backends.base import make_backends

        parser = make_backends(self.s).parser
        llm = parser.name == "llm" and await asyncio.to_thread(parser.available)
        try:
            r = await asyncio.wait_for(asyncio.to_thread(parser.parse, req.text, req.species, req.current_spec, req.tapped_fields), 3.0)
        except Exception:  # noqa: BLE001 - LLM down or slow: taps alone, brief for flavour only
            from backend.core.parser import parse as rules

            r, llm = rules(req.text, req.species, req.current_spec, req.tapped_fields), False
        return m.ParseResponse(patch=r.patch, changed_fields=r.changed_fields, personality=r.personality,
                               free_text_unmapped=r.free_text_unmapped, parser="llm" if llm else "rules", llm_available=llm,
                               flavour_only=bool(req.text.strip()) and not r.changed_fields, blocked=r.blocked, ms=r.ms)

    async def create_job(self, body: m.JobCreate) -> m.JobCreated:
        spec = self._check_spec(body.spec)
        with self.db() as db:
            sess = db.get(SessionRow, body.session_id)
            if not sess:
                raise ApiError(404, "unknown session")
            if self._left(sess) <= 0:
                raise ApiError(409, "This session has used all of its figurines.")
            sess.generate_count += 1
            job = self._new_job(db, sess.id, spec)
            return m.JobCreated(job_id=job.id, status="queued", queue_position=self._queue_position(db, job),
                                generations_left=self._left(sess))

    async def get_job(self, job_id: str, base: str) -> m.Job:
        with self.db() as db:
            job = self._job(db, job_id)
            arts = db.scalars(select(ArtefactRow).where(ArtefactRow.job_id == job_id).order_by(ArtefactRow.id)).all()
            timings = db.scalars(select(StageTimingRow).where(StageTimingRow.job_id == job_id).order_by(StageTimingRow.id)).all()
            qpos = self._queue_position(db, job)
        artefacts = [m.Artefact(name=a.name, kind=a.kind, stage=a.stage, url=self._url(a.object_key), bytes=a.bytes)
                     for a in arts if not a.name.endswith(".npy")]
        previews: dict[str, str] = {}
        for a in arts:
            if a.kind == "concept":
                previews["concept"] = self._url(a.object_key)
            elif a.kind == "view":
                previews[f"view_{a.name.split('/')[-1].removesuffix('.png')}"] = self._url(a.object_key)
            elif a.kind in ("shape", "glb", "thumbnail", "turntable"):
                previews[a.kind] = self._url(a.object_key)
        done = job.status in ("done", "fulfilled")
        if not done:
            previews.pop("glb", None)
        return m.Job(job_id=job.id, session_id=job.session_id, status=job.status, stage=job.stage, pct=job.pct, message=job.message,
                     queue_position=qpos, seed=job.seed, species=job.pet_spec["species"], pet_name=job.pet_spec.get("pet_name"),
                     created_at=aware(job.created_at), finished_at=aware(job.finished_at), error=job.error, fallback=job.fallback,
                     fidelity=job.fidelity, timings=[m.StageTiming(stage=t.stage, status=t.status, ms=t.ms, started_at=aware(t.started_at),
                                                                   ended_at=aware(t.ended_at)) for t in timings],
                     artefacts=artefacts, previews=previews,
                     result_url=f"{self._public_base(base)}/r/{make_token(self.secret, job.id)}" if done else None,
                     ticket=job.ticket, spec=job.pet_spec)

    async def job_events(self, job_id: str, base: str) -> AsyncIterator[m.ProgressEvent]:
        with self.db() as db:
            self._job(db, job_id)
        after = 0
        last_queue = None
        while True:
            events = await asyncio.to_thread(self.bus.tail, job_id, after)
            for eid, ev in events:
                after = eid
                key = ev.pop("preview_key", None)
                yield m.ProgressEvent(**{**ev, "preview_url": self._url(key) if key else None})
                if ev["status"] in TERMINAL:
                    return
            with self.db() as db:
                job = db.get(JobRow, job_id)
                if job.status == "queued":
                    pos = self._queue_position(db, job)
                    if pos != last_queue:
                        last_queue = pos
                        yield m.ProgressEvent(job_id=job_id, status="queued", stage="queued", pct=0, message="Waiting for the studio",
                                              queue_position=pos)
                elif job.status in TERMINAL and not events:
                    # Terminal before we subscribed and no terminal event left to replay.
                    if not await asyncio.to_thread(self.bus.tail, job_id, after):
                        yield m.ProgressEvent(job_id=job_id, status=job.status, stage=job.stage, pct=job.pct, message=job.message)
                        return
            await asyncio.sleep(0.25)

    async def tweak(self, job_id: str, req: m.TweakRequest) -> m.JobCreated:
        with self.db() as db:
            old = self._job(db, job_id)
            spec, _ = apply_patch(old.pet_spec, req.patch)
            spec["seed"] = old.seed
        return await self.create_job(m.JobCreate(session_id=req.session_id, spec=spec))

    async def fulfil(self, job_id: str) -> m.FulfilResponse:
        with self.db() as db:
            job = self._job(db, job_id)
            if job.status not in ("done", "fulfilled"):
                raise ApiError(409, "job is not finished")
            if not job.ticket:
                job.ticket = f"PP-{random.randint(1000, 9999)}"
            ticket = job.ticket
            folder = self.s.fulfil_dir / f"{ticket}_{job_id}"
            folder.mkdir(parents=True, exist_ok=True)
            files = []
            for name in PRINT_BUNDLE:
                key = f"jobs/{job_id}/{name}"
                if self.store.exists(key):
                    (folder / name).write_bytes(self.store.get(key))
                    files.append(name)
            job.status = "fulfilled"
            db.commit()
        return m.FulfilResponse(job_id=job_id, ticket=ticket, files=files)

    async def result(self, token: str, base: str) -> m.ResultPage:
        job_id, exp = read_token(self.secret, token)
        with self.db() as db:
            job = self._job(db, job_id)
            arts = {a.kind: a for a in db.scalars(select(ArtefactRow).where(ArtefactRow.job_id == job_id)).all()}
        if "glb" not in arts:
            raise ApiError(404, "result not ready")
        url = lambda k: self._url(arts[k].object_key) if k in arts else None  # noqa: E731
        return m.ResultPage(job_id=job_id, pet_name=job.pet_spec.get("pet_name"), species=job.pet_spec["species"],
                            breed_label=job.pet_spec["breed"]["label"], glb_url=url("glb"), thumbnail_url=url("thumbnail"),
                            turntable_url=url("turntable"), created_at=aware(job.created_at),
                            expires_at=datetime.fromtimestamp(exp, UTC))

    async def file(self, key: str, exp: int, sig: str) -> Response:
        if not check_sig(self.secret, key, exp, sig):
            raise ApiError(403, "bad or expired signature")
        try:
            data = await asyncio.to_thread(self.store.get, key)
        except KeyError as exc:
            raise ApiError(404, "unknown file") from exc
        media = mimetypes.guess_type(key)[0] or "application/octet-stream"
        if key.endswith(".glb"):
            media = "model/gltf-binary"
        return Response(data, media_type=media, headers={"Cache-Control": "private, max-age=3600"})

    # ------------------------------------------------------------------ staff
    def _staff_job(self, job: JobRow) -> m.StaffJob:
        thumb = f"jobs/{job.id}/thumbnail.png"
        total = int((job.finished_at - job.started_at).total_seconds() * 1000) if job.finished_at and job.started_at else None
        return m.StaffJob(job_id=job.id, status=job.status, stage=job.stage, pet_name=job.pet_spec.get("pet_name"),
                          species=job.pet_spec["species"], created_at=aware(job.created_at), finished_at=aware(job.finished_at),
                          fallback=job.fallback, total_ms=total,
                          thumbnail_url=self._url(thumb) if job.status in ("done", "fulfilled") else None, error=job.error)

    async def staff_queue(self, base: str) -> m.StaffQueue:
        with self.db() as db:
            running = db.scalars(select(JobRow).where(JobRow.status == "running")).first()
            queued = db.scalars(select(JobRow).where(JobRow.status == "queued").order_by(JobRow.created_at)).all()
            recent = db.scalars(select(JobRow).where(JobRow.status.in_(TERMINAL)).order_by(JobRow.finished_at.desc()).limit(20)).all()
        return m.StaffQueue(mode=self.mode, running=self._staff_job(running) if running else None,
                            queued=[self._staff_job(j) for j in queued], recent=[self._staff_job(j) for j in recent],
                            gpu=gpu_status(self.s))

    async def staff_retry(self, job_id: str) -> m.JobCreated:
        """Re-run a job's spec as a new job (does not count against the session cap)."""
        with self.db() as db:
            old = self._job(db, job_id)
            job = self._new_job(db, old.session_id, old.pet_spec)
            return m.JobCreated(job_id=job.id, status="queued", queue_position=self._queue_position(db, job), generations_left=0)

    # ------------------------------------------------------------------ housekeeping
    def purge_free_text(self, days: int = 7) -> int:
        """Privacy (Section 11): free text is removed from stored specs after 7 days."""
        cutoff = utcnow() - timedelta(days=days)
        n = 0
        with self.db() as db:
            for job in db.scalars(select(JobRow).where(JobRow.created_at < cutoff)).all():
                if job.pet_spec.get("free_text"):
                    job.pet_spec = {**job.pet_spec, "free_text": ""}
                    n += 1
            db.commit()
        return n


def gpu_status(s: Settings) -> m.GpuStatus:
    if s.mode == "mock":
        return m.GpuStatus(name="none (mock mode, CPU)", temp_c=None, vram_used_mb=None, mock=True)
    smi = shutil.which("nvidia-smi")
    if smi:
        import subprocess

        try:
            out = subprocess.run([smi, "--query-gpu=name,temperature.gpu,memory.used", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=3).stdout.strip().splitlines()[0]
            name, temp, mem = [x.strip() for x in out.split(",")]
            return m.GpuStatus(name=name, temp_c=float(temp), vram_used_mb=int(float(mem)), mock=False)
        except Exception:  # noqa: BLE001
            pass
    return m.GpuStatus(name="unknown", temp_c=None, vram_used_mb=None, mock=False)
