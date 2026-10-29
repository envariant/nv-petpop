"""Repository paths (from petpop_core) plus the backend's runtime switches."""
from __future__ import annotations

import os

from petpop_core.paths import (ACCESSORY_DIR, ASSETS, BASE_DIR, BREEDS_DIR, CONFIG, DATA, FIXTURES, PIPELINES,  # noqa: F401
                               ROOT, SCHEMA_DIR, VAR)


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
