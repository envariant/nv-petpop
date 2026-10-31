"""Library-mode painting in the UV atlas (BRIEF Section 16): pattern layers, stamps, eyes and nose.

The export re-renders a composition's layers and stamps here, deterministically from the composition JSON, so
the print matches the kiosk screen. The kiosk does the same maths: stamps with packages/viewer/src/stamps.ts
(the same algorithm in float64, quantised the same way) and layers in the pattern shader
(packages/viewer/src/PatternMaterial.ts). Rules shared by both:

- A layer covers a texel when its mask value m is below coverage * MASK_MAX (masks rank 0..250; 255 means
  outside the pattern's region), with a 2-step soft edge: a = clamp((coverage * MASK_MAX - m) / 2 + 0.5, 0, 1);
  colour = colour + (layer - colour) * a, layers in order.
- A stamp (p, r, colour) paints every texel whose 3D base-mesh position lies within r of p, soft over
  FEATHER_MM: a = clamp((r - d) / FEATHER_MM + 0.5, 0, 1), composited "over" in order into an RGBA stamp layer
  that is quantised to 8 bits (it is an 8-bit texture on the kiosk) before it goes over the layers.
- On a mesh with its own texture (decision 119) the base is that texture, tinted per channel by
  base_colour / coat_hex and clamped to 0..255; otherwise it is the flat base colour.
- Eyes and nose (mask >= 128) are painted last, flat.
- Every channel is quantised with floor(x + 0.5), clamped to 0..255.
"""
from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image

from .atlas import TexelMap
from .meshkit import BaseMesh

FEATHER_MM = 0.5
EDGE = 2.0
MASK_MAX = 250.0


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float64)


def q8(x: np.ndarray) -> np.ndarray:
    return np.clip(np.floor(x + 0.5), 0, 255).astype(np.uint8)


def triangle_spheres(base: BaseMesh) -> tuple[np.ndarray, np.ndarray]:
    """Centroid and bounding radius of every triangle on the base mesh (stamp candidate search)."""
    p = base.co.astype(np.float64)[base.tri_verts]
    c = p.mean(axis=1)
    r = np.linalg.norm(p - c[:, None, :], axis=2).max(axis=1)
    return c, r


def stamp_layer(base: BaseMesh, tm: TexelMap, stamps: list[dict[str, Any]]) -> np.ndarray:
    """(S, S, 4) uint8 RGBA stamp layer: rgb straight colour, a coverage."""
    size = tm.size
    rgb = np.zeros((size * size, 3), np.float64)
    alpha = np.zeros(size * size, np.float64)
    if stamps:
        centres, radii = triangle_spheres(base)
        co = base.co.astype(np.float64)
        bary = tm.bary.reshape(-1, 3)
        for s in stamps:
            p = np.asarray(s["p"], np.float64)
            r = float(s["r"])
            col = hex_rgb(s["colour"])
            near = np.nonzero(np.linalg.norm(centres - p, axis=1) <= r + FEATHER_MM + radii)[0]
            for t in near:  # triangle index order, as on the kiosk
                tex = tm.texels_of(int(t))
                if not len(tex):
                    continue
                tv = base.tri_verts[t]
                w = bary[tex]
                pos = w[:, 0:1] * co[tv[0]] + w[:, 1:2] * co[tv[1]] + w[:, 2:3] * co[tv[2]]
                d = np.sqrt(((pos - p) ** 2).sum(axis=1))
                a = np.clip((r - d) / FEATHER_MM + 0.5, 0.0, 1.0)
                hit = a > 0
                if not hit.any():
                    continue
                tex, a = tex[hit], a[hit]
                a0 = alpha[tex]
                na = a + a0 * (1.0 - a)
                rgb[tex] = (col * a[:, None] + rgb[tex] * (a0 * (1.0 - a))[:, None]) / na[:, None]
                alpha[tex] = na
    out = np.zeros((size, size, 4), np.uint8)
    out[..., :3] = q8(rgb).reshape(size, size, 3)
    out[..., 3] = q8(alpha * 255.0).reshape(size, size)
    return out


def composite(masks: np.ndarray, channels: dict[str, int], composition: dict[str, Any],
              pattern_channel: dict[str, int], stamps: np.ndarray, texture: np.ndarray | None = None,
              coat_hex: str | None = None) -> np.ndarray:
    """(S, S, 3) uint8 albedo at mask resolution. masks: (S, S, K) uint8, one channel per mask; texture: the
    mesh's own (S, S, 3) uint8 texture, if it has one."""
    size = masks.shape[0]
    c = np.empty((size, size, 3), np.float64)
    if texture is not None and coat_hex:
        tint = hex_rgb(composition["base_colour"]) / np.maximum(hex_rgb(coat_hex), 1.0)
        c[:] = np.clip(texture.astype(np.float64) * tint, 0.0, 255.0)
    else:
        c[:] = hex_rgb(composition["base_colour"])
    for layer in composition["layers"]:
        m = masks[..., pattern_channel[layer["pattern_id"]]].astype(np.float64)
        a = np.clip((float(layer["coverage"]) * MASK_MAX - m) / EDGE + 0.5, 0.0, 1.0)[..., None]
        c += (hex_rgb(layer["colour"]) - c) * a
    sa = stamps[..., 3:4].astype(np.float64) / 255.0
    c = c * (1.0 - sa) + stamps[..., :3].astype(np.float64) * sa
    c[masks[..., channels["nose"]] >= 128] = hex_rgb(composition["nose_colour"])
    c[masks[..., channels["eye"]] >= 128] = hex_rgb(composition["eye_colour"])
    return q8(c)


def read_masks(files: list[bytes]) -> np.ndarray:
    """Concatenate RGBA mask PNGs into (S, S, 4 * len(files)) uint8."""
    arrs = [np.asarray(Image.open(io.BytesIO(b)).convert("RGBA")) for b in files]
    return np.concatenate(arrs, axis=2)


def albedo_png(albedo: np.ndarray, out_size: int) -> bytes:
    img = Image.fromarray(albedo, "RGB")
    if out_size != albedo.shape[0]:
        img = img.resize((out_size, out_size), Image.Resampling.BICUBIC)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
