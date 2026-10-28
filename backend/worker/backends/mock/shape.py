"""MockShapeBackend: the morphed base mesh with low-frequency noise and small random ear and tail
perturbation, triangulated (BRIEF Section 13)."""
from __future__ import annotations

from backend.core import lowfi
import numpy as np
import trimesh

from backend.core.accessories import placed
from backend.core.meshkit import load_base
from backend.core.vocab import morph_weights

from ..base import ShapeResult
from .pacing import Pace


class MockShapeBackend:
    name = "mock-shape"

    def _shape(self, spec, seed: int, scale: float) -> ShapeResult:
        base = load_base(spec["species"])
        co = base.morph(morph_weights(spec))
        shape = co + (lowfi.mock_shape(base, co, seed) - co) * scale
        # The generator sees accessories in the views, so its shape includes them too.
        av, af = placed(spec.get("accessories", []), shape, base.landmarks, base.shell)
        verts = np.concatenate([shape, av]) if len(av) else shape
        tris = np.concatenate([base.tri_verts, af + len(shape)]) if len(af) else base.tri_verts
        mesh = trimesh.Trimesh(np.stack([verts[:, 0], verts[:, 2], -verts[:, 1]], axis=1), tris, process=False)
        return ShapeResult(glb=mesh.export(file_type="glb"), co=verts, tris=tris, backend=self.name)

    def multiview(self, ctx, spec, views):
        with Pace("D"):
            return self._shape(spec, int(spec["seed"]), 1.0)

    def single_view(self, ctx, spec, front):
        with Pace("D"):
            return self._shape(spec, int(spec["seed"]) + 1, 0.6)
