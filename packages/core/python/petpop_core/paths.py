"""Repository paths shared by every Python component (pure: no environment switches beyond PETPOP_VAR)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
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
