"""Texture transfer (decision 108): a provider mesh's own colours land on the base UV layout, texture or vertex
coloured, with glTF's base-colour factor applied; texels far from the provider surface fall back to flat."""
from __future__ import annotations

import sys

import numpy as np
import trimesh
from PIL import Image

from backend.core.paths import PIPELINES
from petpop_core.spec import default_spec
from petpop_core.vocab import morph_weights
from petpop_library.meshkit import load_base, raster_uv

sys.path.insert(0, str(PIPELINES / "blender"))
import transfer_texture  # noqa: E402


def provider_glb(co: np.ndarray, tris: np.ndarray, textured: bool) -> bytes:
    """The wrapped mesh itself as the provider mesh (glTF frame): front half red, back half blue."""
    gl = np.stack([co[:, 0], co[:, 2], -co[:, 1]], axis=1)  # Z-up front -Y -> glTF Y-up front +Z
    front = co[:, 1] < np.median(co[:, 1])
    if not textured:
        colours = np.where(front[:, None], [255, 0, 0, 255], [0, 0, 255, 255]).astype(np.uint8)
        return trimesh.Trimesh(gl, tris, vertex_colors=colours, process=False).export(file_type="glb")
    tex = Image.new("RGB", (4, 1))
    for x, c in enumerate([(255, 0, 0), (255, 0, 0), (0, 0, 255), (0, 0, 255)]):
        tex.putpixel((x, 0), c)
    uv = np.stack([np.where(front, 0.125, 0.875), np.full(len(co), 0.5)], axis=1)  # each between two same pixels
    mat = trimesh.visual.material.PBRMaterial(baseColorTexture=tex, baseColorFactor=[255, 255, 255, 255])
    m = trimesh.Trimesh(gl, tris, visual=trimesh.visual.TextureVisuals(uv=uv, material=mat), process=False)
    return m.export(file_type="glb")


def check(textured: bool) -> None:
    spec = default_spec("dog", "beagle", seed=1)
    base = load_base("dog")
    co = base.morph(morph_weights(spec))
    out = transfer_texture.transfer(base, spec, co, provider_glb(co, base.tri_verts, textured), 256, samples=200_000)
    front = (co[:, 1] < np.median(co[:, 1])).astype(np.float32)[:, None]
    side, cov = raster_uv(base, front, 256)
    sure = cov & ((side[..., 0] > 0.95) | (side[..., 0] < 0.05))  # texels well inside one half
    red = out[..., 0] > 0.8
    blue = out[..., 2] > 0.8
    want_red = side[..., 0] > 0.5
    agree = np.where(want_red, red, blue)[sure].mean()
    assert agree > 0.9, f"only {agree:.0%} of texels took the provider colour of their half"


def test_transfer_from_a_texture():
    check(textured=True)


def test_transfer_from_vertex_colours():
    check(textured=False)


def test_far_from_the_provider_surface_is_flat():
    spec = default_spec("dog", "beagle", seed=1)
    base = load_base("dog")
    co = base.morph(morph_weights(spec))
    far = provider_glb(co + [0, 0, 500.0], base.tri_verts, textured=False)  # nowhere near the wrapped mesh
    out = transfer_texture.transfer(base, spec, co, far, 128, samples=50_000)
    _, cov = raster_uv(base, np.ones((len(co), 1), np.float32), 128)
    pure = ((out[..., 0] > 0.95) & (out[..., 1] < 0.05) & (out[..., 2] < 0.05)) | (
        (out[..., 2] > 0.95) & (out[..., 0] < 0.05) & (out[..., 1] < 0.05))
    assert pure[cov].mean() < 0.01  # flat PetSpec colours, not the provider's pure red or blue
