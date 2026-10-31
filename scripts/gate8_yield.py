"""Gate 8 on a GenAI host (BRIEF Section 16): 20 generated figurines yield at least 15 published meshes with valid
segmentation and no manual mesh edits (decision 119: each figurine is a library mesh of its own, with its family).

Runs a 20-figurine batch (20 dog breeds, preset, one seed) through the studio worker on the active GenAI profile,
accepts and publishes every family that passed QC (no curator edits), and counts the published meshes. On the Mac this
takes several hours; run it in the foreground on a quiet host.

    GENAI_PROFILE=mac-m4pro python scripts/gate8_yield.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

N, NEED = 20, 15


def main() -> int:
    os.environ.setdefault("PETPOP_VAR", tempfile.mkdtemp(prefix="pp-g8-yield-"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from backend.api.service import BackendApi
    from backend.core.config import settings
    from backend.worker.service import Worker
    from gate8_lib import accept_and_publish, run_batch
    from petpop_core.breeds import all_breeds

    s = settings()
    breeds = [b["id"] for b in all_breeds("dog") if b["id"] != "mixed"][:N]
    api, worker = BackendApi(s), Worker(s, queue="studio")
    batch = accept_and_publish(api, run_batch(api, worker, "dog", breeds))
    sm = batch.summary
    print(f"profile {s.profile}: {sm.figurines} figurines, {sm.failed} failed, {sm.passed_qc}/{sm.candidates} passed QC, "
          f"{sm.meshes_published} meshes published (need {NEED})")
    return 0 if sm.meshes_published >= NEED else 1


if __name__ == "__main__":
    sys.exit(main())
