"""Run the whole pipeline for one spec without the API or a database (fixture pack, regression set)."""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from backend.api.store import LocalStore
from backend.core.config import settings

from .backends.base import make_backends
from .context import StageContext
from .runner import StageRunner

log = logging.getLogger("petpop.worker")


def run_pipeline(job_id: str, spec: dict[str, Any], store, s=None, progress=None, kind: str = "pipeline",
                 pipeline: str | None = None, options: dict[str, bool] | None = None):
    s = s or settings()
    ctx = StageContext(job_id=job_id, settings=s, store=store, backends=make_backends(s),
                       progress=progress or (lambda *a, **k: None), kind=kind, pipeline=pipeline,
                       options=options)
    try:
        return StageRunner(ctx, spec).run()
    finally:
        shutil.rmtree(ctx.tmp, ignore_errors=True)


def run_pipeline_to_dir(job_id: str, spec: dict[str, Any], out: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pp-local-") as tmp:
        store = LocalStore(Path(tmp))
        manifest = run_pipeline(job_id, spec, store)
        src = Path(tmp) / "jobs" / job_id
        out.mkdir(parents=True, exist_ok=True)
        for f in src.rglob("*"):
            if f.is_file() and not f.name.endswith(".tmp"):
                dst = out / f.relative_to(src)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
        return manifest.data
