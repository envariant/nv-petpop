"""Guessed part sizes per breed (decision 128): how big each part of a kit should be, in millimetres, in the kit frame
(x the pet's left, y up, z front; docs/PARTS.md).

Parts generated one at a time (Tripo, docs/PROVIDERS.md) come back at an arbitrary, normalised scale, so the sizes
that make them fit together have to come from somewhere else. They come from the breed database
(data/breeds/<species>_pebbles_simple.json): the per-part prompts state proportions ("about 1.35 times as long as it
is tall", "barely taller than it is wide"), and the preset gives the size class, build, leg length, muzzle, ears and
tail. The model works in torso heights (the torso is 1 tall), then scales the whole breed so its figure is
`FIGURE_MM` tall, the mandrel's figure height (config/mandrel.json), or `LENGTH_MM` long from nose to tail when that
comes first (long, low breeds). Composing a figure fits the whole figure to the mandrel again, so what these sizes
must get right is each part relative to the others.

Every breed gets the same figure height: one mandrel, one box. The size class changes proportions instead, the way
designer toys do: small breeds get bigger heads.

The numbers are first guesses for the rigging workbench, not measurements; a curator's edits and the composed
figure's own fit to the mandrel come after.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from petpop_core.paths import BREEDS_DIR

from .parts import SHARED, SITTING

FIGURE_MM = 90.0
LENGTH_MM = 120.0  # placeholder, like the mandrel's numbers: the longest a figure may be, nose to tail
MIN_FEATURE_MM = 3.0  # thinner than this is fragile in print (BRIEF print rules)

NUMBER = {"as": 1.0, "barely": 1.15, "only slightly": 1.1, "twice": 2.0, "two": 2.0, "three": 3.0, "four": 4.0,
          "one and a half": 1.5, "two and a half": 2.5}
WIDTH = {  # torso width over height, from the prompt's "... from side to side"
    "very slender and narrow": 0.55, "slender and narrow": 0.62, "fairly narrow": 0.7, "moderately full": 0.8,
    "broad and full": 0.9, "round and plump": 0.95, "very broad and heavy": 1.05,
}
LEG_RATIO = {"short": 1.15, "medium": 2.0, "long": 3.0}  # fore leg height over width, when a prompt says nothing
HIND_RATIO = {"short": 1.0, "medium": 1.5, "long": 2.5}
BUILD_LEG_W = {"slim": 0.30, "standard": 0.35, "stocky": 0.40}  # fore leg width, in torso heights
FORE_TYPE_W = {"peg": 0.85, "boot": 1.0, "paw": 1.05, "feathered": 1.12}
HEAD_SIZE = {"tiny": 1.0, "small": 0.9, "medium": 0.8, "large": 0.72}  # head width, in torso heights
MUZZLE_W = {"narrow": 0.92, "medium": 1.0, "wide": 1.1}
MUZZLE_L = {"short": 1.0, "medium": 1.25, "long": 1.5}
EAR_UP = {"erect": 1.0, "semi_erect": 0.5, "rose": 0.25, "drop": 0.0}
EAR_SIZE = {"small": 0.3, "medium": 0.45, "large": 0.65}
TAIL_LEN = {"short": 0.35, "medium": 0.7, "long": 1.0}
TAIL_THICK = {"bob": 0.3, "straight": 0.2, "straight_up": 0.2, "long_thin": 0.12, "otter": 0.28, "brush": 0.33,
              "plume": 0.3, "curl_tight": 0.22, "sickle": 0.2}


def _ratio(text: str, pattern: str) -> float | None:
    """The number in a proportion phrase: `pattern` has one group for the quantity ("1.35 times", "twice", "as")."""
    m = re.search(pattern, text or "")
    if not m:
        return None
    q = m.group(1).strip().removesuffix(" times").strip()
    try:
        return float(q)
    except ValueError:
        return NUMBER.get(q)


def torso_ratio(prompt: str) -> float | None:
    if re.search(r"only slightly longer than it is tall", prompt or ""):
        return NUMBER["only slightly"]
    if re.search(r"about as long as it is tall", prompt or ""):
        return 1.0
    return _ratio(prompt, r"about ([\w. ]+?) as long as it is tall")


def torso_width(prompt: str) -> float | None:
    m = re.search(r"it is tall and ([\w ]+?) from side to side", prompt or "")
    return WIDTH.get(m.group(1)) if m else None


def leg_ratio(prompt: str) -> float | None:
    if re.search(r"barely taller than it is wide", prompt or ""):
        return NUMBER["barely"]
    if re.search(r"about as tall as it is wide", prompt or ""):
        return 1.0
    return _ratio(prompt, r"about ([\w. ]+?) as tall as it is wide")


def _r(x: float, nd: int = 1) -> float:
    return round(float(x), nd)


def guess(breed: dict[str, Any], figure_mm: float = FIGURE_MM, length_mm: float = LENGTH_MM) -> dict[str, Any]:
    """Sizes for one breed of the pebble database: {"parts": {"<kind>/<variant>": {"size_mm": [x, y, z], ...}}, ...}."""
    pre = breed.get("preset", {})
    body, head_p, ears, tail_p = pre.get("body", {}), pre.get("head", {}), pre.get("ears", {}), pre.get("tail", {})
    types, prompts = breed.get("part_types", {}), breed.get("prompts", {})
    legs = body.get("leg_length", "medium")
    notes: list[str] = []

    def said(value, fallback, what):
        if value is None:
            notes.append(f"{what}: no proportion in the prompt, used {fallback}")
            return fallback
        return value

    # torso: 1 tall, L long, W wide
    L = said(torso_ratio(prompts.get("torso", "")), {"long_low": 2.0, "deep_lean": 1.0}.get(types.get("torso"), 1.3), "torso length")
    W = said(torso_width(prompts.get("torso", "")), 0.8, "torso width")
    # fore leg: width from build and type, height from the prompt's ratio
    fw = BUILD_LEG_W.get(body.get("build"), 0.35) * FORE_TYPE_W.get(types.get("fore_leg"), 1.0)
    fh = fw * said(leg_ratio(prompts.get("fore_leg", "")), LEG_RATIO.get(legs, 2.0), "fore leg height")
    below = fh - 0.5 * fw  # the leg's domed top tucks into the torso
    # hind leg (standing): a triangle on its corner whose broad top meets the torso's side, reaching the same ground
    hh = below + 0.6
    hz = hh / said(leg_ratio(prompts.get("hind_leg", "")), HIND_RATIO.get(legs, 1.5), "hind leg width")
    hx = fw
    # hind leg (sitting): lying on one face, the paw end forward
    sz, sy, sx = 0.95 * hh, max(0.45, 0.5 * hh), 1.1 * fw
    # head: width from the size class and muzzle, length from the muzzle, ears on top (or at the sides)
    hw = HEAD_SIZE.get(body.get("size"), 0.8) * MUZZLE_W.get(head_p.get("muzzle_width"), 1.0)
    brachy = bool(head_p.get("brachycephalic"))
    hl = hw * (0.9 if brachy else MUZZLE_L.get(head_p.get("muzzle_length"), 1.25))
    hy = 0.85 * hw
    shape, esize = ears.get("shape", "drop"), EAR_SIZE.get(ears.get("size"), 0.45)
    up = EAR_UP.get(shape, 0.0) * esize * hy
    side = (esize * 0.45 if shape == "drop" else 0.1) * hw
    down = (esize - 0.3) * hy if shape == "drop" else 0.0  # long drop ears hang below the jaw
    head = (hw + side, hy + up + max(0.0, down), hl)
    # tail: length from the preset, thickness and carriage from the part type
    ttype = types.get("tail", "straight")
    tl = TAIL_LEN.get(tail_p.get("length"), 0.7) * (1.1 if ttype == "long_thin" else 1.0)
    tt = TAIL_THICK.get(ttype, 0.22)
    if ttype == "bob":
        tail = (tt * 0.9, tt, max(tt, 0.3))
    elif ttype == "curl_tight":
        tail = (tt * 1.4, 0.45, 0.45)
    elif ttype == "sickle":
        tail = (tt * 0.9, 0.8 * tl, 0.6 * tl)
    elif ttype == "straight_up":
        tail = (tt * 0.9, tl, tt)
    elif ttype == "plume":
        tail = (tt * 0.9, tt + 0.12, tl)  # the feathered fringe hangs below
    else:
        tail = (tt * 0.9, tt, tl)

    # the figure, in torso heights. A kit never tilts its torso (docs/PARTS.md): standing or sitting, the torso rides
    # level on its fore legs, so both poses are about as tall; sitting folds the hind legs under instead.
    head_above = 0.65 * hy + up
    tall = below + 1.0 + head_above
    tail_back = 0.0 if ttype in ("curl_tight", "sickle", "straight_up", "bob") else 0.7 * tail[2]
    long = L + 0.5 * hl + tail_back
    k = min(figure_mm / tall, length_mm / long)  # mm per torso height
    if k < figure_mm / tall:
        notes.append(f"long figure: sized to {length_mm:.0f} mm nose to tail, so it stands {tall * k:.0f} mm tall")

    # keyed by the breed's part types: the shared library's variant names (decision 130)
    defaults = {"head": "default", "torso": types.get("torso", "standard"), "front_leg": types.get("fore_leg", "paw"),
                "hind_leg": types.get("hind_leg", "bean"), "tail": ttype}
    sitting = types.get("hind_leg_sitting", SITTING)
    parts = {
        f"torso/{defaults['torso']}": (W, 1.0, L),
        f"front_leg/{defaults['front_leg']}": (fw, fh, fw),
        f"hind_leg/{defaults['hind_leg']}": (hx, hh, hz),
        f"hind_leg/{sitting}": (sx, sy, sz),
        "head/default": head,
        f"tail/{ttype}": tail,
    }
    out = {}
    for key, dims in parts.items():
        mm = [_r(d * k) for d in dims]
        out[key] = {"size_mm": mm, "longest_mm": max(mm)}
        if min(mm) < MIN_FEATURE_MM:
            notes.append(f"{key}: {min(mm)} mm across, under the {MIN_FEATURE_MM} mm print minimum")
    return {"breed_id": breed["id"], "label": breed.get("label", breed["id"]), "mm_per_torso_height": _r(k, 2),
            "figure_mm": {"height": _r(tall * k), "length": _r(long * k)},
            "inputs": {"size": body.get("size"), "build": body.get("build"), "leg_length": legs, "torso": types.get("torso"),
                       "fore_leg": types.get("fore_leg"), "hind_leg": types.get("hind_leg"), "tail": ttype,
                       "torso_length_to_height": L, "torso_width_to_height": W, "ears": f"{ears.get('size')} {shape}",
                       "muzzle": "brachycephalic" if brachy else head_p.get("muzzle_length")},
            "defaults": defaults, "sitting": sitting, "parts": out, "notes": notes}


def build_table(db: dict[str, Any], figure_mm: float = FIGURE_MM, length_mm: float = LENGTH_MM) -> dict[str, Any]:
    return {"version": "part-sizes-1", "species": db.get("species"), "figure_mm": figure_mm, "length_mm": length_mm,
            "frame": "kit frame, mm: [x the pet's left, y up, z front] of the part as it sits on the figure",
            "breeds": {b["id"]: guess(b, figure_mm, length_mm) for b in db["breeds"]}}


# --------------------------------------------------------------------------- using the table
def table_path(species: str) -> Path:
    return BREEDS_DIR / f"{species}_part_sizes.json"


_TABLES: dict[str, dict[str, Any] | None] = {}


def table(species: str) -> dict[str, Any] | None:
    if species not in _TABLES:
        p = table_path(species)
        _TABLES[species] = json.loads(p.read_text()) if p.is_file() else None
    return _TABLES[species]


def _default_key(row: dict[str, Any], kind: str) -> str:
    return f"{kind}/{(row.get('defaults') or {}).get(kind, 'default')}"


def target(species: str, breed_id: str, kind: str, variant: str) -> tuple[list[float], str] | None:
    """The guessed size of a part, and where it came from: the breed's own row (a variant it does not use takes its
    kind's default), else, for the shared library or an unknown breed, the median of the breeds that use that variant
    (or of every breed's default for the kind)."""
    t = table(species)
    if not t or not t.get("breeds"):
        return None
    row = t["breeds"].get(breed_id) if breed_id != SHARED else None
    if row:
        p = row["parts"].get(f"{kind}/{variant}") or row["parts"].get(_default_key(row, kind))
        if p:
            return p["size_mm"], f"{breed_id} size guess"
    rows = list(t["breeds"].values())
    sizes = [r["parts"][f"{kind}/{variant}"]["size_mm"] for r in rows if f"{kind}/{variant}" in r["parts"]]
    what = f"median {variant} {kind.replace('_', ' ')}"
    if not sizes:
        sizes = [r["parts"][_default_key(r, kind)]["size_mm"] for r in rows if _default_key(r, kind) in r["parts"]]
        what = f"median {kind.replace('_', ' ')}"
    if not sizes:
        return None
    return [float(x) for x in np.median(np.asarray(sizes), axis=0)], f"{what} size guess"


STRETCH_RANGE = (0.4, 2.5)


def stretch_guess(species: str, breed_id: str, kind: str, variant: str, extents) -> list[float]:
    """How much to stretch a shared part (its mesh `extents`, mm, kit frame) per axis to give it the breed's
    proportions (decision 130). A variant the breed's database row names fills the breed's guessed box; any other
    variant keeps its own proportions at the breed's scale (the breed's default for the kind against the median)."""
    t = table(species)
    row = (t or {}).get("breeds", {}).get(breed_id)
    ext = np.maximum(np.asarray(extents, float), 1e-6)
    if not row:
        return [1.0, 1.0, 1.0]
    own = row["parts"].get(f"{kind}/{variant}")
    if own:
        s = np.asarray(own["size_mm"], float) / ext
    else:
        mine, base = row["parts"].get(_default_key(row, kind)), target(species, SHARED, kind, (row.get("defaults") or {}).get(kind, "default"))
        if not mine or not base:
            return [1.0, 1.0, 1.0]
        s = np.full(3, float(np.prod(np.asarray(mine["size_mm"]) / np.asarray(base[0])) ** (1 / 3)))
    return [round(float(x), 3) for x in np.clip(s, *STRETCH_RANGE)]


@lru_cache
def breed_entry(species: str, breed_id: str) -> dict[str, Any] | None:
    """The breed's entry in the breed database (data/breeds/<species>_pebbles_simple.json), or None."""
    p = BREEDS_DIR / f"{species}_pebbles_simple.json"
    if not p.is_file():
        return None
    return next((b for b in json.loads(p.read_text())["breeds"] if b["id"] == breed_id), None)


def recipe(species: str, breed_id: str) -> dict[str, Any]:
    """What a breed's kit starts with (decision 130): its default variant per kind and the shared variants it allows
    (its part types: the sitting hind leg too), and its default texture configuration (colours, pattern, markings)."""
    b = breed_entry(species, breed_id) if breed_id != SHARED else None
    if not b:
        return {"defaults": {}, "allowed": {}, "sitting": None, "texture": None}
    types, colour = b.get("part_types", {}), (b.get("preset") or {}).get("colour") or {}
    defaults = {"torso": types.get("torso"), "front_leg": types.get("fore_leg"), "hind_leg": types.get("hind_leg"),
                "tail": types.get("tail")}
    defaults = {k: v for k, v in defaults.items() if v}
    sitting = types.get("hind_leg_sitting")
    allowed = {k: [v] for k, v in defaults.items()}
    if sitting:
        allowed.setdefault("hind_leg", []).append(sitting)
    texture = None
    if colour.get("base"):
        texture = {"base": colour["base"], "secondary": colour.get("secondary"), "pattern": colour.get("pattern"),
                   "markings": list(colour.get("markings") or [])}
    return {"defaults": defaults, "allowed": allowed, "sitting": sitting, "texture": texture}


def fit(v: np.ndarray, size_mm: list[float]) -> tuple[np.ndarray, float, list[str]]:
    """Scale a part so its longest side is the guess's longest side. Each part is exported on its own, at whatever
    scale its generator chose, so no part's own size means anything; its proportions and its longest side survive
    any orientation, so that is the one measure to match. Returns the vertices, the factor and notes."""
    ext = v.max(0) - v.min(0)
    longest = float(ext.max())
    if longest <= 0:
        return v, 1.0, []
    s = float(max(size_mm)) / longest
    got, exp = sorted(ext * s), sorted(size_mm)
    notes = []
    if got[0] > 0 and exp[0] > 0 and not 0.6 <= got[0] / exp[0] <= 1.6:
        notes.append(f"thinnest side {got[0]:.1f} mm where about {exp[0]:.1f} mm was expected")
    return v * s, s, notes


def normalise(species: str, breed: str, kind: str, variant: str, v: np.ndarray,
              scale: bool = True) -> tuple[np.ndarray | None, bool, list[str]]:
    """What an uploaded part needs before the first guess.

    scale on (the default): each part is its own export, at its own scale and about its own origin; it is centred,
    scaled to its breed's size guess, and legs are taken as left legs (as the breed database's prompts ask for them).
    The torso is the figure's frame: centred on the mirror plane (x = 0) and lifted to stand on its guessed legs, so
    y = 0 is the ground.
    scale off: the parts were split from one figure, so they are in proportion and in place; a leg on the pet's
    right (centre at -X) is mirrored to the left.
    Returns the 4x4 to apply (None when nothing changes), whether it mirrors, and notes."""
    matrix = np.eye(4)
    notes: list[str] = []
    mirrored = not scale and kind in ("front_leg", "hind_leg") and float(v[:, 0].mean()) < 0
    if mirrored:
        matrix[0, 0] = -1.0
        notes.append("a right leg, mirrored to the left")
    size = target(species, breed, kind, variant) if scale else None
    if size:
        _, s, why = fit(v, size[0])
        centre = np.eye(4)
        centre[:3, 3] = -(v.min(0) + v.max(0)) / 2
        lift = np.eye(4)
        if kind == "torso":
            leg = target(species, breed, "front_leg", "default")
            if leg:
                fw, fh = leg[0][0], leg[0][1]
                lift[1, 3] = (fh - 0.5 * fw) + float(np.ptp(v[:, 1])) * s / 2  # its underside at the legs' height
        matrix = lift @ np.diag([s, s, s, 1.0]) @ centre
        notes.append(f"centred, scaled x{s:.3g} to {max(size[0]):.0f} mm long ({size[1]})")
        notes += why
    elif scale:
        notes.append(f"no size guess for {species} {kind}: left at its own scale")
    return (None if np.allclose(matrix, np.eye(4)) else matrix), mirrored, notes


def transform_glb(data: bytes, matrix: np.ndarray) -> bytes:
    """The GLB with `matrix` baked into its vertices, its UVs and materials (textures) kept. A mirror flips the
    faces' winding too, so the outside stays out."""
    import io  # noqa: PLC0415

    import trimesh  # noqa: PLC0415

    scene = trimesh.load(io.BytesIO(data), file_type="glb")
    meshes = scene.dump() if isinstance(scene, trimesh.Scene) else [scene]
    for mesh in meshes:
        mesh.apply_transform(matrix)
    return trimesh.Scene(meshes).export(file_type="glb")
