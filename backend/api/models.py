"""API contract models (BRIEF Sections 9 and 17). Shared by mock-server/ and backend/api/ so both publish the
identical OpenAPI document (data/schema/openapi.json). 2.0.0 splits the surface into /kiosk and /studio."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema

API_VERSION = "2.0.0"

# Placeholders swapped for $refs to the JSON-Schema-derived components in contract.contract_openapi().
PetSpec = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "PetSpec"})]
PetSpecPatch = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "PetSpecPatch"})]
Species = Literal["dog", "cat"]
JobStatus = Literal["queued", "running", "done", "failed", "fulfilled"]
Stage = Literal["queued", "A", "control", "B", "C", "D", "E", "F", "done"]
Fallback = Literal["none", "single_view", "parametric", "unwrapped"]
Role = Literal["operator", "curator", "admin"]
JobKind = Literal["pipeline", "bespoke"]
ArtefactKind = Literal["spec", "control", "concept", "view", "shape", "wrapped", "uv_obj", "albedo", "glb", "3mf",
                       "stl", "mask", "turntable", "thumbnail", "manifest"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Health(_M):
    status: Literal["ok"]
    mode: Literal["mock", "real"]
    api_version: str
    server: Literal["mock-server", "backend"]


class IdlePolicy(_M):
    idle_seconds: int = 90
    countdown_seconds: int = 15


class SessionCreate(_M):
    kiosk_id: str = Field("kiosk-1", max_length=40)


class Session(_M):
    """An anonymous kiosk session (no accounts); wiped on idle."""
    session_id: str
    kiosk_id: str
    started_at: datetime
    idle_policy: IdlePolicy
    bespoke_enabled: bool = Field(description="KIOSK_BESPOKE: whether the kiosk offers \"Make it unique\".")


class BespokeRequest(_M):
    session_id: str
    spec: PetSpec
    contact: str | None = Field(None, max_length=80, description="How to reach the customer when it is ready.")


class BespokeAccepted(_M):
    request_id: str = Field(description="The studio job that will produce the one-off figurine.")
    ticket: str
    message: str


class KioskOps(_M):
    """The kiosk's five-tap ops panel: release version, health, reprint; no generation controls."""
    api_version: str
    mode: Literal["mock", "real"]
    kiosk_id: str
    release_version: str | None
    bespoke_enabled: bool
    exports_queued: int
    exports_running: int


class StaffLogin(_M):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


class StaffUser(_M):
    username: str
    role: Role


class StaffToken(_M):
    token: str = Field(description="Bearer token for the /studio routes (Authorization: Bearer <token>).")
    user: StaffUser
    expires_at: datetime


class Breed(_M):
    id: str
    species: Species
    label: str
    prompt_hint: str
    preset: dict[str, Any] = Field(description="Default values for every PetSpec field the breed fixes.")


class BreedList(_M):
    species: Species
    accent: str
    total: int
    items: list[Breed]


class ParseRequest(_M):
    species: Species
    current_spec: PetSpec
    text: str = Field(max_length=500)
    tapped_fields: list[str] = Field(default_factory=list,
                                     description="Dotted PetSpec paths the user tapped; the parser never changes them.")


class ParseResponse(_M):
    patch: PetSpecPatch
    changed_fields: list[str]
    personality: list[str]
    free_text_unmapped: str
    parser: Literal["rules", "llm"]
    llm_available: bool
    flavour_only: bool = Field(description="True when the brief could not be parsed and is used for flavour only.")
    blocked: bool = Field(description="True when the content screen removed words from the brief.")
    ms: int


class JobCreate(_M):
    spec: PetSpec


class JobCreated(_M):
    job_id: str
    status: JobStatus
    queue_position: int


class Artefact(_M):
    name: str
    kind: ArtefactKind
    stage: str
    url: str
    bytes: int


class StageTiming(_M):
    stage: str
    status: Literal["ok", "failed", "skipped", "fallback", "running"]
    ms: int
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Job(_M):
    job_id: str
    kind: JobKind
    session_id: str | None = Field(None, description="The kiosk session of a bespoke request; null for studio jobs.")
    requested_by: str = Field(description="Staff username, or kiosk:<kiosk_id> for a bespoke request.")
    status: JobStatus
    stage: Stage
    pct: int = Field(ge=0, le=100)
    message: str
    queue_position: int
    seed: int
    species: Species
    pet_name: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    fallback: Fallback
    fidelity: Literal["high", "low"]
    timings: list[StageTiming]
    artefacts: list[Artefact]
    previews: dict[str, str] = Field(description="Latest preview URL per kind (concept, view_front, shape, glb ...).")
    result_url: str | None = Field(None, description="Signed public result page URL for the QR code (7 days).")
    ticket: str | None = None
    spec: PetSpec


class ProgressEvent(_M):
    job_id: str
    status: JobStatus
    stage: Stage
    pct: int
    message: str
    queue_position: int = 0
    preview_url: str | None = None
    preview_kind: str | None = None


class TweakRequest(_M):
    patch: PetSpecPatch


class FulfilResponse(_M):
    job_id: str
    ticket: str
    files: list[str]


class ResultPage(_M):
    job_id: str
    pet_name: str | None
    species: Species
    breed_label: str
    glb_url: str
    thumbnail_url: str | None
    turntable_url: str | None
    created_at: datetime
    expires_at: datetime


class StaffJob(_M):
    job_id: str
    kind: JobKind
    requested_by: str
    status: JobStatus
    stage: Stage
    pet_name: str | None
    species: Species
    created_at: datetime
    finished_at: datetime | None
    fallback: Fallback
    total_ms: int | None
    thumbnail_url: str | None
    error: str | None


class GpuStatus(_M):
    name: str
    temp_c: float | None
    vram_used_mb: int | None
    mock: bool


class StaffQueue(_M):
    mode: Literal["mock", "real"]
    running: StaffJob | None
    queued: list[StaffJob]
    recent: list[StaffJob]
    gpu: GpuStatus


class ErrorBody(_M):
    detail: Any
