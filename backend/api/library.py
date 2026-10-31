"""The kiosk's library mode in the real backend (BRIEF Sections 16 and 17).

Releases: loaded at start from the inbox (PETPOP_RELEASE_INBOX, default var/releases/inbox, where Studio drops
release-<species>-<n>.tar) and, on a fresh kiosk, from the committed proxy releases; then re-checked every 30 s.
The ReleaseStore keeps the last two per species and switches atomically. The kiosk reads nothing else from Studio.

Compositions: the order record. Exporting one enqueues a Stage-F-only job on the kiosk queue and issues the
ticket; when it finishes, the worker writes the print bundle and the composition to the fulfilment folder.
"""
from __future__ import annotations

import logging
import random
import threading
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.core.config import Settings
from backend.core.paths import ROOT
from petpop_core.breeds import all_breeds
from petpop_library import release as rel
from petpop_library.composition import errors as composition_errors
from petpop_library.composition import to_spec
from petpop_library.figure import schema

from . import models as m
from .contract import KIOSK, ApiError, make_token, signed_file_url
from .db import ArtefactRow, CompositionRow, JobRow, SessionRow, utcnow
from .fulfilment import copy_bundle

log = logging.getLogger("petpop.library")
PROXY_RELEASES = ROOT / "fixtures" / "library"
POLL_S = 30.0


def inbox_dirs(s: Settings) -> list[Path]:
    return [Path(p) for p in s.release_inbox] + ([PROXY_RELEASES] if s.seed_proxy_library else [])


def files_url(species: str) -> str:
    return f"{KIOSK}/library/{species}/files/"


def media_type(path: str) -> str:
    return {"png": "image/png", "glb": "model/gltf-binary", "json": "application/json"}.get(path.rsplit(".", 1)[-1],
                                                                                          "application/octet-stream")


# The listing models, from a release manifest alone (shared with the mock server).
def release_model(man: dict[str, Any]) -> m.LibraryRelease:
    return m.LibraryRelease(species=man["species"], release_version=man["release_version"],
                            segmentation_version=man["segmentation_version"], files_url=files_url(man["species"]), manifest=man)


def families_model(man: dict[str, Any]) -> m.LibraryFamilies:
    u = files_url(man["species"])
    return m.LibraryFamilies(species=man["species"], release_version=man["release_version"], items=[
        m.LibraryFamily(id=f["id"], name=f["name"], mesh_id=f["mesh_id"], default_parts=f["default_parts"], breeds=f["breeds"],
                        tags=f["tags"], version=f["version"], delta_url=u + f["delta"] if f["delta"] else None,
                        thumbnail_url=u + f["thumbnail"]) for f in man["families"]],
        meshes=[m.LibraryMesh(id=me["id"], name=me["name"], breeds=me["breeds"],
                              family_ids=[f["id"] for f in man["families"] if f["mesh_id"] == me["id"]],
                              bin_url=u + me["bin"], info_url=u + me["info"], texture_url=u + me["texture"] if me.get("texture") else None,
                              thumbnail_url=u + me["thumbnail"]) for me in man["meshes"]])


def parts_model(man: dict[str, Any], region: str | None) -> m.LibraryParts:
    u = files_url(man["species"])
    items = [m.LibraryPart(id=d["id"], name=d["name"], kind="delta", region=d["region"], mesh_id=d["mesh_id"], tags=d["tags"], version=d["version"],
                           url=u + d["delta"], thumbnail_url=u + d["thumbnail"])
             for d in man["region_deltas"] if region in (None, d["region"])]
    if region in (None, "shells"):
        items += [m.LibraryPart(id=sh["id"], name=sh["name"], kind="shell", socket=sh["socket"], tags=sh.get("tags", []),
                                version=sh["version"], url=u + sh["mesh"], thumbnail_url=u + sh["thumbnail"],
                                default_colour=sh["default_colour"]) for sh in man["shell_parts"]]
    return m.LibraryParts(species=man["species"], release_version=man["release_version"], items=items)


def patterns_model(man: dict[str, Any]) -> m.LibraryPatterns:
    u = files_url(man["species"])
    return m.LibraryPatterns(species=man["species"], release_version=man["release_version"], items=[
        m.LibraryPattern(id=p["id"], name=p["name"], channel=p["channel"], default_colour=p["default_colour"],
                         coverage=m.PatternCoverage(**p["coverage"]), version=p["version"], thumbnail_url=u + p["thumbnail"])
        for p in man["pattern_layers"]])


def aware(dt):
    from datetime import UTC

    return dt.replace(tzinfo=UTC) if dt and dt.tzinfo is None else dt


class KioskLibrary:
    def __init__(self, s: Settings, db, bus, store, secret: str) -> None:
        self.s, self.db, self.bus, self.store, self.secret = s, db, bus, store, secret
        self.releases = rel.ReleaseStore(s.var / "releases", segmentation={sp: schema(sp)["schema_version"] for sp in ("dog", "cat")})
        self._stop = threading.Event()

    # ------------------------------------------------------------------ release loading
    def load_releases(self) -> list[str]:
        bundles = [p for d in inbox_dirs(self.s) if d.exists() for p in d.glob("release-*-*.tar")]
        done = []
        for path in sorted(bundles, key=lambda p: int(p.stem.rsplit("-", 1)[1])):
            try:
                done += self.releases.install_newer([path])
            except rel.ReleaseError as exc:
                log.error("release %s refused: %s", path.name, exc)
        if done:
            log.info("library releases loaded: %s", ", ".join(done))
        return done

    def watch(self) -> threading.Thread:
        def loop() -> None:
            while not self._stop.wait(POLL_S):
                self.load_releases()

        t = threading.Thread(target=loop, name="release-inbox", daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()

    def versions(self) -> dict[str, str]:
        out = {}
        for sp in ("dog", "cat"):
            r = self.releases.active(sp)
            if r:
                out[sp] = r.version
        return out

    def active(self, species: str) -> rel.Release:
        r = self.releases.active(species)
        if not r:
            raise ApiError(404, f"no library release loaded for {species}")
        return r

    # ------------------------------------------------------------------ library listing
    def release_info(self, species: str) -> m.LibraryRelease:
        return release_model(self.active(species).manifest)

    def families(self, species: str) -> m.LibraryFamilies:
        return families_model(self.active(species).manifest)

    def parts(self, species: str, region: str | None) -> m.LibraryParts:
        return parts_model(self.active(species).manifest, region)

    def patterns(self, species: str) -> m.LibraryPatterns:
        return patterns_model(self.active(species).manifest)

    def file(self, species: str, path: str) -> tuple[bytes, str]:
        r = self.active(species)
        try:
            return r.file(path), media_type(path)
        except KeyError as exc:
            raise ApiError(404, "unknown library file") from exc

    # ------------------------------------------------------------------ compositions
    def _row(self, db, cid: str) -> CompositionRow:
        row = db.get(CompositionRow, cid)
        if not row:
            raise ApiError(404, f"unknown composition {cid}")
        return row

    def create(self, body: m.CompositionCreate, base: str = "") -> m.CompositionStatus:
        comp = body.composition
        if comp.get("species") not in ("dog", "cat"):
            raise ApiError(422, {"composition": ["species: must be dog or cat"]})
        r = self.active(comp["species"])
        errs = composition_errors(r.manifest, comp)
        if errs:
            raise ApiError(422, {"composition": errs})
        with self.db() as db:
            if not db.get(SessionRow, body.session_id):
                raise ApiError(404, "unknown session")
            row = CompositionRow(id="c_" + uuid.uuid4().hex[:12], session_id=body.session_id, species=comp["species"],
                                 release_version=comp["release_version"], pet_name=comp.get("pet_name") or None, body=comp,
                                 status="draft", created_at=utcnow())
            db.add(row)
            db.commit()
            return self._status(db, row, base)

    def status(self, cid: str, base: str = "") -> m.CompositionStatus:
        with self.db() as db:
            return self._status(db, self._row(db, cid), base)

    def _status(self, db, row: CompositionRow, base: str = "") -> m.CompositionStatus:
        job = db.get(JobRow, row.job_id) if row.job_id else None
        state = row.status
        export = None
        artefacts: list[m.Artefact] = []
        previews: dict[str, str] = {}
        result_url = None
        if job:
            state = {"queued": "exporting", "running": "exporting", "done": "ready", "fulfilled": "ready", "failed": "failed"}[job.status]
            export = m.ExportStatus(job_id=job.id, status=job.status, stage=job.stage, pct=job.pct, message=job.message)
            if state == "ready":
                arts = db.scalars(select(ArtefactRow).where(ArtefactRow.job_id == job.id).order_by(ArtefactRow.id)).all()
                url = lambda key: signed_file_url(self.secret, key)  # noqa: E731
                artefacts = [m.Artefact(name=a.name, kind=a.kind, stage=a.stage, url=url(a.object_key), bytes=a.bytes) for a in arts]
                previews = {a.kind: url(a.object_key) for a in arts if a.kind in ("glb", "thumbnail")}
                result_url = f"{base}/r/{make_token(self.secret, job.id)}"
        return m.CompositionStatus(composition_id=row.id, session_id=row.session_id, status=state, pet_name=row.pet_name,
                                   species=row.species, release_version=row.release_version, created_at=aware(row.created_at),
                                   export=export, ticket=row.ticket, result_url=result_url, artefacts=artefacts, previews=previews,
                                   error=job.error if job and job.status == "failed" else None, composition=row.body)

    def export(self, cid: str) -> m.ExportAccepted:
        """Order: issue the ticket and enqueue Stage F on the kiosk queue (idempotent)."""
        with self.db() as db:
            row = self._row(db, cid)
            if row.job_id:
                job = db.get(JobRow, row.job_id)
                if job and job.status != "failed":
                    return m.ExportAccepted(composition_id=cid, job_id=job.id, ticket=row.ticket, queue_position=0)
            breed = next((b for b in all_breeds(row.species) if b["id"] == row.body.get("breed_id")), None)
            spec_like = {"species": row.species, "seed": 0, "pet_name": row.pet_name or "",
                         "breed": {"id": breed["id"] if breed else "mixed", "label": breed["label"] if breed else "Mixed"},
                         "composition_id": row.id, "composition": row.body}
            job = JobRow(id="j_" + uuid.uuid4().hex[:12], queue="kiosk", kind="export", session_id=row.session_id,
                         requested_by=f"kiosk:{self.s.kiosk_id}", pet_spec=spec_like, status="queued", stage="queued",
                         message="Preparing your order", seed=0, created_at=utcnow())
            db.add(job)
            row.job_id = job.id
            row.ticket = row.ticket or f"PP-{random.randint(1000, 9999)}"
            job.ticket = row.ticket
            row.status = "exporting"
            db.commit()
            self.bus.enqueue(job.id, "kiosk")
            return m.ExportAccepted(composition_id=cid, job_id=job.id, ticket=row.ticket, queue_position=1)

    def orders(self, limit: int = 20) -> list[m.KioskOrder]:
        with self.db() as db:
            rows = db.scalars(select(CompositionRow).where(CompositionRow.job_id.is_not(None))
                              .order_by(CompositionRow.created_at.desc()).limit(limit)).all()
            out = []
            for row in rows:
                st = self._status(db, row)
                out.append(m.KioskOrder(composition_id=row.id, ticket=row.ticket, pet_name=row.pet_name, species=row.species,
                                        status=st.status, created_at=aware(row.created_at), thumbnail_url=st.previews.get("thumbnail")))
            return out

    def reprint(self, cid: str) -> m.KioskOrder:
        """Ops panel: copy the order's print bundle to the fulfilment folder again."""
        with self.db() as db:
            row = self._row(db, cid)
            job = db.get(JobRow, row.job_id) if row.job_id else None
            if not job or job.status not in ("done", "fulfilled"):
                raise ApiError(409, "the order has no finished print bundle yet")
            copy_bundle(self.s.fulfil_dir, self.store, job.id, row.ticket or job.ticket)
            row.reprints += 1
            db.commit()
            st = self._status(db, row)
            return m.KioskOrder(composition_id=row.id, ticket=row.ticket, pet_name=row.pet_name, species=row.species,
                                status=st.status, created_at=aware(row.created_at), thumbnail_url=st.previews.get("thumbnail"))

    def bespoke_spec(self, cid: str) -> tuple[str | None, dict[str, Any], str]:
        """A composition as a bespoke job's starting PetSpec (BRIEF Section 16: POST /compositions/{id}/bespoke)."""
        with self.db() as db:
            row = self._row(db, cid)
            body, session_id, species = row.body, row.session_id, row.species
        return session_id, to_spec(self.active(species).manifest, body, random.randint(1, 2**31 - 1)), species
