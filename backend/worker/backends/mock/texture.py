"""Mock texture source: PetSpec colours painted over the region masks in the fixed UV layout (the views
are renders of the same colours, so projecting them would add nothing in mock mode)."""
from __future__ import annotations

import sys

from backend.core import lowfi
from backend.core.meshkit import load_base
from backend.core.paths import PIPELINES

from .pacing import Pace

sys.path.insert(0, str(PIPELINES / "blender"))
import bake  # noqa: E402


class MockTextureBackend:
    name = "mock-texture"

    def paint(self, ctx, spec, wrapped_obj, coords, views):
        with Pace("F"):
            base = load_base(spec["species"])
            img = bake.flat_albedo(base, spec, coords, int(ctx.quality["albedo_px"]))
            return lowfi.png_bytes(img)
