"""Runtime settings from the environment (.env.example lists every variable)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from .paths import ROOT, mode


def _var() -> Path:
    return Path(os.environ.get("PETPOP_VAR", ROOT / "var")).resolve()


def _secret(name: str, var: Path) -> str:
    """Env value, else a random dev value persisted under var/ (never committed)."""
    val = os.environ.get(name)
    if val:
        return val
    f = var / f".{name.lower()}"
    if f.exists():
        return f.read_text().strip()
    var.mkdir(parents=True, exist_ok=True)
    val = secrets.token_hex(16)
    f.write_text(val)
    return val


# Quality profiles: "full" follows the brief; "dev" keeps a CPU job around a minute; "test" is the minimum
# that still exercises every code path (used by the contract test and the regression smoke run).
PROFILES = {
    "full": dict(concept_px=1024, view_px=768, control_px=512, samples=16, albedo_px=2048, voxel_mm=0.15,
                 print_tris=250_000, turntable_frames=36, turntable_px=512, mask_px=2048),
    "dev": dict(concept_px=512, view_px=384, control_px=384, samples=8, albedo_px=1024, voxel_mm=0.35,
                print_tris=150_000, turntable_frames=36, turntable_px=256, mask_px=1024),
    "fixture": dict(concept_px=512, view_px=384, control_px=256, samples=8, albedo_px=1024, voxel_mm=0.45,
                    print_tris=30_000, turntable_frames=36, turntable_px=256, mask_px=1024),
    "test": dict(concept_px=192, view_px=160, control_px=160, samples=2, albedo_px=512, voxel_mm=0.8,
                 print_tris=60_000, turntable_frames=8, turntable_px=96, mask_px=512),
}


@dataclass
class Settings:
    mode: str
    var: Path
    database_url: str
    secret: str
    staff_token: str
    public_url: str
    fulfil_dir: Path
    kiosk_id: str
    redis_url: str
    s3_endpoint: str
    s3_bucket: str
    comfy_url: str
    ollama_url: str
    ollama_model: str
    bpy_python: str
    fail_stage: str
    profile: str
    embed_worker: bool

    @property
    def quality(self) -> dict:
        return PROFILES[self.profile]


def settings() -> Settings:
    var = _var()
    md = mode()
    return Settings(
        mode=md,
        var=var,
        database_url=os.environ.get("DATABASE_URL") or f"sqlite:///{var / 'petpop.db'}",
        secret=_secret("PETPOP_SECRET", var),
        staff_token=_secret("PETPOP_STAFF_TOKEN", var),
        public_url=os.environ.get("PETPOP_PUBLIC_URL", ""),
        fulfil_dir=Path(os.environ.get("PETPOP_FULFIL_DIR", var / "fulfilment")),
        kiosk_id=os.environ.get("KIOSK_ID", "kiosk-1"),
        redis_url=os.environ.get("REDIS_URL", ""),
        s3_endpoint=os.environ.get("S3_ENDPOINT", ""),
        s3_bucket=os.environ.get("S3_BUCKET", "petpop"),
        comfy_url=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"),
        ollama_url=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_K_M"),
        bpy_python=os.environ.get("PETPOP_BPY_PYTHON", "/opt/bpy/bin/python"),
        fail_stage=os.environ.get("PETPOP_FAIL_STAGE", "").upper(),
        profile=os.environ.get("PETPOP_PROFILE", "dev" if md == "mock" else "full"),
        embed_worker=os.environ.get("PETPOP_EMBED_WORKER", "0") == "1",
    )
