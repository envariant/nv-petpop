#!/usr/bin/env python3
"""Run one pipeline job on the active GenAI profile, outside the API (the provider harness's end-to-end check).

    GENAI_PROFILE=tripo python scripts/run_job.py --species dog --breed beagle --seed 1
    GENAI_PROFILE=tripo-manual python scripts/run_job.py --species dog --breed beagle --seed 1   # re-run to resume

Artefacts and the manifest go to var/run_job/<job_id>/ (the job's store; a second run resumes from it). Prints each
stage with its notes (provider task ids and credits) and, for an API provider, the balance before and after. In
manual mode it prints the pending request (also in var/run_job/<job_id>/jobs/<job_id>/manual/) and exits 3: put the
output at the printed result path, or use PetPop Studio's Manual inbox with make dev, then run again.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: E402,F401  (puts packages/*/python on sys.path)

from backend.api.store import LocalStore  # noqa: E402
from backend.core.config import settings  # noqa: E402
from backend.worker.local_run import run_pipeline  # noqa: E402
from backend.worker.providers import make_provider  # noqa: E402
from backend.worker.providers.base import AwaitingOperator  # noqa: E402
from petpop_core.spec import default_spec  # noqa: E402


def balances(s) -> dict:
    out = {}
    for name in (s.genai.get("providers") or {}):
        try:
            out[name] = make_provider(s.genai, name).balance()
        except Exception as exc:  # noqa: BLE001 - shown, not fatal
            out[name] = f"unavailable: {exc}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--species", default="dog", choices=["dog", "cat"])
    ap.add_argument("--breed", default="beagle")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--name", default=None, help="pet name")
    ap.add_argument("--kind", default="pipeline", choices=["pipeline", "bespoke", "batch"])
    ap.add_argument("--job", default=None, help="job id (default j_<breed>_<seed>); reuse it to resume")
    a = ap.parse_args()
    s = settings()
    job_id = a.job or f"j_{a.breed}_{a.seed}"
    store = LocalStore(ROOT / "var" / "run_job" / job_id)
    print(f"profile {s.genai.name}, job {job_id}, store {store.root}")
    before = balances(s)
    if before:
        print("balance before:", json.dumps(before))
    spec = default_spec(a.species, a.breed, seed=a.seed, pet_name=a.name)
    try:
        m = run_pipeline(job_id, spec, store, s, lambda st, pct, msg, **k: print(f"  {st:<8} {pct:>3}% {msg}", flush=True),
                         kind=a.kind).data
    except AwaitingOperator as w:
        p = w.packet
        print(f"\nWAITING for the operator: {p['title']} ({p['task_id']})")
        if p.get("prompt"):
            print(f"  prompt: {p['prompt']}\n  negative: {p.get('negative_prompt')}")
        for line in p.get("settings", []):
            print(f"  {line}")
        for i in p.get("inputs", []):
            print(f"  input {i['name']}: {store.root / i['key']}")
        print(f"  put the {p['expects']['kind']} ({', '.join(p['expects']['accept'])}) at {store.root / p['result_key']}, then run again")
        return 3
    print("\nstage    status    seconds  notes")
    for st in m["stages"]:
        print(f"{st['stage']:<8} {st['status']:<9} {st['ms'] / 1000:>7.1f}  {st.get('notes', '')}")
    print(f"\nfallback {m['fallback']}, fidelity {m['fidelity']}, iou {m['metrics'].get('iou_views')}, "
          f"watertight {m['metrics'].get('print_watertight')}")
    after = balances(s)
    if after:
        print("balance after:", json.dumps(after))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
