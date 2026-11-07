"""A figure of part kits (decision 135): the parts of a composition 3.0 placed, painted and joined into one mesh with
one albedo atlas, as a figure mesh (petpop_library.figure) the print export takes like any other.

Placement is the kit's (parts.compose_plan: stretch, the torso shape's socket offsets, the pose), the figure stood on
the floor. Painting is per part in its own UVs, its texture template's (decision 129): colour A everywhere, the
texture's pattern and markings where their masks are, in colour B, a mask named `<name>_c` in colour C, the head's
`eye` and `nose` masks in the eye and nose colours (decision 133), then the customer's spots and brush dabs
(decision 139): a stamp belongs to one slot and sits in that part's own frame (mm, before placement), so it stays put
when the pose, the shape or the other parts change. Each distinct part, and each slot with stamps of its own, gets a
tile of the atlas and its UVs move into it, inset by a gutter of repeated edge pixels so a UV on its tile's edge never
samples the next one; a mirrored right leg without stamps of its own shares its left leg's tile. The customer app
paints with the same maths (packages/scene/src/kitPaint.ts: the masks sampled bilinearly at texel centres, float64,
the stamps by the atlas rasteriser), so a tile on screen is the tile in the print, byte for byte.
"""
from __future__ import annotations

import io
import math
from collections.abc import Callable
from typing import Any

import numpy as np

from . import figure
from . import parts as P

SLOT_GROUP = {"torso": "body", "head": "head", "front_left": "leg_FL", "front_right": "leg_FR", "hind_left": "leg_BL",
              "hind_right": "leg_BR", "tail": "tail"}
GROUPS = list(dict.fromkeys(SLOT_GROUP.values()))
EYE, NOSE = "eye", "nose"
GUTTER = 4  # pixels of repeated edge around each part's painted square in the atlas


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def variants_for(kit: dict[str, Any], comp: dict[str, Any]) -> dict[str, str]:
    """The composition's variants, less those its pose swaps in (the pose's win, decision 134)."""
    pose = next(p for p in kit["poses"] if p["pose_id"] == comp["pose_id"])
    swapped = pose.get("variants") or {}
    return {k: v for k, v in comp["variants"].items() if k not in swapped}


def mask_layers(texture: dict[str, Any], eye: str | None, nose: str | None) -> list[tuple[str, np.ndarray]]:
    """(mask name, colour) to paint over colour A, in order: the pattern, then the markings, each in colour B (its
    `_c` mask in colour C), then the eyes and nose."""
    b = texture.get("secondary") or texture["base"]
    c = texture.get("tertiary") or b
    out = []
    for name in [texture.get("pattern"), *(texture.get("markings") or [])]:
        if name:
            out += [(name, hex_rgb(b["hex"])), (f"{name}_c", hex_rgb(c["hex"]))]
    if eye:
        out.append((EYE, hex_rgb(eye)))
    if nose:
        out.append((NOSE, hex_rgb(nose)))
    return out


def sample_mask(m: np.ndarray, size: int) -> np.ndarray:
    """(size, size) float64 in [0, 1]: a mask ((h, w) uint8) sampled bilinearly at each texel centre, edges clamped.
    The customer app's sampleMask (packages/scene/src/kitPaint.ts) does the same sums in the same order."""
    h, w = m.shape
    c = (np.arange(size, dtype=np.float64) + 0.5) / size

    def axis(n: int):
        s = np.clip(c * n - 0.5, 0.0, n - 1.0)
        i0 = np.floor(s).astype(np.int64)
        return i0, np.minimum(i0 + 1, n - 1), s - i0

    x0, x1, fx = axis(w)
    y0, y1, fy = axis(h)
    f = m.astype(np.float64)
    top = f[y0][:, x0] * (1.0 - fx) + f[y0][:, x1] * fx
    bot = f[y1][:, x0] * (1.0 - fx) + f[y1][:, x1] * fx
    return (top * (1.0 - fy)[:, None] + bot * fy[:, None]) / 255.0


def q8(x: np.ndarray) -> np.ndarray:
    return np.clip(np.floor(x + 0.5), 0, 255).astype(np.uint8)


def paint_layers(size: int, texture: dict[str, Any], masks: dict[str, np.ndarray], eye: str | None = None,
                 nose: str | None = None) -> np.ndarray:
    """(size, size, 3) float64: colour A, then each mask layer over it."""
    img = np.empty((size, size, 3), np.float64)
    img[:] = hex_rgb(texture["base"]["hex"]).astype(np.float64)
    for name, colour in mask_layers(texture, eye, nose):
        m = masks.get(name)
        if m is None:
            continue
        a = sample_mask(m, size)[..., None]
        img = img * (1.0 - a) + colour.astype(np.float64) * a
    return img


def paint_tile(size: int, texture: dict[str, Any], masks: dict[str, np.ndarray], eye: str | None = None,
               nose: str | None = None, part: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
               stamps: list[dict[str, Any]] | None = None) -> np.ndarray:
    """(size, size, 3) uint8: one part's albedo in its template's UVs, image rows top down (row 0 is v = 1): the
    layers, then `stamps` (on `part`, its (vertices, faces, uv)) over them."""
    img = paint_layers(size, texture, masks, eye, nose)
    if stamps and part is not None:
        layer = stamp_tile(part, size, stamps)
        sa = layer[..., 3:4].astype(np.float64) / 255.0
        img = img * (1.0 - sa) + layer[..., :3].astype(np.float64) * sa
    return q8(img)


def part_mesh(part: tuple[np.ndarray, np.ndarray, np.ndarray]):
    """A part as the atlas rasteriser reads a mesh: its own vertices, faces and (clamped) corner UVs."""
    from types import SimpleNamespace

    v, faces, uv = part
    t = len(faces)
    return SimpleNamespace(co=np.asarray(v, np.float64), tri_verts=np.asarray(faces, np.int64),
                           uv=np.clip(np.asarray(uv, np.float64), 0.0, 1.0)[faces].reshape(t * 3, 2),
                           tri_loops=np.arange(t * 3, dtype=np.int64).reshape(t, 3))


def stamp_tile(part: tuple[np.ndarray, np.ndarray, np.ndarray], size: int, stamps: list[dict[str, Any]]) -> np.ndarray:
    """(size, size, 4) uint8: a slot's stamps on its part's texels (each texel's position in the part's own frame),
    grown 2 texels into the UV padding as the 2.x atlas is, so a stamp at an island's edge samples cleanly."""
    from .atlas import build_texel_map, dilate_into_padding
    from .paint import stamp_layer

    mesh = part_mesh(part)
    tm = build_texel_map(mesh, size)  # type: ignore[arg-type]
    return dilate_into_padding(stamp_layer(mesh, tm, stamps), tm.tri >= 0, 2)  # type: ignore[arg-type]


def mirror_stamp(slot: str, s: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """A stamp's mirror image across the pet's centre line: a leg's on the other leg at the same place (the right legs
    are the left ones mirrored), a centre part's at -x."""
    other = {"front_left": "front_right", "front_right": "front_left", "hind_left": "hind_right", "hind_right": "hind_left"}
    if slot in other:
        return other[slot], dict(s)
    return slot, {**s, "p": [-s["p"][0], s["p"][1], s["p"][2]]}


def read_part(glb: bytes) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(vertices, faces, per-vertex uv) of a part GLB (one mesh; a part without UVs gets (0.5, 0.5))."""
    import trimesh

    scene = trimesh.load(io.BytesIO(glb), file_type="glb")
    meshes = scene.dump() if isinstance(scene, trimesh.Scene) else [scene]
    vs, fs, uvs, n = [], [], [], 0
    for m in meshes:
        uv = getattr(m.visual, "uv", None)
        vs.append(np.asarray(m.vertices, np.float64))
        fs.append(np.asarray(m.faces, np.int64) + n)
        uvs.append(np.asarray(uv, np.float64) if uv is not None and len(uv) == len(m.vertices) else np.full((len(m.vertices), 2), 0.5))
        n += len(m.vertices)
    return np.concatenate(vs), np.concatenate(fs), np.concatenate(uvs)


def _landmarks(co: np.ndarray, slot_of: np.ndarray) -> dict[str, int]:
    """The segmentation schema's landmarks, near enough (glTF frame: +Y up, +Z front, +X the pet's left), so code
    that reads them (extras' anchors, previews) finds them on a figure of parts."""
    def pick(slot: str, score: Callable[[np.ndarray], np.ndarray], side: int = 0) -> int:
        idx = np.flatnonzero(slot_of == list(SLOT_GROUP).index(slot))
        if side:
            s = idx[co[idx, 0] * side > 0]
            idx = s if len(s) else idx
        if not len(idx):
            idx = np.arange(len(co))
        return int(idx[np.argmax(score(co[idx]))])

    head = lambda f, side=0: pick("head", f, side)  # noqa: E731
    return {
        "nose_tip": head(lambda v: v[:, 2]), "chin": head(lambda v: -v[:, 1] + 0.5 * v[:, 2]),
        "eye_L": head(lambda v: v[:, 2] + 0.6 * v[:, 1], 1), "eye_R": head(lambda v: v[:, 2] + 0.6 * v[:, 1], -1),
        "ear_tip_L": head(lambda v: v[:, 1], 1), "ear_tip_R": head(lambda v: v[:, 1], -1),
        "ear_base_L": head(lambda v: v[:, 1] - 0.5 * v[:, 2], 1), "ear_base_R": head(lambda v: v[:, 1] - 0.5 * v[:, 2], -1),
        "back_of_head": head(lambda v: -v[:, 2]), "neck_front": head(lambda v: -v[:, 1] - 0.2 * v[:, 2]),
        "tail_tip": pick("tail", lambda v: -v[:, 2] + 0.3 * v[:, 1]),
        "paw_FL": pick("front_left", lambda v: -v[:, 1]), "paw_FR": pick("front_right", lambda v: -v[:, 1]),
        "base_centre": int(np.argmin(co[:, 1] + 0.05 * np.abs(co[:, 0]) + 0.05 * np.abs(co[:, 2]))),
    }


def slot_tiles(species: str, kit: dict[str, Any], comp: dict[str, Any], plan: dict[str, Any] | None,
               read: Callable[[str], bytes], mask_file: Callable[[str, str], str | None], size: int) -> dict[str, tuple[str, np.ndarray]]:
    """Per slot, (tile key, (size, size, 3) uint8 painted tile): a slot shares its part's tile unless it has stamps of
    its own. The customer app paints the same tiles (gate 7 compares them)."""
    from PIL import Image

    plan = plan or P.compose_plan(kit, variants_for(kit, comp), comp["pose_id"], comp["preset_id"])
    layout = {(p["kind"], p["variant"]): p.get("uv_layout") or P.uv_layout(species, kit["breed_id"], p["kind"]) for p in kit["parts"]}
    names = {n for n, _ in mask_layers(comp["texture"], comp.get("eye_colour"), comp.get("nose_colour"))}
    by_slot: dict[str, list[dict[str, Any]]] = {}
    for s in comp.get("stamps") or []:
        by_slot.setdefault(s["slot"], []).append({"p": s["p"], "r": s["r"], "colour": s["colour"]})
    masks_of: dict[str, dict[str, np.ndarray]] = {}
    parts: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    painted: dict[str, np.ndarray] = {}
    out: dict[str, tuple[str, np.ndarray]] = {}
    for e in plan["parts"]:
        f = e["file"]
        uvl = layout[(e["kind"], e["variant"])]
        if uvl not in masks_of:
            masks_of[uvl] = {}
            for name in names:
                path = mask_file(uvl, name)
                if path:
                    masks_of[uvl][name] = np.asarray(Image.open(io.BytesIO(read(path))).convert("RGB"))[..., 0]
        stamps = by_slot.get(e["slot"]) or []
        key = f if not stamps else f"{f}#{e['slot']}"
        if key not in painted:
            if stamps and f not in parts:
                parts[f] = read_part(read(f))
            painted[key] = paint_tile(size, comp["texture"], masks_of[uvl], comp.get("eye_colour"), comp.get("nose_colour"),
                                      parts.get(f), stamps)
        out[e["slot"]] = (key, painted[key])
    return out


def build(species: str, kit: dict[str, Any], comp: dict[str, Any], read: Callable[[str], bytes],
          mask_file: Callable[[str, str], str | None], tile: int = 512, schema_version: str | None = None):
    """(figure mesh in the print frame (mm, +Z up, the pet facing -Y), its coordinates, albedo atlas (h, w, 3) uint8)
    for a composition 3.0. `read(path)` gives a release file; `mask_file(uv_layout, name)` the path of a mask or None."""
    plan = P.compose_plan(kit, variants_for(kit, comp), comp["pose_id"], comp["preset_id"])
    inner = tile - 2 * GUTTER
    tiles = slot_tiles(species, kit, comp, plan, read, mask_file, inner)
    keys = list(dict.fromkeys(k for k, _ in tiles.values()))
    cols = math.ceil(math.sqrt(len(keys)))
    rows = math.ceil(len(keys) / cols)
    atlas = np.zeros((rows * tile, cols * tile, 3), np.uint8)
    for k, painted in {k: img for k, img in tiles.values()}.items():
        r, c = divmod(keys.index(k), cols)
        atlas[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile] = np.pad(painted, ((GUTTER, GUTTER), (GUTTER, GUTTER), (0, 0)), mode="edge")
    cache = {f: read_part(read(f)) for f in dict.fromkeys(e["file"] for e in plan["parts"])}
    vs, tris, corner_uv, slot_of = [], [], [], []
    n = 0
    for e in plan["parts"]:
        v, faces, uv = cache[e["file"]]
        M = np.asarray(e["matrix"])
        placed = v @ M[:3, :3].T + M[:3, 3]
        f = faces[:, ::-1] if e["mirrored"] else faces
        r, c = divmod(keys.index(tiles[e["slot"]][0]), cols)
        # tile i's painted square starts GUTTER pixels into its cell; image rows run top down, v up
        uvc = np.clip(uv, 0.0, 1.0)
        tuv = np.stack([(c * tile + GUTTER + uvc[:, 0] * inner) / (cols * tile),
                        1 - (r * tile + GUTTER + (1 - uvc[:, 1]) * inner) / (rows * tile)], axis=1)
        vs.append(placed)
        tris.append(f + n)
        corner_uv.append(tuv[f])
        slot_of.append(np.full(len(v), list(SLOT_GROUP).index(e["slot"])))
        n += len(v)
    co_y = np.concatenate(vs)
    co_y[:, 1] -= co_y[:, 1].min()  # on the floor
    slots = np.concatenate(slot_of)
    co = np.stack([co_y[:, 0], -co_y[:, 2], co_y[:, 1]], axis=1)  # glTF (Y up, +Z front) -> print frame (Z up, -Y front)
    groups = np.zeros((len(GROUPS), len(co)), np.float32)
    for s, slot in enumerate(SLOT_GROUP):
        groups[GROUPS.index(SLOT_GROUP[slot]), slots == s] = 1.0
    lm = _landmarks(co_y, slots)
    mesh = figure.make(species, co, np.concatenate(tris), np.concatenate(corner_uv), GROUPS, groups, [], np.zeros((0, len(co)), np.float32),
                       lm, schema_version)
    from dataclasses import replace

    mesh = replace(mesh, source="kit")
    return mesh, co, atlas
