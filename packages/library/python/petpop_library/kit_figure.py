"""A figure of part kits (decision 135): the parts of a composition 3.0 placed, painted and joined into one mesh with
one albedo atlas, as a figure mesh (petpop_library.figure) the print export takes like any other.

Placement is the kit's (parts.compose_plan: stretch, the torso shape's socket offsets, the pose), the figure stood on
the floor. Painting is per part in its own UVs, its texture template's (decision 129): colour A everywhere, the
texture's pattern and markings where their masks are, in colour B, a mask named `<name>_c` in colour C, the head's
`eye` and `nose` masks in the eye and nose colours (decision 133). Each distinct part gets a tile of the atlas and its
UVs move into it, inset by a gutter of repeated edge pixels so a UV on its tile's edge never samples the next one; a
mirrored right leg shares its left leg's tile. The customer app paints with the same rules
(packages/scene/src/kitFigure.ts), so the print matches the screen.
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


def paint_tile(size: int, texture: dict[str, Any], masks: dict[str, np.ndarray], eye: str | None = None,
               nose: str | None = None) -> np.ndarray:
    """(size, size, 3) uint8: one part's albedo in its template's UVs, image rows top down (row 0 is v = 1)."""
    from PIL import Image

    img = np.empty((size, size, 3), np.float32)
    img[:] = hex_rgb(texture["base"]["hex"])
    for name, colour in mask_layers(texture, eye, nose):
        m = masks.get(name)
        if m is None:
            continue
        a = np.asarray(Image.fromarray(m).resize((size, size), Image.BILINEAR), np.float32)[..., None] / 255.0
        img = img * (1 - a) + colour * a
    return np.clip(np.rint(img), 0, 255).astype(np.uint8)


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


def build(species: str, kit: dict[str, Any], comp: dict[str, Any], read: Callable[[str], bytes],
          mask_file: Callable[[str, str], str | None], tile: int = 512, schema_version: str | None = None):
    """(figure mesh in the print frame (mm, +Z up, the pet facing -Y), its coordinates, albedo atlas (h, w, 3) uint8)
    for a composition 3.0. `read(path)` gives a release file; `mask_file(uv_layout, name)` the path of a mask or None."""
    from PIL import Image

    plan = P.compose_plan(kit, variants_for(kit, comp), comp["pose_id"], comp["preset_id"])
    layout = {(p["kind"], p["variant"]): p.get("uv_layout") or P.uv_layout(species, kit["breed_id"], p["kind"]) for p in kit["parts"]}
    files = list(dict.fromkeys(e["file"] for e in plan["parts"]))
    cols = math.ceil(math.sqrt(len(files)))
    rows = math.ceil(len(files) / cols)
    atlas = np.zeros((rows * tile, cols * tile, 3), np.uint8)
    inner = tile - 2 * GUTTER
    names = {n for n, _ in mask_layers(comp["texture"], comp.get("eye_colour"), comp.get("nose_colour"))}
    cache: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for i, f in enumerate(files):
        entry = next(e for e in plan["parts"] if e["file"] == f)
        uvl = layout[(entry["kind"], entry["variant"])]
        masks = {}
        for name in names:
            path = mask_file(uvl, name)
            if path:
                masks[name] = np.asarray(Image.open(io.BytesIO(read(path))).convert("L"))
        r, c = divmod(i, cols)
        painted = paint_tile(inner, comp["texture"], masks, comp.get("eye_colour"), comp.get("nose_colour"))
        atlas[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile] = np.pad(painted, ((GUTTER, GUTTER), (GUTTER, GUTTER), (0, 0)), mode="edge")
        cache[f] = read_part(read(f))
    vs, tris, corner_uv, slot_of = [], [], [], []
    n = 0
    for e in plan["parts"]:
        v, faces, uv = cache[e["file"]]
        M = np.asarray(e["matrix"])
        placed = v @ M[:3, :3].T + M[:3, 3]
        f = faces[:, ::-1] if e["mirrored"] else faces
        i = files.index(e["file"])
        r, c = divmod(i, cols)
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
