"""Compositions (BRIEF Section 16, contract 2): the kiosk's order record and the only input to a library export.

A composition names one release; every id in it must exist there, in the right region. Shared by the backend and
the mock server so both refuse the same compositions.
"""
from __future__ import annotations

from typing import Any

from petpop_core.schemas import composition_errors


def errors(manifest: dict[str, Any], body: dict[str, Any]) -> list[str]:
    """Schema errors, then id errors against the release manifest."""
    errs = composition_errors(body)
    return errs or check_ids(manifest, body)


def check_ids(manifest: dict[str, Any], body: dict[str, Any]) -> list[str]:
    """Every id in a composition must exist in the release it names, in the right region (shared with the backend)."""
    errs = []
    if body["release_version"] != manifest["release_version"]:
        errs.append(f"release_version: this kiosk serves {manifest['release_version']}")
    if body["base_mesh_version"] != manifest["base_mesh_version"]:
        errs.append("base_mesh_version: does not match the release")
    fams = {f["id"] for f in manifest["families"]}
    if body["family_id"] not in fams:
        errs.append(f"family_id: unknown {body['family_id']}")
    deltas = {d["id"]: d["region"] for d in manifest["region_deltas"]}
    for region, pid in body["parts"].items():
        if deltas.get(pid) != region:
            errs.append(f"parts.{region}: unknown {pid}")
    shells = {s["id"] for s in manifest["shell_parts"]}
    errs += [f"shells: unknown {s['part_id']}" for s in body["shells"] if s["part_id"] not in shells]
    patterns = {p["id"] for p in manifest["pattern_layers"]}
    errs += [f"layers: unknown {layer['pattern_id']}" for layer in body["layers"] if layer["pattern_id"] not in patterns]
    return errs


def sample(manifest: dict[str, Any], *, layers: int = 3, stamps: int = 0, pet_name: str = "Biscuit", seed: int = 0) -> dict[str, Any]:
    """A valid composition for tests and gates: the first family with its default parts, the first `layers`
    pattern layers at their default coverage, and `stamps` spots spread over the base mesh."""
    import numpy as np

    from .meshkit import load_base

    fam = manifest["families"][0]
    body = {
        "composition_version": "1.0", "species": manifest["species"], "release_version": manifest["release_version"],
        "base_mesh_version": manifest["base_mesh_version"], "pet_name": pet_name, "family_id": fam["id"],
        "parts": dict(fam["default_parts"]), "shells": [], "base_colour": "#C8763A",
        "layers": [{"pattern_id": p["id"], "coverage": p["coverage"]["default"], "colour": p["default_colour"]}
                   for p in manifest["pattern_layers"][:layers]],
        "stamps": [], "eye_colour": "#3B2412", "nose_colour": "#1E1B1A",
    }
    if stamps:
        co = load_base(manifest["species"]).co
        rng = np.random.default_rng(seed)
        for i in rng.choice(len(co), stamps, replace=False):
            body["stamps"].append({"p": [round(float(x), 3) for x in co[i]], "r": float(rng.choice([1.5, 3.0, 5.0])),
                                   "colour": "#1E1B1A"})
    if manifest["shell_parts"]:
        s = manifest["shell_parts"][0]
        body["shells"].append({"part_id": s["id"], "colour": s["default_colour"]})
    return body


def to_spec(manifest: dict[str, Any], body: dict[str, Any], seed: int) -> dict[str, Any]:
    """A composition as a bespoke job's starting PetSpec (BRIEF Section 16: POST /compositions/{id}/bespoke): the
    breed preset it started from, its colours, eyes and accessories, and the pet name."""
    from petpop_core.breeds import all_breeds
    from petpop_core.spec import default_spec, fill_colour_names

    species = body["species"]
    breed = body.get("breed_id") if body.get("breed_id") in {b["id"] for b in all_breeds(species)} else "mixed"
    spec = default_spec(species, breed, seed=seed, pet_name=body.get("pet_name") or None)
    spec["colour"]["base"] = {"name": "custom", "hex": body["base_colour"].upper()}
    spec["eyes"]["hex"] = body["eye_colour"].upper()
    kinds = {s["id"]: s["kind"] for s in manifest["shell_parts"]}
    spec["accessories"] = [{"type": kinds[s["part_id"]], "colour_hex": s["colour"].upper()} for s in body["shells"] if s["part_id"] in kinds]
    return fill_colour_names(spec)
