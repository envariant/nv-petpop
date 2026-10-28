"""The /api/v1 surface, built once and bound to an implementation.

mock-server/ and backend/api/ both call `make_app(impl)`, so their OpenAPI documents are identical by
construction and data/schema/openapi.json is the single contract. The contract test then checks that each
implementation's responses actually conform to it.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol

from fastapi import APIRouter, FastAPI, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response

from . import models as m
from .schemas import load_schema

API_PREFIX = "/api/v1"


class ApiError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class ApiImpl(Protocol):
    mode: str
    server: str
    staff_token: str

    async def create_session(self, body: m.SessionCreate) -> m.Session: ...
    async def breeds(self, species: str, q: str | None) -> m.BreedList: ...
    async def parse(self, req: m.ParseRequest) -> m.ParseResponse: ...
    async def create_job(self, body: m.JobCreate) -> m.JobCreated: ...
    async def get_job(self, job_id: str, base: str) -> m.Job: ...
    def job_events(self, job_id: str, base: str) -> AsyncIterator[m.ProgressEvent]: ...
    async def tweak(self, job_id: str, req: m.TweakRequest) -> m.JobCreated: ...
    async def fulfil(self, job_id: str) -> m.FulfilResponse: ...
    async def result(self, token: str, base: str) -> m.ResultPage: ...
    async def file(self, key: str, exp: int, sig: str) -> Response: ...
    async def staff_queue(self, base: str) -> m.StaffQueue: ...
    async def staff_retry(self, job_id: str) -> m.JobCreated: ...


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


# --------------------------------------------------------------------------- router

ERR = {404: {"model": m.ErrorBody}, 409: {"model": m.ErrorBody}, 422: {"model": m.ErrorBody}}


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def make_router(impl: ApiImpl) -> APIRouter:
    r = APIRouter(prefix=API_PREFIX)

    def staff(token: str | None) -> None:
        if not token or not hmac.compare_digest(token, impl.staff_token):
            raise ApiError(403, "staff token required")

    @r.get("/health", response_model=m.Health, tags=["meta"], operation_id="health")
    async def health() -> m.Health:
        return m.Health(status="ok", mode=impl.mode, api_version=m.API_VERSION, server=impl.server)

    @r.post("/sessions", response_model=m.Session, status_code=201, tags=["kiosk"], operation_id="createSession")
    async def create_session(body: m.SessionCreate) -> m.Session:
        return await impl.create_session(body)

    @r.get("/breeds", response_model=m.BreedList, tags=["kiosk"], operation_id="listBreeds", responses=ERR)
    async def breeds(species: m.Species = Query(...), q: str | None = Query(None, max_length=40)) -> m.BreedList:
        return await impl.breeds(species, q)

    @r.post("/spec/parse", response_model=m.ParseResponse, tags=["kiosk"], operation_id="parseSpec", responses=ERR)
    async def parse(req: m.ParseRequest) -> m.ParseResponse:
        return await impl.parse(req)

    @r.post("/jobs", response_model=m.JobCreated, status_code=201, tags=["jobs"], operation_id="createJob",
            responses=ERR)
    async def create_job(body: m.JobCreate) -> m.JobCreated:
        return await impl.create_job(body)

    @r.get("/jobs/{job_id}", response_model=m.Job, tags=["jobs"], operation_id="getJob", responses=ERR)
    async def get_job(job_id: str, request: Request) -> m.Job:
        return await impl.get_job(job_id, _base(request))

    @r.post("/jobs/{job_id}/tweak", response_model=m.JobCreated, status_code=201, tags=["jobs"],
            operation_id="tweakJob", responses=ERR)
    async def tweak(job_id: str, req: m.TweakRequest) -> m.JobCreated:
        return await impl.tweak(job_id, req)

    @r.post("/jobs/{job_id}/fulfil", response_model=m.FulfilResponse, tags=["jobs"], operation_id="fulfilJob",
            responses=ERR)
    async def fulfil(job_id: str) -> m.FulfilResponse:
        return await impl.fulfil(job_id)

    @r.get("/r/{token}", response_model=m.ResultPage, tags=["public"], operation_id="getResult",
           responses={404: {"model": m.ErrorBody}, 410: {"model": m.ErrorBody}})
    async def result(token: str, request: Request) -> m.ResultPage:
        return await impl.result(token, _base(request))

    @r.get("/files/{key:path}", tags=["public"], operation_id="getFile",
           responses={200: {"content": {"application/octet-stream": {}}, "description": "Artefact bytes"},
                      403: {"model": m.ErrorBody}, 404: {"model": m.ErrorBody}})
    async def file(key: str, exp: int = Query(...), sig: str = Query(...)) -> Response:
        return await impl.file(key, exp, sig)

    @r.get("/staff/queue", response_model=m.StaffQueue, tags=["staff"], operation_id="staffQueue",
           responses={403: {"model": m.ErrorBody}})
    async def staff_queue(request: Request, x_staff_token: str | None = Header(None)) -> m.StaffQueue:
        staff(x_staff_token)
        return await impl.staff_queue(_base(request))

    @r.post("/staff/jobs/{job_id}/retry", response_model=m.JobCreated, tags=["staff"], operation_id="staffRetry",
            responses={403: {"model": m.ErrorBody}, 404: {"model": m.ErrorBody}})
    async def staff_retry(job_id: str, x_staff_token: str | None = Header(None)) -> m.JobCreated:
        staff(x_staff_token)
        return await impl.staff_retry(job_id)

    @r.websocket("/jobs/{job_id}/events")
    async def events(ws: WebSocket, job_id: str) -> None:
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

    return r


def make_app(impl: ApiImpl, title: str = "PetPop API") -> FastAPI:
    app = FastAPI(title=title, version=m.API_VERSION, docs_url=f"{API_PREFIX}/docs",
                  openapi_url=f"{API_PREFIX}/openapi.json")
    app.include_router(make_router(impl))

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    app.openapi = lambda: contract_openapi(app)  # type: ignore[method-assign]
    return app


# --------------------------------------------------------------------------- OpenAPI document

def _petspec_components() -> dict[str, Any]:
    raw = json.loads(json.dumps(load_schema("petspec.schema.json")))
    defs = raw.pop("$defs", {})
    for k in ("$schema", "$id"):
        raw.pop(k, None)

    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and node["$ref"].startswith("#/$defs/"):
                node["$ref"] = "#/components/schemas/PetSpec_" + node["$ref"].split("/")[-1]
            return {k: fix(v) for k, v in node.items()}
        if isinstance(node, list):
            return [fix(v) for v in node]
        return node

    comps = {"PetSpec": fix(raw)}
    for k, v in defs.items():
        comps[f"PetSpec_{k}"] = fix(v)
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
                      description="PetPop kiosk API (BRIEF Section 9). Source of truth: data/schema/openapi.json.")
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
    comps["ProgressEvent"] = swap(m.ProgressEvent.model_json_schema(ref_template="#/components/schemas/{model}"))
    doc["paths"][f"{API_PREFIX}/jobs/{{job_id}}/events"] = {
        "get": {
            "operationId": "jobEvents",
            "tags": ["jobs"],
            "summary": "WebSocket progress stream",
            "description": "WebSocket. Each text frame is a ProgressEvent JSON; the server closes after the job "
                           "reaches done, failed or fulfilled. Close code 4404 means unknown job.",
            "x-websocket": True,
            "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {"101": {"description": "Switching protocols",
                                  "content": {"application/json": {
                                      "schema": {"$ref": "#/components/schemas/ProgressEvent"}}}}},
        }
    }
    app.openapi_schema = doc
    return doc


def openapi_text(app: FastAPI) -> str:
    return json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n"
