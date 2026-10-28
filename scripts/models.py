#!/usr/bin/env python3
"""make models: download pinned weights from pipelines/comfy/models.yaml and verify SHA256 (GPU host only).

Never run in a cloud session (CLAUDE.md). Refuses unpinned entries, so nothing ad hoc is ever fetched.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.environ.get("PETPOP_MODELS", "/srv/models"))
    ap.add_argument("--check", action="store_true", help="only verify files already present")
    args = ap.parse_args()
    if os.environ.get("PETPOP_MODE", "mock") == "mock":
        print("make models is for the GPU host (PETPOP_MODE=real); refusing in mock mode")
        return 2
    cfg = yaml.safe_load((ROOT / "pipelines/comfy/models.yaml").read_text())
    bad = 0
    for m in cfg["models"]:
        dest = Path(args.dest) / m["dest"]
        if not m.get("sha256") or m["sha256"] == "TODO" or m["url"].startswith("local://"):
            print(f"[SKIP] {m['name']}: not pinned (fill sha256 in models.yaml)")
            bad += 1
            continue
        if not dest.exists() and not args.check:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            with httpx.stream("GET", m["url"], follow_redirects=True, timeout=None) as r, tmp.open("wb") as f:
                r.raise_for_status()
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
            tmp.replace(dest)
        ok = dest.exists() and sha256(dest) == m["sha256"]
        print(f"[{'OK' if ok else 'BAD'}] {m['name']} -> {dest}")
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
