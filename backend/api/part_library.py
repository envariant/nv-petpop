"""The Studio part library (decision 127): breeds as kits of parts. Curators upload labelled GLBs, Studio makes the
first guess at every joint (petpop_library.parts.auto_rig), the workbench edits rigs, poses and defaults, and a commit
freezes a versioned kit (data/schema/part_kit.schema.json) that releases and the Blender composition script consume.

The same service backs the backend and the mock server (each on its own database and store), so both behave alike.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from datetime import UTC
from typing import Any

import numpy as np
from sqlalchemy import select

from petpop_core.breeds import all_breeds
from petpop_core.schemas import load_schema
from petpop_library import parts as P

from . import models as m
from .contract import ApiError, signed_file_url
from .db import KitRow, PartRow, utcnow

NAME = re.compile(r"^(?P<breed>[a-z0-9_]+)__(?P<kind>head|torso|front_leg|hind_leg|tail)(?:__(?P<variant>[a-z0-9_]{1,40}))?\.glb$")
DEFAULT_POSE = {"pose_id": "standing", "label": "Standing", "legs": {s: 0 for s in P.LEG_SLOTS}, "head": {"yaw": 0, "pitch": 0, "roll": 0}}
LABELS = {"default": "Standard"}


def _aware(d):
    return d.replace(tzinfo=UTC) if d and d.tzinfo is None else d


def read_glb(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    import trimesh  # noqa: PLC0415

    try:
        mesh = trimesh.load(io.BytesIO(data), file_type="glb", force="mesh", process=False)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(422, f"not a readable GLB: {exc}") from exc
    v, f = np.asarray(mesh.vertices, float), np.asarray(mesh.faces, int)
    if not len(v) or not len(f):
        raise ApiError(422, "the GLB has no mesh")
    return v, f


def write_glb(v: np.ndarray, f: np.ndarray) -> bytes:
    import trimesh  # noqa: PLC0415

    return trimesh.Trimesh(v, f, process=False).export(file_type="glb")


class PartLibrary:
    def __init__(self, db, store, secret: str) -> None:
        self.db, self.store, self.secret = db, store, secret
        self._mesh_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    # ------------------------------------------------------------------ helpers
    def _breed_label(self, species: str, breed_id: str) -> str:
        b = next((b for b in all_breeds(species) if b["id"] == breed_id), None)
        return b["label"] if b else breed_id.replace("_", " ").title()

    def _mesh(self, row: PartRow) -> tuple[np.ndarray, np.ndarray]:
        if row.sha256 not in self._mesh_cache:
            self._mesh_cache[row.sha256] = read_glb(self.store.get(row.mesh_key))
        return self._mesh_cache[row.sha256]

    def _kit_row(self, db, species: str, breed_id: str) -> KitRow:
        row = db.get(KitRow, (species, breed_id))
        if not row:
            row = KitRow(species=species, breed_id=breed_id, defaults={}, poses=[DEFAULT_POSE], default_pose="standing",
                         symmetry=True, version=0, dirty=True)
            db.add(row)
        return row

    def _rows(self, db, species: str, breed_id: str) -> list[PartRow]:
        return list(db.scalars(select(PartRow).where(PartRow.species == species, PartRow.breed_id == breed_id)
                               .order_by(PartRow.kind, PartRow.variant)).all())

    def _defaults(self, kit: KitRow, rows: list[PartRow]) -> dict[str, str]:
        out = {}
        for kind in P.KINDS:
            variants = [r.variant for r in rows if r.kind == kind]
            want = (kit.defaults or {}).get(kind)
            out[kind] = want if want in variants else ("default" if "default" in variants else (variants[0] if variants else ""))
        return out

    def _part(self, r: PartRow) -> m.Part:
        rig = r.rig or {}
        guess = {k: m.RigGuess(method=g["method"], confidence=g["confidence"]) for k, g in (r.auto.get("guess") or {}).items()}
        return m.Part(part_id=r.id, kind=r.kind, variant=r.variant, label=r.label, mesh_url=signed_file_url(self.secret, r.mesh_key),
                      tris=r.tris, sha256=r.sha256, joint=rig.get("joint"), attachments=rig.get("attachments"),
                      limits=rig.get("limits"), guess=guess, edited=r.edited, mirrored=r.mirrored)

    def _kit_doc(self, kit: KitRow, rows: list[PartRow]) -> dict[str, Any]:
        """The kit as data/schema/part_kit.schema.json has it (before commit fields)."""
        parts = []
        for r in rows:
            p: dict[str, Any] = {"part_id": r.id, "kind": r.kind, "variant": r.variant, "label": r.label,
                                 "mesh": {"file": r.mesh_key, "sha256": r.sha256, "tris": r.tris}, "uv_layout": f"{kit.species}-{r.kind}-1"}
            rig = r.rig or {}
            if r.kind == "torso":
                p["attachments"] = rig.get("attachments")
            else:
                p["joint"] = rig.get("joint")
            if r.kind == "head":
                p["limits"] = rig.get("limits") or P.DEFAULT_HEAD_LIMITS
            parts.append(p)
        return {"kit_version": "kit-1", "species": kit.species, "breed_id": kit.breed_id, "version": kit.version + 1,
                "parts": parts, "defaults": self._defaults(kit, rows), "poses": kit.poses or [DEFAULT_POSE],
                "default_pose": kit.default_pose}

    def kit(self, species: str, breed_id: str, notes: list[str] | None = None) -> m.PartKit:
        with self.db() as db:
            rows = self._rows(db, species, breed_id)
            kit = db.get(KitRow, (species, breed_id))
            if not rows and not kit:
                raise ApiError(404, f"no parts for {breed_id} yet")
            kit = kit or self._kit_row(db, species, breed_id)
            doc = self._kit_doc(kit, rows)
            return m.PartKit(species=species, breed_id=breed_id, breed_label=self._breed_label(species, breed_id),
                             parts=[self._part(r) for r in rows], defaults={k: v for k, v in doc["defaults"].items() if v},
                             poses=doc["poses"], default_pose=kit.default_pose, symmetry=kit.symmetry, version=kit.version,
                             committed_at=_aware(kit.committed_at), committed_by=kit.committed_by, dirty=kit.dirty,
                             problems=P.kit_problems(doc), notes=notes or [])

    def kits(self, species: str) -> m.PartKitList:
        with self.db() as db:
            breeds = sorted({r for r in db.scalars(select(PartRow.breed_id).where(PartRow.species == species)).all()}
                            | {k.breed_id for k in db.scalars(select(KitRow).where(KitRow.species == species)).all()})
            out = []
            for b in breeds:
                rows = self._rows(db, species, b)
                kit = db.get(KitRow, (species, b)) or self._kit_row(db, species, b)
                out.append(m.PartKitSummary(breed_id=b, breed_label=self._breed_label(species, b),
                                            kinds=sorted({r.kind for r in rows}, key=P.KINDS.index), parts=len(rows),
                                            version=kit.version, dirty=kit.dirty, problems=len(P.kit_problems(self._kit_doc(kit, rows)))))
            db.rollback()  # summaries never create kit rows
            return m.PartKitList(items=out)

    # ------------------------------------------------------------------ upload and the first guess
    def upload(self, species: str, files: list[tuple[str, bytes]], user: str, breed_id: str | None = None) -> m.PartUploadResult:
        taken: list[PartRow] = []
        skipped: list[str] = []
        breeds: set[str] = set()
        with self.db() as db:
            for name, data in files:
                mt = NAME.match(name.lower())
                if not mt:
                    skipped.append(f"{name}: expected <breed>__<kind>[__<variant>].glb")
                    continue
                breed = breed_id or mt["breed"]
                kind, variant = mt["kind"], mt["variant"] or "default"
                try:
                    v, f = read_glb(data)
                except ApiError as exc:
                    skipped.append(f"{name}: {exc.detail}")
                    continue
                v, f, mirrored = P.as_left(kind, v, f)
                glb = write_glb(v, f) if mirrored else data
                sha = hashlib.sha256(glb).hexdigest()
                key = f"parts/{species}/{breed}/{kind}__{variant}__{sha[:12]}.glb"
                self.store.put(key, glb)
                self._mesh_cache[sha] = (v, f)
                row = db.scalar(select(PartRow).where(PartRow.species == species, PartRow.breed_id == breed,
                                                      PartRow.kind == kind, PartRow.variant == variant))
                if not row:
                    row = PartRow(id="pt_" + uuid.uuid4().hex[:12], species=species, breed_id=breed, kind=kind, variant=variant,
                                  label=LABELS.get(variant, variant.replace("_", " ").title()), rig={}, auto={}, edited=False,
                                  created_at=utcnow())
                    db.add(row)
                row.mesh_key, row.sha256, row.tris, row.mirrored = key, sha, int(len(f)), mirrored
                row.uploaded_by, row.updated_at = user, utcnow()
                kit = self._kit_row(db, species, breed)
                kit.dirty = True
                taken.append(row)
                breeds.add(breed)
            db.commit()
            ids = [r.id for r in taken]
        notes: list[str] = []
        for b in sorted(breeds):
            notes += self._guess(species, b)
        with self.db() as db:
            items = [self._part(db.get(PartRow, i)) for i in ids]
        return m.PartUploadResult(items=items, breeds=sorted(breeds), skipped=skipped + notes)

    def _guess(self, species: str, breed_id: str, only: str | None = None, force: bool = False) -> list[str]:
        """Run the first guess for a breed and apply it to every part not edited since (or to `only`, forced)."""
        with self.db() as db:
            rows = self._rows(db, species, breed_id)
            kit = self._kit_row(db, species, breed_id)
            defaults = self._defaults(kit, rows)
            torso = next((r for r in rows if r.kind == "torso" and r.variant == defaults["torso"]), None)
            if not torso:
                db.commit()
                return [f"{breed_id}: no torso yet, so no joints can be found"]
            tv, tf = self._mesh(torso)
            meshes = {f"{r.kind}/{r.variant}": self._mesh(r) for r in rows if r.kind != "torso"}
            guess = P.auto_rig(meshes, (tv, tf))
            for r in rows:
                if only and r.id != only:
                    continue
                if r.edited and not force:
                    continue
                if r.kind == "torso":
                    att = {s: {"position": [float(x) for x in a["position"]], "axis": [float(x) for x in a["axis"]], "twist": 0.0}
                           for s, a in guess.attachments.items()}
                    r.rig = {"attachments": att}
                    r.auto = {"guess": {s: {"method": a["method"], "confidence": a["confidence"]} for s, a in guess.attachments.items()}}
                else:
                    j = guess.joints[f"{r.kind}/{r.variant}"]
                    r.rig = {"joint": {"pivot": [float(x) for x in j["pivot"]], "axis": [float(x) for x in j["axis"]], "twist": 0.0},
                             **({"limits": (r.rig or {}).get("limits") or P.DEFAULT_HEAD_LIMITS} if r.kind == "head" else {})}
                    r.auto = {"guess": {"joint": {"method": j["method"], "confidence": j["confidence"]}}}
                if force:
                    r.edited = False
                r.updated_at = utcnow()
            kit.dirty = True
            db.commit()
            return guess.notes

    def reguess(self, species: str, breed_id: str, part_id: str) -> m.PartKit:
        with self.db() as db:
            row = db.get(PartRow, part_id)
            if not row or row.species != species or row.breed_id != breed_id:
                raise ApiError(404, f"unknown part {part_id}")
        notes = self._guess(species, breed_id, only=part_id, force=True)
        return self.kit(species, breed_id, notes)

    # ------------------------------------------------------------------ workbench edits
    def edit(self, species: str, breed_id: str, part_id: str, patch: m.PartRigPatch) -> m.PartKit:
        with self.db() as db:
            row = db.get(PartRow, part_id)
            if not row or row.species != species or row.breed_id != breed_id:
                raise ApiError(404, f"unknown part {part_id}")
            rig = dict(row.rig or {})
            if patch.label is not None:
                row.label = patch.label.strip() or row.label
            if patch.joint is not None:
                if row.kind == "torso":
                    raise ApiError(422, "the torso has attachments, not a joint")
                rig["joint"] = self._check_joint(patch.joint.model_dump(), "pivot")
            if patch.attachments is not None:
                if row.kind != "torso":
                    raise ApiError(422, "only the torso has attachments")
                att = dict(rig.get("attachments") or {})
                for slot, a in patch.attachments.items():
                    att[slot] = self._check_joint(a.model_dump(), "position")
                rig["attachments"] = att
            if patch.limits is not None:
                if row.kind != "head":
                    raise ApiError(422, "only the head has limits")
                lim = patch.limits.model_dump()
                if any(lo > hi for lo, hi in lim.values()):
                    raise ApiError(422, "each limit is [low, high]")
                rig["limits"] = lim
            row.rig = rig
            if patch.joint is not None or patch.attachments is not None or patch.limits is not None:
                row.edited = True
            row.updated_at = utcnow()
            self._kit_row(db, species, breed_id).dirty = True
            db.commit()
        return self.kit(species, breed_id)

    def _check_joint(self, j: dict[str, Any], point: str) -> dict[str, Any]:
        try:
            axis = P.unit(j["axis"])
        except ValueError as exc:
            raise ApiError(422, "an axis must not be zero") from exc
        return {point: [float(x) for x in j[point]], "axis": [float(x) for x in axis], "twist": float(j.get("twist", 0.0)) % 360.0}

    def setup(self, species: str, breed_id: str, body: m.PartKitSetup) -> m.PartKit:
        with self.db() as db:
            kit = self._kit_row(db, species, breed_id)
            rows = self._rows(db, species, breed_id)
            if body.defaults is not None:
                for kind, variant in body.defaults.items():
                    if not any(r.kind == kind and r.variant == variant for r in rows):
                        raise ApiError(422, f"no {kind} variant {variant}")
                kit.defaults = {**(kit.defaults or {}), **body.defaults}
            if body.poses is not None:
                ids = [p.pose_id for p in body.poses]
                if len(set(ids)) != len(ids):
                    raise ApiError(422, "pose ids must be unique")
                kit.poses = [p.model_dump() for p in body.poses]
                if kit.default_pose not in ids:
                    kit.default_pose = ids[0]
            if body.default_pose is not None:
                if body.default_pose not in [p["pose_id"] for p in kit.poses or [DEFAULT_POSE]]:
                    raise ApiError(422, f"no pose {body.default_pose}")
                kit.default_pose = body.default_pose
            if body.symmetry is not None:
                kit.symmetry = body.symmetry
            kit.dirty = True
            db.commit()
        return self.kit(species, breed_id)

    def delete(self, species: str, breed_id: str, part_id: str) -> m.PartKit:
        with self.db() as db:
            row = db.get(PartRow, part_id)
            if not row or row.species != species or row.breed_id != breed_id:
                raise ApiError(404, f"unknown part {part_id}")
            db.delete(row)
            self._kit_row(db, species, breed_id).dirty = True
            db.commit()
        return self.kit(species, breed_id)

    # ------------------------------------------------------------------ commit
    def commit(self, species: str, breed_id: str, user: str) -> m.PartKit:
        """Freeze the kit as its next version: checked, valid against the kit schema, written to the store."""
        import jsonschema  # noqa: PLC0415

        with self.db() as db:
            kit = self._kit_row(db, species, breed_id)
            rows = self._rows(db, species, breed_id)
            doc = self._kit_doc(kit, rows)
            problems = P.kit_problems(doc)
            if problems:
                raise ApiError(409, {"kit": problems})
            doc["committed_by"], doc["committed_at"] = user, utcnow().replace(tzinfo=UTC).isoformat()
            jsonschema.validate(doc, load_schema("part_kit.schema.json"))
            key = f"kits/{species}/{breed_id}/kit-{doc['version']}.json"
            self.store.put(key, (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode())
            kit.version, kit.committed_key, kit.committed_by, kit.committed_at, kit.dirty = doc["version"], key, user, utcnow(), False
            db.commit()
        return self.kit(species, breed_id)

    def committed(self, species: str, breed_id: str) -> dict[str, Any] | None:
        """The breed's latest committed kit document, or None."""
        with self.db() as db:
            kit = db.get(KitRow, (species, breed_id))
            key = kit.committed_key if kit else None
        return json.loads(self.store.get(key)) if key else None
