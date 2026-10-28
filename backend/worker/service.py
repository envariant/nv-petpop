"""Worker process: claims queued jobs one at a time and runs the StageRunner, mirroring progress, timings
and artefacts into the database and the event bus (the arq entry point on the GPU host calls run_job)."""
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

from .backends.base import make_backends
from .context import StageContext
from .runner import JobFailed, StageRunner

log = logging.getLogger("petpop.worker")


class Worker:
    def __init__(self, s: Settings | None = None) -> None:
        self.s = s or settings()
        self.db = session_factory(self.s.database_url)
        self.bus = make_bus(self.s, self.db)
        self.store = make_store(self.s)
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
    def run_job(self, job_id: str) -> str:
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
            with self.db() as db:
                pct = db.get(JobRow, job_id).pct
            self._update(job_id, status="failed", stage=exc.stage, finished_at=utcnow(), error=str(exc)[:500],
                         message=f"Stage {exc.stage} failed")
            self.bus.publish(job_id, {"job_id": job_id, "status": "failed", "stage": exc.stage, "pct": pct,
                                      "message": f"Stage {exc.stage} failed", "queue_position": 0})
            return "failed"
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
                if httpx.get(f"{self.s.comfy_url}/system_stats", timeout=3).status_code == 200:
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
        log.info("worker started (mode=%s, profile=%s)", self.s.mode, self.s.profile)
        self._recover()
        if self.s.mode == "real":
            threading.Thread(target=self.watchdog, name="comfy-watchdog", daemon=True).start()
        while not self._stop.is_set():
            job_id = self.bus.claim()
            if job_id:
                self.run_job(job_id)
            else:
                self._stop.wait(poll)

    def _recover(self) -> None:
        """A job left 'running' by a crashed worker is re-queued; it resumes at its failed stage."""
        with self.db() as db:
            for job in db.scalars(select(JobRow).where(JobRow.status == "running")).all():
                job.status = "queued"
            db.commit()

    def start_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.loop, name="petpop-worker", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    w = Worker()
    try:
        w.loop()
    except KeyboardInterrupt:
        w.stop()
        time.sleep(0.1)
