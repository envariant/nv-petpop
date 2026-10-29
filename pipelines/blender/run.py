"""Run one or more Blender stage tasks in a single bpy process.

    python run.py render_control,render_views job.json result.json

Each task is a module in this folder exposing main(job) -> dict; results are merged into result.json.
"""
import importlib
import json
import sys
import time
import traceback
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
# This folder, the repo root and the shared Python packages (bpy runs without the backend's PYTHONPATH).
for _p in (_ROOT / "packages" / "library" / "python", _ROOT / "packages" / "core" / "python", _ROOT, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def main() -> int:
    tasks, job_path, result_path = sys.argv[-3].split(","), sys.argv[-2], sys.argv[-1]
    job = json.loads(Path(job_path).read_text())
    result: dict = {"ok": True, "tasks": {}}
    for t in tasks:
        t0 = time.perf_counter()
        try:
            out = importlib.import_module(t).main(job)
            result["tasks"][t] = {"ok": True, "ms": int((time.perf_counter() - t0) * 1000), **(out or {})}
        except Exception as exc:  # noqa: BLE001 - reported to the worker
            result["ok"] = False
            result["tasks"][t] = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-3000:]}
            break
    Path(result_path).write_text(json.dumps(result, indent=1))
    print("BLENDER_RESULT", json.dumps({"ok": result["ok"]}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
