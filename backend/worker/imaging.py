"""Image helpers: alpha matting and re-centring (what BiRefNet + crop/pad do on the GPU host)."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image


def matte_square(png: bytes, size: int, margin: float = 0.08) -> bytes:
    """Crop to the alpha bounding box, re-centre on a square canvas with an 8 % margin, RGBA."""
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    a = np.asarray(img)[..., 3]
    ys, xs = np.nonzero(a > 8)
    if len(xs) == 0:
        return png
    crop = img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    inner = int(round(size * (1 - 2 * margin)))
    scale = inner / max(crop.size)
    crop = crop.resize((max(1, round(crop.size[0] * scale)), max(1, round(crop.size[1] * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    canvas.paste(crop, ((size - crop.size[0]) // 2, (size - crop.size[1]) // 2), crop)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def alpha_of(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))[..., 3] > 127


def depth_to_alpha(depth_png: bytes) -> bytes:
    d = np.asarray(Image.open(io.BytesIO(depth_png)))
    a = (d > 0).astype(np.uint8) * 255
    buf = io.BytesIO()
    Image.fromarray(a, "L").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def matte(png: bytes, cfg: dict, size: int) -> bytes:
    """Matte a generated view per the profile: 'alpha' keeps the image's own alpha; 'white_key' keys the plain
    white background (largest connected subject, holes filled), then re-centres like matte_square."""
    if cfg.get("method", "alpha") == "white_key":
        from scipy import ndimage

        img = Image.open(io.BytesIO(png)).convert("RGB")
        rgb = np.asarray(img)
        fg = rgb.min(axis=2) < int(cfg.get("threshold", 236))
        lab, n = ndimage.label(fg)
        if n:
            sizes = ndimage.sum(fg, lab, range(1, n + 1))
            fg = lab == (1 + int(np.argmax(sizes)))
        fg = ndimage.binary_fill_holes(fg)
        alpha = (ndimage.gaussian_filter(fg.astype(np.float32), 0.7) * 255).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(buf, format="PNG")
        png = buf.getvalue()
    return matte_square(png, size)
