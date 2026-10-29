"""Two queues, two workers (BRIEF Section 17): only the studio worker builds GenAI adapters; the kiosk worker
claims kiosk jobs only, refuses pipeline work, and never reaches the GenAI host."""
from __future__ import annotations

import subprocess
import sys

import pytest

from backend.core.paths import ROOT


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("PETPOP_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("PETPOP_STUDIO_PASSWORD", "x")
    # A real profile whose host is unreachable: anything that tried to talk to it would fail.
    monkeypatch.setenv("GENAI_PROFILE", "mac-m4pro")
    for name in ("COMFY_URL", "SHAPE_URL", "OLLAMA_URL"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    from backend.core.config import settings

    return settings()


def test_kiosk_worker_builds_no_adapters(env, monkeypatch):
    import backend.worker.backends.base as base
    from backend.worker.service import Worker

    def boom(*_a, **_k):
        raise AssertionError("the kiosk worker must not build GenAI adapters")

    monkeypatch.setattr(base, "make_backends", boom)
    w = Worker(env, queue="kiosk")
    assert w.backends is None
    with pytest.raises(AssertionError):
        Worker(env, queue="studio")


def test_importing_the_worker_loads_no_real_adapter():
    code = ("import sys, backend.worker.service; "
            "bad = [m for m in sys.modules if m.startswith('backend.worker.backends.real') or m == 'backend.worker.backends.base']; "
            "assert not bad, bad")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin"})


def test_each_queue_claims_only_its_own_jobs(env):
    from backend.api.bus import LocalBus
    from backend.api.db import JobRow, session_factory, utcnow
    from backend.worker.service import Worker

    db = session_factory(env.database_url)
    with db() as s:
        s.add(JobRow(id="j_studio", queue="studio", kind="pipeline", requested_by="operator", pet_spec={"seed": 1},
                     seed=1, created_at=utcnow()))
        s.add(JobRow(id="j_kiosk", queue="kiosk", kind="pipeline", requested_by="kiosk:k1", pet_spec={"seed": 1},
                     seed=1, created_at=utcnow()))
        s.commit()
    bus = LocalBus(db)
    assert bus.claim("kiosk") == "j_kiosk"
    assert bus.claim("kiosk") is None  # one at a time per queue
    assert bus.claim("studio") == "j_studio"
    # A pipeline job that somehow lands on the kiosk queue is failed, not run.
    w = Worker(env, queue="kiosk")
    assert w.run_job("j_kiosk") == "failed"
    with db() as s:
        job = s.get(JobRow, "j_kiosk")
        assert job.status == "failed" and "kiosk queue" in job.error
