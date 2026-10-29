"""The /api/v1 surface, built once and bound to an implementation (BRIEF Sections 9 and 17).

mock-server/ and backend/api/ both call `make_app(impl)`, so their OpenAPI documents are identical by
construction and data/schema/openapi.json is the single contract. The contract test then checks that each
implementation's responses actually conform to it.

Three routers: meta (health, signed files, the public result page), /kiosk (anonymous kiosk session: the library
release, compositions and their Stage-F-only export, the five-tap ops panel behind the kiosk's staff PIN) and
/studio (staff login; roles operator < curator < admin).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response

from . import models as m
from petpop_core.schemas import load_schema

API_PREFIX = "/api/v1"
KIOSK = f"{API_PREFIX}/kiosk"
STUDIO = f"{API_PREFIX}/studio"
ROLE_RANK = {"operator": 1, "curator": 2, "admin": 3}
STAFF_TOKEN_TTL_S = 12 * 3600


class ApiError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class ApiImpl(Protocol):
    mode: str
    server: str
    staff_token: str  # the kiosk's local ops PIN
    secret: str

    # studio auth: the role of a valid username/password, else None
    def authenticate(self, username: str, password: str) -> str | None: ...

    # kiosk
    async def create_session(self, body: m.SessionCreate) -> m.Session: ...
    async def breeds(self, species: str, q: str | None) -> m.BreedList: ...
    async def kiosk_ops(self) -> m.KioskOps: ...
    async def kiosk_reprint(self, composition_id: str) -> m.KioskOrder: ...
    # kiosk library mode (BRIEF Section 16)
    async def library_release(self, species: str) -> m.LibraryRelease: ...
    async def library_families(self, species: str) -> m.LibraryFamilies: ...
    async def library_parts(self, species: str, region: str | None) -> m.LibraryParts: ...
    async def library_patterns(self, species: str) -> m.LibraryPatterns: ...
    async def library_file(self, species: str, path: str) -> Response: ...
    async def create_composition(self, body: m.CompositionCreate, base: str) -> m.CompositionStatus: ...
    async def get_composition(self, composition_id: str, base: str) -> m.CompositionStatus: ...
    async def export_composition(self, composition_id: str) -> m.ExportAccepted: ...
    async def bespoke(self, composition_id: str, body: m.BespokeRequest) -> m.BespokeAccepted: ...
    # studio
    async def parse(self, req: m.ParseRequest) -> m.ParseResponse: ...
    async def create_job(self, body: m.JobCreate, user: m.StaffUser) -> m.JobCreated: ...
    async def get_job(self, job_id: str, base: str) -> m.Job: ...
    def job_events(self, job_id: str, base: str) -> AsyncIterator[m.ProgressEvent]: ...
    async def tweak(self, job_id: str, req: m.TweakRequest, user: m.StaffUser) -> m.JobCreated: ...
    async def fulfil(self, job_id: str) -> m.FulfilResponse: ...
    async def staff_queue(self, base: str) -> m.StaffQueue: ...
    async def staff_retry(self, job_id: str, user: m.StaffUser) -> m.JobCreated: ...
    # meta
    async def result(self, token: str, base: str) -> m.ResultPage: ...
    async def file(self, key: str, exp: int, sig: str) -> Response: ...


# --------------------------------------------------------------------------- signing

def sign(secret: str, key: str, exp: int) -> str:
    return hmac.new(secret.encode(), f"{key}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def signed_file_url(secret: str, key: str, ttl_s: int = 7 * 24 * 3600, base: str = "") -> str:
    exp = int(time.time()) + ttl_s
    return f"{base}{API_PREFIX}/files/{key}?exp={exp}&sig={sign(secret, key, exp)}"


def check_sig(secret: str, key: str, exp: int, sig: str) -> bool:
    return exp >= int(time.time()) and hmac.compare_digest(sign(secret, key, exp), sig)


def make_token(secret: str, job_id: str, ttl_s: int = 7 * 24 * 3600) -> str:
    exp = int(time.time()) + ttl_s
    return f"{job_id}.{exp}.{sign(secret, 'result:' + job_id, exp)}"


def read_token(secret: str, token: str) -> tuple[str, int]:
    try:
        job_id, exp_s, sig = token.rsplit(".", 2)
        exp = int(exp_s)
    except ValueError as exc:
        raise ApiError(404, "unknown result") from exc
    if not check_sig(secret, "result:" + job_id, exp, sig):
        raise ApiError(410, "result link expired or invalid")
    return job_id, exp


def make_staff_token(secret: str, username: str, role: str, ttl_s: int = STAFF_TOKEN_TTL_S) -> m.StaffToken:
    exp = int(time.time()) + ttl_s
    token = f"{username}.{role}.{exp}.{sign(secret, f'staff:{username}:{role}', exp)}"
    return m.StaffToken(token=token, user=m.StaffUser(username=username, role=role),
                        expires_at=datetime.fromtimestamp(exp, UTC))


def read_staff_token(secret: str, token: str | None) -> m.StaffUser:
    try:
        username, role, exp_s, sig = (token or "").rsplit(".", 3)
        exp = int(exp_s)
    except ValueError as exc:
        raise ApiError(401, "staff login required") from exc
    if role not in ROLE_RANK or not check_sig(secret, f"staff:{username}:{role}", exp, sig):
        raise ApiError(401, "staff login required")
    return m.StaffUser(username=username, role=role)


# --------------------------------------------------------------------------- router

ERR = {404: {"model": m.ErrorBody}, 409: {"model": m.ErrorBody}, 422: {"model": m.ErrorBody}}
AUTH = {401: {"model": m.ErrorBody}, 403: {"model": m.ErrorBody}}


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def make_routers(impl: ApiImpl) -> list[APIRouter]:
    meta = APIRouter(prefix=API_PREFIX)
    kiosk = APIRouter(prefix=KIOSK, tags=["kiosk"])
    studio = APIRouter(prefix=STUDIO, tags=["studio"])

    def staff(min_role: str = "operator"):
        def dep(authorization: str | None = Header(None)) -> m.StaffUser:
            user = read_staff_token(impl.secret, _bearer(authorization))
            if ROLE_RANK[user.role] < ROLE_RANK[min_role]:
                raise ApiError(403, f"needs the {min_role} role")
            return user
        return dep

    operator = Depends(staff("operator"))

    # ------------------------------------------------------------------ meta
    @meta.get("/health", response_model=m.Health, tags=["meta"], operation_id="health")
    async def health() -> m.Health:
        return m.Health(status="ok", mode=impl.mode, api_version=m.API_VERSION, server=impl.server)

    @meta.get("/r/{token}", response_model=m.ResultPage, tags=["public"], operation_id="getResult",
              responses={404: {"model": m.ErrorBody}, 410: {"model": m.ErrorBody}})
    async def result(token: str, request: Request) -> m.ResultPage:
        return await impl.result(token, _base(request))

    @meta.get("/files/{key:path}", tags=["public"], operation_id="getFile",
              responses={200: {"content": {"application/octet-stream": {}}, "description": "Artefact bytes"},
                         403: {"model": m.ErrorBody}, 404: {"model": m.ErrorBody}})
    async def file(key: str, exp: int = Query(...), sig: str = Query(...)) -> Response:
        return await impl.file(key, exp, sig)

    # ------------------------------------------------------------------ kiosk (anonymous session)
    @kiosk.post("/sessions", response_model=m.Session, status_code=201, operation_id="kioskCreateSession")
    async def create_session(body: m.SessionCreate) -> m.Session:
        return await impl.create_session(body)

    @kiosk.get("/breeds", response_model=m.BreedList, operation_id="kioskListBreeds", responses=ERR)
    async def kiosk_breeds(species: m.Species = Query(...), q: str | None = Query(None, max_length=40)) -> m.BreedList:
        return await impl.breeds(species, q)

    # library mode: the active release (read-only) and compositions, the order record
    @kiosk.get("/library/{species}", response_model=m.LibraryRelease, operation_id="kioskLibraryRelease", responses=ERR)
    async def library_release(species: m.Species) -> m.LibraryRelease:
        return await impl.library_release(species)

    @kiosk.get("/library/{species}/families", response_model=m.LibraryFamilies, operation_id="kioskLibraryFamilies", responses=ERR)
    async def library_families(species: m.Species) -> m.LibraryFamilies:
        return await impl.library_families(species)

    @kiosk.get("/library/{species}/parts", response_model=m.LibraryParts, operation_id="kioskLibraryParts", responses=ERR)
    async def library_parts(species: m.Species, region: m.Region | Literal["shells"] | None = Query(None)) -> m.LibraryParts:
        return await impl.library_parts(species, region)

    @kiosk.get("/library/{species}/patterns", response_model=m.LibraryPatterns, operation_id="kioskLibraryPatterns", responses=ERR)
    async def library_patterns(species: m.Species) -> m.LibraryPatterns:
        return await impl.library_patterns(species)

    @kiosk.get("/library/{species}/files/{path:path}", operation_id="kioskLibraryFile",
               responses={200: {"content": {"application/octet-stream": {}}, "description": "A file of the active release"},
                          404: {"model": m.ErrorBody}})
    async def library_file(species: m.Species, path: str) -> Response:
        return await impl.library_file(species, path)

    @kiosk.post("/compositions", response_model=m.CompositionStatus, status_code=201, operation_id="kioskCreateComposition",
                responses=ERR)
    async def create_composition(body: m.CompositionCreate, request: Request) -> m.CompositionStatus:
        return await impl.create_composition(body, _base(request))

    @kiosk.get("/compositions/{composition_id}", response_model=m.CompositionStatus, operation_id="kioskGetComposition",
               responses=ERR)
    async def get_composition(composition_id: str, request: Request) -> m.CompositionStatus:
        return await impl.get_composition(composition_id, _base(request))

    @kiosk.post("/compositions/{composition_id}/export", response_model=m.ExportAccepted, status_code=202,
                operation_id="kioskExportComposition", responses=ERR)
    async def export_composition(composition_id: str) -> m.ExportAccepted:
        return await impl.export_composition(composition_id)

    @kiosk.post("/compositions/{composition_id}/bespoke", response_model=m.BespokeAccepted, status_code=201,
                operation_id="kioskBespoke", responses={**ERR, 403: {"model": m.ErrorBody}})
    async def bespoke(composition_id: str, body: m.BespokeRequest) -> m.BespokeAccepted:
        return await impl.bespoke(composition_id, body)

    @kiosk.get("/ops", response_model=m.KioskOps, operation_id="kioskOps", responses={403: {"model": m.ErrorBody}})
    async def kiosk_ops(x_staff_token: str | None = Header(None)) -> m.KioskOps:
        if not x_staff_token or not hmac.compare_digest(x_staff_token, impl.staff_token):
            raise ApiError(403, "staff PIN required")
        return await impl.kiosk_ops()

    @kiosk.post("/ops/orders/{composition_id}/reprint", response_model=m.KioskOrder, operation_id="kioskReprint",
                responses={**ERR, 403: {"model": m.ErrorBody}})
    async def kiosk_reprint(composition_id: str, x_staff_token: str | None = Header(None)) -> m.KioskOrder:
        if not x_staff_token or not hmac.compare_digest(x_staff_token, impl.staff_token):
            raise ApiError(403, "staff PIN required")
        return await impl.kiosk_reprint(composition_id)

    # ------------------------------------------------------------------ studio (staff login)
    @studio.post("/auth/login", response_model=m.StaffToken, operation_id="studioLogin", responses=AUTH)
    async def login(body: m.StaffLogin) -> m.StaffToken:
        role = impl.authenticate(body.username, body.password)
        if not role:
            raise ApiError(401, "wrong username or password")
        return make_staff_token(impl.secret, body.username, role)

    @studio.get("/auth/me", response_model=m.StaffUser, operation_id="studioMe", responses=AUTH)
    async def me(user: m.StaffUser = operator) -> m.StaffUser:
        return user

    @studio.get("/breeds", response_model=m.BreedList, operation_id="studioListBreeds", responses={**ERR, **AUTH})
    async def studio_breeds(species: m.Species = Query(...), q: str | None = Query(None, max_length=40),
                            _: m.StaffUser = operator) -> m.BreedList:
        return await impl.breeds(species, q)

    @studio.post("/spec/parse", response_model=m.ParseResponse, operation_id="studioParseSpec", responses={**ERR, **AUTH})
    async def parse(req: m.ParseRequest, _: m.StaffUser = operator) -> m.ParseResponse:
        return await impl.parse(req)

    @studio.post("/jobs", response_model=m.JobCreated, status_code=201, operation_id="studioCreateJob",
                 responses={**ERR, **AUTH})
    async def create_job(body: m.JobCreate, user: m.StaffUser = operator) -> m.JobCreated:
        return await impl.create_job(body, user)

    @studio.get("/jobs/{job_id}", response_model=m.Job, operation_id="studioGetJob", responses={**ERR, **AUTH})
    async def get_job(job_id: str, request: Request, _: m.StaffUser = operator) -> m.Job:
        return await impl.get_job(job_id, _base(request))

    @studio.post("/jobs/{job_id}/tweak", response_model=m.JobCreated, status_code=201, operation_id="studioTweakJob",
                 responses={**ERR, **AUTH})
    async def tweak(job_id: str, req: m.TweakRequest, user: m.StaffUser = operator) -> m.JobCreated:
        return await impl.tweak(job_id, req, user)

    @studio.post("/jobs/{job_id}/fulfil", response_model=m.FulfilResponse, operation_id="studioFulfilJob",
                 responses={**ERR, **AUTH})
    async def fulfil(job_id: str, _: m.StaffUser = operator) -> m.FulfilResponse:
        return await impl.fulfil(job_id)

    @studio.post("/jobs/{job_id}/retry", response_model=m.JobCreated, operation_id="studioRetryJob",
                 responses={**ERR, **AUTH})
    async def retry(job_id: str, user: m.StaffUser = operator) -> m.JobCreated:
        return await impl.staff_retry(job_id, user)

    @studio.get("/queue", response_model=m.StaffQueue, operation_id="studioQueue", responses=AUTH)
    async def queue(request: Request, _: m.StaffUser = operator) -> m.StaffQueue:
        return await impl.staff_queue(_base(request))

    @studio.websocket("/jobs/{job_id}/events")
    async def events(ws: WebSocket, job_id: str, token: str | None = Query(None)) -> None:
        try:
            read_staff_token(impl.secret, token)
        except ApiError:
            await ws.close(code=4401, reason="staff login required")
            return
        await ws.accept()
        base = f"{'https' if ws.url.scheme == 'wss' else 'http'}://{ws.url.netloc}"
        try:
            async for ev in impl.job_events(job_id, base):
                await ws.send_text(ev.model_dump_json())
            await ws.close()
        except ApiError as e:
            await ws.close(code=4404, reason=str(e.detail)[:100])
        except (WebSocketDisconnect, asyncio.CancelledError, RuntimeError):
            pass

    return [meta, kiosk, studio]


def make_app(impl: ApiImpl, title: str = "PetPop API", lifespan=None) -> FastAPI:
    app = FastAPI(title=title, version=m.API_VERSION, docs_url=f"{API_PREFIX}/docs",
                  openapi_url=f"{API_PREFIX}/openapi.json", lifespan=lifespan)
    for router in make_routers(impl):
        app.include_router(router)

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    app.openapi = lambda: contract_openapi(app)  # type: ignore[method-assign]
    return app


# --------------------------------------------------------------------------- OpenAPI document

def _schema_components(name: str, file: str) -> dict[str, Any]:
    """A JSON Schema from data/schema/ as OpenAPI components: <name> plus <name>_<def> for each $defs entry."""
    raw = json.loads(json.dumps(load_schema(file)))
    defs = raw.pop("$defs", {})
    for k in ("$schema", "$id"):
        raw.pop(k, None)

    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and node["$ref"].startswith("#/$defs/"):
                node["$ref"] = f"#/components/schemas/{name}_" + node["$ref"].split("/")[-1]
            return {k: fix(v) for k, v in node.items()}
        if isinstance(node, list):
            return [fix(v) for v in node]
        return node

    comps = {name: fix(raw)}
    for k, v in defs.items():
        comps[f"{name}_{k}"] = fix(v)
    return comps


def _petspec_components() -> dict[str, Any]:
    comps = _schema_components("PetSpec", "petspec.schema.json")
    comps["PetSpecPatch"] = {
        "type": "object",
        "additionalProperties": True,
        "title": "PetSpecPatch",
        "description": "Deep-partial PetSpec: any subset of PetSpec fields, merged over the current spec.",
    }
    return comps


def contract_openapi(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    doc = get_openapi(title="PetPop API", version=m.API_VERSION, routes=app.routes,
                      description="PetPop API (BRIEF Sections 9 and 17): /kiosk for the customer kiosk, /studio for staff. "
                                  "Source of truth: data/schema/openapi.json.")
    def swap(node: Any) -> Any:
        if isinstance(node, dict):
            if "x-petpop-ref" in node:
                return {"$ref": f"#/components/schemas/{node['x-petpop-ref']}"}
            return {k: swap(v) for k, v in node.items()}
        if isinstance(node, list):
            return [swap(v) for v in node]
        return node

    doc = swap(doc)
    comps = doc.setdefault("components", {}).setdefault("schemas", {})
    comps.update(_petspec_components())
    comps.update(_schema_components("Composition", "composition.schema.json"))
    comps.update(_schema_components("ReleaseManifest", "release.schema.json"))
    comps["ProgressEvent"] = swap(m.ProgressEvent.model_json_schema(ref_template="#/components/schemas/{model}"))
    doc["paths"][f"{STUDIO}/jobs/{{job_id}}/events"] = {
        "get": {
            "operationId": "studioJobEvents",
            "tags": ["studio"],
            "summary": "WebSocket progress stream",
            "description": "WebSocket. Each text frame is a ProgressEvent JSON; the server closes after the job "
                           "reaches done, failed or fulfilled. Browsers cannot send headers on a WebSocket, so the "
                           "staff token goes in the `token` query parameter. Close code 4401 means no valid token, "
                           "4404 unknown job.",
            "x-websocket": True,
            "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}},
                           {"name": "token", "in": "query", "required": True, "schema": {"type": "string"}}],
            "responses": {"101": {"description": "Switching protocols",
                                  "content": {"application/json": {
                                      "schema": {"$ref": "#/components/schemas/ProgressEvent"}}}}},
        }
    }
    app.openapi_schema = doc
    return doc


def openapi_text(app: FastAPI) -> str:
    return json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n"
