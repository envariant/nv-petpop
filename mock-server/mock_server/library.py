"""Library mode in the mock server (BRIEF Section 16): the proxy releases from fixtures/library/, compositions in
memory, and exports that "finish" after a short scripted delay with the fixture pack's artefacts (no Blender)."""
from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import dataclass
from typing import Any

from backend.api import models as m
from backend.api.contract import ApiError, make_token, signed_file_url
from backend.api.library import families_model, media_type, parts_model, patterns_model, release_model
from backend.core.paths import FIXTURES, ROOT
from petpop_library import release
from petpop_library.composition import errors as composition_errors
from petpop_library.composition import to_spec

LIBRARY_DIR = ROOT / "fixtures" / "library"
EXPORT_S = 6.0  # scripted export time (x PETPOP_MOCK_SPEED)


@dataclass
class MockComposition:
    id: str
    session_id: str
    body: dict[str, Any]
    created: float
    ticket: str | None = None
    export_start: float | None = None
    speed: float = 0.1
    pet: str = "biscuit"
    reprints: int = 0
    bespoke_job: str | None = None

    def export_state(self, now: float) -> dict[str, Any]:
        if self.export_start is None:
            return {"status": "draft"}
        t = (now - self.export_start) / max(EXPORT_S * self.speed, 1e-6)
        if t >= 1:
            return {"status": "ready", "stage": "done", "pct": 100, "message": "Your figurine is ready"}
        return {"status": "exporting", "stage": "F", "pct": int(10 + 85 * t), "message": "Preparing the print file"}


class MockLibrary:
    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.releases: dict[str, tuple[dict[str, Any], dict[str, bytes]]] = {}
        for path in sorted(LIBRARY_DIR.glob("release-*.tar")):
            manifest, files = release.read(path.read_bytes(), key=release.DEV_RELEASE_KEY.encode())
            cur = self.releases.get(manifest["species"])
            if not cur or cur[0]["number"] < manifest["number"]:
                self.releases[manifest["species"]] = (manifest, files)
        self.compositions: dict[str, MockComposition] = {}

    # ------------------------------------------------------------------ helpers
    def release(self, species: str) -> tuple[dict[str, Any], dict[str, bytes]]:
        if species not in self.releases:
            raise ApiError(404, f"no library release loaded for {species}")
        return self.releases[species]

    def versions(self) -> dict[str, str]:
        return {sp: man["release_version"] for sp, (man, _) in sorted(self.releases.items())}

    def composition(self, cid: str) -> MockComposition:
        c = self.compositions.get(cid)
        if not c:
            raise ApiError(404, f"unknown composition {cid}")
        return c

    def check(self, body: dict[str, Any]) -> None:
        if body.get("species") not in ("dog", "cat"):
            raise ApiError(422, {"composition": ["species: must be dog or cat"]})
        manifest, _ = self.release(body["species"])
        errs = composition_errors(manifest, body)
        if errs:
            raise ApiError(422, {"composition": errs})

    def pick_pet(self, body: dict[str, Any]) -> str:
        index = json.loads((FIXTURES / "index.json").read_text())["pets"]
        same = [p for p in index if p["species"] == body["species"]]
        exact = [p for p in same if p["breed"] == body.get("breed_id")]
        return (exact or same or index)[0]["id"]

    def url(self, c: MockComposition, name: str, base: str = "") -> str:
        return signed_file_url(self.secret, f"compositions/{c.id}/{name}", base=base)

    # ------------------------------------------------------------------ listing
    def release_info(self, species: str) -> m.LibraryRelease:
        return release_model(self.release(species)[0])

    def families(self, species: str) -> m.LibraryFamilies:
        return families_model(self.release(species)[0])

    def parts(self, species: str, region: str | None) -> m.LibraryParts:
        return parts_model(self.release(species)[0], region)

    def patterns(self, species: str) -> m.LibraryPatterns:
        return patterns_model(self.release(species)[0])

    def release_file(self, species: str, path: str) -> tuple[bytes, str]:
        files = self.release(species)[1]
        if path not in files:
            raise ApiError(404, "unknown library file")
        return files[path], media_type(path)

    def bespoke_spec(self, c: MockComposition) -> dict[str, Any]:
        return to_spec(self.release(c.body["species"])[0], c.body, random.randint(1, 2**31 - 1))

    def orders(self) -> list[m.KioskOrder]:
        now = time.time()
        out = []
        for c in sorted(self.compositions.values(), key=lambda c: -c.created):
            if c.export_start is None:
                continue
            ready = c.export_state(now)["status"] == "ready"
            out.append(m.KioskOrder(composition_id=c.id, ticket=c.ticket, pet_name=c.body.get("pet_name"), species=c.body["species"],
                                    status=c.export_state(now)["status"], created_at=m_utc(c.created),
                                    thumbnail_url=self.url(c, "thumbnail.png") if ready else None))
        return out[:20]

    def reprint(self, cid: str) -> m.KioskOrder:
        c = self.composition(cid)
        if c.export_state(time.time())["status"] != "ready":
            raise ApiError(409, "the order has no finished print bundle yet")
        c.reprints += 1
        return next(o for o in self.orders() if o.composition_id == cid)

    # ------------------------------------------------------------------ compositions
    def status(self, c: MockComposition, base: str) -> m.CompositionStatus:
        st = c.export_state(time.time())
        ready = st["status"] == "ready"
        artefacts, previews = [], {}
        if ready:
            manifest = json.loads((FIXTURES / c.pet / "manifest.json").read_text())
            for f in manifest["files"]:
                if f["stage"] == "F":
                    artefacts.append(m.Artefact(name=f["name"], kind=f["kind"], stage="F", url=self.url(c, f["name"]), bytes=f["bytes"]))
            body = json.dumps(c.body, indent=1).encode()
            artefacts.append(m.Artefact(name="composition.json", kind="spec", stage="F", url=self.url(c, "composition.json"), bytes=len(body)))
            previews = {"glb": self.url(c, "figure.glb"), "thumbnail": self.url(c, "thumbnail.png")}
        export = None
        if c.export_start is not None:
            export = m.ExportStatus(job_id=f"j_{c.id[2:]}", status="done" if ready else "running", stage=st["stage"], pct=st["pct"],
                                    message=st["message"])
        return m.CompositionStatus(
            composition_id=c.id, session_id=c.session_id, status=st["status"], pet_name=c.body.get("pet_name"),
            species=c.body["species"], release_version=c.body["release_version"], created_at=m_utc(c.created), export=export,
            ticket=c.ticket, result_url=f"{base}/r/{make_token(self.secret, c.id)}" if ready else None, artefacts=artefacts,
            previews=previews, error=None, composition=c.body)

    def result(self, cid: str, exp: int) -> m.ResultPage:
        c = self.composition(cid)
        if c.export_state(time.time())["status"] != "ready":
            raise ApiError(404, "result not ready")
        return m.ResultPage(job_id=f"j_{c.id[2:]}", pet_name=c.body.get("pet_name"), species=c.body["species"],
                            breed_label=(c.body.get("breed_id") or "mixed").replace("_", " ").title(),
                            glb_url=self.url(c, "figure.glb"), thumbnail_url=self.url(c, "thumbnail.png"), turntable_url=None,
                            created_at=m_utc(c.created), expires_at=m_utc(exp))

    def create(self, session_id: str, body: dict[str, Any], speed: float) -> MockComposition:
        self.check(body)
        c = MockComposition(id="c_" + uuid.uuid4().hex[:12], session_id=session_id, body=body, created=time.time(), speed=speed)
        c.pet = self.pick_pet(body)
        self.compositions[c.id] = c
        return c

    def export(self, c: MockComposition) -> None:
        if c.export_start is None:
            c.export_start = time.time()
            c.ticket = f"PP-{random.randint(1000, 9999)}"

    def file(self, key: str) -> tuple[bytes, str]:
        _, cid, name = key.split("/", 2)
        c = self.composition(cid)
        if c.export_state(time.time())["status"] != "ready":
            raise ApiError(404, "not exported yet")
        if name == "composition.json":
            return json.dumps(c.body, indent=1).encode(), "application/json"
        path = (FIXTURES / c.pet / name).resolve()
        if not str(path).startswith(str(FIXTURES.resolve())) or not path.is_file():
            raise ApiError(404, "unknown file")
        return path.read_bytes(), media_type(path.name) if path.suffix != ".obj" else "text/plain"


def m_utc(ts: float):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts, UTC)
