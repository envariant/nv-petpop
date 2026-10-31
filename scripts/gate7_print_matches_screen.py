"""Gate 7: print matches screen (BRIEF Section 16). The kiosk's shader atlas, baked in the browser for a real
composition (apps/kiosk/tests/gate7), against the export's albedo rendered from the same composition JSON by
backend.worker.export.render_albedo. Texel for texel over the covered UV atlas.

    python scripts/gate7_print_matches_screen.py apps/kiosk/test-results/gate7
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from backend.worker.export import render_albedo
from petpop_library.atlas import mesh_texel_map
from petpop_library.release import Release, read

MAX_MEAN = 0.5   # mean absolute difference per channel, 0..255
MAX_P999 = 8     # 99.9th percentile; GPU float maths at the soft 2-step layer edges
MIN_EXACT = 0.97  # share of covered texels within 1 level on every channel


def main(out_dir: str) -> int:
    d = Path(out_dir)
    comp = json.loads((d / "composition.json").read_text())
    bundle = Path("fixtures/library") / f"{comp['release_version']}.tar"
    manifest, files = read(bundle.read_bytes())

    class Mem(Release):
        def file(self, path: str) -> bytes:  # noqa: D401 - the bundle in memory
            return files[path]

    rel = Mem(manifest, Path("."))
    server = render_albedo(rel, comp).astype(np.int16)
    size = rel.item("meshes", comp["mesh_id"])["atlas"]["size"]
    screen = np.frombuffer((d / "bake.rgba").read_bytes(), np.uint8).reshape(size, size, 4)[..., :3].astype(np.int16)
    covered = mesh_texel_map(rel.mesh(comp["mesh_id"]), size).tri >= 0
    diff = np.abs(server - screen)[covered]
    mean, p999 = float(diff.mean()), float(np.percentile(diff, 99.9))
    exact = float((diff.max(axis=1) <= 1).mean())
    print(f"print vs screen over {int(covered.sum())} covered texels: {len(comp['layers'])} layers, {len(comp['stamps'])} stamps; "
          f"mean |diff| {mean:.3f}, p99.9 {p999:.1f}, within 1 level {exact * 100:.2f} %")
    ok = mean <= MAX_MEAN and p999 <= MAX_P999 and exact >= MIN_EXACT and comp["stamps"]
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "apps/kiosk/test-results/gate7"))
