"""Durable state (BRIEF Section 9 data model): SQLite in `make dev`, Postgres on the GPU host."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kiosk_id: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    generate_count: Mapped[int] = mapped_column(Integer, default=0)


class JobRow(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    queue: Mapped[str] = mapped_column(String(8), default="studio", index=True)  # kiosk | studio (BRIEF Section 17)
    kind: Mapped[str] = mapped_column(String(16), default="pipeline")  # pipeline | bespoke | export | batch
    batch_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)  # a Studio curation batch (M8)
    genai_profile: Mapped[str | None] = mapped_column(String(40), nullable=True)  # the job's GenAI profile (decision 113)
    pipeline: Mapped[str | None] = mapped_column(String(40), nullable=True)  # its pipeline, e.g. multiview (decision 114)
    options: Mapped[dict[str, bool] | None] = mapped_column(JSON, nullable=True)  # its quality switches (decision 115)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(48), default="")
    contact: Mapped[str | None] = mapped_column(String(80), nullable=True)
    pet_spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued/running/done/failed/fulfilled
    stage: Mapped[str] = mapped_column(String(16), default="queued")
    pct: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(200), default="Waiting for the studio")
    seed: Mapped[int] = mapped_column(BigInteger)
    fallback: Mapped[str] = mapped_column(String(16), default="none")
    fidelity: Mapped[str] = mapped_column(String(8), default="high")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Split deployments (decision 124): a bespoke job the shop pulled from the cloud keeps the cloud's id and is
    # marked origin "cloud"; synced_at is when its result (or failure) went back; remote_result_url is the
    # customer's result page on the cloud.
    origin: Mapped[str | None] = mapped_column(String(8), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remote_result_url: Mapped[str | None] = mapped_column(String(400), nullable=True)


class StaffUserRow(Base):
    """Studio staff accounts (local, BRIEF Section 17): roles operator / curator / admin."""
    __tablename__ = "staff_users"
    username: Mapped[str] = mapped_column(String(40), primary_key=True)
    role: Mapped[str] = mapped_column(String(12))
    password_hash: Mapped[str] = mapped_column(String(200))


class ArtefactRow(Base):
    __tablename__ = "artefacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(120))
    object_key: Mapped[str] = mapped_column(String(240))
    bytes: Mapped[int] = mapped_column(BigInteger)


class StageTimingRow(Base):
    __tablename__ = "stage_timings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ms: Mapped[int] = mapped_column(Integer, default=0)
    vram_peak_mb: Mapped[float | None] = mapped_column(Float, nullable=True)


class BreedRow(Base):
    __tablename__ = "breeds"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    species: Mapped[str] = mapped_column(String(8), primary_key=True)
    label: Mapped[str] = mapped_column(String(64))
    preset: Mapped[dict[str, Any]] = mapped_column(JSON)
    prompt_hint: Mapped[str] = mapped_column(Text)


class EventRow(Base):
    """Progress events for the local (no-Redis) event bus; the API tails this table for WebSockets."""
    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# --------------------------------------------------------------------------- library mode (BRIEF Section 16)
# The Studio's library: every item is versioned (base_mesh_version holds the segmentation schema version since
# decision 118; families and part variants name their mesh); only published items are packed
# into a release. The kiosk never reads these tables: it reads its installed release bundles and writes only
# compositions (the order record).

class _LibraryItem:
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    species: Mapped[str] = mapped_column(String(8), primary_key=True)  # ids repeat across species (shell_collar)
    base_mesh_version: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)  # draft/accepted/rejected/published
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    files: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)  # role -> object key (delta, mesh, mask, thumbnail)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("curation_batches.id"), nullable=True)
    source_job: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ManualTaskRow(Base):
    """Manual mode (decision 111): a provider request waiting for the operator to run it in the vendor's app."""
    __tablename__ = "manual_tasks"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # <job_id>.<request_id>
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)  # pending | submitted
    packet: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(48), nullable=True)
    result_name: Mapped[str | None] = mapped_column(String(120), nullable=True)


class CurationBatchRow(Base):
    """A Studio batch: breeds x variants x seeds through stages A to E (M8)."""
    __tablename__ = "curation_batches"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    species: Mapped[str] = mapped_column(String(8))
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued/running/review/done
    created_by: Mapped[str] = mapped_column(String(40))
    genai_profile: Mapped[str | None] = mapped_column(String(40), nullable=True)  # decision 113
    pipeline: Mapped[str | None] = mapped_column(String(40), nullable=True)  # decision 114
    options: Mapped[dict[str, bool] | None] = mapped_column(JSON, nullable=True)  # decision 115
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FamilyRow(_LibraryItem, Base):
    """A body or head variant: a full-mesh delta with its default parts set and breed tags."""
    __tablename__ = "families"
    mesh_id: Mapped[str | None] = mapped_column(String(40), nullable=True)  # the mesh it is built on (decision 118)
    default_parts: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    breeds: Mapped[list[str]] = mapped_column(JSON, default=list)


class RegionDeltaRow(_LibraryItem, Base):
    """Vertex offsets for one vertex group (float16), with QC metrics and the curator's score."""
    __tablename__ = "region_deltas"
    mesh_id: Mapped[str | None] = mapped_column(String(40), nullable=True)  # the one mesh it applies to
    region: Mapped[str] = mapped_column(String(12), index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)


class ShellPartRow(_LibraryItem, Base):
    """A separate mesh on a named socket (accessories, extreme ears and tails)."""
    __tablename__ = "shell_parts"
    socket: Mapped[str] = mapped_column(String(12))
    kind: Mapped[str] = mapped_column(String(24))
    default_colour: Mapped[str] = mapped_column(String(7))


class PatternLayerRow(_LibraryItem, Base):
    """A signed-distance mask channel in the species UV atlas, with default colour and coverage range."""
    __tablename__ = "pattern_layers"
    default_colour: Mapped[str] = mapped_column(String(7))
    coverage: Mapped[dict[str, float]] = mapped_column(JSON)


class LibraryReleaseRow(Base):
    """A release Studio packed (or imported): release-<species>-<n>, its bundle in the store and its counts."""
    __tablename__ = "library_releases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    species: Mapped[str] = mapped_column(String(8), index=True)
    number: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    object_key: Mapped[str | None] = mapped_column(String(240), nullable=True)
    counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)


class CompositionRow(Base):
    """Contract 2: what a customer assembled (data/schema/composition.schema.json). The order record and the only
    input to a library export."""
    __tablename__ = "compositions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    species: Mapped[str] = mapped_column(String(8))
    release_version: Mapped[str] = mapped_column(String(32))
    pet_name: Mapped[str | None] = mapped_column(String(24), nullable=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft/exporting (export state is the job's)
    job_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bespoke_job_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ticket: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reprints: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # the shop pulled the print bundle
    # decision 126: who placed it (a signed-in account) and where to tell them it is ready (a guest's contact)
    account_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(24), nullable=True)


class AccountRow(Base):
    """A customer account (decision 126). Email and phone are stored only once verified (a code, or Apple's or
    Google's verified email) and are each unique across accounts."""
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, unique=True)
    phone: Mapped[str | None] = mapped_column(String(24), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IdentityRow(Base):
    """A Sign in with Apple or Google identity: the provider's stable subject, linked to one account."""
    __tablename__ = "account_identities"
    provider: Mapped[str] = mapped_column(String(12), primary_key=True)  # apple | google
    subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)  # as the provider last reported it
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AccountSessionRow(Base):
    """A signed-in device: the sha256 of its bearer token, so a leaked database does not leak sessions."""
    __tablename__ = "account_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class OtpRow(Base):
    """A one-time code sent to an email or phone (hashed, 10 minutes, 5 tries)."""
    __tablename__ = "account_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(8))
    destination: Mapped[str] = mapped_column(String(254), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class DeviceRow(Base):
    """A device's push token (Firebase Cloud Messaging), registered by a signed-in app."""
    __tablename__ = "account_devices"
    token: Mapped[str] = mapped_column(String(4096), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    platform: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NotificationRow(Base):
    """One message sent (or attempted) about an order: once per event and channel."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ref: Mapped[str] = mapped_column(String(40), index=True)  # composition id, or a bespoke job id
    event: Mapped[str] = mapped_column(String(24))  # order_confirmed | bespoke_ready
    channel: Mapped[str] = mapped_column(String(8))  # push | email | sms
    destination: Mapped[str] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(12))  # sent | failed | skipped
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PartRow(Base):
    """One part of a breed's kit (decision 127): its mesh in the store, and its rig (a joint for every kind but the
    torso; six attachments for the torso; limits for the head). `auto` keeps the first guess; `edited` is set once
    someone changes the rig in the workbench, so a re-upload's guess no longer overwrites it."""
    __tablename__ = "parts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    species: Mapped[str] = mapped_column(String(8), index=True)
    breed_id: Mapped[str] = mapped_column(String(48), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    variant: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(60))
    mesh_key: Mapped[str] = mapped_column(String(240))
    sha256: Mapped[str] = mapped_column(String(64))
    tris: Mapped[int] = mapped_column(Integer)
    rig: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"joint": ...} or {"attachments": ...}; "limits"
    auto: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # the first guess, with method and confidence
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    mirrored: Mapped[bool] = mapped_column(Boolean, default=False)  # a right leg, kept as its left mirror image
    uploaded_by: Mapped[str] = mapped_column(String(48), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KitRow(Base):
    """A breed's kit settings (defaults, poses, symmetry) and its committed versions (decision 127)."""
    __tablename__ = "part_kits"
    species: Mapped[str] = mapped_column(String(8), primary_key=True)
    breed_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    defaults: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    poses: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    default_pose: Mapped[str] = mapped_column(String(40), default="standing")
    symmetry: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=0)  # the last committed version (0: never)
    committed_key: Mapped[str | None] = mapped_column(String(240), nullable=True)
    committed_by: Mapped[str | None] = mapped_column(String(48), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dirty: Mapped[bool] = mapped_column(Boolean, default=True)  # changed since the last commit


class PaymentRow(Base):
    """A payment for an order (decision 125): one row per attempt; the latest is the order's payment."""
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    composition_id: Mapped[str] = mapped_column(ForeignKey("compositions.id"), index=True)
    provider: Mapped[str] = mapped_column(String(12))  # hitpay | fake
    provider_ref: Mapped[str] = mapped_column(String(80), index=True)  # HitPay's payment request id
    method: Mapped[str] = mapped_column(String(12))  # paynow | card
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)  # pending | paid | failed | expired
    amount: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3))
    qr: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


_engines: dict[str, Engine] = {}

# Columns added after a table first shipped: create_all() makes new tables but never alters existing ones, so an
# existing database (a local var/petpop.db, a Postgres volume) gets them here. Additive and nullable only.
ADDED_COLUMNS = [("jobs", "genai_profile", "VARCHAR(40)"), ("curation_batches", "genai_profile", "VARCHAR(40)"),
                 ("jobs", "pipeline", "VARCHAR(40)"), ("curation_batches", "pipeline", "VARCHAR(40)"),
                 ("jobs", "options", "JSON"), ("curation_batches", "options", "JSON"),
                 ("families", "mesh_id", "VARCHAR(40)"), ("region_deltas", "mesh_id", "VARCHAR(40)"),
                 ("jobs", "origin", "VARCHAR(8)"), ("jobs", "synced_at", "TIMESTAMP"), ("jobs", "remote_result_url", "VARCHAR(400)"),
                 ("compositions", "collected_at", "TIMESTAMP"), ("compositions", "account_id", "VARCHAR(40)"),
                 ("compositions", "contact_email", "VARCHAR(254)"), ("compositions", "contact_phone", "VARCHAR(24)")]


def _add_missing_columns(eng: Engine) -> None:
    from sqlalchemy import inspect, text

    insp = inspect(eng)
    with eng.begin() as conn:
        for table, column, ddl in ADDED_COLUMNS:
            if table in insp.get_table_names() and column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def engine(url: str) -> Engine:
    if url not in _engines:
        if url.startswith("sqlite:///"):
            from pathlib import Path

            Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {},
                            pool_pre_ping=True)
        if url.startswith("sqlite"):
            @event.listens_for(eng, "connect")
            def _pragma(conn, _):  # WAL lets the API read while the worker writes
                cur = conn.cursor()
                cur.execute("PRAGMA busy_timeout=30000")
                _wal(cur)
                cur.close()
        _create_schema(eng)
        _engines[url] = eng
    return _engines[url]


def _wal(cur, attempts: int = 50) -> None:
    """Switch a SQLite database to WAL once (the mode is stored in the file). Switching takes an exclusive lock and
    SQLite does not wait on a busy lock for it, so when `make dev` starts several processes on a fresh database the
    others retry briefly instead of failing with "database is locked"."""
    import sqlite3
    import time

    for n in range(attempts):
        try:
            if str(cur.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal":
                return
            cur.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or n == attempts - 1:
                raise
            time.sleep(0.1 + 0.05 * n)


def _create_schema(eng: Engine, attempts: int = 5) -> None:
    """Create missing tables and columns. `make dev` starts the API and both workers at once on a fresh database, so
    another process may create a table between our check and our CREATE: that loser retries and finds it done."""
    import time

    from sqlalchemy.exc import OperationalError, ProgrammingError

    for n in range(attempts):
        try:
            Base.metadata.create_all(eng)
            _add_missing_columns(eng)
            return
        except (OperationalError, ProgrammingError) as exc:
            text = str(exc).lower()
            if not any(k in text for k in ("already exists", "duplicate column", "database is locked")) or n == attempts - 1:
                raise
            time.sleep(0.2 * (n + 1))


def session_factory(url: str):
    return sessionmaker(engine(url), expire_on_commit=False)


def seed_breeds(factory) -> None:
    from petpop_core.breeds import all_breeds

    with factory() as db:
        if db.query(BreedRow).count():
            return
        for species in ("dog", "cat"):
            for b in all_breeds(species):
                db.add(BreedRow(id=b["id"], species=species, label=b["label"], preset=b["preset"],
                                prompt_hint=b["prompt_hint"]))
        db.commit()


# --------------------------------------------------------------------------- staff accounts

def hash_password(password: str, salt: bytes | None = None) -> str:
    import hashlib
    import os

    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    import hmac

    try:
        algo, salt, _ = stored.split("$")
    except ValueError:
        return False
    return algo == "scrypt" and hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)


def seed_staff(factory, users: list[tuple[str, str, str]]) -> None:
    """Create the configured staff accounts that do not exist yet (username, role, password)."""
    with factory() as db:
        for username, role, password in users:
            if not db.get(StaffUserRow, username):
                db.add(StaffUserRow(username=username, role=role, password_hash=hash_password(password)))
        db.commit()
