"""Gate 7: composition to print bundle in under 60 s on CPU, with the GenAI host unreachable (BRIEF Sections 16, 17).

For each species, a composition at the limits (10 pattern layers, 400 stamps, a shell part) goes through the real
backend's kiosk API and the kiosk worker (Stage F only, Blender on CPU). The GenAI profile points at hosts that do
not answer, which the kiosk never notices. Checks: time, the print bundle and composition in the fulfilment
folder, a valid manifest naming the composition, a watertight print mesh.

    python scripts/gate7_export.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time

LIMIT_S = 60.0
os.environ.pop("PETPOP_QUALITY", None)  # the profile's own print quality
os.environ.update(PETPOP_VAR=tempfile.mkdtemp(prefix="pp-gate7-"),
                  GENAI_PROFILE="mac-m4pro", COMFY_URL="http://127.0.0.1:9", SHAPE_URL="http://127.0.0.1:9",
                  OLLAMA_URL="http://127.0.0.1:9", GENAI_TOKEN="unreachable")


def main() -> int:
    from backend.api import models as m
    from backend.api.service import BackendApi
    from backend.core.config import settings
    from backend.worker.service import Worker
    from petpop_core.schemas import manifest_errors
    from petpop_library.composition import sample

    s = settings()
    api = BackendApi(s)
    worker = Worker(s, queue="kiosk")
    assert worker.backends is None, "the kiosk worker must not build GenAI adapters"
    ok = True
    for species in ("dog", "cat"):
        man = api.library.active(species).manifest
        comp = sample(man, layers=10, stamps=400, pet_name="Gate", seed=7)
        sess = asyncio.run(api.create_session(m.SessionCreate(kiosk_id="gate-7")))
        st = asyncio.run(api.create_composition(m.CompositionCreate(session_id=sess.session_id, composition=comp), "http://kiosk"))
        t0 = time.perf_counter()
        acc = asyncio.run(api.export_composition(st.composition_id))
        result = worker.run_job(acc.job_id)
        dt = time.perf_counter() - t0
        st = asyncio.run(api.get_composition(st.composition_id, "http://kiosk"))
        folder = s.fulfil_dir / f"{acc.ticket}_{acc.job_id}"
        files = sorted(p.name for p in folder.iterdir()) if folder.exists() else []
        manifest = json.loads(api.store.get(f"jobs/{acc.job_id}/manifest.json"))
        checks = {
            f"under {LIMIT_S:.0f} s": dt < LIMIT_S,
            "ready": result == "done" and st.status == "ready",
            "print bundle and composition in the fulfilment folder": {"figure.3mf", "figure.stl", "albedo.png", "composition.json",
                                                                      "manifest.json"} <= set(files),
            "manifest valid and names the composition": not manifest_errors(manifest)
            and manifest["source"]["composition_id"] == st.composition_id,
            "print mesh watertight": bool(manifest["metrics"].get("print_watertight")),
            "full-fidelity export (Blender)": manifest["fidelity"] == "high",
        }
        print(f"{species}: {dt:.1f} s, {len(comp['layers'])} layers, {len(comp['stamps'])} stamps, {len(comp['shells'])} shell; "
              f"ticket {acc.ticket}; " + ", ".join(f"{k}: {'ok' if v else 'FAIL'}" for k, v in checks.items()))
        ok &= all(checks.values())
    print("GenAI profile:", s.profile, "->", s.genai.url("comfy"), "(unreachable; never contacted by the kiosk)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
