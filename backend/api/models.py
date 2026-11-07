"""API contract models (BRIEF Sections 9 and 17). Shared by mock-server/ and backend/api/ so both publish the
identical OpenAPI document (data/schema/openapi.json). 2.0.0 splits the surface into /kiosk and /studio; 3.0.0 adds
the kiosk library mode (releases, compositions, Stage-F-only exports) and moves bespoke onto a composition; 3.1.0
adds Studio's curation: batches, review, the parts and pattern editors, publish and releases; 3.9.0 adds payment for
an order (decision 125: HitPay, PayNow and cards); 3.10.0 adds customer accounts (email and phone codes, Sign in
with Apple and Google), the contact an order needs, the account's orders and devices, and an itemised quote
(decision 126); 3.11.0 adds the Studio part library: breeds as kits of parts rigged at joints (decision 127); 3.12.0 adds
notes to a part upload (mirrored, scaled to the breed's size guess, decision 128); 3.13.0 adds the shared library of
torsos, legs and tails, each breed's allowed variants, per-breed stretches and default texture (decision 130); 3.14.0
adds torso presets, the customers' shape choices, each a stretch and socket offsets (decision 131); 3.15.0 adds a
third colour to a breed's default texture, edited in the workbench; 3.16.0 adds marking and pattern masks on texture
templates, uploaded with the parts and carried by releases with the kits (decision 133); 3.17.0 adds composition 3.0,
a figure of part kits (decision 134)."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema

API_VERSION = "3.17.0"

# Placeholders swapped for $refs to the JSON-Schema-derived components in contract.contract_openapi().
PetSpec = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "PetSpec"})]
PetSpecPatch = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "PetSpecPatch"})]
Species = Literal["dog", "cat"]
JobStatus = Literal["queued", "running", "waiting", "done", "failed", "fulfilled"]
Stage = Literal["queued", "A", "control", "B", "C", "D", "E", "F", "done"]
Fallback = Literal["none", "single_view", "parametric", "unwrapped"]
Role = Literal["operator", "curator", "admin"]
JobKind = Literal["pipeline", "bespoke", "export", "batch"]
ArtefactKind = Literal["spec", "control", "concept", "view", "shape", "segmented", "uv_obj", "albedo", "glb", "3mf",
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


PaymentMethod = Literal["paynow", "card"]
PaymentState = Literal["pending", "paid", "failed", "expired"]


class Price(_M):
    amount: str = Field(description="Decimal string in the currency's major unit, e.g. \"39.00\".", pattern=r"^\d+\.\d{2}$")
    currency: Literal["SGD"]


class QuoteItem(_M):
    label: str
    amount: str = Field(pattern=r"^-?\d+\.\d{2}$")


class Quote(_M):
    """What an order costs, line by line (the figurine, then any options and extras, decision 126); `total` is what a
    payment asks for."""
    items: list[QuoteItem]
    total: Price


class PaymentOffer(_M):
    """How this server takes payment for an order (decision 125). Absent when orders are not paid for in the app
    (payments off: the shop takes payment at the counter)."""
    price: Price
    methods: list[PaymentMethod]
    provider: Literal["hitpay", "fake"] = Field(description="fake: a test provider; the app offers a \"simulate payment\" button.")


class Session(_M):
    """An anonymous kiosk session (no accounts); wiped on idle."""
    session_id: str
    kiosk_id: str
    started_at: datetime
    idle_policy: IdlePolicy
    bespoke_enabled: bool = Field(description="KIOSK_BESPOKE: whether the kiosk offers \"Make it unique\".")
    payment: PaymentOffer | None = None


class PaymentCreate(_M):
    method: PaymentMethod


class Payment(_M):
    """A payment for one order. PayNow: `qr` is the payload to render as a QR code (a banking app scans it). Card:
    `checkout_url` is the provider's hosted page (open it, or show it as a QR on a kiosk). The order is printed and its
    result QR shown once `status` is paid."""
    payment_id: str
    composition_id: str
    method: PaymentMethod
    status: PaymentState
    price: Price
    provider: Literal["hitpay", "fake"]
    qr: str | None = None
    checkout_url: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
    paid_at: datetime | None = None


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
    genai_profile: str | None = Field(None, description="GenAI profile to run on (GET /studio/profiles lists them); empty = the server default (GENAI_PROFILE).")
    pipeline: str | None = Field(None, description="Pipeline to run (GenaiProfileInfo.pipelines, e.g. single_view or multiview); empty = the profile default.")
    options: dict[str, bool] | None = Field(None, description="Quality switches by name (GenaiProfileInfo.options); omitted ones take the profile default.")


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
    genai_profile: str | None = Field(None, description="The GenAI profile the job runs on, fixed at creation (decision 113).")
    pipeline: str | None = Field(None, description="Its pipeline, e.g. single_view or multiview, fixed at creation (decision 114).")
    options: dict[str, bool] | None = Field(None, description="Its quality switches, fixed at creation (decision 115).")
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
    genai_profile: str | None = None
    pipeline: str | None = None
    options: dict[str, bool] | None = None


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


# --------------------------------------------------------------------------- per-job GenAI profiles (decision 113, API 3.3.0)

class GenaiPipeline(_M):
    name: str
    title: str
    default: bool
    credits: int | None = Field(None, description="Estimated API credits per figurine, where the provider prices by credit.")
    note: str | None = None


class GenaiOption(_M):
    name: str
    title: str
    default: bool
    credits: int | None = Field(None, description="API credits it adds per figurine.")
    note: str | None = None


class GenaiProfileInfo(_M):
    name: str
    description: str
    mode: Literal["mock", "real"]
    host: str = Field(description="Where the GenAI runs: cpu, apple-silicon, nvidia or api.")
    ready: bool = Field(description="False when a key it needs is missing from the server's environment.")
    missing: list[str] = Field(description="Environment variables it needs that are not set (names only).")
    pipelines: list[GenaiPipeline] = Field(description="What a job on it can run (decision 114); empty = one fixed pipeline.")
    options: list[GenaiOption] = Field(description="Quality switches a job on it can toggle (decision 115).")


class GenaiProfiles(_M):
    default: str = Field(description="GENAI_PROFILE: kiosk bespoke jobs and jobs that name none run on it.")
    items: list[GenaiProfileInfo]


# --------------------------------------------------------------------------- manual mode (decision 111, API 3.2.0)

ManualCapability = Literal["text_to_image", "image_to_model", "multiview_to_model", "image_to_multiview", "segment_model"]


class ManualInput(_M):
    name: str = Field(description="File to upload to the vendor's app, e.g. input.png.")
    url: str


class ManualExpects(_M):
    kind: Literal["image", "model", "views"]
    accept: list[str] = Field(description="File extensions the upload may have, e.g. ['.glb'].")
    slots: list[str] = Field(default_factory=list, description="views: one upload per slot (front, left, back, right).")


class ManualTask(_M):
    """A provider request in manual mode: exactly what the API would have been sent, for the operator to run in the
    vendor's own app; uploading the output resumes the job (status `waiting` until then)."""
    task_id: str
    job_id: str
    status: Literal["pending", "submitted"]
    capability: ManualCapability
    title: str
    provider: str
    vendor: str
    manifest: str = Field(description="Provider manifest and version that built the request, e.g. 'tripo-v3 v1'.")
    route: str = Field(description="The API route the request would have gone to.")
    request: dict[str, Any] = Field(description="The JSON body the API would have received (inputs shown as <upload name>).")
    prompt: str | None = None
    negative_prompt: str | None = None
    settings: list[str] = Field(description="The request's options as 'field: value' lines.")
    inputs: list[ManualInput]
    instructions: list[str]
    expects: ManualExpects
    species: Species
    pet_name: str | None = None
    breed_label: str | None = None
    batch_id: str | None = None
    created_at: datetime
    submitted_at: datetime | None = None
    result_name: str | None = None
    filled: list[str] = Field(default_factory=list, description="views: the slots uploaded so far.")


class ManualTaskList(_M):
    pending: int
    items: list[ManualTask]


# --------------------------------------------------------------------------- library mode (BRIEF Section 16, API 3.0.0)

Composition = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "Composition"})]
ReleaseManifest = Annotated[dict[str, Any], WithJsonSchema({"type": "object", "x-petpop-ref": "ReleaseManifest"})]
Region = Literal["ears", "tail", "muzzle", "head", "legs"]
CompositionState = Literal["draft", "exporting", "ready", "failed"]


class LibraryRelease(_M):
    """The active release for a species: its manifest (data/schema/release.schema.json) and where its files are."""
    species: Species
    release_version: str
    segmentation_version: str = Field(description="The segmentation schema every mesh of the release is labelled to.")
    files_url: str = Field(description="Prefix for the release's files: <files_url><path>.")
    manifest: ReleaseManifest


class LibraryFamily(_M):
    id: str
    name: str
    mesh_id: str = Field(description="The mesh the family is built on (LibraryFamilies.meshes).")
    default_parts: dict[str, str]
    breeds: list[str]
    tags: list[str]
    version: int
    delta_url: str | None = Field(description="float16 offsets on its mesh; null when the family is the mesh as published.")
    thumbnail_url: str


class LibraryMesh(_M):
    """One library mesh (decision 116): every breed listed here shares it; part variants apply only to it."""
    id: str
    name: str
    breeds: list[str] = Field(description="Every breed whose family is built on this mesh.")
    family_ids: list[str]
    bin_url: str
    info_url: str
    texture_url: str | None = None
    thumbnail_url: str


class LibraryFamilies(_M):
    species: Species
    release_version: str
    items: list[LibraryFamily]
    meshes: list[LibraryMesh]


class LibraryPart(_M):
    id: str
    name: str
    kind: Literal["delta", "shell"]
    region: Region | None = Field(None, description="Region of a region-delta part.")
    mesh_id: str | None = Field(None, description="The one mesh a region part applies to (shell parts fit every mesh).")
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
    payment: Payment | None = Field(None, description="The order's latest payment, when payments are on.")
    quote: Quote | None = Field(None, description="What the order costs, when payments are on.")
    contact: OrderContact | None = Field(None, description="Where we tell the customer it is ready (masked).")
    account_id: str | None = Field(None, description="The signed-in account that placed the order.")


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


# --------------------------------------------------------------------------- customer accounts (decision 126, API 3.10.0)

Channel = Literal["email", "phone"]
Provider = Literal["apple", "google"]


class OrderContact(_M):
    """How to tell a guest (or an account) the order is ready: an email, a phone number, or both. In a response the
    values are masked."""
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=24)


class OrderRequest(_M):
    """Placing an order (the export). A signed-in account's verified email or phone is used when no contact is given;
    a guest must give one."""
    contact: OrderContact | None = None


class AuthConfig(_M):
    """Which sign-in methods this server offers, and the public client ids the apps need for Apple and Google."""
    email: bool
    phone: bool
    apple_client_id: str | None = None
    google_client_id: str | None = Field(None, description="The web client id (Google Identity Services and the native SDKs' server client id).")
    dev_codes: bool = Field(description="Development: codes are returned in the response instead of sent.")
    fake_providers: bool = Field(description="Tests: Apple and Google tokens of the form fake:<subject>:<email> are accepted.")


class CodeRequest(_M):
    channel: Channel
    to: str = Field(min_length=3, max_length=254, description="An email address, or a phone number (E.164, or local to PETPOP_DEFAULT_COUNTRY_CODE).")


class CodeSent(_M):
    channel: Channel
    to: str = Field(description="The normalised destination, masked.")
    expires_in: int
    dev_code: str | None = Field(None, description="Only on a server running development messaging.")


class CodeVerify(_M):
    channel: Channel
    to: str = Field(min_length=3, max_length=254)
    code: str = Field(pattern=r"^\d{6}$")
    name: str | None = Field(None, max_length=60, description="For a new account.")


class ProviderSignIn(_M):
    id_token: str = Field(min_length=10, max_length=8000)
    nonce: str | None = Field(None, max_length=200, description="Apple: the raw nonce the app passed to Apple.")
    name: str | None = Field(None, max_length=60, description="Apple sends the name only on the first sign-in, to the app.")


class Account(_M):
    account_id: str
    name: str | None
    email: str | None = Field(description="Verified; unique across accounts.")
    phone: str | None = Field(description="Verified, E.164; unique across accounts.")
    providers: list[Provider]
    created_at: datetime


class AccountSession(_M):
    token: str = Field(description="Bearer token for the account routes and for placing orders as this account.")
    account: Account
    created: bool = Field(description="True when this sign-in created the account.")
    linked: Provider | None = Field(None, description="Apple or Google joined an existing account with the same verified email.")


class AccountPatch(_M):
    name: str | None = Field(None, max_length=60)


class AccountOrders(_M):
    items: list[KioskOrder]


class Device(_M):
    """A device that receives push notifications for this account (Firebase Cloud Messaging token)."""
    token: str = Field(min_length=10, max_length=4096)
    platform: Literal["ios", "android", "web"]


# --------------------------------------------------------------------------- studio library (BRIEF Section 16, M8, API 3.1.0)

ItemKind = Literal["family", "region", "shell", "pattern"]
ItemStatus = Literal["draft", "accepted", "rejected", "published", "superseded"]
BatchState = Literal["running", "review", "done"]


class BatchVariant(_M):
    label: str = Field(min_length=1, max_length=24, pattern=r"^[a-z0-9_-]+$")
    patch: PetSpecPatch = Field(default_factory=dict, description="Applied over each breed's preset.")


class BatchCreate(_M):
    """A curation batch: breeds x variants x seeds, each a full pipeline run on the studio queue."""
    species: Species
    breeds: list[str] = Field(min_length=1, max_length=30)
    variants: list[BatchVariant] = Field(default_factory=lambda: [BatchVariant(label="preset")], min_length=1, max_length=5)
    seeds: int = Field(1, ge=1, le=10)
    first_seed: int = Field(1, ge=1, le=2**31 - 1)
    genai_profile: str | None = Field(None, description="GenAI profile to run on (GET /studio/profiles lists them); empty = the server default (GENAI_PROFILE).")
    pipeline: str | None = Field(None, description="Pipeline to run (GenaiProfileInfo.pipelines, e.g. single_view or multiview); empty = the profile default.")
    options: dict[str, bool] | None = Field(None, description="Quality switches by name (GenaiProfileInfo.options); omitted ones take the profile default.")


class LibraryCandidate(_M):
    id: str
    version: int
    kind: Literal["family", "region"]
    region: Region | None
    mesh_id: str | None = Field(None, description="The mesh it is built on: a curated figurine's family is on its own mesh (decision 119).")
    name: str
    status: ItemStatus
    tags: list[str]
    qc: dict[str, Any] = Field(description="A figurine's mesh: segmentation_valid, print_watertight, min_wall_mm, figure_tris, passed, reasons.")
    auto_rejected: bool
    thumbnail_url: str | None


class BatchFigurine(_M):
    job_id: str
    breed_id: str
    variant: str
    seed: int
    status: JobStatus
    stage: Stage
    error: str | None = None
    glb_url: str | None
    thumbnail_url: str | None
    turntable_url: str | None
    candidates: list[LibraryCandidate] = Field(description="The figurine's family and one part per region, once curated.")


class BatchSummary(_M):
    figurines: int
    finished: int
    failed: int
    candidates: int
    passed_qc: int
    accepted: int
    rejected: int
    published: int
    meshes_published: int = Field(description="Figurines whose family, on the figurine's own mesh, is published (decision 119).")


class Batch(_M):
    batch_id: str
    species: Species
    status: BatchState
    created_by: str
    created_at: datetime
    request: dict[str, Any]
    genai_profile: str | None = Field(None, description="The GenAI profile its figurines run on (decision 113).")
    pipeline: str | None = Field(None, description="Their pipeline (decision 114).")
    options: dict[str, bool] | None = Field(None, description="Their quality switches (decision 115).")
    summary: BatchSummary
    figurines: list[BatchFigurine]


class BatchList(_M):
    items: list[Batch]


class ReviewDecision(_M):
    item_id: str
    action: Literal["accept", "reject"]
    tags: list[str] | None = None


class ReviewRequest(_M):
    decisions: list[ReviewDecision] = Field(min_length=1, max_length=400)


class LibraryItem(_M):
    kind: ItemKind
    id: str
    version: int
    versions: list[int]
    published_version: int | None
    species: Species
    name: str
    status: ItemStatus
    tags: list[str]
    region: Region | None = None
    socket: Literal["neck", "head", "face"] | None = None
    default_colour: str | None = None
    coverage: PatternCoverage | None = None
    breeds: list[str] | None = None
    mesh_id: str | None = Field(None, description="Families and part variants: the mesh they are built on.")
    shared_with: list[str] | None = Field(None, description="Families: breeds of other families on the same mesh (they share it).")
    default_parts: dict[str, str] | None = None
    qc: dict[str, Any] | None = None
    source_job: str | None = None
    batch_id: str | None = None
    thumbnail_url: str | None
    published_at: datetime | None = None


class LibraryItemList(_M):
    species: Species
    items: list[LibraryItem]


class LibraryItemPatch(_M):
    """The parts and pattern editors. Editing a published item starts its next version (a draft)."""
    name: str | None = Field(None, min_length=1, max_length=64)
    tags: list[str] | None = None
    default_colour: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    coverage: PatternCoverage | None = None
    breeds: list[str] | None = None


class ReleaseCreate(_M):
    species: Species


class ReleaseInfo(_M):
    release_version: str
    species: Species
    number: int
    created_by: str
    created_at: datetime
    counts: dict[str, int]
    bytes: int
    sha256: str
    url: str | None = Field(None, description="Signed download of the bundle (none for the imported proxy release).")


class ReleaseList(_M):
    items: list[ReleaseInfo]


# --------------------------------------------------------------------------- part kits (decision 127, API 3.11.0)

PartKind = Literal["head", "torso", "front_leg", "hind_leg", "tail"]
Slot = Literal["head", "front_left", "front_right", "hind_left", "hind_right", "tail"]
Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]


class PartJoint(_M):
    """Where a part meets the torso: its pivot, the axis from the joint into the part, and its rest twist (degrees)."""
    pivot: Vec3
    axis: Vec3
    twist: float = 0.0


class PartAttachment(_M):
    """A torso slot: the position, the axis out of the torso, and the twist (degrees)."""
    position: Vec3
    axis: Vec3
    twist: float = 0.0


class HeadLimits(_M):
    yaw: Annotated[list[float], Field(min_length=2, max_length=2)] = [-35.0, 35.0]
    pitch: Annotated[list[float], Field(min_length=2, max_length=2)] = [-25.0, 25.0]
    roll: Annotated[list[float], Field(min_length=2, max_length=2)] = [-20.0, 20.0]


class RigGuess(_M):
    """How the first guess found a joint or attachment, and how sure it is (0..1)."""
    method: str
    confidence: float


class SocketOffset(_M):
    """A breed's move of a torso socket (decision 131): translation in mm, then a turn of the socket's frame about its
    position, Euler degrees about x, then y, then z (fixed axes)."""
    translate: Vec3 = [0.0, 0.0, 0.0]
    rotate: Vec3 = [0.0, 0.0, 0.0]


class TorsoPreset(_M):
    """A named shape for a torso variant on a breed (decision 131): what customers choose. The first is 'default'."""
    preset_id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    label: str = Field(min_length=1, max_length=60)
    stretch: Vec3 | None = Field(None, description="Per-axis stretch; null: the torso variant's own (the default preset's).")
    sockets: dict[Slot, SocketOffset] = {}


class Part(_M):
    part_id: str
    kind: PartKind
    variant: str
    label: str
    mesh_url: str
    tris: int
    sha256: str
    joint: PartJoint | None = Field(None, description="Every kind but the torso.")
    attachments: dict[Slot, PartAttachment] | None = Field(None, description="The torso's six slots.")
    limits: HeadLimits | None = Field(None, description="The head's yaw, pitch and roll limits.")
    guess: dict[str, RigGuess] = Field(description="The first guess per joint ('joint', or a slot for the torso).")
    edited: bool = Field(description="The rig was changed in the workbench since the first guess.")
    mirrored: bool = Field(description="Supplied as a right leg; kept as its left mirror image.")
    shared: bool = Field(False, description="From the species' shared library (decision 130): its rig is the same for every breed.")
    stretch: Vec3 = Field([1.0, 1.0, 1.0], description="Per-axis scale of the part on this breed (decision 130).")
    stretch_edited: bool = Field(False, description="The stretch was set in the workbench (otherwise it is the size guess).")
    presets: list[TorsoPreset] = Field([], description="A torso's presets on this breed, the default first, each stretch filled in.")


class Pose(_M):
    pose_id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    label: str = Field(min_length=1, max_length=60)
    legs: dict[Literal["front_left", "front_right", "hind_left", "hind_right"], Literal[0, 1, 2]] = {}
    head: dict[Literal["yaw", "pitch", "roll"], float] = {}
    variants: dict[PartKind, str] = Field({}, description="Variants this pose swaps in (a sitting pose folds the hind legs).")


class TextureColour(_M):
    name: str | None = None
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class BreedTexture(_M):
    """A breed's default texture configuration (decision 130): its colours, pattern and markings (masks)."""
    base: TextureColour
    secondary: TextureColour | None = None
    tertiary: TextureColour | None = Field(None, description="A third colour, for tricolour patterns.")
    pattern: str | None = Field(None, max_length=60)
    markings: list[Annotated[str, Field(pattern=r"^[a-z0-9_]{1,40}$")]] = Field([], max_length=20)


class PartKit(_M):
    """A breed's kit in the workbench: its parts and rigs, the default variant per kind, the allowed poses, and where
    it stands against its last commit."""
    species: Species
    breed_id: str
    breed_label: str
    parts: list[Part]
    defaults: dict[PartKind, str]
    poses: list[Pose]
    default_pose: str
    symmetry: bool
    allowed: dict[PartKind, list[str]] = Field({}, description="The variants a customer may choose per kind (decision 130).")
    texture: BreedTexture | None = Field(None, description="The breed's default texture configuration.")
    version: int = Field(description="The last committed kit version (0: never committed).")
    committed_at: datetime | None = None
    committed_by: str | None = None
    dirty: bool = Field(description="Changed since the last commit.")
    problems: list[str] = Field(description="What stops a commit.")
    notes: list[str] = []
    masks: dict[str, list[str]] = Field({}, description="Per texture template this kit's parts use, the masks uploaded for it.")


class PartKitSummary(_M):
    breed_id: str
    breed_label: str
    kinds: list[PartKind]
    parts: int
    version: int
    dirty: bool
    problems: int


class PartKitList(_M):
    items: list[PartKitSummary]


class PartUploadResult(_M):
    items: list[Part]
    breeds: list[str]
    skipped: list[str] = Field(description="Files not taken, with why.")
    notes: list[str] = Field(default_factory=list, description="What Studio did to the files it took (mirrored a right leg, "
                             "scaled a part to its breed's size guess) and what the first guess could not do.")


class PartRigPatch(_M):
    """A workbench edit to one part: any of its label, joint, torso attachments (some slots) and head limits."""
    label: str | None = Field(None, max_length=60)
    joint: PartJoint | None = None
    attachments: dict[Slot, PartAttachment] | None = None
    limits: HeadLimits | None = None


class PartKitSetup(_M):
    """The breed-level settings: the default variant per kind, the allowed poses and the default one, symmetry, the
    variants a customer may choose, each part's stretch on this breed and the default texture (decision 130)."""
    defaults: dict[PartKind, str] | None = None
    poses: list[Pose] | None = Field(None, min_length=1)
    default_pose: str | None = None
    symmetry: bool | None = None
    allowed: dict[PartKind, list[str]] | None = Field(None, description="Replaces the allowed variants of the kinds given.")
    stretch: dict[Annotated[str, Field(pattern=r"^(head|torso|front_leg|hind_leg|tail)/[a-z0-9_]{1,40}$")], Vec3 | None] | None = Field(
        None, description="'<kind>/<variant>' to a per-axis stretch; null puts the size guess back.")
    texture: BreedTexture | None = None
    presets: dict[Annotated[str, Field(pattern=r"^torso/[a-z0-9_]{1,40}$")], list[TorsoPreset]] | None = Field(
        None, description="'torso/<variant>' to its presets, replacing them (the default's stretch is the part's: see stretch).")


class ErrorBody(_M):
    detail: Any


KioskOps.model_rebuild()
CompositionStatus.model_rebuild()
