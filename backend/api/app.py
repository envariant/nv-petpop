"""FastAPI app: the /api/v1 contract, both built SPAs from the same origin (customer app at /, studio at /studio/), and
Prometheus /metrics.

PETPOP_DEPLOY picks what this process serves (decision 124): "all" (one box), "cloud" (the customer app and /kiosk,
the kiosk export worker, the /sync routes the shop calls) or "studio" (Studio and /studio, the studio worker, and the
sync agent that talks to the cloud). One contract either way: a route of the other role answers 404."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager


from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from backend.core.config import Settings, settings
from backend.api.contract import KIOSK, STUDIO, make_app
from backend.core.paths import ROOT

from .db import JobRow, StageTimingRow
from .service import BackendApi
from .sync import SyncAgent, make_sync_router

SPA = ROOT / "apps" / "customer" / "dist"
STUDIO_SPA = ROOT / "apps" / "studio" / "dist"


# The queues each role works and the API prefix each role does not serve.
ROLE_QUEUES = {"all": ("studio", "kiosk"), "cloud": ("kiosk",), "studio": ("studio",)}
ROLE_BLOCKS = {"all": (), "cloud": (STUDIO,), "studio": (KIOSK,)}


def create_app(embed_worker: bool | None = None, s: Settings | None = None, sync_client=None) -> FastAPI:
    s = s or settings()
    impl = BackendApi(s)
    workers = []
    if embed_worker if embed_worker is not None else s.embed_worker:
        from backend.worker.service import Worker  # dev and tests: this role's queue workers in-process

        workers = [Worker(s, queue=q) for q in ROLE_QUEUES[s.deploy]]
    agent = SyncAgent(impl, sync_client) if s.deploy == "studio" and (s.cloud_url or sync_client) and s.sync_token else None
    if s.deploy == "studio" and not agent:
        logging.getLogger("petpop").warning("PETPOP_DEPLOY=studio without PETPOP_CLOUD_URL and PETPOP_SYNC_TOKEN: no sync")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        impl.purge_free_text()
        impl.library.watch()  # new release bundles in the inbox are picked up within 30 s
        for w in workers:
            w.start_thread()
        if agent:
            agent.start()
        yield
        impl.library.stop()
        if agent:
            agent.stop()
        for w in workers:
            w.stop()

    app = make_app(impl, title="PetPop API", lifespan=lifespan)
    app.state.impl = impl
    app.state.sync_agent = agent
    app.include_router(make_sync_router(impl))
    stats = {"requests": 0, "started": time.time()}
    blocked = ROLE_BLOCKS[s.deploy]

    @app.middleware("http")
    async def count(request: Request, call_next):
        stats["requests"] += 1
        if blocked and request.url.path.startswith(blocked):
            where = "in the shop" if s.deploy == "cloud" else "in the cloud"
            return JSONResponse({"detail": f"not served here (PETPOP_DEPLOY={s.deploy}): this runs {where}"}, status_code=404)
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

    if STUDIO_SPA.exists() and s.deploy != "cloud":
        app.mount("/studio", StaticFiles(directory=STUDIO_SPA, html=True), name="studio-spa")

    if s.deploy == "studio":  # the shop's box opens on Studio; the customer app stays for its one-offs' result pages
        @app.get("/", include_in_schema=False)
        def home() -> RedirectResponse:
            return RedirectResponse("/studio/")

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


