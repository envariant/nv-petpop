"""arq entry points for Compose (REDIS_URL set), one worker process per queue (BRIEF Section 17):

    arq backend.worker.arq_worker.StudioWorkerSettings   # full pipeline; the only one that reaches the GenAI host
    arq backend.worker.arq_worker.KioskWorkerSettings    # Stage-F-only exports
"""
from __future__ import annotations

import asyncio
import os

from backend.api.bus import arq_queue

from .service import Worker

_workers: dict[str, Worker] = {}


def _runner(queue: str):
    async def run_job(ctx, job_id: str) -> str:
        if queue not in _workers:
            _workers[queue] = Worker(queue=queue)
        return await asyncio.to_thread(_workers[queue].run_job, job_id)

    return run_job


try:
    from arq.connections import RedisSettings
    from arq.worker import func

    _redis = RedisSettings.from_dsn(os.environ["REDIS_URL"]) if os.environ.get("REDIS_URL") else None
except ImportError:  # arq is only installed for the Compose stack
    func = None
    _redis = None


class StudioWorkerSettings:
    queue_name = arq_queue("studio")
    functions = [func(_runner("studio"), name="run_job")] if func else []
    max_jobs = 1  # one job at a time per GPU
    job_timeout = 3600
    redis_settings = _redis


class KioskWorkerSettings:
    queue_name = arq_queue("kiosk")
    functions = [func(_runner("kiosk"), name="run_job")] if func else []
    max_jobs = 1
    job_timeout = 300
    redis_settings = _redis
