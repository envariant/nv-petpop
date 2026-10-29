"""Flat colour layout from PetSpec over the base-mesh region masks.

The same rules drive the S0/S2 mock renders, the stand-in albedo and (ported to GLSL) the Build-screen
preview, so the swatches, preview and output agree. Patterns are procedural and seeded.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .meshkit import BaseMesh
from petpop_core.vocab import hex_to_rgb, vocab

NOSE_HEX = {"black": "#1E1B1A", "brown": "#5C3A21", "pink": "#E8A0A0", "liver": "#7A3E2A", "grey": "#6E6E6E"}
WHITE = np.array(hex_to_rgb("#F4EFE6")) / 255.0
BLACK = np.array(hex_to_rgb("#1E1B1A")) / 255.0


def rgb(hexv: str) -> np.ndarray:
    return np.array(hex_to_rgb(hexv), dtype=np.float64) / 255.0


def value_noise(p: np.ndarray, scale: float, seed: int) -> np.ndarray:
    """Cheap smooth 3D noise in [0, 1] (sum of seeded sines); deterministic for a given seed."""
    rng = np.random.default_rng(seed)
    out = np.zeros(len(p))
    for _ in range(4):
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        f = scale * rng.uniform(0.7, 1.4)
        out += np.sin(p @ d * f + rng.uniform(0, 6.283))
    return (out / 4.0) * 0.5 + 0.5


def vertex_colours(base: BaseMesh, spec: dict[str, Any], co: np.ndarray | None = None) -> np.ndarray:
    """(n, 3) linear-ish sRGB floats per vertex."""
    co = base.co if co is None else co
    m = {k: base.mask(k) for k in base.mask_names}
    col = spec.get("colour", {})
    seed = int(spec.get("seed", 0)) % (2**31)
    base_c = rgb(col.get("base", {}).get("hex", "#B88A5A"))
    sec_c = rgb(col["secondary"]["hex"]) if col.get("secondary") else WHITE
    dark = base_c * 0.45
    out = np.tile(base_c, (len(co), 1))

    def paint(mask: np.ndarray, colour: np.ndarray) -> None:
        nonlocal out
        w = np.clip(mask, 0, 1)[:, None]
        out = out * (1 - w) + colour * w

    pattern = col.get("pattern", "solid")
    white_parts = np.clip(m["chest"] + m["socks"] + m["blaze"], 0, 1)
    if pattern == "bicolour":
        paint(np.clip(m["chest"] + m["socks"], 0, 1), sec_c)
    elif pattern == "tricolour":
        paint(m["saddle"], BLACK if base_c.mean() > 0.25 else rgb("#B88A5A"))
        paint(white_parts, sec_c if col.get("secondary") else WHITE)
    elif pattern == "saddle_with_white_chest":
        paint(m["saddle"], dark)
        paint(white_parts, sec_c)
    elif pattern == "tuxedo":
        paint(white_parts, sec_c)
    elif pattern == "colourpoint":
        paint(m["points"], sec_c if col.get("secondary") else dark)
    elif pattern == "sable":
        top = np.clip((co[:, 1] - 2) / 12, 0, 1) * np.clip((co[:, 2] - 20) / 30, 0, 1)
        paint(top * 0.8, dark)
    elif pattern == "brindle":
        stripes = (np.sin(co[:, 2] * 0.9 + 3 * value_noise(co, 0.15, seed)) > 0.55).astype(float)
        paint(stripes * 0.85, dark)
    elif pattern == "tabby":
        ang = np.arctan2(co[:, 1], co[:, 0])
        stripes = (np.sin(ang * 7 + co[:, 2] * 0.15 + 2 * value_noise(co, 0.1, seed)) > 0.35).astype(float)
        paint(stripes * 0.9, sec_c if col.get("secondary") else dark)
    elif pattern == "spotted":
        spots = (value_noise(co, 0.45, seed) > 0.78).astype(float)
        paint(spots, sec_c if col.get("secondary") else BLACK)
    elif pattern == "merle":
        patches = (value_noise(co, 0.25, seed) > 0.62).astype(float)
        paint(patches, BLACK if base_c.mean() > 0.3 else dark)
        paint(white_parts * 0.9, sec_c)
    elif pattern == "calico":
        n1 = value_noise(co, 0.18, seed)
        n2 = value_noise(co, 0.18, seed + 1)
        paint((n1 > 0.6).astype(float), sec_c)
        paint(((n2 > 0.65) & (n1 <= 0.6)).astype(float), BLACK)
        paint(m["chest"], WHITE)

    marks = set(col.get("markings", []))
    if "white_blaze" in marks:
        paint(m["blaze"], WHITE)
    if "white_socks" in marks:
        paint(m["socks"], WHITE)
    if "white_chest" in marks:
        paint(m["chest"], WHITE)
    if "dark_mask" in marks:
        paint(m["face_mask"] * 0.85, BLACK)
    if "points" in marks and pattern != "colourpoint":
        paint(m["points"] * 0.85, sec_c if col.get("secondary") else dark)

    eyes = spec.get("eyes", {})
    eye_c = rgb(eyes.get("hex", "#3B2412"))
    eye_l = (base.shell == 4).astype(float)
    eye_r = (base.shell == 5).astype(float)
    paint(eye_l, eye_c)
    second = rgb(eyes["second_hex"]) if eyes.get("heterochromia") and eyes.get("second_hex") else eye_c
    paint(eye_r, second)
    nose_hex = NOSE_HEX.get(spec.get("nose", {}).get("colour", "black"), "#1E1B1A")
    paint((base.shell == 6).astype(float), rgb(nose_hex))
    return np.clip(out, 0, 1)


def palette_hex(name: str) -> str:
    return vocab()["palette"][name]["hex"]
