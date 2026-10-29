"""arq entry point for the GPU host (REDIS_URL set): `arq backend.worker.arq_worker.WorkerSettings`."""
from __future__ import annotations

import asyncio
import os

from .service import Worker

_worker: Worker | None = None


async def run_job(ctx, job_id: str) -> str:
    global _worker
    _worker = _worker or Worker()
    return await asyncio.to_thread(_worker.run_job, job_id)


class WorkerSettings:
    functions = [run_job]
    max_jobs = 1  # one job at a time per GPU
    job_timeout = 900
    try:
        from arq.connections import RedisSettings

        redis_settings = RedisSettings.from_dsn(os.environ["REDIS_URL"]) if os.environ.get("REDIS_URL") else None
    except ImportError:  # arq is only installed on the GPU host
        pass
