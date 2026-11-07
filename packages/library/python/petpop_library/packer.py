"""The release packer (BRIEF Section 17, Contract 1): Studio's published library for one species, packed into a
signed release-<species>-<n>.tar (release 2.0, decision 118). Shared by the backend and the mock server so both
pack the same bundle from the same items.

Each item arrives as its manifest entry (the release schema's fields) plus the bytes of the files it names; the
packer adds every mesh the families and part variants are built on (meshes/<mesh_id>/: binary, info, figure
package, masks, texture, thumbnail), lays the item files out under deltas/, shells/ and thumbs/, and signs the
manifest.
"""
from __future__ import annotations

import hashlib
import json
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


def kit_files(kits: list[dict[str, Any]], masks: list[dict[str, Any]], read: Callable[[str], bytes]):
    """Release entries and files for kits ([{"label", "doc"}], part files as source keys) and masks ([{"uv_layout",
    "name", "key"}]), decision 133: parts laid out by content (parts/<sha256>.glb, a shared part once), masks as
    masks/<uv_layout>/<name>.png. Returns (kit entries sorted by breed, mask entries, files)."""
    files: dict[str, bytes] = {}
    kit_entries = []
    for k in kits:
        doc = json.loads(json.dumps(k["doc"]))
        for p in doc["parts"]:
            p.pop("source", None)  # an OBJ part's original is for Blender in the studio, not for kiosks
            data = read(p["mesh"]["file"])
            sha = hashlib.sha256(data).hexdigest()
            path = f"parts/{sha[:24]}.glb"
            files[path] = data
            p["mesh"] = {**p["mesh"], "file": path, "sha256": sha}
        kit_entries.append({**doc, "label": k["label"]})
    mask_entries = []
    for mk in masks:
        path = f"masks/{mk['uv_layout']}/{mk['name']}.png"
        files[path] = read(mk["key"])
        mask_entries.append({"uv_layout": mk["uv_layout"], "name": mk["name"], "file": path})
    return sorted(kit_entries, key=lambda k: k["breed_id"]), mask_entries, files


def pack(species: str, number: int, items: dict[str, list[dict[str, Any]]], read: Callable[[str], bytes],
         mesh_of: Callable[[str], tuple[BaseMesh, dict[str, Any]]], created_by: str, notes: str = "",
         created_at: str | None = None, key: bytes | None = None, kits: list[dict[str, Any]] | None = None,
         masks: list[dict[str, Any]] | None = None) -> tuple[bytes, dict[str, Any]]:
    """items: kind -> manifest entries whose file fields hold *source* keys for `read`; mesh_of(mesh_id) gives each
    mesh the families and part variants name, with its metadata (name, breeds, version, source_job, texture
    bytes, or `prebuilt`: its (entry, files) from content.mesh_entry). kits: [{"label", "doc"}] committed kit
    documents whose part files are source keys; masks: [{"uv_layout", "name", "key"}] (decision 133). Part files are
    laid out by content (parts/<sha256>.glb), so a part shared by several breeds is packed once.
    Returns (bundle, manifest)."""
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
        if meta.get("prebuilt"):  # the mesh's release files, built once when it entered the library
            entry, mfiles = meta["prebuilt"]
            entry = {**entry, "name": meta["name"], "breeds": sorted(set(meta.get("breeds", []))),
                     "version": int(meta.get("version", 1)), "source_job": meta.get("source_job")}
        else:
            entry, mfiles = mesh_entry(mesh, meta["name"], meta.get("breeds", []), int(meta.get("version", 1)),
                                       meta.get("source_job"), texture=meta.get("texture"))
        meshes.append(entry)
        files.update(mfiles)
    kit_entries, mask_entries, kfiles = kit_files(kits or [], masks or [], read)
    files.update(kfiles)
    m = release_manifest(species, number, schema(species)["schema_version"], created_by,
                         created_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"), meshes,
                         out["families"], out["region_deltas"], out["shell_parts"], out["pattern_layers"], notes=notes,
                         kits=kit_entries, masks=mask_entries)
    bundle = release.pack(m, files, key=key)
    manifest, _ = release.read(bundle, key=key)  # the packed manifest carries the file list and hashes
    return bundle, manifest
