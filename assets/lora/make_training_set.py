#!/usr/bin/env python3
"""Render the petpop_style LoRA training set (BRIEF Section 12): N morphed, coloured base-mesh variants from
random breeds, poses of the camera and accessories, each with a caption built by the prompt compiler.

Run once the hand-built base meshes exist (S4); on the proxies it is a smoke test.
    python assets/lora/make_training_set.py --count 150 --out assets/lora/dataset
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.core.breeds import all_breeds  # noqa: E402
from backend.core.meshkit import load_base  # noqa: E402
from backend.core.paths import PIPELINES, bpy_python  # noqa: E402
from backend.core.spec import default_spec  # noqa: E402
from backend.core.vocab import morph_weights  # noqa: E402
from backend.prompts.compiler import compile_prompts  # noqa: E402
from backend.worker import blender  # noqa: E402

sys.path.insert(0, str(PIPELINES / "blender"))
import bake  # noqa: E402

ACC = ["collar", "bandana", "bow", "hat", "glasses"]
COLOURS = ["#DD3333", "#3366CC", "#2E9E5B", "#F2C230", "#E04A8A"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=150)
    ap.add_argument("--out", default=str(ROOT / "assets/lora/dataset"))
    ap.add_argument("--px", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i in range(args.count):
        species = "dog" if rng.random() < 0.6 else "cat"
        breed = rng.choice([b for b in all_breeds(species) if b["id"] != "mixed"])
        spec = default_spec(species, breed["id"], seed=rng.randrange(2**31 - 1))
        if rng.random() < 0.5:
            spec["accessories"] = [{"type": rng.choice(ACC), "colour_hex": rng.choice(COLOURS)}]
        base = load_base(species)
        co = base.morph(morph_weights(spec))
        work = out / f"_work_{i:03d}"
        work.mkdir(exist_ok=True)
        albedo = work / "albedo.png"
        bake.flat_albedo(base, spec, co, 1024).save(albedo)
        view = rng.choice(["concept", "front", "left", "right", "back"])
        blender.run(bpy_python(), ["render_views"], {"species": species, "weights": morph_weights(spec), "albedo": str(albedo),
                    "accessories": spec.get("accessories", []), "quality": {"concept_px": args.px, "view_px": args.px, "samples": 32},
                    "out_dir": str(work), "views": [view]}, timeout=600)
        src = work / ("concept.png" if view == "concept" else f"view_{view}.png")
        name = f"{i:03d}_{species}_{breed['id']}"
        src.replace(out / f"{name}.png")
        caption = compile_prompts(spec)["views"]["front" if view == "concept" else view]
        (out / f"{name}.txt").write_text(caption + "\n")
        manifest.append({"file": f"{name}.png", "species": species, "breed": breed["id"], "view": view, "seed": spec["seed"]})
        for f in work.iterdir():
            f.unlink()
        work.rmdir()
        print(f"[{i + 1}/{args.count}] {name} {view}", flush=True)
    (out / "manifest.json").write_text(json.dumps({"count": len(manifest), "items": manifest}, indent=1) + "\n")


if __name__ == "__main__":
    main()
