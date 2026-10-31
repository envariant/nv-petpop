"""Library export (BRIEF Section 16, "Export without AI"): Stage F only, on the kiosk queue.

The composition JSON is the only input. The worker loads the release it names, applies the family delta and the
part variants to the composition's mesh (decision 118), re-renders the layers and stamps into the albedo with petpop_library.paint (the same
maths as the kiosk's shader, so the print matches the screen), fuses the shells, and then runs the ordinary
Stage F export: base disc and mandrel socket, print and paint checks, the GLB and the print bundle. No GenAI host,
no adapter, no network: a kiosk can take orders while the GenAI host is unreachable. Target: under 60 s on CPU.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from backend.core.config import Settings
from petpop_core.manifest import ManifestBuilder
from petpop_library import paint
from petpop_library.atlas import dilate_into_padding, mesh_texel_map
from petpop_library.deltas import compose, decode
from petpop_library.figure import schema
from petpop_library.release import Release, ReleaseStore

from .context import StageContext, StageFailed
from .stage_f import finish_export


def release_store(s: Settings) -> ReleaseStore:
    return ReleaseStore(s.var / "releases", segmentation={sp: schema(sp)["schema_version"] for sp in ("dog", "cat")})


def library_genai(quality: str) -> dict[str, Any]:
    """The manifest's GenAI block for a library export: no profile, no adapter, no model."""
    return {"profile": "none (library export)", "profile_version": 0, "profile_sha": "", "host": "kiosk", "accelerator": "cpu",
            "adapters": {"parser": "none", "image": "none", "shape": "library", "texture": "library"}, "models": {}, "model_pins": {},
            "quality": quality}


def find_release(store: ReleaseStore, composition: dict[str, Any]) -> Release:
    species = composition["species"]
    active = store.active(species)
    if active and active.version == composition["release_version"]:
        return active
    d = store.root / species / composition["release_version"]
    if (d / "manifest.json").exists():
        import json

        return Release(json.loads((d / "manifest.json").read_text()), d)
    raise StageFailed("F", f"release {composition['release_version']} is not installed on this kiosk")


def composed_coords(rel: Release, composition: dict[str, Any], mesh=None) -> np.ndarray:
    """The composition's mesh with its family delta and part variants applied (all on that one mesh)."""
    mesh = mesh if mesh is not None else rel.mesh(composition["mesh_id"])
    if rel.manifest["segmentation_version"] != mesh.schema_version:
        raise StageFailed("F", "the release mesh does not follow the release's segmentation schema")
    n = len(mesh.co)
    fam = rel.item("families", composition["family_id"])
    parts = [decode(rel.file(rel.item("region_deltas", pid)["delta"]), n) for pid in composition["parts"].values()]
    return compose(mesh, decode(rel.file(fam["delta"]), n) if fam["delta"] else None, parts)


def render_albedo(rel: Release, composition: dict[str, Any], mesh=None) -> np.ndarray:
    """The composition's atlas at mask resolution, in its mesh's UVs: layers, stamps, eyes and nose."""
    base = mesh if mesh is not None else rel.mesh(composition["mesh_id"])
    atlas = rel.item("meshes", composition["mesh_id"])["atlas"]
    masks = paint.read_masks([rel.file(f) for f in atlas["mask_files"]])
    pattern_channel = {p["id"]: p["channel"] for p in rel.manifest["pattern_layers"]}
    tm = mesh_texel_map(base, atlas["size"])
    # Padded like the kiosk's stamp texture, so a stamp across a UV seam samples the same on screen and in print.
    stamps = dilate_into_padding(paint.stamp_layer(base, tm, composition["stamps"]), tm.tri >= 0, 2)
    return paint.composite(masks, atlas["channels"], composition, pattern_channel, stamps)


def run_export(ctx: StageContext, job_id: str, composition: dict[str, Any], composition_id: str) -> ManifestBuilder:
    """Stage F for a composition. Returns the finished manifest (already stored as manifest.json)."""
    t0 = time.perf_counter()
    store = release_store(ctx.settings)
    rel = find_release(store, composition)
    spec_like = {"species": composition["species"], "seed": 0, "pet_name": composition.get("pet_name", ""),
                 "accessories": [{"type": rel.item("shell_parts", s["part_id"])["kind"], "colour_hex": s["colour"]}
                                 for s in composition["shells"]]}
    mb = ManifestBuilder(job_id, spec_like, mode="mock" if ctx.settings.mode == "mock" else "real",
                         base_mesh_version=rel.manifest["segmentation_version"], genai=library_genai(ctx.quality["preset"]))
    mb.data["source"] = {"kind": "composition", "composition_id": composition_id, "release_version": rel.version}
    ctx.progress("F", 10, "Shaping your figurine")
    mesh = rel.mesh(composition["mesh_id"])
    coords = composed_coords(rel, composition, mesh)
    ctx.progress("F", 25, "Painting the patterns")
    albedo = render_albedo(rel, composition, mesh)
    albedo_png = paint.albedo_png(albedo, int(ctx.quality["albedo_px"]))
    ctx.put(mb, "composition.json", "spec", "F", _json(composition))
    ctx.put(mb, "albedo.png", "albedo", "F", albedo_png)
    ctx.progress("F", 40, "Preparing the print file")
    metrics, _ = finish_export(ctx, mb, spec_like, mesh, coords, albedo_png)
    mb.metric(**metrics, segmentation_valid=True, segmentation_notes="library composition", uv_layout_hash=mesh.uv_hash(),
              topology_hash=mesh.topology_hash(), mesh_id=mesh.mesh_id, segmentation_version=mesh.schema_version)
    mb.stage("F", "ok", int((time.perf_counter() - t0) * 1000), 1, "library-export")
    mb.data["fidelity"] = ctx.state.get("fidelity", "high")
    mb.finish()
    errs = mb.errors()
    if errs:
        raise StageFailed("F", f"manifest invalid: {errs[:3]}")
    ctx.put(mb, "manifest.json", "manifest", "F", mb.to_json())
    return mb


def _json(obj: Any) -> bytes:
    import json

    return (json.dumps(obj, indent=1) + "\n").encode()
