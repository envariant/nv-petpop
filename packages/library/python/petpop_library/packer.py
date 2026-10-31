"""The release packer (BRIEF Section 17, Contract 1): Studio's published library for one species, packed into a
signed release-<species>-<n>.tar (release 2.0, decision 118). Shared by the backend and the mock server so both
pack the same bundle from the same items.

Each item arrives as its manifest entry (the release schema's fields) plus the bytes of the files it names; the
packer adds every mesh the families and part variants are built on (meshes/<mesh_id>/: binary, info, figure
package, masks, texture, thumbnail), lays the item files out under deltas/, shells/ and thumbs/, and signs the
manifest.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from . import release
from .content import manifest as release_manifest
from .content import mesh_entry
from .figure import schema
from .meshkit import BaseMesh

KINDS = ("families", "region_deltas", "shell_parts", "pattern_layers")
FILE_FIELDS = {"families": ("delta", "thumbnail"), "region_deltas": ("delta", "thumbnail"), "shell_parts": ("mesh", "thumbnail"),
               "pattern_layers": ("thumbnail",)}
FOLDERS = {"delta": "deltas", "mesh": "shells", "thumbnail": "thumbs"}
EXT = {"delta": "f16", "mesh": "glb", "thumbnail": "png"}


def pack(species: str, number: int, items: dict[str, list[dict[str, Any]]], read: Callable[[str], bytes],
         mesh_of: Callable[[str], tuple[BaseMesh, dict[str, Any]]], created_by: str, notes: str = "",
         created_at: str | None = None, key: bytes | None = None) -> tuple[bytes, dict[str, Any]]:
    """items: kind -> manifest entries whose file fields hold *source* keys for `read`; mesh_of(mesh_id) gives each
    mesh the families and part variants name, with its metadata (name, breeds, version, source_job, texture
    bytes). Returns (bundle, manifest)."""
    files: dict[str, bytes] = {}
    out: dict[str, list[dict[str, Any]]] = {}
    for kind in KINDS:
        entries = []
        for it in sorted(items.get(kind, []), key=lambda x: x["id"]):
            entry = dict(it)
            for f in FILE_FIELDS[kind]:
                if it.get(f) is None:
                    continue
                path = f"{FOLDERS[f]}/{it['id']}.{EXT[f]}"
                files[path] = read(it[f])
                entry[f] = path
            entries.append(entry)
        out[kind] = entries
    meshes = []
    for mid in sorted({e["mesh_id"] for k in ("families", "region_deltas") for e in out[k]}):
        mesh, meta = mesh_of(mid)
        entry, mfiles = mesh_entry(mesh, meta["name"], meta.get("breeds", []), int(meta.get("version", 1)),
                                   meta.get("source_job"), texture=meta.get("texture"))
        meshes.append(entry)
        files.update(mfiles)
    m = release_manifest(species, number, schema(species)["schema_version"], created_by,
                         created_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"), meshes,
                         out["families"], out["region_deltas"], out["shell_parts"], out["pattern_layers"], notes=notes)
    bundle = release.pack(m, files, key=key)
    manifest, _ = release.read(bundle, key=key)  # the packed manifest carries the file list and hashes
    return bundle, manifest
