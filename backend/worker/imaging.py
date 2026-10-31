"""Image helpers: alpha matting and re-centring (local keys, or the mask from the host's background removal)."""
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


def border_key(png: bytes) -> bytes:
    """Key a plain backdrop of any colour: the top and side border's median colour (the floor is left out),
    speckle opened away, the largest subject kept, holes filled. Returns RGBA."""
    from scipy import ndimage

    a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(np.int16)
    b = max(2, a.shape[0] // 25)
    bg = np.median(np.concatenate([a[:b].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)]), axis=0)
    fg = ndimage.binary_opening(np.abs(a - bg).max(axis=2) > 40, iterations=3)
    lab, n = ndimage.label(fg)
    if n:
        fg = lab == (1 + int(np.argmax(ndimage.sum(fg, lab, range(1, n + 1)))))
    fg = ndimage.binary_fill_holes(fg)
    buf = io.BytesIO()
    Image.fromarray(np.dstack([a.astype(np.uint8), (fg * 255).astype(np.uint8)]), "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def matte(png: bytes, cfg: dict, size: int) -> bytes:
    """Matte a generated view per the profile: 'alpha' keeps the image's own alpha; 'white_key' keys the plain
    white background (largest connected subject, holes filled); 'border_key' keys a plain backdrop of any colour;
    then re-centres like matte_square."""
    if cfg.get("method") == "border_key":
        return matte_square(border_key(png), size)
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


def apply_mask(png: bytes, mask_png: bytes, size: int) -> bytes:
    """Use a background-removal mask (white = subject) as the image's alpha, keep the largest subject (stray specks
    would widen the crop), then re-centre like matte_square."""
    from scipy import ndimage

    rgb = Image.open(io.BytesIO(png)).convert("RGB")
    a = np.asarray(Image.open(io.BytesIO(mask_png)).convert("L").resize(rgb.size, Image.BILINEAR)).astype(np.float32)
    fg = a > 127
    lab, n = ndimage.label(fg)
    if n > 1:
        keep = lab == (1 + int(np.argmax(ndimage.sum(fg, lab, range(1, n + 1)))))
        a[~ndimage.binary_dilation(keep, iterations=2)] = 0
    a[a < 16] = 0
    buf = io.BytesIO()
    Image.fromarray(np.dstack([np.asarray(rgb), a.astype(np.uint8)]), "RGBA").save(buf, format="PNG")
    return matte_square(buf.getvalue(), size)


def mv_reference(png: bytes, size: int, fill: float = 0.9, grey: int = 127) -> bytes:
    """A matted concept as a multi-view reference, the way MV-Adapter prepares its own: the subject's longer side at
    90 % of a square frame, centred, on mid-grey (scripts/inference_i2mv_sdxl.py, preprocess_image)."""
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    ys, xs = np.nonzero(np.asarray(img)[..., 3] > 8)
    if len(xs):
        img = img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    scale = size * fill / max(img.size)
    img = img.resize((max(1, round(img.size[0] * scale)), max(1, round(img.size[1] * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (grey, grey, grey, 255))
    canvas.alpha_composite(img, ((size - img.size[0]) // 2, (size - img.size[1]) // 2))
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
