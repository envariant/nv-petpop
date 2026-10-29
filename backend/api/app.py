"""FastAPI app: the /api/v1 contract, both built SPAs from the same origin (kiosk at /, studio at /studio/), and
Prometheus /metrics."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager


from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from backend.core.config import settings
from backend.api.contract import make_app
from backend.core.paths import ROOT

from .db import JobRow, StageTimingRow
from .service import BackendApi

SPA = ROOT / "apps" / "kiosk" / "dist"
STUDIO_SPA = ROOT / "apps" / "studio" / "dist"


def create_app(embed_worker: bool | None = None) -> FastAPI:
    s = settings()
    impl = BackendApi(s)
    workers = []
    if embed_worker if embed_worker is not None else s.embed_worker:
        from backend.worker.service import Worker  # dev and tests: both queues' workers in-process

        workers = [Worker(s, queue="studio"), Worker(s, queue="kiosk")]

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        impl.purge_free_text()
        impl.library.watch()  # new release bundles in the inbox are picked up within 30 s
        for w in workers:
            w.start_thread()
        yield
        impl.library.stop()
        for w in workers:
            w.stop()

    app = make_app(impl, title="PetPop API", lifespan=lifespan)
    app.state.impl = impl
    stats = {"requests": 0, "started": time.time()}

    @app.middleware("http")
    async def count(request: Request, call_next):
        stats["requests"] += 1
        return await call_next(request)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> PlainTextResponse:
        lines = ["# TYPE petpop_jobs gauge"]
        with impl.db() as db:
            for status, n in db.execute(select(JobRow.status, func.count()).group_by(JobRow.status)).all():
                lines.append(f'petpop_jobs{{status="{status}"}} {n}')
            lines.append("# TYPE petpop_stage_ms_avg gauge")
            for stage, avg in db.execute(select(StageTimingRow.stage, func.avg(StageTimingRow.ms))
                                         .where(StageTimingRow.status != "running").group_by(StageTimingRow.stage)).all():
                lines.append(f'petpop_stage_ms_avg{{stage="{stage}"}} {float(avg or 0):.0f}')
        lines += ["# TYPE petpop_http_requests_total counter", f"petpop_http_requests_total {stats['requests']}",
                  "# TYPE petpop_uptime_seconds gauge", f"petpop_uptime_seconds {time.time() - stats['started']:.0f}"]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    if STUDIO_SPA.exists():
        app.mount("/studio", StaticFiles(directory=STUDIO_SPA, html=True), name="studio-spa")

    if SPA.exists():
        app.mount("/assets", StaticFiles(directory=SPA / "assets"), name="spa-assets")
        for sub in ("draco", "fixtures"):
            if (SPA / sub).exists():
                app.mount(f"/{sub}", StaticFiles(directory=SPA / sub), name=f"spa-{sub}")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            f = (SPA / path).resolve()
            if path and str(f).startswith(str(SPA.resolve())) and f.is_file():
                return FileResponse(f)
            return FileResponse(SPA / "index.html")

    logging.getLogger("petpop").setLevel(logging.INFO)
    return app


