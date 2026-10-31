"""Studio's library (BRIEF Sections 16 and 17, M8): batches, curation, the parts and pattern editors, publish with
versioning, and releases.

- A batch is breeds x variants x seeds of `batch` jobs on the studio queue: the full pipeline (stages A to F, so
  every figurine has a GLB and a turntable for review), then `curate()` in the studio worker keeps the figurine's
  own mesh (decision 119) with one family on it for its breed, runs the QC checks and files the family as a
  draft, or as auto-rejected with its reasons.
- Curators accept, reject, tag and add breeds (breeds on one family share its mesh and are labelled so);
  publishing makes an item part of the next release. Editing a
  published item creates a new draft version; publishing it supersedes the old version.
- `POST /studio/releases` packs the latest published version of every item into a signed release bundle
  (petpop_library.packer) and drops it in the kiosk's release inbox.
- On first start Studio imports the committed proxy release as its published starting library, so the first
  Studio release is release-<species>-2.

Library files live in the artefact store under library/<species>/<kind>/<id>/v<version>/.
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import func, select

from backend.core.config import Settings
from backend.core.paths import ROOT
from petpop_core.breeds import all_breeds
from petpop_core.schemas import spec_errors
from petpop_core.spec import apply_patch, default_spec, fill_colour_names
from petpop_library import content, figure, qc, release
from petpop_library.deltas import decode
from petpop_library.extract import normalised_weights
from petpop_library.meshkit import load_base
from petpop_library.packer import pack

from . import models as m
from .contract import ApiError, signed_file_url
from .db import (ArtefactRow, CurationBatchRow, FamilyRow, JobRow, LibraryReleaseRow, PatternLayerRow, RegionDeltaRow,
                 ShellPartRow, utcnow)

log = logging.getLogger("petpop.studio")
PROXY_RELEASES = ROOT / "fixtures" / "library"
ROWS = {"family": FamilyRow, "region": RegionDeltaRow, "shell": ShellPartRow, "pattern": PatternLayerRow}
MANIFEST_KIND = {"family": "families", "region": "region_deltas", "shell": "shell_parts", "pattern": "pattern_layers"}
KIND_OF = {v: k for k, v in MANIFEST_KIND.items()}
MAX_BATCH = 60



def aware(dt):
    from datetime import UTC

    return dt.replace(tzinfo=UTC) if dt and dt.tzinfo is None else dt


def item_key(species: str, kind: str, item_id: str, version: int, name: str) -> str:
    return f"library/{species}/{kind}/{item_id}/v{version}/{name}"


def mesh_key(species: str, mesh_id: str, name: str) -> str:
    return f"library/{species}/meshes/{mesh_id}/{name}"


def put_mesh(store, mesh, meta: dict[str, Any], texture: bytes | None = None,
             prebuilt: tuple[dict[str, Any], dict[str, bytes]] | None = None) -> str:
    """Keep a library mesh in Studio's store (decision 118): its figure package, metadata (name, source job) and its
    release files, built here once (masks, texel maps and thumbnails take seconds) so packing a release is quick."""
    sp, mid = mesh.species, mesh.mesh_id
    store.put(mesh_key(sp, mid, "figure_mesh.npz"), figure.save(mesh))
    store.put(mesh_key(sp, mid, "meta.json"), json.dumps(meta, sort_keys=True).encode())
    if texture is not None:
        store.put(mesh_key(sp, mid, "texture.png"), texture)
    entry, files = prebuilt or content.mesh_entry(mesh, meta["name"], [], int(meta.get("version", 1)), meta.get("source_job"),
                                                  texture=texture)
    for path, data in files.items():
        store.put(mesh_key(sp, mid, f"release/{path}"), data)
    store.put(mesh_key(sp, mid, "release.json"), json.dumps({"entry": entry, "files": sorted(files)}, sort_keys=True).encode())
    return mid


def get_mesh(store, species: str, mesh_id: str):
    """(mesh, meta) of a stored library mesh; meta carries the texture bytes when the mesh has one."""
    mesh = figure.load(store.get(mesh_key(species, mesh_id, "figure_mesh.npz")))
    meta = json.loads(store.get(mesh_key(species, mesh_id, "meta.json")))
    tex = mesh_key(species, mesh_id, "texture.png")
    if store.exists(tex):
        meta["texture"] = store.get(tex)
    built = mesh_key(species, mesh_id, "release.json")
    if store.exists(built):
        doc = json.loads(store.get(built))
        meta["prebuilt"] = (doc["entry"], {p: store.get(mesh_key(species, mesh_id, f"release/{p}")) for p in doc["files"]})
    return mesh, meta


def template_mesh(store, species: str):
    """The species template as a library mesh (stored on first use): what curation measures parts on until
    figurines are published as meshes of their own."""
    base = load_base(species)
    mesh = figure.from_template(base, base.co)
    if not store.exists(mesh_key(species, mesh.mesh_id, "meta.json")):
        put_mesh(store, mesh, {"name": f"Classic {species}", "source_job": None, "version": 1})
    return mesh


# --------------------------------------------------------------------------- curation (studio worker)

def mesh_qc(manifest: dict[str, Any]) -> dict[str, Any]:
    """QC of a figurine as a library mesh (decision 119): it must be the generated mesh (no fallback to the
    template), labelled validly to the schema, and printable."""
    met, fallback = manifest["metrics"], manifest.get("fallback", "none")
    reasons = []
    if fallback not in ("none", "single_view"):
        reasons.append(f"fallback {fallback}: the template shipped, not a generated mesh")
    if not met.get("segmentation_valid", False):
        reasons.append(f"segmentation: {met.get('segmentation_notes', 'invalid')}")
    if not met.get("print_watertight", False):
        reasons.append("print mesh is not watertight")
    if met.get("min_wall_ok") is False:
        reasons.append(f"walls thinner than the printer's minimum ({met.get('min_wall_mm')} mm)")
    return {"mesh_id": met.get("mesh_id"), "segmentation_valid": bool(met.get("segmentation_valid", False)),
            "segmentation_notes": met.get("segmentation_notes", ""), "print_watertight": bool(met.get("print_watertight", False)),
            "min_wall_mm": met.get("min_wall_mm"), "figure_tris": met.get("figure_tris"), "fallback": fallback,
            "passed": not reasons, "reasons": reasons}


def curate(db_factory, store, job_id: str) -> dict[str, Any]:
    """File one finished batch figurine as a library mesh of its own (decision 119): its mesh, with the texture
    the pipeline made for it, and one family on that mesh for its breed, as a draft (or a rejection with QC
    reasons). Other breeds can be added to the family later; they then share the mesh and are labelled so."""
    with db_factory() as db:
        job = db.get(JobRow, job_id)
        batch = db.get(CurationBatchRow, job.batch_id)
        spec, info = job.pet_spec, batch.spec["jobs"][job_id]
    species = spec["species"]
    manifest = json.loads(store.get(f"jobs/{job_id}/manifest.json"))
    q = mesh_qc(manifest)
    mesh = figure.load(store.get(f"jobs/{job_id}/figure_mesh.npz"))
    tag = job_id[2:8]
    breed, variant = info["breed"], info["variant"]
    label = next((b["label"] for b in all_breeds(species) if b["id"] == breed), breed)
    albedo = f"jobs/{job_id}/albedo.png"
    put_mesh(store, mesh, {"name": f"{label} ({variant})", "source_job": job_id, "version": 1},
             store.get(albedo) if store.exists(albedo) else None)
    fid = f"family_{breed}_{tag}"
    files = {"thumbnail": item_key(species, "family", fid, 1, "thumb.png")}
    thumb = f"jobs/{job_id}/thumbnail.png"
    store.put(files["thumbnail"], store.get(thumb) if store.exists(thumb) else content.thumbnail(mesh, mesh.co))
    row = FamilyRow(id=fid, version=1, species=species, base_mesh_version=mesh.schema_version, mesh_id=mesh.mesh_id,
                    name=f"{label} ({variant})", status="draft" if q["passed"] else "rejected", tags=[f"breed:{breed}", f"variant:{variant}"],
                    files=files, meta={"qc": q, "auto_rejected": not q["passed"]}, batch_id=batch.id, source_job=job_id,
                    created_at=utcnow(), default_parts={}, breeds=[breed])
    with db_factory() as db:
        db.merge(row)
        db.commit()
    return q


# --------------------------------------------------------------------------- the service

class StudioLibrary:
    def __init__(self, s: Settings, db, store, bus, secret: str) -> None:
        self.s, self.db, self.store, self.bus, self.secret = s, db, store, bus, secret

    def url(self, key: str | None) -> str | None:
        return signed_file_url(self.secret, key) if key else None

    # ------------------------------------------------------------------ the starting library
    def seed(self) -> None:
        for species in ("dog", "cat"):
            with self.db() as db:
                if db.scalar(select(func.count()).select_from(FamilyRow).where(FamilyRow.species == species)):
                    continue
            bundles = sorted(PROXY_RELEASES.glob(f"release-{species}-*.tar"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
            if bundles:
                self.import_release(bundles[-1].read_bytes(), "proxy")

    def import_release(self, bundle: bytes, source: str) -> str:
        """Every item of a release becomes a published library item (the proxy release seeds Studio)."""
        manifest, files = release.read(bundle)
        species, now = manifest["species"], utcnow()
        for me in manifest["meshes"]:
            d = me["bin"].rsplit("/", 1)[0] + "/"  # the release's own files for the mesh are its prebuilt files
            put_mesh(self.store, figure.load(files[me["package"]]),
                     {"name": me["name"], "source_job": me.get("source_job"), "version": me["version"]},
                     files[me["texture"]] if me.get("texture") else None,
                     prebuilt=(me, {p: data for p, data in files.items() if p.startswith(d)}))
        # Pattern thumbnails are drawn on the first mesh (the template in the proxy release).
        atlas = manifest["meshes"][0]["atlas"]
        for i, path in enumerate(atlas["mask_files"]):
            self.store.put(f"library/{species}/atlas/masks_{i}.png", files[path])
        self.store.put(f"library/{species}/atlas/atlas.json",
                       json.dumps({"size": atlas["size"], "channels": atlas["channels"], "masks": len(atlas["mask_files"]),
                                   "mesh_id": manifest["meshes"][0]["id"]}).encode())
        with self.db() as db:
            for mkind, entries in ((k, manifest[k]) for k in MANIFEST_KIND.values()):
                kind = KIND_OF[mkind]
                for e in entries:
                    stored = {}
                    for field in ("delta", "mesh", "thumbnail"):
                        if e.get(field):
                            key = item_key(species, kind, e["id"], e["version"], Path(e[field]).name)
                            self.store.put(key, files[e[field]])
                            stored[field] = key
                    common = dict(id=e["id"], version=e["version"], species=species, base_mesh_version=manifest["segmentation_version"],
                                  name=e["name"], status="published", tags=e.get("tags", []), files=stored,
                                  meta={"source": source, "release": manifest["release_version"]}, published_at=now, created_at=now)
                    if kind == "family":
                        row = FamilyRow(**common, mesh_id=e["mesh_id"], default_parts=e["default_parts"], breeds=e["breeds"])
                    elif kind == "region":
                        row = RegionDeltaRow(**common, mesh_id=e["mesh_id"], region=e["region"], score=e.get("curator_score"))
                    elif kind == "shell":
                        row = ShellPartRow(**common, socket=e["socket"], kind=e["kind"], default_colour=e["default_colour"])
                    else:
                        common["meta"] = {**common["meta"], "channel": e["channel"]}
                        row = PatternLayerRow(**common, default_colour=e["default_colour"], coverage=e["coverage"])
                    db.merge(row)
            if not db.get(LibraryReleaseRow, manifest["release_version"]):
                db.add(LibraryReleaseRow(id=manifest["release_version"], species=species, number=manifest["number"],
                                         created_by=f"import:{source}", created_at=now, object_key=None,
                                         counts={k: len(manifest[k]) for k in MANIFEST_KIND.values()}, sha256="", bytes=len(bundle)))
            db.commit()
        log.info("studio library seeded from %s (%s)", manifest["release_version"], source)
        return manifest["release_version"]

    # ------------------------------------------------------------------ batches
    def create_batch(self, body: m.BatchCreate, user: m.StaffUser) -> m.Batch:
        species = body.species
        known = {b["id"] for b in all_breeds(species)}
        unknown = [b for b in body.breeds if b not in known]
        if unknown:
            raise ApiError(422, {"breeds": [f"unknown breed {b}" for b in unknown]})
        total = len(body.breeds) * len(body.variants) * body.seeds
        if total > MAX_BATCH:
            raise ApiError(422, {"batch": [f"{total} figurines; at most {MAX_BATCH} per batch"]})
        specs = []
        for breed in body.breeds:
            for variant in body.variants:
                for k in range(body.seeds):
                    seed = body.first_seed + k
                    spec, _ = apply_patch(default_spec(species, breed, seed=seed), variant.patch)
                    spec = fill_colour_names(spec)
                    errs = spec_errors(spec)
                    if errs:
                        raise ApiError(422, {"variants": [f"{variant.label}: {e}" for e in errs[:3]]})
                    specs.append((breed, variant.label, seed, spec))
        bid = "b_" + uuid.uuid4().hex[:10]
        with self.db() as db:
            batch = CurationBatchRow(id=bid, species=species, spec={"request": body.model_dump(), "jobs": {}}, status="running",
                                     created_by=user.username, created_at=utcnow(), genai_profile=body.genai_profile,
                                     pipeline=body.pipeline, options=body.options)
            db.add(batch)
            jobs = {}
            for breed, variant, seed, spec in specs:
                job = JobRow(id="j_" + uuid.uuid4().hex[:12], queue="studio", kind="batch", batch_id=bid, requested_by=user.username,
                             pet_spec=spec, status="queued", stage="queued", seed=seed, created_at=utcnow(),
                             genai_profile=body.genai_profile, pipeline=body.pipeline, options=body.options)
                db.add(job)
                jobs[job.id] = {"breed": breed, "variant": variant, "seed": seed}
            batch.spec = {"request": body.model_dump(), "jobs": jobs}
            db.commit()
        for job_id in jobs:
            self.bus.enqueue(job_id, "studio")
        return self.batch(bid)

    def _items_for_jobs(self, db, job_ids: list[str]) -> dict[str, list]:
        out: dict[str, list] = {j: [] for j in job_ids}
        for Row in (FamilyRow, RegionDeltaRow):
            for r in db.scalars(select(Row).where(Row.source_job.in_(job_ids))).all():
                out[r.source_job].append(r)
        return out

    def batch(self, bid: str) -> m.Batch:
        with self.db() as db:
            b = db.get(CurationBatchRow, bid)
            if not b:
                raise ApiError(404, f"unknown batch {bid}")
            jobs = b.spec["jobs"]
            rows = {j.id: j for j in db.scalars(select(JobRow).where(JobRow.id.in_(list(jobs)))).all()}
            arts = {}
            for a in db.scalars(select(ArtefactRow).where(ArtefactRow.job_id.in_(list(jobs)))).all():
                arts.setdefault(a.job_id, {})[a.kind] = a.object_key
            items = self._items_for_jobs(db, list(jobs))
            figurines = []
            for job_id, info in jobs.items():
                job = rows[job_id]
                cands = [self._candidate(r) for r in sorted(items[job_id], key=lambda r: (r.__tablename__ != "families", r.id))]
                a = arts.get(job_id, {})
                # A figurine is finished once curated: the pipeline is done before its parts are filed.
                curating = job.status == "done" and not cands
                figurines.append(m.BatchFigurine(job_id=job_id, breed_id=info["breed"], variant=info["variant"], seed=info["seed"],
                                                 status="running" if curating else job.status, stage="F" if curating else job.stage,
                                                 error=job.error,
                                                 glb_url=self.url(a.get("glb")), thumbnail_url=self.url(a.get("thumbnail")),
                                                 turntable_url=self.url(a.get("turntable")), candidates=cands))
            return self._batch_model(b, figurines)

    def _batch_model(self, b: CurationBatchRow, figurines: list[m.BatchFigurine]) -> m.Batch:
        done = [f for f in figurines if f.status in ("done", "failed", "fulfilled")]
        cands = [c for f in figurines for c in f.candidates]
        meshes = sum(1 for f in figurines if mesh_published(f.candidates))
        status = b.status
        if status == "running" and figurines and len(done) == len(figurines):
            status = "review"
        if status == "review" and cands and not any(c.status in ("draft", "accepted") for c in cands):
            status = "done"
        summary = m.BatchSummary(figurines=len(figurines), finished=len(done), failed=sum(f.status == "failed" for f in figurines),
                                 candidates=len(cands), passed_qc=sum(not c.auto_rejected for c in cands),
                                 accepted=sum(c.status == "accepted" for c in cands), rejected=sum(c.status == "rejected" for c in cands),
                                 published=sum(c.status == "published" for c in cands), meshes_published=meshes)
        return m.Batch(batch_id=b.id, species=b.species, status=status, created_by=b.created_by, created_at=aware(b.created_at),
                       request=b.spec["request"], genai_profile=b.genai_profile, pipeline=b.pipeline, options=b.options,
                       summary=summary,
                       figurines=figurines)

    def batches(self) -> m.BatchList:
        with self.db() as db:
            ids = [b.id for b in db.scalars(select(CurationBatchRow).order_by(CurationBatchRow.created_at.desc()).limit(50)).all()]
        return m.BatchList(items=[self.batch(i).model_copy(update={"figurines": []}) for i in ids])

    def _candidate(self, r) -> m.LibraryCandidate:
        kind = "family" if r.__tablename__ == "families" else "region"
        return m.LibraryCandidate(id=r.id, version=r.version, kind=kind, region=getattr(r, "region", None), mesh_id=r.mesh_id, name=r.name, status=r.status,
                                  tags=r.tags, qc=r.meta.get("qc", {}), auto_rejected=bool(r.meta.get("auto_rejected")),
                                  thumbnail_url=self.url(r.files.get("thumbnail")))

    def review(self, bid: str, body: m.ReviewRequest, user: m.StaffUser) -> m.Batch:
        with self.db() as db:
            b = db.get(CurationBatchRow, bid)
            if not b:
                raise ApiError(404, f"unknown batch {bid}")
            for d in body.decisions:
                row = self._latest(db, b.species, d.item_id)
                if not row or row.batch_id != bid:
                    raise ApiError(404, f"{d.item_id} is not in batch {bid}")
                if row.status == "published":
                    raise ApiError(409, f"{d.item_id} is published; unpublish it first")
                row.status = "accepted" if d.action == "accept" else "rejected"
                if d.tags is not None:
                    row.tags = sorted(set(d.tags))
                row.meta = {**row.meta, "reviewed_by": user.username, "reviewed_at": utcnow().isoformat()}
            db.commit()
        return self.batch(bid)

    # ------------------------------------------------------------------ items: parts and pattern editors
    def _latest(self, db, species: str, item_id: str, kind: str | None = None):
        for k, Row in ROWS.items():
            if kind and k != kind:
                continue
            row = db.scalars(select(Row).where(Row.species == species, Row.id == item_id).order_by(Row.version.desc())).first()
            if row:
                return row
        return None

    def _item(self, db, row) -> m.LibraryItem:
        kind = next(k for k, Row in ROWS.items() if isinstance(row, Row))
        Row = ROWS[kind]
        mine = (Row.species == row.species, Row.id == row.id)
        versions = sorted(db.scalars(select(Row.version).where(*mine)).all())
        published = db.scalars(select(Row.version).where(*mine, Row.status == "published")).first()
        mesh_id = getattr(row, "mesh_id", None)
        shared: list[str] | None = None
        if kind == "family" and mesh_id:  # other families on the same mesh: their breeds share it
            others = db.scalars(select(FamilyRow).where(FamilyRow.species == row.species, FamilyRow.mesh_id == mesh_id,
                                                        FamilyRow.id != row.id, FamilyRow.status != "rejected")).all()
            shared = sorted({b for o in others for b in o.breeds})
        return m.LibraryItem(mesh_id=mesh_id, shared_with=shared,kind=kind, id=row.id, version=row.version, versions=versions, published_version=published,
                             species=row.species, name=row.name, status=row.status, tags=row.tags,
                             region=getattr(row, "region", None), socket=getattr(row, "socket", None),
                             default_colour=getattr(row, "default_colour", None),
                             coverage=m.PatternCoverage(**row.coverage) if kind == "pattern" else None,
                             breeds=getattr(row, "breeds", None), default_parts=getattr(row, "default_parts", None),
                             qc=row.meta.get("qc"), source_job=row.source_job, batch_id=row.batch_id,
                             thumbnail_url=self.url(row.files.get("thumbnail")), published_at=aware(row.published_at))

    def items(self, species: str, kind: str | None, status: str | None) -> m.LibraryItemList:
        out = []
        with self.db() as db:
            for k, Row in ROWS.items():
                if kind and k != kind:
                    continue
                rows = db.scalars(select(Row).where(Row.species == species).order_by(Row.id, Row.version.desc())).all()
                seen = set()
                for r in rows:  # latest version of each id
                    if r.id in seen:
                        continue
                    seen.add(r.id)
                    if status and r.status != status:
                        continue
                    out.append(self._item(db, r))
        return m.LibraryItemList(species=species, items=out)

    def item(self, species: str, kind: str, item_id: str) -> m.LibraryItem:
        with self.db() as db:
            row = self._latest(db, species, item_id, kind)
            if not row:
                raise ApiError(404, f"unknown {kind} {item_id}")
            return self._item(db, row)

    def edit(self, species: str, kind: str, item_id: str, patch: m.LibraryItemPatch) -> m.LibraryItem:
        with self.db() as db:
            row = self._latest(db, species, item_id, kind)
            if not row:
                raise ApiError(404, f"unknown {kind} {item_id}")
            if row.status == "published":  # editing a published item starts its next version
                row = self._new_version(db, kind, row)
            fields = patch.model_dump(exclude_none=True)
            if "coverage" in fields:
                if kind != "pattern":
                    raise ApiError(422, {"coverage": ["only pattern layers have a coverage range"]})
                c = fields["coverage"]
                if not 0 <= c["min"] <= c["default"] <= c["max"] <= 1:
                    raise ApiError(422, {"coverage": ["needs 0 <= min <= default <= max <= 1"]})
                row.coverage = c
            if "default_colour" in fields:
                if kind not in ("shell", "pattern"):
                    raise ApiError(422, {"default_colour": ["only shells and patterns have a default colour"]})
                row.default_colour = fields["default_colour"].upper()
            if "breeds" in fields:
                if kind != "family":
                    raise ApiError(422, {"breeds": ["only families list breeds"]})
                row.breeds = fields["breeds"]
            for f in ("name", "tags"):
                if f in fields:
                    setattr(row, f, fields[f])
            db.commit()
            return self._item(db, row)

    def _new_version(self, db, kind: str, row):
        Row = ROWS[kind]
        clone = Row(**{c.key: getattr(row, c.key) for c in Row.__table__.columns})
        clone.version = row.version + 1
        clone.status = "draft"
        clone.published_at = None
        clone.created_at = utcnow()
        clone.files = dict(row.files)
        db.add(clone)
        db.flush()
        return clone

    def publish(self, species: str, kind: str, item_id: str, user: m.StaffUser) -> m.LibraryItem:
        """Publish the latest version: it ships in the next release; any earlier published version is superseded.
        The thumbnail (and a pattern's preview) is regenerated from the item as published."""
        with self.db() as db:
            row = self._latest(db, species, item_id, kind)
            if not row:
                raise ApiError(404, f"unknown {kind} {item_id}")
            if row.status == "published":
                return self._item(db, row)
            if row.status == "rejected":
                raise ApiError(409, f"{item_id} is rejected; accept it in review first")
            Row = ROWS[kind]
            for old in db.scalars(select(Row).where(Row.species == species, Row.id == item_id, Row.status == "published")).all():
                old.status = "superseded"
            key = item_key(species, kind, item_id, row.version, "thumb.png")
            self.store.put(key, self._thumbnail(kind, row))
            row.files = {**row.files, "thumbnail": key}
            row.status = "published"
            row.published_at = utcnow()
            row.meta = {**row.meta, "published_by": user.username}
            db.commit()
            return self._item(db, row)

    def unpublish(self, species: str, kind: str, item_id: str) -> m.LibraryItem:
        with self.db() as db:
            Row = ROWS[kind]
            row = db.scalars(select(Row).where(Row.species == species, Row.id == item_id, Row.status == "published")).first()
            if not row:
                raise ApiError(404, f"{kind} {item_id} has no published version")
            row.status = "accepted"
            db.commit()
            return self._item(db, row)

    def _thumbnail(self, kind: str, row) -> bytes:
        if kind in ("region", "family"):
            base = get_mesh(self.store, row.species, row.mesh_id)[0] if row.mesh_id else load_base(row.species)
            n = len(base.co)
            d = decode(self.store.get(row.files["delta"]), n) if row.files.get("delta") else np.zeros((n, 3))
            if kind == "region":
                return content.thumbnail(base, base.co + d, content.highlight(base, normalised_weights(base)[row.region]))
            return content.thumbnail(base, base.co + d)
        base = load_base(row.species)
        if kind == "pattern":
            atlas = json.loads(self.store.get(f"library/{row.species}/atlas/atlas.json"))
            from petpop_library.paint import read_masks

            masks = read_masks([self.store.get(f"library/{row.species}/atlas/masks_{i}.png") for i in range(atlas["masks"])])
            return content.pattern_thumbnail(base, masks, row.id, row.meta["channel"], row.coverage["default"], row.default_colour)
        import trimesh

        mesh = trimesh.load(io.BytesIO(self.store.get(row.files["mesh"])), file_type="glb", force="mesh")
        return content.mesh_thumbnail(np.asarray(mesh.vertices), np.asarray(mesh.faces), row.default_colour)

    # ------------------------------------------------------------------ releases (Contract 1)
    def create_release(self, species: str, user: m.StaffUser) -> m.ReleaseInfo:
        with self.db() as db:
            latest: dict[str, list] = {}
            for kind, Row in ROWS.items():
                rows = db.scalars(select(Row).where(Row.species == species, Row.status == "published").order_by(Row.id)).all()
                latest[kind] = rows
            number = (db.scalar(select(func.max(LibraryReleaseRow.number)).where(LibraryReleaseRow.species == species)) or 0) + 1
        items, problems = release_entries(latest)
        if problems:
            raise ApiError(409, {"release": problems})
        bundle, manifest = pack(species, number, items, self.store.get, lambda mid: get_mesh(self.store, species, mid),
                                created_by=f"studio:{user.username}", notes=f"Published by {user.username} in PetPop Studio.")
        version = manifest["release_version"]
        key = f"releases/{species}/{version}.tar"
        self.store.put(key, bundle)
        inbox = self.s.release_inbox[0] if self.s.release_inbox else None
        if inbox:
            inbox.mkdir(parents=True, exist_ok=True)
            tmp = inbox / f".{version}.tar.tmp"
            tmp.write_bytes(bundle)
            tmp.replace(inbox / f"{version}.tar")  # the kiosk never sees a half-written bundle
        import hashlib

        counts = {k: len(manifest[k]) for k in MANIFEST_KIND.values()}
        with self.db() as db:
            db.add(LibraryReleaseRow(id=version, species=species, number=number, created_by=user.username, created_at=utcnow(),
                                     object_key=key, counts=counts, sha256=hashlib.sha256(bundle).hexdigest(), bytes=len(bundle)))
            db.commit()
            return self._release(db.get(LibraryReleaseRow, version))

    def _release(self, r: LibraryReleaseRow) -> m.ReleaseInfo:
        return m.ReleaseInfo(release_version=r.id, species=r.species, number=r.number, created_by=r.created_by,
                             created_at=aware(r.created_at), counts=r.counts, bytes=r.bytes, sha256=r.sha256,
                             url=self.url(r.object_key))

    def releases(self) -> m.ReleaseList:
        with self.db() as db:
            rows = db.scalars(select(LibraryReleaseRow).order_by(LibraryReleaseRow.created_at.desc())).all()
            return m.ReleaseList(items=[self._release(r) for r in rows])


def release_entries(latest: dict[str, list]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Manifest entries (with source keys) for the published rows; problems that block a release."""
    problems = []
    # Part variants are optional (a generated mesh has none, decision 119) and only ever belong to their own mesh.
    regions = {(row.mesh_id, row.region): [] for row in latest["region"]}
    for row in latest["region"]:
        regions[(row.mesh_id, row.region)].append(row.id)
    if not latest["family"]:
        problems.append("no published family")
    if not latest["pattern"]:
        problems.append("no published pattern layer")
    items: dict[str, list[dict[str, Any]]] = {}
    items["families"] = [{"id": r.id, "name": r.name, "mesh_id": r.mesh_id, "delta": r.files.get("delta"), "breeds": r.breeds, "tags": r.tags,
                          "version": r.version, "thumbnail": r.files["thumbnail"], "source_job": r.source_job,
                          # A default part that is not published falls back to the first published part of that region
                          # on the family's mesh, or is dropped when the mesh has none.
                          "default_parts": {reg: (pid if pid in regions.get((r.mesh_id, reg), []) else regions[(r.mesh_id, reg)][0])
                                            for reg, pid in r.default_parts.items() if regions.get((r.mesh_id, reg))}}
                         for r in latest["family"]]
    items["region_deltas"] = [{"id": r.id, "name": r.name, "region": r.region, "mesh_id": r.mesh_id, "delta": r.files["delta"], "tags": r.tags,
                               "version": r.version, "thumbnail": r.files["thumbnail"], "source_job": r.source_job,
                               "curator_score": r.score} for r in latest["region"]]
    items["shell_parts"] = [{"id": r.id, "name": r.name, "socket": r.socket, "kind": r.kind, "mesh": r.files["mesh"],
                             "default_colour": r.default_colour, "tags": r.tags, "version": r.version,
                             "thumbnail": r.files["thumbnail"]} for r in latest["shell"]]
    items["pattern_layers"] = [{"id": r.id, "name": r.name, "channel": r.meta["channel"], "default_colour": r.default_colour,
                                "coverage": r.coverage, "tags": r.tags, "version": r.version, "thumbnail": r.files["thumbnail"]}
                               for r in latest["pattern"]]
    return items, problems


def mesh_published(cands: list[m.LibraryCandidate]) -> bool:
    """A figurine whose family, on its own mesh, is published (decision 119)."""
    return any(c.kind == "family" and c.status == "published" for c in cands)
