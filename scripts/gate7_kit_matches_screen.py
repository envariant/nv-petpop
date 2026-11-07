"""Gate 7: print matches screen for a figure of part kits (decisions 135, 139). Every slot's tile as the customer app
painted it (apps/customer/tests/gate7: the masks of its texture, the spots on its part), against the export's
(petpop_library.kit_figure.slot_tiles) from the same composition 3.0, byte for byte.

    python scripts/gate7_kit_matches_screen.py apps/customer/test-results/gate7/kit
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import numpy as np

from petpop_library import kit_figure
from petpop_library.release import Release, read


def main(out_dir: str) -> int:
    d = Path(out_dir)
    comp = json.loads((d / "composition.json").read_text())
    baked = json.loads((d / "tiles.json").read_text())
    size = int(baked["size"])
    manifest, files = read((Path("fixtures/library") / f"{comp['release_version']}.tar").read_bytes())

    class Mem(Release):
        def file(self, path: str) -> bytes:  # noqa: D401 - the bundle in memory
            return files[path]

    rel = Mem(manifest, Path("."))
    kit = rel.kit(comp["breed_id"])
    server = kit_figure.slot_tiles(comp["species"], kit, comp, None, rel.file, rel.mask_file, size)
    ok = set(server) == set(baked["tiles"]) and comp.get("stamps") and comp.get("shells")
    worst, exact = 0, []
    for slot, (key, img) in server.items():
        b = baked["tiles"].get(slot)
        if b is None:
            print(f"{slot}: not baked on screen")
            ok = False
            continue
        screen = np.frombuffer(base64.b64decode(b["b64"]), np.uint8).reshape(size, size, 4)[..., :3].astype(int)
        diff = np.abs(screen - img.astype(int)).max(axis=2)
        worst = max(worst, int(diff.max()))
        exact.append(float((diff == 0).mean()))
        same_key = b["key"] == key
        ok = ok and same_key
        print(f"{slot}: tile {key.rsplit('/', 1)[-1]}{'' if same_key else ' (screen: ' + b['key'] + ')'}, "
              f"{int((diff > 0).sum())} texels differ, max {int(diff.max())}")
    stamped = sum("#" in k for k, _ in server.values())
    print(f"print vs screen, {len(server)} slots ({stamped} with spots of their own), {len(comp.get('stamps') or [])} spots, "
          f"{len(comp['texture']['markings'])} markings: identical texels {min(exact) * 100:.3f} % (worst slot), max diff {worst}")
    ok = bool(ok) and worst <= 1 and min(exact) >= 0.999 and stamped > 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "apps/customer/test-results/gate7/kit"))
