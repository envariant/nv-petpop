"""Stage F texture bake helpers (BRIEF Section 6.6), numpy only so they run in the worker as well as bpy.

- flat_albedo(): the mock texture source: PetSpec colours over the region masks, in the fixed UV layout.
- colour_correct(): per-region gain toward the PetSpec hex values for a generated texture (Hunyuan3D-Paint
  on the GPU host); nose and eye regions are painted flat.
- pad(): 2 px UV seam padding.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.colouring import NOSE_HEX, rgb, vertex_colours  # noqa: E402
from backend.core.meshkit import BaseMesh, dilate, raster_uv  # noqa: E402


def coverage(base: BaseMesh, size: int) -> np.ndarray:
    _, cov = raster_uv(base, np.ones((len(base.co), 1), np.float32), size)
    return cov


def flat_albedo(base: BaseMesh, spec: dict, co: np.ndarray, size: int) -> Image.Image:
    img, cov = raster_uv(base, vertex_colours(base, spec, co), size)
    return Image.fromarray((np.clip(pad(img, cov, 2), 0, 1) * 255).astype(np.uint8), "RGB")


def pad(img: np.ndarray, cov: np.ndarray, px: int = 2) -> np.ndarray:
    return dilate(img, cov, px)


def colour_correct(base: BaseMesh, spec: dict, albedo: Image.Image) -> Image.Image:
    size = albedo.size[0]
    a = np.asarray(albedo.convert("RGB"), dtype=np.float32) / 255.0
    region_vals = np.stack([base.mask("coat"), base.mask("eye"), base.mask("nose")], axis=1)
    regions, cov = raster_uv(base, region_vals, size)
    target_coat = rgb(spec["colour"]["base"]["hex"])
    coat = (regions[..., 0] > 0.5) & cov
    secondary = np.zeros_like(coat)
    for k in ("chest", "socks", "blaze"):
        m, _ = raster_uv(base, base.mask(k)[:, None], size)
        secondary |= m[..., 0] > 0.5
    main = coat & ~secondary
    if main.any():
        mean = a[main].mean(0)
        gain = np.clip(target_coat / np.maximum(mean, 1e-3), 0.6, 1.6)
        a[main] = np.clip(a[main] * (0.5 + 0.5 * gain), 0, 1)
    a[(regions[..., 1] > 0.5) & cov] = rgb(spec["eyes"]["hex"])
    a[(regions[..., 2] > 0.5) & cov] = rgb(NOSE_HEX.get(spec["nose"]["colour"], "#1E1B1A"))
    return Image.fromarray((np.clip(pad(a, cov, 2), 0, 1) * 255).astype(np.uint8), "RGB")
