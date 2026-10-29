"""Repository paths and environment switches shared by every Python component."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SCHEMA_DIR = DATA / "schema"
BREEDS_DIR = DATA / "breeds"
ASSETS = ROOT / "assets"
BASE_DIR = ASSETS / "base"
ACCESSORY_DIR = ASSETS / "accessories"
FIXTURES = ROOT / "fixtures" / "pets"
CONFIG = ROOT / "config"
PIPELINES = ROOT / "pipelines"
VAR = Path(os.environ.get("PETPOP_VAR", ROOT / "var"))


def mode() -> str:
    """'mock' or 'real', from the GenAI profile (GENAI_PROFILE, default mock)."""
    from .genai import Profile

    return Profile().mode


def mock_speed() -> float:
    """Fraction of each real stage timeout a mock stage sleeps; 0 makes tests instant."""
    try:
        return float(os.environ.get("PETPOP_MOCK_SPEED", "0.1"))
    except ValueError:
        return 0.1


def bpy_python() -> str:
    return os.environ.get("PETPOP_BPY_PYTHON", "/opt/bpy/bin/python")
