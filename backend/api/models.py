"""API contract models (BRIEF Sections 9 and 17). Shared by mock-server/ and backend/api/ so both publish the
identical OpenAPI document (data/schema/openapi.json). 2.0.0 splits the surface into /kiosk and /studio; 3.0.0 adds
the kiosk library mode (releases, compositions, Stage-F-only exports) and moves bespoke onto a composition."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema

API_VERSION = "3.0.0"

# Placeholders swapped for $refs to the JSON-Schema-derived components in contract.contract_openapi().
PetSpec = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "PetSpec"})]
PetSpecPatch = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "PetSpecPatch"})]
Species = Literal["dog", "cat"]
JobStatus = Literal["queued", "running", "done", "failed", "fulfilled"]
Stage = Literal["queued", "A", "control", "B", "C", "D", "E", "F", "done"]
Fallback = Literal["none", "single_view", "parametric", "unwrapped"]
Role = Literal["operator", "curator", "admin"]
JobKind = Literal["pipeline", "bespoke", "export"]
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
    """"Make it unique" from a composition: the studio starts a bespoke job from it (BRIEF Section 17)."""
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
    releases: dict[str, str] = Field(description="Active library release per species.")
    bespoke_enabled: bool
    exports_queued: int
    exports_running: int
    orders: list[KioskOrder] = Field(description="The last 20 orders, newest first.")


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


# --------------------------------------------------------------------------- library mode (BRIEF Section 16, API 3.0.0)

Composition = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "Composition"})]
ReleaseManifest = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "ReleaseManifest"})]
Region = Literal["ears", "tail", "muzzle", "head", "legs"]
CompositionState = Literal["draft", "exporting", "ready", "failed"]


class LibraryRelease(_M):
    """The active release for a species: its manifest (data/schema/release.schema.json) and where its files are."""
    species: Species
    release_version: str
    base_mesh_version: str
    files_url: str = Field(description="Prefix for the release's files: <files_url><path>.")
    manifest: ReleaseManifest


class LibraryFamily(_M):
    id: str
    name: str
    default_parts: dict[str, str]
    breeds: list[str]
    tags: list[str]
    version: int
    delta_url: str
    thumbnail_url: str


class LibraryFamilies(_M):
    species: Species
    release_version: str
    items: list[LibraryFamily]


class LibraryPart(_M):
    id: str
    name: str
    kind: Literal["delta", "shell"]
    region: Region | None = Field(None, description="Region of a region-delta part.")
    socket: Literal["neck", "head", "face"] | None = Field(None, description="Socket of a shell part.")
    tags: list[str]
    version: int
    url: str = Field(description="float16 delta (region parts) or GLB (shell parts).")
    thumbnail_url: str
    default_colour: str | None = None


class LibraryParts(_M):
    species: Species
    release_version: str
    items: list[LibraryPart]


class PatternCoverage(_M):
    min: float
    max: float
    default: float


class LibraryPattern(_M):
    id: str
    name: str
    channel: int
    default_colour: str
    coverage: PatternCoverage
    version: int
    thumbnail_url: str


class LibraryPatterns(_M):
    species: Species
    release_version: str
    items: list[LibraryPattern]


class CompositionCreate(_M):
    session_id: str
    composition: Composition


class ExportStatus(_M):
    job_id: str
    status: JobStatus
    stage: Stage
    pct: int
    message: str


class CompositionStatus(_M):
    composition_id: str
    session_id: str
    status: CompositionState
    pet_name: str | None
    species: Species
    release_version: str
    created_at: datetime
    export: ExportStatus | None
    ticket: str | None = Field(None, description="Order ticket, issued when the export is requested.")
    result_url: str | None = Field(None, description="Signed public result page for the QR code (7 days), once ready.")
    artefacts: list[Artefact]
    previews: dict[str, str]
    error: str | None = None
    composition: Composition


class ExportAccepted(_M):
    composition_id: str
    job_id: str
    ticket: str
    queue_position: int


class KioskOrder(_M):
    composition_id: str
    ticket: str | None
    pet_name: str | None
    species: Species
    status: CompositionState
    created_at: datetime
    thumbnail_url: str | None


class ErrorBody(_M):
    detail: Any


KioskOps.model_rebuild()
