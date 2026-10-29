"""Worker processes, one per queue (BRIEF Section 17): each claims its queue's jobs one at a time, mirroring
progress, timings and artefacts into the database and the event bus (the arq entry points call run_job).

- studio: full pipeline jobs, bespoke requests from the kiosk and curation batches (each figurine is curated into
  library parts when its pipeline finishes). The only process that builds GenAI adapters, so the only one that
  ever reaches the GenAI host.
- kiosk: Stage-F-only library exports (M7) and nothing else. It never builds an adapter and never imports
  one, so a kiosk keeps taking orders with the GenAI host unreachable.

    python -m backend.worker --queue studio|kiosk
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from typing import Any

from sqlalchemy import delete, select

from backend.api.bus import make_bus
from backend.api.db import ArtefactRow, JobRow, StageTimingRow, session_factory, utcnow
from backend.api.store import make_store
from backend.core.config import Settings, settings

from .context import StageContext
from .runner import JobFailed, StageRunner

log = logging.getLogger("petpop.worker")


JOB_KINDS = {"studio": {"pipeline", "bespoke", "batch"}, "kiosk": {"export"}}


class Worker:
    def __init__(self, s: Settings | None = None, queue: str = "studio") -> None:
        if queue not in JOB_KINDS:
            raise ValueError(f"unknown queue {queue!r}")
        self.s = s or settings()
        self.queue = queue
        self.db = session_factory(self.s.database_url)
        self.bus = make_bus(self.s, self.db)
        self.store = make_store(self.s)
        self.backends = None
        if queue == "studio":
            from .backends.base import make_backends  # GenAI adapters: studio worker only

            self.backends = make_backends(self.s)
        self._stop = threading.Event()

    # ------------------------------------------------------------------ db mirrors
    def _update(self, job_id: str, **values: Any) -> None:
        with self.db() as db:
            job = db.get(JobRow, job_id)
            for k, v in values.items():
                setattr(job, k, v)
            db.commit()

    def _progress(self, job_id: str):
        def progress(stage: str, pct: int, message: str, preview: tuple[str, str] | None = None) -> None:
            self._update(job_id, stage=stage, pct=pct, message=message[:200])
            ev = {"job_id": job_id, "status": "running", "stage": stage, "pct": pct, "message": message, "queue_position": 0}
            if preview:
                ev["preview_kind"], ev["preview_key"] = preview
            self.bus.publish(job_id, ev)
        return progress

    def _artefact(self, job_id: str):
        def on_artefact(name: str, kind: str, stage: str, key: str, nbytes: int) -> None:
            with self.db() as db:
                db.execute(delete(ArtefactRow).where(ArtefactRow.job_id == job_id, ArtefactRow.name == name))
                db.add(ArtefactRow(job_id=job_id, stage=stage, kind=kind, name=name, object_key=key, bytes=nbytes))
                db.commit()
        return on_artefact

    def _stage(self, job_id: str):
        def on_stage(stage: str, status: str, ms: int, started: str | None) -> None:
            with self.db() as db:
                row = db.scalars(select(StageTimingRow).where(StageTimingRow.job_id == job_id, StageTimingRow.stage == stage)
                                 .order_by(StageTimingRow.id.desc())).first()
                if status == "running" or row is None:
                    db.add(StageTimingRow(job_id=job_id, stage=stage, status=status, started_at=utcnow(), ms=0))
                else:
                    row.status, row.ms, row.ended_at = status, ms, utcnow()
                db.commit()
        return on_stage

    # ------------------------------------------------------------------ run
    def _fail(self, job_id: str, stage: str, error: str) -> str:
        with self.db() as db:
            pct = db.get(JobRow, job_id).pct
        self._update(job_id, status="failed", stage=stage, finished_at=utcnow(), error=error[:500], message=f"Stage {stage} failed")
        self.bus.publish(job_id, {"job_id": job_id, "status": "failed", "stage": stage, "pct": pct,
                                  "message": f"Stage {stage} failed", "queue_position": 0})
        return "failed"

    def run_job(self, job_id: str) -> str:
        with self.db() as db:
            job = db.get(JobRow, job_id)
            kind, queue = job.kind, job.queue
        if queue != self.queue or kind not in JOB_KINDS[self.queue]:
            log.error("job %s (%s on %s) is not for the %s worker", job_id, kind, queue, self.queue)
            return self._fail(job_id, "queued", f"{kind} jobs do not run on the {self.queue} queue")
        if kind == "export":
            return self.run_export(job_id)
        result = self.run_pipeline(job_id)
        if kind == "batch" and result == "done":
            return self.curate(job_id)
        return result

    def curate(self, job_id: str) -> str:
        """A batch figurine (M8): extract its family and region parts, run QC, file them for review."""
        from backend.api.studio_library import curate

        try:
            report = curate(self.db, self.store, job_id)
            log.info("curated %s: passed %s", job_id, ", ".join(report["passed_regions"]) or "nothing")
            return "done"
        except Exception as exc:  # noqa: BLE001 - the figurine stays visible in review with the error
            log.exception("curation of %s failed", job_id)
            return self._fail(job_id, "F", f"curation failed: {exc}")

    def run_export(self, job_id: str) -> str:
        """A library export (BRIEF Section 16): Stage F only, from the composition JSON; then the print bundle and
        the composition go to the fulfilment folder under the order's ticket."""
        from backend.api.fulfilment import copy_bundle

        from .export import run_export

        with self.db() as db:
            job = db.get(JobRow, job_id)
            spec = dict(job.pet_spec)
            ticket = job.ticket
            job.status, job.started_at, job.attempts = "running", job.started_at or utcnow(), job.attempts + 1
            db.commit()
        ctx = StageContext(job_id=job_id, settings=self.s, store=self.store, backends=None,
                           progress=self._progress(job_id), on_artefact=self._artefact(job_id),
                           deadline=time.monotonic() + self.s.genai.timeout("F"))
        on_stage = self._stage(job_id)
        t0 = time.perf_counter()
        on_stage("F", "running", 0, None)
        try:
            mb = run_export(ctx, job_id, spec["composition"], spec["composition_id"])
            key = ctx.key("manifest.json")
            self._artefact(job_id)("manifest.json", "manifest", "F", key, len(self.store.get(key)))
            on_stage("F", "ok", int((time.perf_counter() - t0) * 1000), None)
            if ticket:
                copy_bundle(self.s.fulfil_dir, self.store, job_id, ticket)
            msg = "Your figurine is ready"
            self._update(job_id, status="done", stage="done", pct=100, message=msg, finished_at=utcnow(), fallback="none",
                         fidelity=mb.data["fidelity"], error=None)
            self.bus.publish(job_id, {"job_id": job_id, "status": "done", "stage": "done", "pct": 100, "message": msg,
                                      "queue_position": 0, "preview_kind": "glb", "preview_key": ctx.key("figure.glb")})
            return "done"
        except Exception as exc:  # noqa: BLE001 - any failure fails the order visibly; staff can reprint or retry
            log.exception("export %s failed", job_id)
            on_stage("F", "failed", int((time.perf_counter() - t0) * 1000), None)
            return self._fail(job_id, "F", str(exc))
        finally:
            shutil.rmtree(ctx.tmp, ignore_errors=True)

    def run_pipeline(self, job_id: str) -> str:
        with self.db() as db:
            job = db.get(JobRow, job_id)
            spec = dict(job.pet_spec)
            job.status, job.started_at, job.attempts = "running", job.started_at or utcnow(), job.attempts + 1
            db.commit()
        ctx = StageContext(job_id=job_id, settings=self.s, store=self.store, backends=self.backends,
                           progress=self._progress(job_id), on_artefact=self._artefact(job_id))
        try:
            manifest = StageRunner(ctx, spec, on_stage=self._stage(job_id)).run()
            # The manifest itself is an artefact too.
            key = ctx.key("manifest.json")
            self._artefact(job_id)("manifest.json", "manifest", "F", key, len(self.store.get(key)))
            fb = manifest.data["fallback"]
            msg = "Your figurine is ready" if fb == "none" else "Your figurine is ready (classic shape)"
            self._update(job_id, status="done", stage="done", pct=100, message=msg, finished_at=utcnow(), fallback=fb,
                         fidelity=manifest.data["fidelity"], error=None)
            glb = ctx.key("figure.glb")
            self.bus.publish(job_id, {"job_id": job_id, "status": "done", "stage": "done", "pct": 100, "message": msg,
                                      "queue_position": 0, "preview_kind": "glb", "preview_key": glb})
            return "done"
        except JobFailed as exc:
            log.error("job %s failed: %s", job_id, exc)
            return self._fail(job_id, exc.stage, str(exc))
        finally:
            shutil.rmtree(ctx.tmp, ignore_errors=True)

    def watchdog(self, period: float = 5.0, limit: float = 30.0) -> None:
        """GPU host: restart ComfyUI if /system_stats has not answered for 30 s (PETPOP_COMFY_RESTART_CMD)."""
        import os
        import subprocess

        import httpx

        last_ok = time.monotonic()
        while not self._stop.wait(period):
            try:
                if httpx.get(f"{self.s.genai.url('comfy')}/system_stats", headers=self.s.genai.auth_headers(), timeout=5).status_code == 200:
                    last_ok = time.monotonic()
                    continue
            except httpx.HTTPError:
                pass
            if time.monotonic() - last_ok > limit:
                cmd = os.environ.get("PETPOP_COMFY_RESTART_CMD", "")
                log.error("ComfyUI unresponsive for %.0f s%s", limit, "; restarting" if cmd else "")
                if cmd:
                    subprocess.run(cmd, shell=True, timeout=120)  # noqa: S602 - operator-configured command
                last_ok = time.monotonic()

    def loop(self, poll: float = 0.5) -> None:
        if self.queue == "studio":
            log.info("studio worker started (GenAI profile %s, mode %s, quality %s)", self.s.profile, self.s.mode,
                     self.s.quality["preset"])
        else:
            log.info("kiosk worker started (Stage F exports only; no GenAI host)")
        self._recover()
        if self.queue == "studio" and "comfy" in (self.s.genai["services"] or {}):
            threading.Thread(target=self.watchdog, name="comfy-watchdog", daemon=True).start()
        while not self._stop.is_set():
            job_id = self.bus.claim(self.queue)
            if job_id:
                self.run_job(job_id)
            else:
                self._stop.wait(poll)

    def _recover(self) -> None:
        """A job left 'running' by a crashed worker is re-queued; it resumes at its failed stage."""
        with self.db() as db:
            for job in db.scalars(select(JobRow).where(JobRow.queue == self.queue, JobRow.status == "running")).all():
                job.status = "queued"
            db.commit()

    def start_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.loop, name=f"petpop-worker-{self.queue}", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m backend.worker")
    ap.add_argument("--queue", choices=sorted(JOB_KINDS), default="studio")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    w = Worker(queue=args.queue)
    try:
        w.loop()
    except KeyboardInterrupt:
        w.stop()
        time.sleep(0.1)
