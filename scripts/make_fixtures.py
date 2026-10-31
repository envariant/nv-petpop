#!/usr/bin/env python3
"""Build the fixture pack: 10 PetSpecs with mock outputs under fixtures/pets/ (BRIEF Section 13).

The pack is shared by the mock server, the MSW handlers, Storybook and the contract tests.
`--lowfi` (S0) uses the numpy/trimesh stand-in; without it (S2+) each pet runs through the real
mock-mode worker pipeline and its outputs are copied in.

    python scripts/make_fixtures.py [--lowfi] [pet_id ...]
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: E402,F401  (puts packages/*/python on sys.path)

from backend.core import lowfi  # noqa: E402
from petpop_library.colouring import vertex_colours  # noqa: E402
from petpop_core.manifest import ManifestBuilder  # noqa: E402
from petpop_library.meshkit import load_base, to_trimesh, write_obj  # noqa: E402
from backend.core.paths import FIXTURES  # noqa: E402
from petpop_core.schemas import spec_errors  # noqa: E402
from petpop_core.spec import apply_patch, default_spec, fill_colour_names  # noqa: E402
from petpop_core.vocab import morph_weights  # noqa: E402

PETS = [
    ("biscuit", "dog", "corgi_pembroke", "Biscuit", 918273,
     {"accessories": [{"type": "collar", "colour_hex": "#DD3333", "tag": True}],
      "personality": ["cheeky", "loves snacks"], "free_text": "Biscuit is a chunky corgi with one ear that flops",
      "overrides": {"ears.asymmetry": "left_floppy"}, "body": {"build": "stocky"}}),
    ("sunny", "dog", "golden_retriever", "Sunny", 1001, {"accessories": [{"type": "bandana", "colour_hex": "#3366CC"}]}),
    ("nova", "dog", "husky", "Nova", 1002, {"eyes": {"colour": "blue", "hex": "#4A86C5", "heterochromia": True,
                                                       "second_colour": "brown", "second_hex": "#3B2412"}}),
    ("gus", "dog", "french_bulldog", "Gus", 1003, {"accessories": [{"type": "bow", "colour_hex": "#E04A8A"}]}),
    ("pepper", "dog", "dalmatian", "Pepper", 1004, {}),
    ("mochi", "dog", "pug", "Mochi", 1005, {"accessories": [{"type": "hat", "colour_hex": "#F2C230"}],
                                            "personality": ["goofy"]}),
    ("oreo", "cat", "tuxedo", "Oreo", 2001, {"accessories": [{"type": "bow", "colour_hex": "#DD3333"}]}),
    ("luna", "cat", "siamese", "Luna", 2002, {"personality": ["curious"]}),
    ("marmalade", "cat", "tabby_orange", "Marmalade", 2003, {"body": {"build": "stocky"},
                                                             "personality": ["lazy"]}),
    ("bear", "cat", "maine_coon", "Bear", 2004, {"accessories": [{"type": "glasses", "colour_hex": "#1E1B1A"}]}),
]


def fixture_spec(pet: tuple) -> dict:
    pid, species, breed, name, seed, patch = pet
    spec = default_spec(species, breed, seed=seed, pet_name=name)
    spec, _ = apply_patch(spec, patch)
    spec = fill_colour_names(spec)
    errs = spec_errors(spec)
    if errs:
        raise SystemExit(f"{pid}: invalid spec {errs}")
    return spec


def write(out: Path, mb: ManifestBuilder, job_id: str, name: str, kind: str, stage: str, data: bytes) -> None:
    p = out / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    mb.file(name, kind, stage, f"jobs/{job_id}/{name}", data)


def build_lowfi(pet: tuple) -> None:
    import numpy as np

    pid = pet[0]
    spec = fixture_spec(pet)
    job_id = f"fx_{pid}"
    out = FIXTURES / pid
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    base = load_base(spec["species"])
    mb = ManifestBuilder(job_id, spec, mode="mock", fidelity="low")
    t = time.perf_counter()

    def tick(stage: str, backend: str, notes: str = "") -> None:
        nonlocal t
        now = time.perf_counter()
        mb.stage(stage, "ok", int((now - t) * 1000), 1, backend, notes)
        t = now

    write(out, mb, job_id, "spec.json", "spec", "A", (json.dumps(spec, indent=1) + "\n").encode())
    tick("A", "rules")
    co = base.morph(morph_weights(spec))
    colours = vertex_colours(base, spec, co)
    tick("control", "lowfi")
    write(out, mb, job_id, "concept.png", "concept", "B", lowfi.png_bytes(lowfi.flat_render(base, co, colours, 0, 512, False)))
    tick("B", "lowfi-render")
    alphas = {}
    for view, az in lowfi.VIEWS.items():
        img = lowfi.flat_render(base, co, colours, az, 384, True)
        alphas[view] = np.array(img)[..., 3] > 0
        write(out, mb, job_id, f"views/{view}.png", "view", "C", lowfi.png_bytes(img))
    tick("C", "lowfi-render")
    shape = lowfi.mock_shape(base, co, spec["seed"])
    ious = lowfi.iou_check(base, shape, alphas, 384)
    sm = to_trimesh(base, shape, yup=True)
    write(out, mb, job_id, "shape.glb", "shape", "D", sm.export(file_type="glb"))
    tick("D", "mock-shape", f"iou {np.mean(ious):.3f}")
    wrapped = lowfi.wrap_nearest(base, co, shape, base.tri_verts)
    tick("E", "lowfi-wrap")
    obj_path = out / "figure_uv.obj"
    write_obj(obj_path, base, wrapped)
    data = obj_path.read_bytes()
    mb.file("figure_uv.obj", "uv_obj", "F", f"jobs/{job_id}/figure_uv.obj", data)
    albedo = lowfi.bake_albedo(base, spec, wrapped, 1024)
    write(out, mb, job_id, "albedo.png", "albedo", "F", lowfi.png_bytes(albedo))
    glb = to_trimesh(base, wrapped, texture=albedo, yup=True).export(file_type="glb")
    write(out, mb, job_id, "figure.glb", "glb", "F", glb)
    pm = lowfi.print_mesh(base, wrapped)
    write(out, mb, job_id, "figure.stl", "stl", "F", pm.export(file_type="stl"))
    write(out, mb, job_id, "figure.3mf", "3mf", "F", pm.export(file_type="3mf"))
    mask, pct = lowfi.paint_check(base, wrapped, 1024)
    write(out, mb, job_id, "paint_mask.png", "mask", "F", lowfi.png_bytes(mask))
    thumb = lowfi.flat_render(base, wrapped, colours, 25, 256, False)
    write(out, mb, job_id, "thumbnail.png", "thumbnail", "F", lowfi.png_bytes(thumb))
    tick("F", "lowfi-bake")
    mb.metric(iou_mean=round(float(np.mean(ious)), 4), iou_views=ious, segmentation_valid=True,
              segmentation_notes="template stand-in", print_watertight=bool(pm.is_watertight),
              print_tris=int(len(pm.faces)), print_height_mm=round(float(pm.extents[2]), 2),
              min_wall_ok=True, min_wall_mm=None, paint_mask_pct=round(pct, 2),
              uv_layout_hash=base.uv_hash(), topology_hash=base.topology_hash())
    mb.finish()
    errs = mb.errors()
    if errs:
        raise SystemExit(f"{pid}: manifest invalid {errs}")
    (out / "manifest.json").write_bytes(mb.to_json())
    print(f"{pid}: {len(mb.data['files'])} files, iou {np.mean(ious):.3f}, paint {pct:.1f}%, "
          f"watertight {pm.is_watertight}")


PRUNE = ("control/", "wrapped_coords.npy", "figure_wrapped.obj")  # intermediates the kiosk never shows


def build_real(pet: tuple) -> None:
    import os

    from backend.worker.local_run import run_pipeline_to_dir  # noqa: PLC0415

    os.environ.setdefault("PETPOP_QUALITY", "fixture")
    os.environ["PETPOP_MOCK_SPEED"] = "0"  # fixtures never pace
    pid = pet[0]
    spec = fixture_spec(pet)
    out = FIXTURES / pid
    if out.exists():
        shutil.rmtree(out)
    m = run_pipeline_to_dir(f"fx_{pid}", spec, out)
    for name in [f["name"] for f in m["files"] if f["name"].startswith(PRUNE)]:
        (out / name).unlink(missing_ok=True)
    shutil.rmtree(out / "control", ignore_errors=True)
    m["files"] = [f for f in m["files"] if not f["name"].startswith(PRUNE)]
    (out / "manifest.json").write_text(json.dumps(m, indent=1) + "\n")
    print(f"{pid}: {m['fallback']}, iou {m['metrics'].get('iou_mean')}, watertight {m['metrics']['print_watertight']}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lowfi_mode = "--lowfi" in sys.argv
    FIXTURES.mkdir(parents=True, exist_ok=True)
    pets = [p for p in PETS if not args or p[0] in args]
    for pet in pets:
        (build_lowfi if lowfi_mode else build_real)(pet)
    index = [{"id": p[0], "species": p[1], "breed": p[2], "pet_name": p[3], "job_id": f"fx_{p[0]}"} for p in PETS]
    (FIXTURES / "index.json").write_text(json.dumps({"pets": index}, indent=1) + "\n")


if __name__ == "__main__":
    main()
