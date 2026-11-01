"""Stage E: segmentation (BRIEF Section 6.5, decision 116). The generated mesh is the figurine: Stage E labels it
to the species segmentation schema (petpop_library.segment) and unwraps it when it arrived without UVs, but never
moves a vertex. With the parametric fallback (Stage D skipped), or when labelling fails outright, the morphed
template ships as the figurine (it is labelled by construction)."""
from __future__ import annotations

import io
import json

import numpy as np

from backend.core import lowfi
from petpop_core.vocab import morph_weights
from petpop_library import figure
from petpop_library.meshkit import load_base
from petpop_library.segment import provider_parts, segment

from . import blender
from .backends.mock.pacing import Pace


def unwrap(ctx, co: np.ndarray, tris: np.ndarray) -> tuple[np.ndarray, str]:
    """Per-corner UVs for a mesh without them: Blender's Smart UV Project, else one cell per triangle."""
    if blender.available(ctx.settings.bpy_python):
        work = ctx.workdir("unwrap")
        np.save(work / "co.npy", co.astype(np.float32))
        np.save(work / "tris.npy", tris.astype(np.int64))
        res = blender.run(ctx.settings.bpy_python, ["unwrap"], {"co": str(work / "co.npy"), "tris": str(work / "tris.npy"),
                          "out_dir": str(work)}, timeout=ctx.remaining())
        return np.load(res["corner_uv"]).astype(np.float64), "smart_project"
    ctx.state["fidelity"] = "low"
    return figure.grid_uvs(len(tris)), "grid"


def provider_segmentation(ctx, manifest, co: np.ndarray) -> tuple[np.ndarray | None, str]:
    """The shape provider's own segmentation when the job switched it on (decision 121): its parts per vertex, or
    None with a note when it is off, unsupported or fails (the template labels then stand; the job goes on)."""
    from backend.core.genai import option_segmentation

    from .providers import AwaitingOperator

    params = option_segmentation(ctx.settings.genai, getattr(ctx, "options", None))
    provider = getattr(ctx.backends.shape, "p", None)
    if params is None:
        return None, ""
    if provider is None or not hasattr(provider, "segment_model"):
        return None, "provider segmentation: the shape backend has none"
    try:
        g = provider.segment_model(ctx, ctx.get("shape.glb"), params)
        notes = ctx.state.setdefault("provider_notes", {})
        notes["E"] = "; ".join(x for x in (notes.get("E"), g.note(provider.name)) if x)
        ctx.put(manifest, "segmented_parts.glb", "segmented", "E", g.data)
        return provider_parts(g.data, co), f"provider segmentation: {provider.name}"
    except AwaitingOperator:
        raise
    except Exception as exc:  # noqa: BLE001 - an experiment never fails the job
        return None, f"provider segmentation failed ({exc}); template labels kept"


def run(job_id, spec, manifest, *, ctx, parametric: bool = False) -> list[str]:
    spec = json.loads(ctx.get("spec.json"))
    base = load_base(spec["species"])
    morphed = base.morph(morph_weights(spec))
    keys: list[str] = []
    fit = morphed
    with Pace("E"):
        if parametric:
            mesh = figure.from_template(base, morphed)
            info = {"valid": True, "fallback": "parametric", "notes": "Stage D skipped: morphed template"}
        elif ctx.settings.fail_stage == "E":
            mesh = figure.from_template(base, morphed)
            info = {"valid": False, "fallback": "unwrapped", "notes": "fault injection: morphed template shipped"}
        else:
            co, tris, corner_uv, albedo = figure.read_glb(ctx.get("shape.glb"))
            parts, provider_note = provider_segmentation(ctx, manifest, co)
            seg = segment(base, morphed, co, tris, parts)
            uv_source = "provider"
            if corner_uv is None:
                corner_uv, uv_source = unwrap(ctx, co, tris)
            mesh = figure.make(spec["species"], co, tris, corner_uv, seg["group_names"], seg["groups"], seg["mask_names"],
                               seg["masks"], seg["landmarks"])
            fit = seg["fit"]
            info = {**seg["info"], "fallback": "none", "uv": uv_source}
            if provider_note:
                info["notes"] = f"{info['notes']}; {provider_note}"
            if albedo is not None:
                keys.append(ctx.put(manifest, "provider_albedo.png", "albedo", "E", lowfi.png_bytes(albedo)))
    info.update(mesh_id=mesh.mesh_id, schema_version=mesh.schema_version, tris=int(len(mesh.tri_verts)),
                topology_hash=mesh.topology_hash(), uv_hash=mesh.uv_hash())
    ctx.state["segmentation"] = info
    keys.append(ctx.put(manifest, "figure_mesh.npz", "segmented", "E", figure.save(mesh)))
    buf = io.BytesIO()
    np.save(buf, fit.astype(np.float32))
    keys.append(ctx.put(manifest, "template_fit.npy", "segmented", "E", buf.getvalue()))
    return keys
