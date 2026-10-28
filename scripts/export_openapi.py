#!/usr/bin/env python3
"""Write (or --check) data/schema/openapi.json from the contract router.

The mock server and the backend mount the same router, so either app yields the same document.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "mock-server")]

from mock_server.app import create_app  # noqa: E402

from backend.core.contract import openapi_text  # noqa: E402

TARGET = ROOT / "data/schema/openapi.json"


def main() -> int:
    text = openapi_text(create_app())
    if "--check" in sys.argv:
        current = TARGET.read_text() if TARGET.exists() else ""
        if current != text:
            sys.stdout.writelines(difflib.unified_diff(current.splitlines(True), text.splitlines(True),
                                                       "committed", "generated", n=2))
            print("openapi.json drift: run `make openapi` and bump the API version")
            return 1
        print("openapi.json up to date")
        return 0
    TARGET.write_text(text)
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
