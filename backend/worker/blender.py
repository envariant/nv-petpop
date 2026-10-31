"""Run pipelines/blender tasks in a bpy subprocess (the same contract as the Blender container)."""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.core.paths import PIPELINES, ROOT

log = logging.getLogger("petpop.blender")

class BlenderError(RuntimeError):
    pass


@lru_cache
def available(python: str) -> bool:
    try:
        r = subprocess.run([python, "-c", "import bpy"], capture_output=True, timeout=60)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def run(python: str, tasks: list[str], job: dict[str, Any], timeout: float) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pp-bpy-") as tmp:
        jp, rp = Path(tmp) / "job.json", Path(tmp) / "result.json"
        jp.write_text(json.dumps(job))
        try:
            proc = subprocess.run([python, str(PIPELINES / "blender" / "run.py"), ",".join(tasks), str(jp), str(rp)],
                                  capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
        except subprocess.TimeoutExpired as exc:
            raise BlenderError(f"blender {','.join(tasks)} timed out after {timeout:.0f} s") from exc
        if not rp.exists():
            raise BlenderError(f"blender {','.join(tasks)} crashed: {proc.stderr[-800:]}")
        result = json.loads(rp.read_text())
        if not result["ok"]:
            bad = next(v for v in result["tasks"].values() if not v["ok"])
            raise BlenderError(f"blender {','.join(tasks)}: {bad['error']}\n{bad.get('trace', '')[-1500:]}")
        merged: dict[str, Any] = {}
        for v in result["tasks"].values():
            merged.update(v)
        merged["ms"] = {t: v.get("ms") for t, v in result["tasks"].items()}  # per task, for timing reports
        log.info("blender %s", ", ".join(f"{t} {v.get('ms')} ms" for t, v in result["tasks"].items()))
        return merged
