"""The release packer (BRIEF Section 17, Contract 1): Studio's published library for one species and base-mesh
version, packed into a signed release-<species>-<n>.tar. Shared by the backend and the mock server so both pack
the same bundle from the same items.

Each item arrives as its manifest entry (the release schema's fields) plus the bytes of the files it names; the
packer adds the base mesh (base.bin, mesh.json) and the atlas masks, lays every file out under deltas/, shells/,
masks/ and thumbs/, and signs the manifest.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from . import release
from .basebin import base_bin, mesh_json
from .content import manifest as release_manifest
from .meshkit import load_base

KINDS = ("families", "region_deltas", "shell_parts", "pattern_layers")
FILE_FIELDS = {"families": ("delta", "thumbnail"), "region_deltas": ("delta", "thumbnail"), "shell_parts": ("mesh", "thumbnail"),
               "pattern_layers": ("thumbnail",)}
FOLDERS = {"delta": "deltas", "mesh": "shells", "thumbnail": "thumbs"}
EXT = {"delta": "f16", "mesh": "glb", "thumbnail": "png"}


def pack(species: str, number: int, base_mesh_version: str, items: dict[str, list[dict[str, Any]]],
         read: Callable[[str], bytes], atlas: dict[str, Any], mask_bytes: list[bytes], created_by: str,
         notes: str = "", created_at: str | None = None, key: bytes | None = None) -> tuple[bytes, dict[str, Any]]:
    """items: kind -> manifest entries whose file fields hold *source* keys for `read`. Returns (bundle, manifest)."""
    base = load_base(species)
    files: dict[str, bytes] = {"base.bin": base_bin(base), "mesh.json": mesh_json(base, base_mesh_version)}
    out: dict[str, list[dict[str, Any]]] = {}
    for kind in KINDS:
        entries = []
        for it in sorted(items.get(kind, []), key=lambda x: x["id"]):
            entry = dict(it)
            for f in FILE_FIELDS[kind]:
                path = f"{FOLDERS[f]}/{it['id']}.{EXT[f]}"
                files[path] = read(it[f])
                entry[f] = path
            entries.append(entry)
        out[kind] = entries
    mask_files = []
    for i, data in enumerate(mask_bytes):
        files[f"masks/masks_{i}.png"] = data
        mask_files.append(f"masks/masks_{i}.png")
    m = release_manifest(species, number, base, base_mesh_version, created_by,
                         created_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                         out["families"], out["region_deltas"], out["shell_parts"], out["pattern_layers"],
                         {**atlas, "mask_files": mask_files}, notes=notes)
    bundle = release.pack(m, files, key=key)
    manifest, _ = release.read(bundle, key=key)  # the packed manifest carries the file list and hashes
    return bundle, manifest
