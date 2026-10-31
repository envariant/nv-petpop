"""The real backend's implementation of the /api/v1 contract (BRIEF Sections 9 and 17).

The API never touches the GPU: it validates, writes jobs to the database, enqueues them on the kiosk or studio
queue, streams progress from the bus and serves artefacts through signed URLs. Mounted on
backend.api.contract like the mock. The kiosk routes never reach the GenAI host.
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

from backend.api import models as m
from petpop_core.breeds import breed_doc
from backend.core.config import Settings
from backend.core.genai import ProfileError, profile_name, profiles_offered, resolve, resolve_options, resolve_pipeline
from backend.api.contract import ApiError, check_sig, make_token, read_token, signed_file_url
from petpop_core.schemas import spec_errors
from petpop_core.spec import apply_patch, fill_colour_names

from .bus import make_bus
from .fulfilment import copy_bundle
from .library import KioskLibrary
from .studio_library import StudioLibrary
from .db import (ArtefactRow, BreedRow, CompositionRow, JobRow, ManualTaskRow, SessionRow, StaffUserRow, StageTimingRow, check_password, seed_breeds,
                 seed_staff, session_factory, utcnow)
from .store import make_store

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
        seed_staff(self.db, s.studio_users)
        self.bus = make_bus(s, self.db)
        self.store = make_store(s)
        self.library = KioskLibrary(s, self.db, self.bus, self.store, self.secret)
        self.library.load_releases()
        self.studio = StudioLibrary(s, self.db, self.store, self.bus, self.secret)
        self.studio.seed()

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
        same = JobRow.queue == job.queue
        ahead = db.scalar(select(func.count()).select_from(JobRow).where(same, JobRow.status == "queued",
                                                                         JobRow.created_at < job.created_at)) or 0
        running = db.scalar(select(func.count()).select_from(JobRow).where(same, JobRow.status == "running")) or 0
        return int(ahead + running + 1) if (ahead + running) else 1

    def _new_job(self, db, spec: dict, *, queue: str, kind: str, requested_by: str, session_id: str | None = None,
                 contact: str | None = None, genai_profile: str | None = None, pipeline: str | None = None,
                 options: dict[str, bool] | None = None) -> JobRow:
        profile = None if queue == "kiosk" else (genai_profile or profile_name())
        job = JobRow(id="j_" + uuid.uuid4().hex[:12], queue=queue, kind=kind, session_id=session_id,
                     requested_by=requested_by, contact=contact, pet_spec=spec, status="queued", stage="queued",
                     seed=int(spec["seed"]), created_at=utcnow(), genai_profile=profile,
                     pipeline=(pipeline or resolve_pipeline(profile, None, kind)) if profile else None,
                     options=(options if options is not None else resolve_options(profile, None)) if profile else None)
        db.add(job)
        db.commit()
        self.bus.enqueue(job.id, queue)
        return job

    def _created(self, db, job: JobRow) -> m.JobCreated:
        return m.JobCreated(job_id=job.id, status="queued", queue_position=self._queue_position(db, job))

    # ------------------------------------------------------------------ studio auth
    def authenticate(self, username: str, password: str) -> str | None:
        with self.db() as db:
            row = db.get(StaffUserRow, username)
        return row.role if row and check_password(password, row.password_hash) else None

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
                             bespoke_enabled=self.s.kiosk_bespoke)

    async def bespoke(self, composition_id: str, body: m.BespokeRequest) -> m.BespokeAccepted:
        """"Make it unique" (KIOSK_BESPOKE): the composition becomes a studio bespoke job's starting spec; the kiosk
        shows "we'll message you", never a Generating screen."""
        if not self.s.kiosk_bespoke:
            raise ApiError(403, "bespoke mode is off on this kiosk")
        session_id, spec, _ = self.library.bespoke_spec(composition_id)
        spec = self._check_spec(spec)
        with self.db() as db:
            sess = db.get(SessionRow, session_id) if session_id else None
            if not sess:
                raise ApiError(404, "unknown session")
            comp = db.get(CompositionRow, composition_id)
            if sess.generate_count >= 1 or comp.bespoke_job_id:
                raise ApiError(409, "This session has already asked for a one-off figurine.")
            sess.generate_count += 1
            job = self._new_job(db, spec, queue="studio", kind="bespoke", requested_by=f"kiosk:{sess.kiosk_id}",
                                session_id=sess.id, contact=body.contact)
            job.ticket = f"PP-{random.randint(1000, 9999)}"
            comp.bespoke_job_id = job.id
            db.commit()
            return m.BespokeAccepted(request_id=job.id, ticket=job.ticket,
                                     message="We'll message you when your one-off figurine is ready.")

    async def kiosk_ops(self) -> m.KioskOps:
        with self.db() as db:
            counts = dict(db.execute(select(JobRow.status, func.count()).where(JobRow.queue == "kiosk")
                                     .group_by(JobRow.status)).all())
        return m.KioskOps(api_version=m.API_VERSION, mode=self.mode, kiosk_id=self.s.kiosk_id, releases=self.library.versions(),
                          bespoke_enabled=self.s.kiosk_bespoke, exports_queued=int(counts.get("queued", 0)),
                          exports_running=int(counts.get("running", 0)), orders=self.library.orders())

    async def kiosk_reprint(self, composition_id: str) -> m.KioskOrder:
        return self.library.reprint(composition_id)

    # ------------------------------------------------------------------ kiosk library mode
    async def library_release(self, species: str) -> m.LibraryRelease:
        return self.library.release_info(species)

    async def library_families(self, species: str) -> m.LibraryFamilies:
        return self.library.families(species)

    async def library_parts(self, species: str, region: str | None) -> m.LibraryParts:
        return self.library.parts(species, region)

    async def library_patterns(self, species: str) -> m.LibraryPatterns:
        return self.library.patterns(species)

    async def library_file(self, species: str, path: str) -> Response:
        data, media = await asyncio.to_thread(self.library.file, species, path)
        return Response(data, media_type=media, headers={"Cache-Control": "public, max-age=86400, immutable"})

    async def create_composition(self, body: m.CompositionCreate, base: str) -> m.CompositionStatus:
        return self.library.create(body, self._public_base(base))

    async def get_composition(self, composition_id: str, base: str) -> m.CompositionStatus:
        return self.library.status(composition_id, self._public_base(base))

    async def export_composition(self, composition_id: str) -> m.ExportAccepted:
        return self.library.export(composition_id)

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
            from petpop_core.parser import parse as rules

            r, llm = rules(req.text, req.species, req.current_spec, req.tapped_fields), False
        return m.ParseResponse(patch=r.patch, changed_fields=r.changed_fields, personality=r.personality,
                               free_text_unmapped=r.free_text_unmapped, parser="llm" if llm else "rules", llm_available=llm,
                               flavour_only=bool(req.text.strip()) and not r.changed_fields, blocked=r.blocked, ms=r.ms)

    # ------------------------------------------------------------------ studio
    async def create_job(self, body: m.JobCreate, user: m.StaffUser) -> m.JobCreated:
        spec = self._check_spec(body.spec)
        profile, pipeline, options = self._profile(body.genai_profile, body.pipeline, body.options)
        with self.db() as db:
            return self._created(db, self._new_job(db, spec, queue="studio", kind="pipeline", requested_by=user.username,
                                                   genai_profile=profile, pipeline=pipeline, options=options))

    @staticmethod
    def _profile(requested: str | None, pipeline: str | None = None, options: dict[str, bool] | None = None,
                 kind: str = "pipeline") -> tuple[str, str | None, dict[str, bool]]:
        """The profile, pipeline and quality switches a new Studio job runs (decisions 113 to 115); 422 when not offered."""
        try:
            profile = resolve(requested)
            return profile, resolve_pipeline(profile, pipeline, kind), resolve_options(profile, options)
        except ProfileError as exc:
            raise ApiError(422, str(exc)) from exc

    async def genai_profiles(self) -> m.GenaiProfiles:
        return m.GenaiProfiles(**profiles_offered())

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
        return m.Job(job_id=job.id, kind=job.kind, session_id=job.session_id, requested_by=job.requested_by,
                     status=job.status, stage=job.stage, pct=job.pct, message=job.message,
                     queue_position=qpos, seed=job.seed, species=job.pet_spec["species"], pet_name=job.pet_spec.get("pet_name"),
                     created_at=aware(job.created_at), finished_at=aware(job.finished_at), error=job.error, fallback=job.fallback,
                     fidelity=job.fidelity, timings=[m.StageTiming(stage=t.stage, status=t.status, ms=t.ms, started_at=aware(t.started_at),
                                                                   ended_at=aware(t.ended_at)) for t in timings],
                     artefacts=artefacts, previews=previews,
                     result_url=f"{self._public_base(base)}/r/{make_token(self.secret, job.id)}" if done else None,
                     ticket=job.ticket, spec=job.pet_spec, genai_profile=job.genai_profile, pipeline=job.pipeline,
                     options=job.options)

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

    async def tweak(self, job_id: str, req: m.TweakRequest, user: m.StaffUser) -> m.JobCreated:
        with self.db() as db:
            old = self._job(db, job_id)
            spec, _ = apply_patch(old.pet_spec, req.patch)
            spec["seed"] = old.seed
            spec = self._check_spec(spec)
            # the tweak runs where the original ran, even if Studio no longer offers that profile for new jobs
            return self._created(db, self._new_job(db, spec, queue="studio", kind="pipeline", requested_by=user.username,
                                                   genai_profile=old.genai_profile, pipeline=old.pipeline, options=old.options))

    async def fulfil(self, job_id: str) -> m.FulfilResponse:
        with self.db() as db:
            job = self._job(db, job_id)
            if job.status not in ("done", "fulfilled"):
                raise ApiError(409, "job is not finished")
            if not job.ticket:
                job.ticket = f"PP-{random.randint(1000, 9999)}"
            ticket = job.ticket
            files = copy_bundle(self.s.fulfil_dir, self.store, job_id, ticket)
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

    # ------------------------------------------------------------------ manual mode (decision 111)
    def _manual(self, row: ManualTaskRow, job: JobRow) -> m.ManualTask:
        p = row.packet
        return m.ManualTask(task_id=row.id, job_id=row.job_id, status=row.status, capability=p["capability"], title=p["title"],
                            provider=p["provider"], vendor=p["vendor"], manifest=p["manifest"], route=p["route"],
                            request=p["request"], prompt=p.get("prompt"), negative_prompt=p.get("negative_prompt"),
                            settings=p.get("settings", []), inputs=[m.ManualInput(name=i["name"], url=self._url(i["key"]))
                                                                    for i in p.get("inputs", [])],
                            instructions=p.get("instructions", []), expects=m.ManualExpects(**p["expects"]),
                            species=job.pet_spec["species"], pet_name=job.pet_spec.get("pet_name"),
                            breed_label=(job.pet_spec.get("breed") or {}).get("label"), batch_id=job.batch_id,
                            created_at=aware(row.created_at), submitted_at=aware(row.submitted_at), result_name=row.result_name,
                            filled=list(p.get("filled", [])))

    async def manual_tasks(self, status: str, base: str) -> m.ManualTaskList:
        with self.db() as db:
            q = select(ManualTaskRow, JobRow).join(JobRow, JobRow.id == ManualTaskRow.job_id)
            if status != "all":
                q = q.where(ManualTaskRow.status == status)
            rows = db.execute(q.order_by(ManualTaskRow.created_at)).all()
            pending = db.scalar(select(func.count()).select_from(ManualTaskRow).where(ManualTaskRow.status == "pending")) or 0
            items = [self._manual(r, j) for r, j in rows]
        return m.ManualTaskList(pending=int(pending), items=items)

    async def manual_task(self, task_id: str, base: str) -> m.ManualTask:
        with self.db() as db:
            row = db.get(ManualTaskRow, task_id)
            if not row:
                raise ApiError(404, f"unknown manual task {task_id}")
            return self._manual(row, self._job(db, row.job_id))

    async def submit_manual(self, task_id: str, filename: str, data: bytes, user: m.StaffUser, base: str,
                            slot: str | None = None) -> m.ManualTask:
        """The operator's output for a waiting job: checked, stored where the job looks for it, and the job re-queued
        to resume from its stored stages. A views task takes one upload per slot and resumes when all are in."""
        from backend.worker.providers.manual import check_output

        with self.db() as db:
            row = db.get(ManualTaskRow, task_id)
            if not row:
                raise ApiError(404, f"unknown manual task {task_id}")
            if row.status != "pending":
                raise ApiError(409, "this task already has its output")
            expects = row.packet["expects"]
            slots = expects.get("slots") or []
            if slots and slot not in slots:
                raise ApiError(422, f"this task takes one image per view: name the slot ({', '.join(slots)})")
            why = check_output(expects["kind"], filename, data)
            if why:
                raise ApiError(422, why)
            key = row.packet["result_keys"][slot] if slots else row.packet["result_key"]
            await asyncio.to_thread(self.store.put, key, data)
            packet = dict(row.packet)
            packet["filled"] = sorted(set(packet.get("filled", [])) | ({slot} if slot else set()), key=lambda s: slots.index(s))
            row.packet, row.result_name = packet, filename[:120]
            job = self._job(db, row.job_id)
            if not slots or set(packet["filled"]) == set(slots):
                row.status, row.submitted_at, row.submitted_by = "submitted", utcnow(), user.username
                job.status, job.message = "queued", "Waiting for the studio"
                db.commit()
                self.bus.enqueue(job.id, job.queue)
            else:
                db.commit()
            return self._manual(row, job)

    # ------------------------------------------------------------------ staff
    def _staff_job(self, job: JobRow) -> m.StaffJob:
        thumb = f"jobs/{job.id}/thumbnail.png"
        total = int((job.finished_at - job.started_at).total_seconds() * 1000) if job.finished_at and job.started_at else None
        return m.StaffJob(job_id=job.id, kind=job.kind, requested_by=job.requested_by, status=job.status, stage=job.stage,
                          pet_name=job.pet_spec.get("pet_name"),
                          species=job.pet_spec["species"], created_at=aware(job.created_at), finished_at=aware(job.finished_at),
                          fallback=job.fallback, total_ms=total,
                          thumbnail_url=self._url(thumb) if job.status in ("done", "fulfilled") else None, error=job.error,
                          genai_profile=job.genai_profile, pipeline=job.pipeline, options=job.options)

    async def staff_queue(self, base: str) -> m.StaffQueue:
        studio = JobRow.queue == "studio"
        with self.db() as db:
            running = db.scalars(select(JobRow).where(studio, JobRow.status == "running")).first()
            queued = db.scalars(select(JobRow).where(studio, JobRow.status == "queued").order_by(JobRow.created_at)).all()
            recent = db.scalars(select(JobRow).where(studio, JobRow.status.in_(TERMINAL))
                                .order_by(JobRow.finished_at.desc()).limit(20)).all()
        return m.StaffQueue(mode=self.mode, running=self._staff_job(running) if running else None,
                            queued=[self._staff_job(j) for j in queued], recent=[self._staff_job(j) for j in recent],
                            gpu=gpu_status(self.s))

    async def staff_retry(self, job_id: str, user: m.StaffUser) -> m.JobCreated:
        """Re-run a job's spec as a new studio job of the same kind."""
        with self.db() as db:
            old = self._job(db, job_id)
            job = self._new_job(db, old.pet_spec, queue=old.queue, kind=old.kind, requested_by=user.username,
                                session_id=old.session_id, contact=old.contact, genai_profile=old.genai_profile,
                                pipeline=old.pipeline, options=old.options)
            return self._created(db, job)

    # ------------------------------------------------------------------ studio library (M8)
    async def create_batch(self, body: m.BatchCreate, user: m.StaffUser) -> m.Batch:
        profile, pipeline, options = self._profile(body.genai_profile, body.pipeline, body.options, "batch")
        body = body.model_copy(update={"genai_profile": profile, "pipeline": pipeline, "options": options})
        return await asyncio.to_thread(self.studio.create_batch, body, user)

    async def list_batches(self) -> m.BatchList:
        return await asyncio.to_thread(self.studio.batches)

    async def get_batch(self, batch_id: str) -> m.Batch:
        return await asyncio.to_thread(self.studio.batch, batch_id)

    async def review_batch(self, batch_id: str, body: m.ReviewRequest, user: m.StaffUser) -> m.Batch:
        return await asyncio.to_thread(self.studio.review, batch_id, body, user)

    async def library_items(self, species: str, kind: str | None, status: str | None) -> m.LibraryItemList:
        return await asyncio.to_thread(self.studio.items, species, kind, status)

    async def edit_item(self, species: str, kind: str, item_id: str, patch: m.LibraryItemPatch) -> m.LibraryItem:
        return await asyncio.to_thread(self.studio.edit, species, kind, item_id, patch)

    async def publish_item(self, species: str, kind: str, item_id: str, user: m.StaffUser) -> m.LibraryItem:
        return await asyncio.to_thread(self.studio.publish, species, kind, item_id, user)

    async def unpublish_item(self, species: str, kind: str, item_id: str) -> m.LibraryItem:
        return await asyncio.to_thread(self.studio.unpublish, species, kind, item_id)

    async def create_release(self, body: m.ReleaseCreate, user: m.StaffUser) -> m.ReleaseInfo:
        info = await asyncio.to_thread(self.studio.create_release, body.species, user)
        await asyncio.to_thread(self.library.load_releases)  # a kiosk on this box switches now, not at the next poll
        return info

    async def list_releases(self) -> m.ReleaseList:
        return await asyncio.to_thread(self.studio.releases)

    # ------------------------------------------------------------------ housekeeping
    def purge_free_text(self, days: int = 7) -> int:
        """Privacy (Section 11): free text is removed from stored specs after 7 days."""
        cutoff = utcnow() - timedelta(days=days)
        n = 0
        with self.db() as db:
            for job in db.scalars(select(JobRow).where(JobRow.created_at < cutoff)).all():
                if job.pet_spec.get("free_text") or job.contact:
                    job.pet_spec = {**job.pet_spec, "free_text": ""}
                    job.contact = None
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
