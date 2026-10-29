"""Pattern layers as signed-distance-style masks in the species UV atlas (BRIEF Section 16).

Each pattern is a scalar field over the base mesh's surface, evaluated per texel at the texel's 3D position, that
grows outward from the pattern's core (the chest from the neck, socks from the floor, points from the
extremities, tabby stripes from their centre lines). The field is rank-normalised over the pattern's allowed
region to 0..MASK_MAX, so thresholding at coverage * MASK_MAX covers that fraction of the region and the
markings grow and shrink smoothly as the slider moves. Texels outside the region hold 255 and are never covered.
Masks pack four to an RGBA PNG, with the eye and nose masks in the last file.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .atlas import TexelMap, dilate_into_padding, texel_positions, texel_values
from .colouring import value_noise
from .deltas import region_weights
from .meshkit import BaseMesh

from .paint import MASK_MAX  # coverage 1.0 thresholds at 250; 255 marks "outside the pattern's region"


@dataclass(frozen=True)
class Pattern:
    id: str
    name: str
    colour: str
    coverage: tuple[float, float, float]  # min, max, default


PATTERNS: list[Pattern] = [
    Pattern("blaze", "Blaze", "#F4EFE6", (0.1, 1.0, 0.45)),
    Pattern("socks", "Socks", "#F4EFE6", (0.1, 1.0, 0.4)),
    Pattern("chest", "Chest", "#F4EFE6", (0.1, 1.0, 0.5)),
    Pattern("mask", "Mask", "#1E1B1A", (0.1, 1.0, 0.5)),
    Pattern("saddle", "Saddle", "#1E1B1A", (0.1, 1.0, 0.5)),
    Pattern("tuxedo", "Tuxedo", "#F4EFE6", (0.1, 1.0, 0.5)),
    Pattern("points", "Points", "#3B2412", (0.05, 1.0, 0.35)),
    Pattern("tabby", "Tabby", "#5C3A21", (0.1, 0.9, 0.45)),
    Pattern("brindle", "Brindle", "#3B2412", (0.1, 0.9, 0.4)),
    Pattern("merle", "Merle", "#6E6E6E", (0.05, 0.8, 0.35)),
]
CHANNELS = [p.id for p in PATTERNS] + ["eye", "nose"]  # flat channel order: file = i // 4, channel = i % 4


def _fields(base: BaseMesh, tm: TexelMap) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per pattern: (field, allowed) over the atlas; lower field values are covered first."""
    pos = texel_positions(base, tm)
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    cov = tm.covered
    w = lambda region: texel_values(base, tm, region_weights(base, region))  # noqa: E731
    g = lambda name: texel_values(base, tm, base.group(name).astype(np.float64))  # noqa: E731
    lm = {k: base.co[v].astype(np.float64) for k, v in base.landmarks.items()}
    shell = texel_values(base, tm, base.shell.astype(np.float64))
    body_shell = cov & (shell < 0.5)
    head = (w("head") + w("muzzle")) > 0.3
    body = g("body") > 0.3
    legs = w("legs") > 0.3
    face_y = (lm["eye_L"][1] + lm["eye_R"][1]) / 2
    eyes = (lm["eye_L"] + lm["eye_R"]) / 2
    neck = lm["neck_front"]
    body_v = (base.group("body") > 0.3) & (base.shell == 0)
    front_y = float(base.co[body_v, 1].min()) if body_v.any() else float(neck[1])
    chest_c = np.array([0.0, front_y, 0.7 * neck[2]])
    width = float(np.abs(base.co[:, 0]).max())
    noise = value_noise(pos.reshape(-1, 3), 0.18, 7).reshape(x.shape)
    extremities = [lm[k] for k in ("ear_tip_L", "ear_tip_R", "nose_tip", "tail_tip", "paw_FL", "paw_FR")]
    d_ext = np.min(np.stack([np.linalg.norm(pos - e, axis=-1) for e in extremities]), axis=0)
    return {
        "blaze": (np.abs(x) + 0.08 * np.maximum(0.0, lm["nose_tip"][2] - z), body_shell & head & (y < face_y + 4)),
        "socks": (z, legs | (body_shell & (z < 10))),
        "chest": (np.hypot(1.2 * x, 0.8 * (z - chest_c[2])) + 0.6 * np.maximum(0.0, y - chest_c[1]),
                  body_shell & (body | (head & (z < neck[2]))) & (y < 0.25 * front_y)),
        "mask": (np.linalg.norm(pos - eyes, axis=-1), body_shell & head),
        "saddle": (-(y + 0.35 * z) + 0.15 * np.abs(x), body_shell & (body | (g("tail") > 0.3)) & (z > 12)),
        "tuxedo": (y + 0.3 * np.abs(x) - 0.2 * z, body_shell & (body | legs)),
        "points": (d_ext, cov & (shell < 3.5)),
        "tabby": (0.5 + 0.5 * np.sin(2 * np.pi * z / 7.0 + 2.2 * noise + 0.6 * np.abs(x) / max(width, 1)), cov & (shell < 3.5)),
        "brindle": (0.5 + 0.5 * np.sin(2 * np.pi * (0.35 * z + 0.65 * y) / 3.6 + 3.0 * noise), body_shell & (body | legs)),
        "merle": (value_noise(pos.reshape(-1, 3), 0.11, 13).reshape(x.shape), cov & (shell < 3.5)),
    }


def rank_normalise(field: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    """uint8 mask: allowed texels ranked to 0..MASK_MAX (equal-area quantiles), everything else 255."""
    out = np.full(field.shape, 255, np.uint8)
    idx = np.nonzero(allowed.ravel())[0]
    if not len(idx):
        return out
    vals = field.ravel()[idx]
    order = np.argsort(vals, kind="stable")
    ranks = np.empty(len(idx), np.float64)
    ranks[order] = np.arange(len(idx), dtype=np.float64) / max(len(idx) - 1, 1)
    flat = out.ravel()
    flat[idx] = np.floor(ranks * MASK_MAX + 0.5).astype(np.uint8)
    return flat.reshape(field.shape)


def build_masks(base: BaseMesh, tm: TexelMap, pad_px: int = 4) -> np.ndarray:
    """(S, S, len(CHANNELS)) uint8: every pattern mask plus eye and nose, dilated into the seam padding."""
    fields = _fields(base, tm)
    chans = [rank_normalise(*fields[p.id]) for p in PATTERNS]
    for name in ("eye", "nose"):
        v = texel_values(base, tm, base.mask(name).astype(np.float64))
        chans.append(np.where(tm.covered, np.floor(np.clip(v, 0, 1) * 255 + 0.5), 0).astype(np.uint8))
    stack = np.stack(chans, axis=-1)
    return dilate_into_padding(stack, tm.covered, pad_px)


def pack_png(masks: np.ndarray) -> list[bytes]:
    """RGBA PNGs, four channels each (zero-filled at the end)."""
    k = masks.shape[-1]
    files = []
    for start in range(0, k, 4):
        block = np.zeros(masks.shape[:2] + (4,), np.uint8)
        part = masks[..., start:start + 4]
        block[..., : part.shape[-1]] = part
        buf = io.BytesIO()
        Image.fromarray(block, "RGBA").save(buf, format="PNG", optimize=True)
        files.append(buf.getvalue())
    return files
