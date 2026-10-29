"""Job queue and progress events.

Two queues (BRIEF Section 17): `kiosk` (Stage-F exports and nothing else) and `studio` (full pipeline jobs,
batches, re-renders), each drained by its own worker process, so a kiosk export never waits behind a batch.

LocalBus (make dev): the jobs table is the queue (a worker claims the oldest queued row of its queue) and
progress events go to the job_events table, which the API tails for WebSockets. It works across the API and
worker processes with no extra service. RedisBus (Compose): one arq queue per queue name + Redis lists/pub-sub.
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from sqlalchemy import select, update

from .db import EventRow, JobRow, utcnow


QUEUES = ("kiosk", "studio")


def arq_queue(queue: str) -> str:
    return f"petpop:{queue}"


class Bus(Protocol):
    def enqueue(self, job_id: str, queue: str) -> None: ...
    def claim(self, queue: str) -> str | None: ...
    def publish(self, job_id: str, event: dict[str, Any]) -> None: ...
    def tail(self, job_id: str, after: int) -> list[tuple[int, dict[str, Any]]]: ...


class LocalBus:
    def __init__(self, factory) -> None:
        self.factory = factory

    def enqueue(self, job_id: str, queue: str) -> None:
        return None  # the row's status='queued' (and its queue column) is the queue entry

    def claim(self, queue: str) -> str | None:
        with self.factory() as db:
            if db.scalar(select(JobRow.id).where(JobRow.queue == queue, JobRow.status == "running")):
                return None  # one job at a time per queue (one GPU for studio, one CPU worker for kiosk)
            job_id = db.scalar(select(JobRow.id).where(JobRow.queue == queue, JobRow.status == "queued")
                               .order_by(JobRow.created_at).limit(1))
            if not job_id:
                return None
            r = db.execute(update(JobRow).where(JobRow.id == job_id, JobRow.status == "queued")
                           .values(status="running", started_at=utcnow(), stage="A"))
            db.commit()
            return job_id if r.rowcount == 1 else None

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        with self.factory() as db:
            db.add(EventRow(job_id=job_id, payload=event))
            db.commit()

    def tail(self, job_id: str, after: int) -> list[tuple[int, dict[str, Any]]]:
        with self.factory() as db:
            rows = db.execute(select(EventRow.id, EventRow.payload).where(EventRow.job_id == job_id, EventRow.id > after)
                              .order_by(EventRow.id)).all()
            return [(r[0], r[1]) for r in rows]


class RedisBus:
    """GPU host: arq on Redis for the queue, a Redis list per job for replayable events."""

    def __init__(self, url: str) -> None:
        import redis  # noqa: PLC0415

        self.url = url
        self.r = redis.Redis.from_url(url)

    def enqueue(self, job_id: str, queue: str) -> None:
        """Enqueue on arq. Called from inside the API's event loop, so the arq client runs on its own thread."""
        import asyncio
        import threading

        from arq import create_pool  # noqa: PLC0415
        from arq.connections import RedisSettings  # noqa: PLC0415

        async def go() -> None:
            pool = await create_pool(RedisSettings.from_dsn(self.url))
            try:
                await pool.enqueue_job("run_job", job_id, _job_id=job_id, _queue_name=arq_queue(queue))
            finally:
                await pool.aclose()

        err: list[BaseException] = []

        def runner() -> None:
            try:
                asyncio.run(go())
            except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
                err.append(exc)

        t = threading.Thread(target=runner, name="arq-enqueue")
        t.start()
        t.join(30)
        if err:
            raise err[0]

    def claim(self, queue: str) -> str | None:
        return None  # arq delivers jobs to backend.worker.arq_worker.run_job on each queue's worker

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        self.r.rpush(f"petpop:events:{job_id}", json.dumps(event))
        self.r.expire(f"petpop:events:{job_id}", 7 * 24 * 3600)
        self.r.publish(f"petpop:events:{job_id}", json.dumps(event))

    def tail(self, job_id: str, after: int) -> list[tuple[int, dict[str, Any]]]:
        items = self.r.lrange(f"petpop:events:{job_id}", after, -1)
        return [(after + i + 1, json.loads(x)) for i, x in enumerate(items)]


def make_bus(s, factory) -> Bus:
    return RedisBus(s.redis_url) if s.redis_url else LocalBus(factory)
