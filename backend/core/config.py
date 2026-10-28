"""Runtime settings from the environment (.env.example lists every variable). Everything GenAI-specific
(mode, quality, hosts, models, timeouts) comes from the GENAI_PROFILE file, see backend/core/genai.py."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from .genai import Profile
from .paths import ROOT


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
    bpy_python: str
    fail_stage: str
    embed_worker: bool
    genai: Profile
    quality: dict

    @property
    def profile(self) -> str:
        """GenAI profile name (config/genai/<name>.yaml)."""
        return self.genai.name


def settings() -> Settings:
    var = _var()
    genai = Profile()
    md = genai.mode
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
        bpy_python=os.environ.get("PETPOP_BPY_PYTHON", "/opt/bpy/bin/python"),
        fail_stage=os.environ.get("PETPOP_FAIL_STAGE", "").upper(),
        embed_worker=os.environ.get("PETPOP_EMBED_WORKER", "0") == "1",
        genai=genai,
        quality=genai.quality(),
    )
