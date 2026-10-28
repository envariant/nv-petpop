"""Durable state (BRIEF Section 9 data model): SQLite in `make dev`, Postgres on the GPU host."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event
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
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
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


_engines: dict[str, Engine] = {}


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
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.close()
        Base.metadata.create_all(eng)
        _engines[url] = eng
    return _engines[url]


def session_factory(url: str):
    return sessionmaker(engine(url), expire_on_commit=False)


def seed_breeds(factory) -> None:
    from backend.core.breeds import all_breeds

    with factory() as db:
        if db.query(BreedRow).count():
            return
        for species in ("dog", "cat"):
            for b in all_breeds(species):
                db.add(BreedRow(id=b["id"], species=species, label=b["label"], preset=b["preset"],
                                prompt_hint=b["prompt_hint"]))
        db.commit()
