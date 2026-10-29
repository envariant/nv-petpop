"""Shared by the gate-8 scripts: run a Studio batch in-process (the real backend's service and studio worker),
accept every part that passed QC, and publish it."""
from __future__ import annotations

import asyncio
import time

from backend.api import models as m


def run_batch(api, worker, species: str, breeds: list[str], seeds: int = 1, variants: list[dict] | None = None,
              user: str = "gate8") -> m.Batch:
    op = m.StaffUser(username=user, role="admin")
    body = m.BatchCreate(species=species, breeds=breeds, seeds=seeds,
                         variants=[m.BatchVariant(**v) for v in (variants or [{"label": "preset", "patch": {}}])])
    batch = asyncio.run(api.create_batch(body, op))
    t0 = time.perf_counter()
    for i, f in enumerate(batch.figurines, 1):
        r = worker.run_job(f.job_id)
        print(f"  figurine {i}/{len(batch.figurines)} {f.breed_id} seed {f.seed}: {r} ({time.perf_counter() - t0:.0f} s)", flush=True)
    return asyncio.run(api.get_batch(batch.batch_id))


def accept_and_publish(api, batch: m.Batch, user: str = "gate8") -> m.Batch:
    cur = m.StaffUser(username=user, role="admin")
    passing = [c for f in batch.figurines for c in f.candidates if not c.auto_rejected]
    if passing:
        asyncio.run(api.review_batch(batch.batch_id, m.ReviewRequest(decisions=[m.ReviewDecision(item_id=c.id, action="accept")
                                                                                 for c in passing]), cur))
        for c in passing:
            asyncio.run(api.publish_item(batch.species, c.kind, c.id, cur))
    return asyncio.run(api.get_batch(batch.batch_id))
