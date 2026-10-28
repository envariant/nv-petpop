#!/usr/bin/env python3
"""Build the accessory library assets/accessories/accessories.blend (BRIEF Section 10) with bpy.

Low-poly quad meshes in a unit frame (anchor at the origin) with their own UV islands; the wrap stage
scales and snaps them to the neck or head landmarks. Run: python scripts/make_accessories.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.core.paths import bpy_python  # noqa: E402

res = subprocess.run([bpy_python(), str(ROOT / "pipelines/blender/accessories_bpy.py"),
                      str(ROOT / "assets/accessories/accessories.blend")], capture_output=True, text=True)
print(res.stdout[-400:])
if "ACCESSORIES_OK" not in res.stdout:
    print(res.stderr[-2000:])
    raise SystemExit(1)
