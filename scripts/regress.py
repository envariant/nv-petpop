#!/usr/bin/env python3
"""make regress: run the 30-pet regression set and write tests/regression/metrics.{json,md}
(per-stage time, IoU, wrap validity, print validity, paint-mask %), which the gates read (BRIEF Section 12).

    python scripts/regress.py [--limit N] [--gate N] [--profile test|dev|full]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: E402,F401  (puts packages/*/python on sys.path)

STAGES = ["A", "control", "B", "C", "D", "E", "F"]
# Gate thresholds: robustness checks are fixed; IoU and latency come from the GenAI profile's `gates` and
# `latency` blocks (latency is skipped where the profile waives it, e.g. mac-m4pro).
BASE = dict(completed=1.0, watertight=1.0, wrap_valid=0.8, min_wall=0.9, one_topology=True)


def gate_thresholds(gate: int, profile) -> dict:
    t = dict(BASE)
    if gate >= 4:
        t["iou"] = profile["gates"]["iou_min"]
    if gate >= 5 and profile["latency"]["enforce"]:
        t.update(p50_s=profile["gates"]["p50_s"], max_s=profile["gates"]["max_s"])
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--gate", type=int, default=0)
    ap.add_argument("--quality", default=os.environ.get("PETPOP_QUALITY"))
    args = ap.parse_args()
    if args.quality:
        os.environ["PETPOP_QUALITY"] = args.quality
    os.environ.setdefault("PETPOP_MOCK_SPEED", "0")
    from backend.api.store import LocalStore
    from backend.core.config import settings
    from backend.worker.local_run import run_pipeline
    from backend.worker.runner import JobFailed

    s = settings()
    pets = json.loads((ROOT / "tests/regression/pets.json").read_text())["pets"]
    if args.limit:
        pets = pets[: args.limit]
    rows = []
    tmp = Path(tempfile.mkdtemp(prefix="pp-regress-"))
    store = LocalStore(tmp)
    try:
        for i, pet in enumerate(pets, 1):
            t0 = time.monotonic()
            row = {"id": pet["id"], "species": pet["spec"]["species"]}
            try:
                m = run_pipeline(f"rg_{i:02d}", pet["spec"], store, s).data
                met = m["metrics"]
                row.update(status="done", fallback=m["fallback"], fidelity=m["fidelity"],
                           stage_ms={st["stage"]: st["ms"] for st in m["stages"]}, iou=met.get("iou_mean"),
                           wrap_valid=met.get("wrap_valid"), watertight=met.get("print_watertight"),
                           min_wall_mm=met.get("min_wall_mm"), min_wall_ok=met.get("min_wall_ok"),
                           paint_mask_pct=met.get("paint_mask_pct"), topology=met.get("topology_hash"),
                           uv=met.get("uv_layout_hash"))
            except JobFailed as exc:
                row.update(status="failed", error=str(exc))
            row["total_s"] = round(time.monotonic() - t0, 1)
            rows.append(row)
            print(f"[{i:02d}/{len(pets)}] {pet['id']:<28} {row['status']:<6} {row.get('fallback', ''):<10} "
                  f"iou={row.get('iou')} wrap={row.get('wrap_valid')} watertight={row.get('watertight')} {row['total_s']}s",
                  flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    summary = summarise(rows, s.mode, f"{s.profile}/{s.quality['preset']}")
    out = ROOT / "tests/regression"
    (out / "metrics.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1) + "\n")
    (out / "metrics.md").write_text(markdown(summary, rows))
    print(json.dumps(summary, indent=1))
    if args.gate:
        if args.gate >= 5 and not s.genai["latency"]["enforce"]:
            print(f"  [WAIVED] latency target on profile {s.profile}")
        return check(summary, gate_thresholds(args.gate, s.genai))
    return 0


def summarise(rows, mode, profile) -> dict:
    done = [r for r in rows if r["status"] == "done"]
    frac = lambda k: round(sum(bool(r.get(k)) for r in done) / max(len(done), 1), 3)  # noqa: E731
    topo = {}
    for r in done:
        topo.setdefault(r["species"], set()).add((r["topology"], r["uv"]))
    times = [r["total_s"] for r in done]
    ious = [r["iou"] for r in done if r.get("iou") is not None]
    return {
        "mode": mode, "profile": profile, "pets": len(rows), "completed": round(len(done) / max(len(rows), 1), 3),
        "watertight": frac("watertight"), "wrap_valid": frac("wrap_valid"), "min_wall": frac("min_wall_ok"),
        "fallbacks": {fb: sum(r.get("fallback") == fb for r in done) for fb in ("none", "single_view", "parametric", "unwrapped")},
        "one_topology": all(len(v) == 1 for v in topo.values()),
        "iou": round(statistics.mean(ious), 4) if ious else None,
        "p50_s": round(statistics.median(times), 1) if times else None, "max_s": max(times) if times else None,
        "paint_mask_pct_mean": round(statistics.mean([r["paint_mask_pct"] for r in done]), 2) if done else None,
        "stage_ms_mean": {st: int(statistics.mean([r["stage_ms"].get(st, 0) for r in done])) for st in STAGES} if done else {},
    }


def check(summary, gate) -> int:
    ok = True
    for k, want in gate.items():
        got = summary.get(k)
        good = got == want if isinstance(want, bool) else (got is not None and (got <= want if k.endswith("_s") else got >= want))
        print(f"  [{'PASS' if good else 'FAIL'}] {k}: {got} (needs {'<=' if k.endswith('_s') else '>='} {want})")
        ok &= good
    return 0 if ok else 1


def markdown(summary, rows) -> str:
    lines = ["# Regression metrics", "",
             f"Mode `{summary['mode']}`, profile `{summary['profile']}`, {summary['pets']} pets. Generated by `make regress`.", "",
             "| Measure | Value |", "| --- | --- |"]
    for k in ("completed", "watertight", "wrap_valid", "min_wall", "one_topology", "iou", "p50_s", "max_s", "paint_mask_pct_mean"):
        lines.append(f"| {k} | {summary[k]} |")
    lines.append(f"| fallbacks | {summary['fallbacks']} |")
    lines.append(f"| mean stage ms | {summary['stage_ms_mean']} |")
    lines += ["", "| Pet | Status | Fallback | IoU | Wrap valid | Watertight | Min wall mm | Paint mask % | Total s |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['status']} | {r.get('fallback', '')} | {r.get('iou', '')} | {r.get('wrap_valid', '')} | "
                     f"{r.get('watertight', '')} | {r.get('min_wall_mm', '')} | {r.get('paint_mask_pct', '')} | {r['total_s']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
