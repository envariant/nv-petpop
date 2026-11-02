"""Split deployments (decision 124): the cloud (customer app, kiosks, print exports) and the studio in the shop (Studio
and its GenAI worker) run this same backend with PETPOP_DEPLOY=cloud and PETPOP_DEPLOY=studio. The shop reaches the
cloud, never the other way round, so nothing in the shop accepts connections from the internet:

    releases   the shop uploads each release bundle Studio packs; the cloud verifies its signature (both sides share
               PETPOP_RELEASE_KEY) and installs it, and kiosks switch to it within 30 s
    bespoke    the shop pulls "Make it unique" requests (studio-queue jobs the cloud never runs), runs them under the
               same job id, and sends the customer-facing result (GLB, thumbnail, turntable) back; the customer's
               result page and QR stay on the cloud
    prints     the shop pulls each finished (and, with payments on, paid) order's print bundle into its fulfilment
               folder, where the printer picks it up, and acknowledges it; the kiosk ops panel's reprint re-queues it

The /sync routes are a protocol between two copies of this code, which ship together; the apps never call them, so
they are not part of data/schema/openapi.json (the app contract). They need the shared bearer token
PETPOP_SYNC_TOKEN and exist only on the cloud.
"""
from __future__ import annotations

import hmac
import logging
import re
import threading
from datetime import UTC
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Header, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from backend.core.genai import profile_name, resolve_options, resolve_pipeline
from petpop_library import release as rel

from .contract import API_PREFIX, ApiError, make_token
from .db import ArtefactRow, CompositionRow, JobRow, utcnow
from .fulfilment import PRINT_BUNDLE

log = logging.getLogger("petpop.sync")
SYNC = f"{API_PREFIX}/sync"
RELEASE_NAME = re.compile(r"^release-(dog|cat)-\d+\.tar$")
# What a bespoke result sends back: the customer-facing files (the print bundle stays in the shop, which prints it).
RESULT_FILES = {"figure.glb": "glb", "thumbnail.png": "thumbnail", "turntable.mp4": "turntable"}


def paid_or_free(impl, row: CompositionRow) -> bool:
    """Whether an order may be printed: paid, or payments are off (decision 125)."""
    return impl.order_payable(row)


# --------------------------------------------------------------------------- the cloud's side
def make_sync_router(impl) -> APIRouter:
    """The /sync routes, bound to a BackendApi. 404 unless this process is the cloud with a sync token set."""
    s = impl.s
    router = APIRouter(prefix=SYNC, include_in_schema=False)

    def shop(authorization: str | None = Header(None)) -> None:
        if s.deploy != "cloud" or not s.sync_token:
            raise ApiError(404, "not found")
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(token.encode(), s.sync_token.encode()):
            raise ApiError(401, "bad sync token")

    auth = [Depends(shop)]

    @router.get("/releases", dependencies=auth)
    def releases() -> dict[str, Any]:
        # every bundle the cloud holds: those in its inbox (older ones too, pruned from the installed set) and those
        # installed, so the shop never re-sends one
        held = {p.stem for d in s.release_inbox if d.exists() for p in d.glob("release-*-*.tar")}
        held |= {v for sp in ("dog", "cat") for v in impl.library.releases.installed(sp)}
        return {"items": sorted(held)}

    @router.put("/releases/{name}", dependencies=auth)
    async def upload_release(name: str, request: Request) -> dict[str, Any]:
        if not RELEASE_NAME.match(name):
            raise ApiError(422, "expected release-<species>-<n>.tar")
        bundle = await request.body()
        try:
            manifest, _ = rel.read(bundle)
        except rel.ReleaseError as exc:
            raise ApiError(422, f"rejected: {exc}") from exc
        if f"{manifest['release_version']}.tar" != name:
            raise ApiError(422, "the bundle's release_version does not match its name")
        inbox = s.release_inbox[0]
        inbox.mkdir(parents=True, exist_ok=True)
        tmp = inbox / f".{name}.tmp"
        tmp.write_bytes(bundle)
        tmp.replace(inbox / name)  # the kiosk never sees a half-written bundle
        impl.library.load_releases()
        return {"installed": manifest["release_version"]}

    @router.get("/bespoke", dependencies=auth)
    def bespoke() -> dict[str, Any]:
        with impl.db() as db:
            rows = db.scalars(select(JobRow).where(JobRow.queue == "studio", JobRow.kind == "bespoke", JobRow.status == "queued")
                              .order_by(JobRow.created_at)).all()
            return {"items": [{"job_id": j.id, "spec": j.pet_spec, "ticket": j.ticket, "contact": j.contact,
                               "requested_by": j.requested_by, "created_at": j.created_at.replace(tzinfo=UTC).isoformat()}
                              for j in rows]}

    def _bespoke_job(db, job_id: str) -> JobRow:
        job = db.get(JobRow, job_id)
        if not job or job.kind != "bespoke":
            raise ApiError(404, f"unknown bespoke request {job_id}")
        return job

    @router.post("/bespoke/{job_id}/claim", dependencies=auth)
    def claim(job_id: str) -> dict[str, Any]:
        with impl.db() as db:
            job = _bespoke_job(db, job_id)
            if job.status == "queued":
                job.status, job.stage, job.message, job.started_at = "running", "studio", "Being made in the studio", utcnow()
                db.commit()
            return {"job_id": job_id, "status": job.status}

    @router.put("/bespoke/{job_id}/result", dependencies=auth)
    async def result(job_id: str, request: Request, files: list[UploadFile] = File(...)) -> dict[str, Any]:
        got = {f.filename: await f.read() for f in files if f.filename in RESULT_FILES}
        if "figure.glb" not in got:
            raise ApiError(422, "a result needs figure.glb")
        with impl.db() as db:
            job = _bespoke_job(db, job_id)
            for name, data in got.items():
                key = f"jobs/{job_id}/{name}"
                impl.store.put(key, data)
                db.add(ArtefactRow(job_id=job_id, stage="F", kind=RESULT_FILES[name], name=name, object_key=key, bytes=len(data)))
            job.status, job.stage, job.pct, job.message = "done", "done", 100, "Your one-off figurine is ready"
            job.finished_at, job.error = utcnow(), None
            db.commit()
        base = s.public_url.rstrip("/") or str(request.base_url).rstrip("/")
        return {"job_id": job_id, "result_url": f"{base}/r/{make_token(impl.secret, job_id)}"}

    @router.post("/bespoke/{job_id}/fail", dependencies=auth)
    async def fail(job_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        with impl.db() as db:
            job = _bespoke_job(db, job_id)
            job.status, job.error, job.finished_at = "failed", str(body.get("error", "failed in the studio"))[:500], utcnow()
            db.commit()
        return {"job_id": job_id, "status": "failed"}

    @router.get("/prints", dependencies=auth)
    def prints() -> dict[str, Any]:
        out = []
        with impl.db() as db:
            rows = db.scalars(select(CompositionRow).where(CompositionRow.job_id.is_not(None), CompositionRow.collected_at.is_(None))
                              .order_by(CompositionRow.created_at)).all()
            for row in rows:
                job = db.get(JobRow, row.job_id)
                if not job or job.status not in ("done", "fulfilled") or not paid_or_free(impl, row):
                    continue
                names = [n for n in PRINT_BUNDLE if impl.store.exists(f"jobs/{job.id}/{n}")]
                out.append({"job_id": job.id, "composition_id": row.id, "ticket": row.ticket or job.ticket,
                            "pet_name": row.pet_name, "files": names})
        return {"items": out}

    @router.get("/prints/{job_id}/files/{name}", dependencies=auth)
    def print_file(job_id: str, name: str) -> Response:
        if name not in PRINT_BUNDLE or not impl.store.exists(f"jobs/{job_id}/{name}"):
            raise ApiError(404, "unknown file")
        return Response(impl.store.get(f"jobs/{job_id}/{name}"), media_type="application/octet-stream")

    @router.post("/prints/{job_id}/ack", dependencies=auth)
    def ack(job_id: str) -> dict[str, Any]:
        with impl.db() as db:
            row = db.scalar(select(CompositionRow).where(CompositionRow.job_id == job_id))
            if not row:
                raise ApiError(404, "unknown order")
            row.collected_at = utcnow()
            db.commit()
        return {"job_id": job_id, "collected": True}

    return router


# --------------------------------------------------------------------------- the shop's side
class SyncAgent:
    """Runs in the studio's API process: every PETPOP_SYNC_INTERVAL seconds it pushes new releases, pulls bespoke
    requests, sends finished ones back and pulls print bundles. Each step logs and carries on when the cloud is
    unreachable; the next round catches up (every step is idempotent)."""

    def __init__(self, impl, client: httpx.Client | None = None) -> None:
        self.impl = impl
        self.s = impl.s
        self.client = client or httpx.Client(base_url=self.s.cloud_url, timeout=120)
        self.client.headers["Authorization"] = f"Bearer {self.s.sync_token}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last: dict[str, Any] = {}

    # -- one round
    def run_once(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, step in (("releases", self.push_releases), ("bespoke", self.pull_bespoke), ("results", self.push_results),
                           ("prints", self.pull_prints)):
            try:
                out[name] = step()
            except Exception as exc:  # noqa: BLE001 - the cloud may be down; the next round retries
                log.warning("sync %s: %s", name, exc)
                out[name] = f"error: {exc}"
        self.last = out
        return out

    def _ok(self, r: httpx.Response) -> httpx.Response:
        r.raise_for_status()
        return r

    def push_releases(self) -> list[str]:
        local = sorted({p for d in self.s.release_inbox if d.exists() for p in d.glob("release-*-*.tar")},
                       key=lambda p: (p.name.split("-")[1], int(p.stem.rsplit("-", 1)[1])))
        if not local:
            return []
        remote = set(self._ok(self.client.get(f"{SYNC}/releases")).json()["items"])
        sent = []
        for p in local:
            if p.stem not in remote:
                self._ok(self.client.put(f"{SYNC}/releases/{p.name}", content=p.read_bytes(),
                                         headers={"Content-Type": "application/x-tar"}))
                sent.append(p.stem)
        return sent

    def pull_bespoke(self) -> list[str]:
        items = self._ok(self.client.get(f"{SYNC}/bespoke")).json()["items"]
        taken = []
        for it in items:
            with self.impl.db() as db:
                if not db.get(JobRow, it["job_id"]):
                    profile = profile_name()
                    job = self.impl._new_job(db, it["spec"], queue="studio", kind="bespoke", requested_by=it["requested_by"],
                                             contact=it.get("contact"), genai_profile=profile,
                                             pipeline=resolve_pipeline(profile, None, "bespoke"),
                                             options=resolve_options(profile, None), job_id=it["job_id"], origin="cloud")
                    job.ticket = it.get("ticket")
                    db.commit()
            self._ok(self.client.post(f"{SYNC}/bespoke/{it['job_id']}/claim"))
            taken.append(it["job_id"])
        return taken

    def push_results(self) -> list[str]:
        sent = []
        with self.impl.db() as db:
            jobs = db.scalars(select(JobRow).where(JobRow.origin == "cloud", JobRow.synced_at.is_(None),
                                                   JobRow.status.in_(("done", "fulfilled", "failed")))).all()
            todo = [(j.id, j.status, j.error) for j in jobs]
        for job_id, status, error in todo:
            if status == "failed":
                self._ok(self.client.post(f"{SYNC}/bespoke/{job_id}/fail", json={"error": error or "failed in the studio"}))
                url = None
            else:
                with self.impl.db() as db:
                    arts = db.scalars(select(ArtefactRow).where(ArtefactRow.job_id == job_id)).all()
                    keys = {a.kind: a.object_key for a in arts if a.kind in ("glb", "thumbnail", "turntable")}
                names = {v: k for k, v in RESULT_FILES.items()}
                files = [("files", (names[kind], self.impl.store.get(key))) for kind, key in keys.items()]
                url = self._ok(self.client.put(f"{SYNC}/bespoke/{job_id}/result", files=files)).json()["result_url"]
            with self.impl.db() as db:
                job = db.get(JobRow, job_id)
                job.synced_at, job.remote_result_url = utcnow(), url
                db.commit()
            sent.append(job_id)
        return sent

    def pull_prints(self) -> list[str]:
        items = self._ok(self.client.get(f"{SYNC}/prints")).json()["items"]
        got = []
        for it in items:
            folder = self.s.fulfil_dir / f"{it['ticket']}_{it['job_id']}"
            folder.mkdir(parents=True, exist_ok=True)
            for name in it["files"]:
                data = self._ok(self.client.get(f"{SYNC}/prints/{it['job_id']}/files/{name}")).content
                tmp = folder / f".{name}.tmp"
                tmp.write_bytes(data)
                tmp.replace(folder / name)
            self._ok(self.client.post(f"{SYNC}/prints/{it['job_id']}/ack"))
            got.append(it["ticket"])
        return got

    # -- background loop
    def start(self) -> None:
        def loop() -> None:
            while not self._stop.is_set():
                self.run_once()
                self._stop.wait(self.s.sync_interval_s)

        self._thread = threading.Thread(target=loop, name="sync-agent", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
