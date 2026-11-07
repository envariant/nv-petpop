"""The Studio part library (decisions 127, 130): breeds as kits of parts. Curators upload labelled GLBs, Studio makes
the first guess at every joint (petpop_library.parts.auto_rig), the workbench edits rigs, poses and defaults, and a
commit freezes a versioned kit (data/schema/part_kit.schema.json) that releases and the Blender composition script
consume.

Decision 130: the torsos, legs and tails are a shared library (breed id `shared`, files `shared__<kind>__<variant>.glb`)
that every breed draws on; each breed brings its own head. A breed's kit is its own parts plus the shared ones it does
not override; it allows some shared variants per kind (first its part types in the breed database), stretches each
shared part per axis to its proportions (first the size guess, petpop_library.part_sizes), and has a default texture
configuration. A shared part's rig is the same for every breed, so editing it from any breed's workbench edits it for
all.

Decision 131: what a breed's kit starts with comes from the per-breed parts file (petpop_library.breed_parts,
data/breeds/<species>_breed_parts.json), not the breed database. Each torso variant on a breed has named presets, the
customers' shape choices: the default (the variant's stretch, no offsets) and others, each a stretch and offsets that
move and turn the torso's sockets for this breed. A breed's head variants are its own.

The same service backs the backend and the mock server (each on its own database and store), so both behave alike.
"""
from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import UTC
from typing import Any

import numpy as np
from sqlalchemy import select, update

from petpop_core.breeds import all_breeds
from petpop_core.schemas import load_schema
from petpop_library import breed_parts as B
from petpop_library import part_sizes as S
from petpop_library import parts as P

from . import models as m
from .contract import ApiError, signed_file_url
from .db import KitRow, PartRow, utcnow

ZERO_HEAD = {"yaw": 0, "pitch": 0, "roll": 0}
DEFAULT_POSE = {"pose_id": "standing", "label": "Standing", "legs": {s: 0 for s in P.LEG_SLOTS}, "head": ZERO_HEAD}
LABELS = {"default": "Standard"}
SHARED_NOTE = ("The shared library: torsos, legs and tails every breed draws on. Rig them here or from any breed's "
               "workbench; each breed allows and stretches them in its own kit.")


def sitting_pose(variant: str) -> dict[str, Any]:
    """The breed database's pose: sitting, the hind legs folded (decision 130)."""
    return {"pose_id": "sitting", "label": "Sitting", "legs": {s: 0 for s in P.LEG_SLOTS}, "head": ZERO_HEAD,
            "variants": {"hind_leg": variant}}


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


class PartLibrary:
    def __init__(self, db, store, secret: str) -> None:
        self.db, self.store, self.secret = db, store, secret
        self._mesh_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    # ------------------------------------------------------------------ helpers
    def _breed_label(self, species: str, breed_id: str) -> str:
        if breed_id == P.SHARED:
            return "Shared parts"
        b = next((b for b in all_breeds(species) if b["id"] == breed_id), None)
        row = ((S.table(species) or {}).get("breeds") or {}).get(breed_id)  # the pebble database has more breeds
        return b["label"] if b else row["label"] if row else breed_id.replace("_", " ").title()

    def _mesh(self, row: PartRow) -> tuple[np.ndarray, np.ndarray]:
        if row.sha256 not in self._mesh_cache:
            self._mesh_cache[row.sha256] = read_glb(self.store.get(row.mesh_key))
        return self._mesh_cache[row.sha256]

    def _rows(self, db, species: str, breed_id: str) -> list[PartRow]:
        return list(db.scalars(select(PartRow).where(PartRow.species == species, PartRow.breed_id == breed_id)
                               .order_by(PartRow.kind, PartRow.variant)).all())

    def _available(self, db, species: str, breed_id: str) -> list[PartRow]:
        """The breed's own parts and the shared ones it does not override (a head is never shared)."""
        own = self._rows(db, species, breed_id)
        if breed_id == P.SHARED:
            return own
        have = {(r.kind, r.variant) for r in own}
        shared = [r for r in self._rows(db, species, P.SHARED) if (r.kind, r.variant) not in have and r.kind != "head"]
        return sorted(own + shared, key=lambda r: (P.KINDS.index(r.kind), r.variant))

    def _kit_row(self, db, species: str, breed_id: str) -> KitRow:
        row = db.get(KitRow, (species, breed_id))
        if not row:
            rec = B.recipe(species, breed_id)
            row = KitRow(species=species, breed_id=breed_id, defaults={}, poses=[DEFAULT_POSE],
                         default_pose="standing", symmetry=True, version=0, dirty=True, allowed=rec["allowed"],
                         stretch=rec["stretch"], texture=rec["texture"], presets=rec["presets"])
            db.add(row)
        return row

    def _refresh(self, kit: KitRow, avail: list[PartRow]) -> None:
        """The breed database sits every breed: once its sitting hind leg is in the library, a kit whose poses were
        never changed gets the sitting pose, as the default."""
        sitting = B.recipe(kit.species, kit.breed_id)["sitting"]
        if sitting and (kit.poses or [DEFAULT_POSE]) == [DEFAULT_POSE] and any(
                r.kind == "hind_leg" and r.variant == sitting for r in avail):
            kit.poses = [DEFAULT_POSE, sitting_pose(sitting)]
            kit.default_pose = "sitting"

    def _allowed_base(self, kit: KitRow, avail: list[PartRow], kind: str) -> list[str]:
        """A kind's allowed variants before the default: the breed's own parts, and the shared ones it allows (every
        one, for the shared library itself)."""
        listed = set((kit.allowed or {}).get(kind) or [])
        return [r.variant for r in avail if r.kind == kind
                and (r.breed_id == kit.breed_id or kit.breed_id == P.SHARED or r.variant in listed)]

    def _defaults(self, kit: KitRow, avail: list[PartRow]) -> dict[str, str]:
        """Per kind: the default set in the workbench; else the breed's own part ("default" first); else its part type
        in the breed database, from the shared library; else the first variant it allows."""
        recipe = B.recipe(kit.species, kit.breed_id)["defaults"]
        out = {}
        for kind in P.KINDS:
            variants = [r.variant for r in avail if r.kind == kind]
            own = [r.variant for r in avail if r.kind == kind and r.breed_id == kit.breed_id]
            base = self._allowed_base(kit, avail, kind)
            want = (kit.defaults or {}).get(kind)
            if want in variants:
                out[kind] = want
            elif own:
                out[kind] = "default" if "default" in own else own[0]
            elif recipe.get(kind) in variants:
                out[kind] = recipe[kind]
            else:
                out[kind] = "default" if "default" in base else (base[0] if base else "")
        return out

    def _allowed(self, kit: KitRow, avail: list[PartRow]) -> dict[str, list[str]]:
        defaults = self._defaults(kit, avail)
        out = {}
        for kind in P.KINDS:
            base = set(self._allowed_base(kit, avail, kind)) | ({defaults[kind]} if defaults[kind] else set())
            out[kind] = [r.variant for r in avail if r.kind == kind and r.variant in base]
        return out

    def _stretch(self, kit: KitRow, r: PartRow) -> tuple[list[float], bool]:
        """A part's stretch on this breed, and whether the workbench set it: set, else the size guess for a shared part
        on a breed, else none."""
        key = f"{r.kind}/{r.variant}"
        if key in (kit.stretch or {}):
            return [float(x) for x in kit.stretch[key]], True
        if r.breed_id == P.SHARED and kit.breed_id != P.SHARED:
            v, _ = self._mesh(r)
            return S.stretch_guess(kit.species, kit.breed_id, r.kind, r.variant, np.ptp(v, axis=0)), False
        return [1.0, 1.0, 1.0], False

    def _presets(self, kit: KitRow, r: PartRow) -> list[dict[str, Any]]:
        """A torso's presets on this breed (decision 131), the default first, each stretch filled in: the default's is
        the variant's own (set, or the size guess); another's is its own, or the default's when it has none."""
        if r.kind != "torso":
            return []
        stored = (kit.presets or {}).get(f"torso/{r.variant}") or []
        base = self._stretch(kit, r)[0]
        first = next((x for x in stored if x.get("preset_id") == "default"), B.default_preset())
        out = [{"preset_id": "default", "label": first.get("label") or "Standard", "stretch": base, "sockets": first.get("sockets") or {}}]
        for x in stored:
            if x.get("preset_id") != "default":
                out.append({"preset_id": x["preset_id"], "label": x.get("label") or x["preset_id"],
                            "stretch": [float(v) for v in x["stretch"]] if x.get("stretch") else base, "sockets": x.get("sockets") or {}})
        return out

    def _part(self, r: PartRow, kit: KitRow | None = None) -> m.Part:
        rig = r.rig or {}
        guess = {k: m.RigGuess(method=g["method"], confidence=g["confidence"]) for k, g in (r.auto.get("guess") or {}).items()}
        stretch, set_ = self._stretch(kit, r) if kit else ([1.0, 1.0, 1.0], False)
        return m.Part(part_id=r.id, kind=r.kind, variant=r.variant, label=r.label, mesh_url=signed_file_url(self.secret, r.mesh_key),
                      tris=r.tris, sha256=r.sha256, joint=rig.get("joint"), attachments=rig.get("attachments"),
                      limits=rig.get("limits"), guess=guess, edited=r.edited, mirrored=r.mirrored,
                      shared=r.breed_id == P.SHARED, stretch=stretch, stretch_edited=set_,
                      presets=self._presets(kit, r) if kit else [])

    def _kit_doc(self, kit: KitRow, avail: list[PartRow]) -> dict[str, Any]:
        """The kit as data/schema/part_kit.schema.json has it (before commit fields): the allowed parts only."""
        allowed = self._allowed(kit, avail)
        parts = []
        for r in avail:
            if r.variant not in allowed[r.kind]:
                continue
            p: dict[str, Any] = {"part_id": r.id, "kind": r.kind, "variant": r.variant, "label": r.label,
                                 "mesh": {"file": r.mesh_key, "sha256": r.sha256, "tris": r.tris},
                                 "uv_layout": P.uv_layout(kit.species, kit.breed_id, r.kind),
                                 "shared": r.breed_id == P.SHARED, "stretch": self._stretch(kit, r)[0]}
            rig = r.rig or {}
            if r.kind == "torso":
                p["attachments"] = rig.get("attachments")
                p["presets"] = self._presets(kit, r)
            else:
                p["joint"] = rig.get("joint")
            if r.kind == "head":
                p["limits"] = rig.get("limits") or P.DEFAULT_HEAD_LIMITS
            parts.append(p)
        return {"kit_version": "kit-3", "species": kit.species, "breed_id": kit.breed_id, "version": kit.version + 1,
                "parts": parts, "defaults": self._defaults(kit, avail), "allowed": {k: v for k, v in allowed.items() if v},
                "texture": kit.texture, "poses": kit.poses or [DEFAULT_POSE], "default_pose": kit.default_pose}

    def _all_dirty(self, db, species: str) -> None:
        """A shared part changed: every breed's kit is out of date."""
        db.execute(update(KitRow).where(KitRow.species == species).values(dirty=True))

    def kit(self, species: str, breed_id: str, notes: list[str] | None = None) -> m.PartKit:
        with self.db() as db:
            avail = self._available(db, species, breed_id)
            kit = db.get(KitRow, (species, breed_id))
            if not self._rows(db, species, breed_id) and not kit:
                raise ApiError(404, f"no parts for {breed_id} yet")
            kit = kit or self._kit_row(db, species, breed_id)
            self._refresh(kit, avail)
            db.commit()
            doc = self._kit_doc(kit, avail)
            shared = breed_id == P.SHARED
            return m.PartKit(species=species, breed_id=breed_id, breed_label=self._breed_label(species, breed_id),
                             parts=[self._part(r, kit) for r in avail], defaults={k: v for k, v in doc["defaults"].items() if v},
                             poses=doc["poses"], default_pose=kit.default_pose, symmetry=kit.symmetry, allowed=doc["allowed"],
                             texture=kit.texture, version=kit.version, committed_at=_aware(kit.committed_at),
                             committed_by=kit.committed_by, dirty=kit.dirty and not shared,
                             problems=[] if shared else P.kit_problems(doc), notes=([SHARED_NOTE] if shared else []) + (notes or []))

    def kits(self, species: str) -> m.PartKitList:
        with self.db() as db:
            breeds = sorted({r for r in db.scalars(select(PartRow.breed_id).where(PartRow.species == species)).all()}
                            | {k.breed_id for k in db.scalars(select(KitRow).where(KitRow.species == species)).all()},
                            key=lambda b: (b != P.SHARED, b))
            out = []
            for b in breeds:
                avail = self._available(db, species, b)
                kit = db.get(KitRow, (species, b)) or self._kit_row(db, species, b)
                shared = b == P.SHARED
                out.append(m.PartKitSummary(breed_id=b, breed_label=self._breed_label(species, b),
                                            kinds=sorted({r.kind for r in avail}, key=P.KINDS.index), parts=len(avail),
                                            version=kit.version, dirty=kit.dirty and not shared,
                                            problems=0 if shared else len(P.kit_problems(self._kit_doc(kit, avail)))))
            db.rollback()  # summaries never create kit rows
            return m.PartKitList(items=out)

    # ------------------------------------------------------------------ upload and the first guess
    def upload(self, species: str, files: list[tuple[str, bytes]], user: str, breed_id: str | None = None,
               scale: bool = True) -> m.PartUploadResult:
        """`scale` (the default) fits each part to its size guess (decision 128: the breed's, or for the shared library
        the median of the breeds using that variant); off for parts already in proportion (split from one figure)."""
        taken: list[PartRow] = []
        skipped: list[str] = []
        done: list[str] = []
        breeds: set[str] = set()
        with self.db() as db:
            for name, data in files:
                parsed = P.parse_name(name)
                if not parsed:
                    skipped.append(f"{name}: expected <breed>__<kind>[__<variant>].glb (breed 'shared' for the shared library)")
                    continue
                breed, kind, variant = parsed
                breed = breed_id or breed
                if breed == P.SHARED and kind == "head":
                    skipped.append(f"{name}: a head belongs to its breed, not the shared library")
                    continue
                try:
                    v, f = read_glb(data)
                except ApiError as exc:
                    skipped.append(f"{name}: {exc.detail}")
                    continue
                matrix, mirrored, what = S.normalise(species, breed, kind, variant, v, scale)
                done += [f"{name}: {w}" for w in what]
                glb = data
                if matrix is not None:
                    glb = S.transform_glb(data, matrix)
                    v, f = read_glb(glb)
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
                row.auto = {**(row.auto or {}), "in_place": not scale}  # split from one figure, or exported on its own
                row.uploaded_by, row.updated_at = user, utcnow()
                kit = self._kit_row(db, species, breed)
                kit.dirty = True
                taken.append(row)
                breeds.add(breed)
            if P.SHARED in breeds:
                self._all_dirty(db, species)
            db.commit()
            ids = [r.id for r in taken]
        notes: list[str] = []
        for b in sorted(breeds):
            notes += self._guess(species, b)
        with self.db() as db:
            items = [self._part(db.get(PartRow, i), self._kit_row(db, species, db.get(PartRow, i).breed_id)) for i in ids]
            db.rollback()
        return m.PartUploadResult(items=items, breeds=sorted(breeds), skipped=skipped, notes=done + notes)

    def _guess(self, species: str, breed_id: str, only: str | None = None, force: bool = False) -> list[str]:
        """Run the first guess for a breed's own parts (the shared library's, for `shared`) and apply it to every part
        not edited since (or to `only`, forced). Joints are found against the breed's default torso, its own or shared."""
        with self.db() as db:
            rows = self._rows(db, species, breed_id)
            avail = self._available(db, species, breed_id)
            kit = self._kit_row(db, species, breed_id)
            self._refresh(kit, avail)
            defaults = self._defaults(kit, avail)
            torso = next((r for r in avail if r.kind == "torso" and r.variant == defaults["torso"]), None)
            limbs = {f"{r.kind}/{r.variant}": self._mesh(r) for r in rows if r.kind != "torso"}
            notes: list[str] = []
            if torso:
                # parts exported on their own (and anything rigged against a torso that was) are guessed from their shape
                placed = (torso.auto or {}).get("in_place", True)
                in_place = {f"{r.kind}/{r.variant}" for r in rows if (r.auto or {}).get("in_place", True)} if placed else set()
                guess = P.auto_rig(limbs, self._mesh(torso), in_place, ground=None if placed else 0.0)
            else:
                guess = P.AutoRig()
                guess.joints = {k: P.part_joint(k.split("/", 1)[0], v, f, None) for k, (v, f) in limbs.items()}
                if limbs:
                    notes.append(f"{breed_id}: no torso yet, so each joint is guessed from its part's shape alone")
            missing = [k for k in P.KINDS if not any(r.kind == k for r in avail) and not (k == "head" and breed_id == P.SHARED)]
            if missing:
                notes.append(f"{breed_id}: no {', '.join(k.replace('_', ' ') for k in missing)} yet")
            for r in rows:
                if only and r.id != only:
                    continue
                if r.edited and not force:
                    continue
                if r.kind == "torso":
                    if (r.auto or {}).get("in_place", True) and guess.attachments:
                        found = guess.attachments
                    else:  # a torso on its own: its sockets from its own shape
                        found = P.torso_attachments(*self._mesh(r), {})
                    r.rig = {"attachments": {s: {"position": [float(x) for x in a["position"]], "axis": [float(x) for x in a["axis"]],
                                                 "twist": 0.0} for s, a in found.items()}}
                    r.auto = {**(r.auto or {}), "guess": {s: {"method": a["method"], "confidence": a["confidence"]} for s, a in found.items()}}
                else:
                    j = guess.joints[f"{r.kind}/{r.variant}"]
                    r.rig = {"joint": {"pivot": [float(x) for x in j["pivot"]], "axis": [float(x) for x in j["axis"]], "twist": 0.0},
                             **({"limits": (r.rig or {}).get("limits") or P.DEFAULT_HEAD_LIMITS} if r.kind == "head" else {})}
                    r.auto = {**(r.auto or {}), "guess": {"joint": {"method": j["method"], "confidence": j["confidence"]}}}
                if force:
                    r.edited = False
                r.updated_at = utcnow()
            kit.dirty = True
            if breed_id == P.SHARED:
                self._all_dirty(db, species)
            db.commit()
            return notes

    def _own_or_shared(self, db, species: str, breed_id: str, part_id: str) -> PartRow:
        row = db.get(PartRow, part_id)
        if not row or row.species != species or row.breed_id not in (breed_id, P.SHARED):
            raise ApiError(404, f"unknown part {part_id}")
        return row

    def reguess(self, species: str, breed_id: str, part_id: str) -> m.PartKit:
        with self.db() as db:
            owner = self._own_or_shared(db, species, breed_id, part_id).breed_id
        notes = self._guess(species, owner, only=part_id, force=True)
        return self.kit(species, breed_id, notes)

    # ------------------------------------------------------------------ workbench edits
    def edit(self, species: str, breed_id: str, part_id: str, patch: m.PartRigPatch) -> m.PartKit:
        """Edit a part's rig. A shared part may be edited from any breed's workbench: the edit is the same for all."""
        with self.db() as db:
            row = self._own_or_shared(db, species, breed_id, part_id)
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
            if row.breed_id == P.SHARED:
                self._all_dirty(db, species)
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
            avail = self._available(db, species, breed_id)
            have = {(r.kind, r.variant) for r in avail}

            def need(kind: str, variant: str) -> None:
                if (kind, variant) not in have:
                    raise ApiError(422, f"no {kind} variant {variant}")

            if body.allowed is not None:
                for kind, variants in body.allowed.items():
                    for v in variants:
                        need(kind, v)
                kit.allowed = {**(kit.allowed or {}), **{k: list(dict.fromkeys(v)) for k, v in body.allowed.items()}}
            if body.defaults is not None:
                for kind, variant in body.defaults.items():
                    need(kind, variant)
                kit.defaults = {**(kit.defaults or {}), **body.defaults}
                allowed = dict(kit.allowed or {})  # a default is always allowed
                for kind, variant in body.defaults.items():
                    allowed[kind] = list(dict.fromkeys([*(allowed.get(kind) or []), variant]))
                kit.allowed = allowed
            if body.stretch is not None:
                stretch = dict(kit.stretch or {})
                for key, s in body.stretch.items():
                    kind, variant = key.split("/", 1)
                    need(kind, variant)
                    if s is None:
                        stretch.pop(key, None)
                    elif any(x <= 0 for x in s):
                        raise ApiError(422, "a stretch must be positive")
                    else:
                        stretch[key] = [float(x) for x in s]
                kit.stretch = stretch
            if body.texture is not None:
                kit.texture = body.texture.model_dump()
            if body.presets is not None:
                presets = dict(kit.presets or {})
                for key, items in body.presets.items():
                    need("torso", key.split("/", 1)[1])
                    ids = [x.preset_id for x in items]
                    if len(set(ids)) != len(ids):
                        raise ApiError(422, "preset ids must be unique")
                    if any(x.stretch and any(v <= 0 for v in x.stretch) for x in items):
                        raise ApiError(422, "a stretch must be positive")
                    rows = [x.model_dump() for x in items]
                    default = next((x for x in rows if x["preset_id"] == "default"), B.default_preset())
                    default["stretch"] = None  # the default's stretch is the variant's own: set it with `stretch`
                    presets[key] = [default] + [x for x in rows if x["preset_id"] != "default"]
                kit.presets = presets
            if body.poses is not None:
                ids = [p.pose_id for p in body.poses]
                if len(set(ids)) != len(ids):
                    raise ApiError(422, "pose ids must be unique")
                for p in body.poses:
                    for kind, v in p.variants.items():
                        need(kind, v)
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
        """Remove one of the breed's own parts (a shared part from the shared library's page)."""
        with self.db() as db:
            row = db.get(PartRow, part_id)
            if not row or row.species != species or row.breed_id != breed_id:
                raise ApiError(404, f"unknown part {part_id}")
            db.delete(row)
            self._kit_row(db, species, breed_id).dirty = True
            if breed_id == P.SHARED:
                self._all_dirty(db, species)
            db.commit()
        return self.kit(species, breed_id)

    # ------------------------------------------------------------------ commit
    def commit(self, species: str, breed_id: str, user: str) -> m.PartKit:
        """Freeze the kit as its next version: checked, valid against the kit schema, written to the store."""
        import jsonschema  # noqa: PLC0415

        if breed_id == P.SHARED:
            raise ApiError(422, "the shared library is committed with each breed's kit, not on its own")
        with self.db() as db:
            kit = self._kit_row(db, species, breed_id)
            doc = self._kit_doc(kit, self._available(db, species, breed_id))
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

    def document(self, species: str, breed_id: str) -> dict[str, Any]:
        """The kit as it stands, uncommitted (version 0): what scripts/draft_parts.py composes."""
        with self.db() as db:
            kit = self._kit_row(db, species, breed_id)
            self._refresh(kit, self._available(db, species, breed_id))
            doc = self._kit_doc(kit, self._available(db, species, breed_id))
            db.rollback()
        return {**doc, "version": 0, "problems": P.kit_problems(doc)}

    def committed(self, species: str, breed_id: str) -> dict[str, Any] | None:
        """The breed's latest committed kit document, or None."""
        with self.db() as db:
            kit = db.get(KitRow, (species, breed_id))
            key = kit.committed_key if kit else None
        return json.loads(self.store.get(key)) if key else None
