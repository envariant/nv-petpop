"""Studio's library in the mock server (BRIEF Section 16, M8): the real StudioLibrary (curation, review, editors,
publish, releases) on a private SQLite database and store, with batch figurines that "finish" on a script from
the fixture pack instead of running the pipeline. Curation then runs for real on the fixture pet's wrapped mesh,
so the mock's QC, parts and release bundles are the backend's, computed from real pipeline output."""
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from backend.api import models as m
from backend.api.db import ArtefactRow, JobRow, session_factory, utcnow
from backend.api.store import LocalStore
from backend.api.studio_library import StudioLibrary, curate
from backend.core.paths import FIXTURES

FIGURINE_S = 4.0  # scripted time per batch figurine (x PETPOP_MOCK_SPEED)
ARTEFACTS = [("figure.glb", "glb"), ("thumbnail.png", "thumbnail"), ("turntable.mp4", "turntable"), ("manifest.json", "manifest")]


class _NoBus:
    def enqueue(self, job_id: str, queue: str) -> None:  # the mock finishes batch jobs itself
        pass


def obj_vertices(path: Path) -> np.ndarray:
    return np.array([line.split()[1:4] for line in path.read_text().splitlines() if line.startswith("v ")], dtype=np.float64)


class MockStudio:
    def __init__(self, secret: str) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="pp-mock-studio-"))
        self.s = SimpleNamespace(release_inbox=[tmp / "inbox"])
        self.db = session_factory(f"sqlite:///{tmp / 'studio.db'}")
        self.store = LocalStore(tmp / "store")
        self.lib = StudioLibrary(self.s, self.db, self.store, _NoBus(), secret)  # type: ignore[arg-type]
        self.index = json.loads((FIXTURES / "index.json").read_text())["pets"]
        self.finish_at: dict[str, tuple[float, str]] = {}
        self._seeded = False
        self._lock = threading.Lock()

    def ready(self) -> StudioLibrary:
        with self._lock:
            if not self._seeded:
                self.lib.seed()
                self._seeded = True
        return self.lib

    def create_batch(self, body: m.BatchCreate, user: m.StaffUser, speed: float) -> m.Batch:
        b = self.ready().create_batch(body, user)
        now = time.time()
        for i, f in enumerate(b.figurines):
            same = [p for p in self.index if p["species"] == body.species]
            pet = next((p for p in same if p["breed"] == f.breed_id), same[i % len(same)])["id"]
            self.finish_at[f.job_id] = (now + (i + 1) * FIGURINE_S * speed, pet)
        return self.batch(b.batch_id)

    def batch(self, bid: str) -> m.Batch:
        self.advance()
        return self.ready().batch(bid)

    def advance(self) -> None:
        now = time.time()
        for job_id, (at, pet) in sorted(self.finish_at.items(), key=lambda kv: kv[1][0]):
            if at <= now:
                del self.finish_at[job_id]
                self._finish(job_id, pet)

    def _finish(self, job_id: str, pet: str) -> None:
        """The fixture pet's pipeline output stands in for this figurine's; then curation runs for real."""
        d = FIXTURES / pet
        with self.db() as db:
            for name, kind in ARTEFACTS:
                if (d / name).exists():
                    key = f"jobs/{job_id}/{name}"
                    data = (d / name).read_bytes()
                    self.store.put(key, data)
                    db.add(ArtefactRow(job_id=job_id, stage="F", kind=kind, name=name, object_key=key, bytes=len(data)))
            import io

            buf = io.BytesIO()
            np.save(buf, obj_vertices(d / "figure_uv.obj"))
            self.store.put(f"jobs/{job_id}/wrapped_coords.npy", buf.getvalue())
            job = db.get(JobRow, job_id)
            job.status, job.stage, job.pct, job.finished_at = "done", "done", 100, utcnow()
            db.commit()
        curate(self.db, self.store, job_id)

    def file(self, key: str) -> bytes | None:
        return self.store.get(key) if self.store.exists(key) else None

    def latest_bundle(self, info: m.ReleaseInfo) -> bytes:
        return (self.s.release_inbox[0] / f"{info.release_version}.tar").read_bytes()

    def stats(self) -> dict[str, Any]:
        return {"pending": len(self.finish_at)}
