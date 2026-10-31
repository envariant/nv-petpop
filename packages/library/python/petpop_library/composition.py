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
    mesh_id = body["mesh_id"]
    if mesh_id not in {m["id"] for m in manifest["meshes"]}:
        errs.append(f"mesh_id: unknown {mesh_id}")
    fams = {f["id"]: f["mesh_id"] for f in manifest["families"]}
    if body["family_id"] not in fams:
        errs.append(f"family_id: unknown {body['family_id']}")
    elif fams[body["family_id"]] != mesh_id:
        errs.append(f"family_id: {body['family_id']} is built on another mesh")
    deltas = {d["id"]: (d["region"], d["mesh_id"]) for d in manifest["region_deltas"]}
    for region, pid in body["parts"].items():
        if pid not in deltas or deltas[pid][0] != region:
            errs.append(f"parts.{region}: unknown {pid}")
        elif deltas[pid][1] != mesh_id:
            errs.append(f"parts.{region}: {pid} belongs to another mesh (part variants never cross meshes)")
    shells = {s["id"] for s in manifest["shell_parts"]}
    errs += [f"shells: unknown {s['part_id']}" for s in body["shells"] if s["part_id"] not in shells]
    patterns = {p["id"] for p in manifest["pattern_layers"]}
    errs += [f"layers: unknown {layer['pattern_id']}" for layer in body["layers"] if layer["pattern_id"] not in patterns]
    return errs


def sample(manifest: dict[str, Any], *, layers: int = 3, stamps: int = 0, pet_name: str = "Biscuit", seed: int = 0,
           files: dict[str, bytes] | None = None, family: str | None = None) -> dict[str, Any]:
    """A valid composition for tests and gates: the first family (or `family`) with its default parts, the first
    `layers` pattern layers at their default coverage, and `stamps` spots spread over its mesh."""
    import numpy as np

    fam = next(f for f in manifest["families"] if f["id"] == family) if family else manifest["families"][0]
    body = {
        "composition_version": "2.0", "species": manifest["species"], "release_version": manifest["release_version"],
        "mesh_id": fam["mesh_id"], "pet_name": pet_name, "family_id": fam["id"],
        "parts": dict(fam["default_parts"]), "shells": [], "base_colour": "#C8763A",
        "layers": [{"pattern_id": p["id"], "coverage": p["coverage"]["default"], "colour": p["default_colour"]}
                   for p in manifest["pattern_layers"][:layers]],
        "stamps": [], "eye_colour": "#3B2412", "nose_colour": "#1E1B1A",
    }
    if stamps:
        co = mesh_co(manifest, fam["mesh_id"], files)
        rng = np.random.default_rng(seed)
        for i in rng.choice(len(co), stamps, replace=False):
            body["stamps"].append({"p": [round(float(x), 3) for x in co[i]], "r": float(rng.choice([1.5, 3.0, 5.0])),
                                   "colour": "#1E1B1A"})
    if manifest["shell_parts"]:
        s = manifest["shell_parts"][0]
        body["shells"].append({"part_id": s["id"], "colour": s["default_colour"]})
    return body


def mesh_co(manifest: dict[str, Any], mesh_id: str, files: dict[str, bytes] | None = None):
    """Vertex positions of a release mesh: from the release's files when given, else from the committed proxy
    bundle of the same version (tests and gates on the proxy library)."""
    from pathlib import Path

    from . import figure, release

    if files is None:
        bundle = Path(__file__).resolve().parents[4] / "fixtures" / "library" / f"{manifest['release_version']}.tar"
        if not bundle.exists():
            raise ValueError(f"pass the files of {manifest['release_version']} to place stamps on its mesh")
        _, files = release.read(bundle.read_bytes())
    entry = next(m for m in manifest["meshes"] if m["id"] == mesh_id)
    return figure.load(files[entry["package"]]).co


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
