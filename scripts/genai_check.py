#!/usr/bin/env python3
"""Probe every service and API provider the active GenAI profile (GENAI_PROFILE) uses, with its credentials;
a provider is probed by reading its account balance (shown, so the credits left are visible).

    python scripts/genai_check.py [--json]

Exit 0 when all are reachable. Used by gates 3 to 6 and by mac/RUNBOOK.md after the tunnel is up.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: E402,F401  (puts packages/*/python on sys.path)

from backend.core.genai import Profile  # noqa: E402

PROBES = {"comfy": "/system_stats", "shape": "/health", "ollama": "/api/tags", "embed": "/health"}


def main() -> int:
    p = Profile()
    results = {}
    for name in [k for k, v in (p["services"] or {}).items() if isinstance(v, dict)]:
        url = p.url(name) + PROBES.get(name, "/")
        try:
            r = httpx.get(url, headers=p.auth_headers(), timeout=10)
            results[name] = {"url": p.url(name), "status": r.status_code, "ok": r.status_code == 200}
        except httpx.HTTPError as exc:
            results[name] = {"url": p.url(name), "status": None, "ok": False, "error": str(exc)[:200]}
    for name in (p.get("providers") or {}):
        from backend.worker.providers import make_provider

        try:
            prov = make_provider(p, name)
            rights = prov.describe()["licence"] if hasattr(prov, "describe") else {}
            results[f"provider:{name}"] = {"url": prov.api.url, "ok": True,
                                           "status": f"balance {json.dumps(prov.balance())}; rights {json.dumps(rights)}"}
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            results[f"provider:{name}"] = {"url": (p["providers"][name] or {}).get("url"), "status": None, "ok": False,
                                           "error": str(exc)[:200]}
    if "--json" in sys.argv:
        print(json.dumps({"profile": p.name, "services": results}, indent=1))
    else:
        print(f"GenAI profile {p.name}")
        for k, v in results.items():
            print(f"  [{'OK' if v['ok'] else 'FAIL'}] {k:<14} {v['url']} {v.get('status') or v.get('error', '')}")
    if not results:
        print("  (profile uses no remote services)")
    return 0 if all(v["ok"] for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
