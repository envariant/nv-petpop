"""The fulfilment folder (BRIEF Section 9): one folder per order, <ticket>_<job id>/, holding the print bundle.
Library exports also carry their composition.json, the order record (BRIEF Section 17, Contract 2)."""
from __future__ import annotations

from pathlib import Path

PRINT_BUNDLE = ["figure.3mf", "figure.stl", "albedo.png", "figure_uv.obj", "paint_mask.png", "manifest.json",
                "composition.json"]


def copy_bundle(fulfil_dir: Path, store, job_id: str, ticket: str) -> list[str]:
    folder = fulfil_dir / f"{ticket}_{job_id}"
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for name in PRINT_BUNDLE:
        key = f"jobs/{job_id}/{name}"
        if store.exists(key):
            (folder / name).write_bytes(store.get(key))
            files.append(name)
    return files
