"""Part kits (decision 127): each breed is a set of parts, head, torso, front leg, hind leg and tail, assembled at
joints. This module is the geometry both Studio and the export rely on; packages/scene/src/parts.ts is its TypeScript
twin (golden-tested against it).

Frame: glTF, millimetres. +Y up, +Z the pet's front, +X the pet's own left. Parts are authored in place (split from
one figure), so a part and the torso meet where they were cut.

Joints. A joint is a point, an axis and a twist:
    part     pivot   where it meets the torso; axis points from the joint INTO the part (away from the torso)
    torso    one attachment per slot (head, front_left, front_right, hind_left, hind_right, tail); axis points OUT of
             the torso
A joint's frame is (axis, ref, axis x ref): ref is the world front (+Z) projected off the axis (world up when the axis
is nearly front or back), turned by the twist about the axis. Assembling a part puts its pivot on the attachment and
its frame onto the attachment's frame; the pose then turns it about the attachment axis:
    legs   one of three twists, 0, 120 or 240 degrees (pose index 0, 1, 2)
    head   yaw (about the attachment's ref), pitch (about axis x ref) and roll (about the axis), within the head's limits
    tail   fixed
Legs are authored as the pet's LEFT legs; the right ones are their mirror image in X, pivot and axis mirrored, and their
pose twist mirrored too, so a symmetric pose has the same index on both sides.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

KINDS = ("head", "torso", "front_leg", "hind_leg", "tail")
SLOTS = ("head", "front_left", "front_right", "hind_left", "hind_right", "tail")
SLOT_KIND = {"head": "head", "front_left": "front_leg", "front_right": "front_leg", "hind_left": "hind_leg",
             "hind_right": "hind_leg", "tail": "tail"}
MIRRORED = {"front_right", "hind_right"}  # these slots use the mirror image of the (left) leg part
LEG_SLOTS = ("front_left", "front_right", "hind_left", "hind_right")
PAIRS = {"front_left": "front_right", "front_right": "front_left", "hind_left": "hind_right", "hind_right": "hind_left"}
LEG_STEP_DEG = 120.0
FRONT = np.array([0.0, 0.0, 1.0])
UP = np.array([0.0, 1.0, 0.0])
MIRROR = np.diag([-1.0, 1.0, 1.0])
DEFAULT_HEAD_LIMITS = {"yaw": [-35.0, 35.0], "pitch": [-25.0, 25.0], "roll": [-20.0, 20.0]}


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        raise ValueError("zero-length axis")
    return v / n


def rot(axis, deg: float) -> np.ndarray:
    """Rodrigues: rotation by `deg` degrees about `axis` (right-handed)."""
    a = unit(axis)
    t = math.radians(deg)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * k + (1 - math.cos(t)) * (k @ k)


@dataclass
class Joint:
    point: np.ndarray  # pivot (part) or attachment position (torso)
    axis: np.ndarray
    twist: float = 0.0

    @classmethod
    def of(cls, d: dict[str, Any]) -> Joint:
        return cls(np.asarray(d["pivot" if "pivot" in d else "position"], float), unit(d["axis"]), float(d.get("twist", 0.0)))

    def as_part(self) -> dict[str, Any]:
        return {"pivot": _r(self.point), "axis": _r(self.axis, 5), "twist": round(self.twist, 3)}

    def as_attachment(self) -> dict[str, Any]:
        return {"position": _r(self.point), "axis": _r(self.axis, 5), "twist": round(self.twist, 3)}

    def frame(self) -> np.ndarray:
        """3x3 with columns (axis, ref, axis x ref)."""
        a = unit(self.axis)
        base = FRONT if abs(float(a @ FRONT)) < 0.95 else UP
        r0 = unit(base - (base @ a) * a)
        r = rot(a, self.twist) @ r0
        return np.stack([a, r, np.cross(a, r)], axis=1)

    def mirrored(self) -> Joint:
        return Joint(MIRROR @ self.point, MIRROR @ self.axis, -self.twist)


def _r(v, nd: int = 3) -> list[float]:
    return [round(float(x), nd) for x in v]


def mirror_vertices(v: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The mirror image of a mesh in X, with the winding flipped so normals still point out."""
    return v * np.array([-1.0, 1.0, 1.0]), faces[:, ::-1].copy()


def pose_rotation(slot: str, attach: Joint, pose: dict[str, Any] | None) -> np.ndarray:
    """The pose's extra rotation at a slot, about the attachment's frame."""
    pose = pose or {}
    if slot in LEG_SLOTS:
        k = int((pose.get("legs") or {}).get(slot, 0)) % 3
        deg = LEG_STEP_DEG * k
        return rot(attach.axis, -deg if slot in MIRRORED else deg)
    if slot == "head":
        h = pose.get("head") or {}
        f = attach.frame()
        a, r, c = f[:, 0], f[:, 1], f[:, 2]
        return rot(r, float(h.get("yaw", 0))) @ rot(c, float(h.get("pitch", 0))) @ rot(a, float(h.get("roll", 0)))
    return np.eye(3)


def placement(part: Joint, attach: Joint, slot: str, pose: dict[str, Any] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(R, t) taking part coordinates to figure coordinates: x' = R (x - pivot) + position, as R x + t."""
    if slot in MIRRORED:
        part = part.mirrored()
    R = pose_rotation(slot, attach, pose) @ attach.frame() @ part.frame().T
    t = attach.point - R @ part.point
    return R, t


def place(vertices: np.ndarray, faces: np.ndarray, part: Joint, attach: Joint, slot: str,
          pose: dict[str, Any] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """A part's mesh in its slot: mirrored for the right legs, then moved onto the torso and posed."""
    v, f = (mirror_vertices(vertices, faces) if slot in MIRRORED else (vertices, faces))
    R, t = placement(part, attach, slot, pose)
    return v @ R.T + t, f


def clamp_head(pose: dict[str, Any], limits: dict[str, list[float]]) -> list[str]:
    """Problems with a pose's head angles against the head's limits (empty when it fits)."""
    out = []
    for k, (lo, hi) in limits.items():
        v = float((pose.get("head") or {}).get(k, 0))
        if not lo - 1e-6 <= v <= hi + 1e-6:
            out.append(f"head {k} {v:g} is outside {lo:g}..{hi:g}")
    return out


# --------------------------------------------------------------------------- automatic first guess
@dataclass
class AutoRig:
    """The analytical first guess for one breed: a joint per part and an attachment per torso slot, each with how it
    was found and a confidence (0..1) that the workbench shows."""
    joints: dict[str, dict[str, Any]] = field(default_factory=dict)  # part key -> joint + method + confidence
    attachments: dict[str, dict[str, Any]] = field(default_factory=dict)  # slot -> attachment + method + confidence
    notes: list[str] = field(default_factory=list)


def _boundary_loops(v: np.ndarray, f: np.ndarray) -> list[np.ndarray]:
    """Vertex index rings of the mesh's open boundaries (cuts), largest first."""
    e = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    uniq, counts = np.unique(e, axis=0, return_counts=True)
    edges = uniq[counts == 1]
    if not len(edges):
        return []
    nbr: dict[int, list[int]] = {}
    for a, b in edges:
        nbr.setdefault(int(a), []).append(int(b))
        nbr.setdefault(int(b), []).append(int(a))
    seen: set[int] = set()
    loops = []
    for start in nbr:
        if start in seen:
            continue
        ring, stack = [], [start]
        while stack:  # connected boundary component (rings can pinch; a component is enough here)
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            ring.append(x)
            stack.extend(y for y in nbr[x] if y not in seen)
        loops.append(np.array(ring))
    lengths = [float(np.linalg.norm(np.diff(v[r], axis=0), axis=1).sum()) for r in loops]
    return [loops[i] for i in np.argsort(lengths)[::-1]]


def _plane_normal(points: np.ndarray) -> np.ndarray:
    c = points - points.mean(axis=0)
    _, _, vt = np.linalg.svd(c, full_matrices=False)
    return vt[-1]


def _nearest(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """For each point of a, the distance to the nearest point of b."""
    from scipy.spatial import cKDTree  # noqa: PLC0415

    return cKDTree(b).query(a, k=1)[0]


def part_joint(kind: str, v: np.ndarray, f: np.ndarray, torso_v: np.ndarray | None) -> dict[str, Any]:
    """Where a part meets the torso, and its axis (into the part).

    in place   parts split from one figure touch the torso: the pivot is the centre of the part's vertices nearest it
               (refined to an open cut's centre when one is there), the axis from there to the part's centre
    cut        a part on its own with an open cut: the cut's centre, its plane's normal turned into the part
    shape      neither: by kind (a leg's top end, a tail's front end, a head's back and lower end)
    """
    centre = v.mean(axis=0)
    loops = _boundary_loops(v, f)
    if torso_v is not None and len(torso_v):
        d = _nearest(v, torso_v)
        span = float(np.linalg.norm(v.max(0) - v.min(0)))
        near = d <= max(np.percentile(d, 8), 0.02 * span)
        if near.sum() >= 3 and float(np.percentile(d, 8)) < 0.08 * span:
            pivot = v[near].mean(axis=0)
            method, conf = "in place", 0.8
            for loop in loops:  # an open cut close to the contact patch: its centre is a better pivot
                c = v[loop].mean(axis=0)
                if np.linalg.norm(c - pivot) < 0.25 * span:
                    pivot, method, conf = c, "in place, cut", 0.9
                    break
            return {"pivot": pivot, "axis": unit(centre - pivot), "method": method, "confidence": conf}
    if loops:
        loop = loops[0]
        c = v[loop].mean(axis=0)
        n = _plane_normal(v[loop])
        n = n if float(n @ (centre - c)) >= 0 else -n
        return {"pivot": c, "axis": unit(n), "method": "cut", "confidence": 0.75}
    lo, hi = v.min(0), v.max(0)
    h = hi - lo
    if kind in ("front_leg", "hind_leg"):
        top = v[v[:, 1] >= hi[1] - 0.12 * h[1]]
        bottom = v[v[:, 1] <= lo[1] + 0.12 * h[1]]
        pivot = top.mean(0)
        return {"pivot": pivot, "axis": unit(bottom.mean(0) - pivot), "method": "shape", "confidence": 0.4}
    if kind == "tail":
        front = v[v[:, 2] >= hi[2] - 0.15 * h[2]]
        pivot = front.mean(0)
        return {"pivot": pivot, "axis": unit(centre - pivot), "method": "shape", "confidence": 0.35}
    # head: the back, lower end (where a neck would be)
    back = v[(v[:, 2] <= lo[2] + 0.3 * h[2]) & (v[:, 1] <= lo[1] + 0.5 * h[1])]
    pivot = back.mean(0) if len(back) else centre
    return {"pivot": pivot, "axis": unit(centre - pivot), "method": "shape", "confidence": 0.3}


def torso_attachments(torso_v: np.ndarray, torso_f: np.ndarray, placed: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """An attachment per slot: where the slot's part was found to meet the torso (its pivot, axis out of the torso), the
    mirror of its pair for the right legs, else a guess from the torso's bounding box."""
    lo, hi = torso_v.min(0), torso_v.max(0)
    mid = (lo + hi) / 2
    h = hi - lo
    guess = {
        "head": (np.array([mid[0], hi[1] - 0.15 * h[1], hi[2] - 0.05 * h[2]]), unit([0, 0.5, 1])),
        "tail": (np.array([mid[0], hi[1] - 0.25 * h[1], lo[2] + 0.05 * h[2]]), unit([0, 0.4, -1])),
        "front_left": (np.array([hi[0] - 0.25 * h[0], lo[1] + 0.1 * h[1], hi[2] - 0.25 * h[2]]), np.array([0, -1.0, 0])),
        "hind_left": (np.array([hi[0] - 0.25 * h[0], lo[1] + 0.1 * h[1], lo[2] + 0.25 * h[2]]), np.array([0, -1.0, 0])),
    }
    out: dict[str, dict[str, Any]] = {}
    for slot in ("head", "tail", "front_left", "hind_left"):
        j = placed.get(slot)
        if j:
            out[slot] = {"position": j["pivot"], "axis": j["axis"], "method": j["method"], "confidence": j["confidence"]}
        else:
            p, a = guess[slot]
            out[slot] = {"position": p, "axis": a, "method": "box", "confidence": 0.25}
    for left in ("front_left", "hind_left"):
        right = PAIRS[left]
        out[right] = {"position": MIRROR @ out[left]["position"], "axis": MIRROR @ out[left]["axis"],
                      "method": f"mirror of {left}", "confidence": out[left]["confidence"]}
    return {s: out[s] for s in SLOTS}


def as_left(kind: str, v: np.ndarray, f: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    """Legs are kept as the pet's left: a leg supplied on the right (centre at -X) is mirrored."""
    if kind in ("front_leg", "hind_leg") and float(v[:, 0].mean()) < 0:
        mv, mf = mirror_vertices(v, f)
        return mv, mf, True
    return v, f, False


def auto_rig(parts: dict[str, tuple[np.ndarray, np.ndarray]], torso: tuple[np.ndarray, np.ndarray]) -> AutoRig:
    """The first guess for a breed: `parts` maps a part key (any id) to (vertices, faces) whose kind is the key's prefix
    up to "/" (e.g. "front_leg/default"); `torso` is the default torso. Joints are found against the torso; the default
    variant of each kind sets the torso's attachment for its slot."""
    tv, tf = torso
    out = AutoRig()
    by_slot: dict[str, dict[str, Any]] = {}
    for key, (v, f) in parts.items():
        kind = key.split("/", 1)[0]
        if kind == "torso":
            continue
        j = part_joint(kind, v, f, tv)
        out.joints[key] = j
        slot = {"head": "head", "tail": "tail", "front_leg": "front_left", "hind_leg": "hind_left"}[kind]
        if key.endswith("/default") or slot not in by_slot:
            by_slot[slot] = j
    out.attachments = torso_attachments(tv, tf, by_slot)
    missing = [k for k in ("head", "front_leg", "hind_leg", "tail") if not any(p.startswith(k + "/") for p in parts)]
    if missing:
        out.notes.append(f"no {', '.join(missing)} part yet: those attachments are guesses from the torso's shape")
    return out


def kit_problems(kit: dict[str, Any]) -> list[str]:
    """What stops a kit from being committed: every kind present with a default, every part jointed, every torso slot
    attached, axes non-zero, poses valid and within the head's limits, and at least one pose allowed."""
    problems: list[str] = []
    parts = kit.get("parts", [])
    for kind in KINDS:
        mine = [p for p in parts if p["kind"] == kind]
        if not mine:
            problems.append(f"no {kind.replace('_', ' ')} part")
        elif not any(p["variant"] == kit.get("defaults", {}).get(kind) for p in mine):
            problems.append(f"no default {kind.replace('_', ' ')} variant")
    for p in parts:
        try:
            if p["kind"] == "torso":
                for s in SLOTS:
                    Joint.of(p["attachments"][s]).frame()
            else:
                Joint.of(p["joint"]).frame()
        except (KeyError, ValueError, TypeError) as exc:
            problems.append(f"{p['kind']} {p['variant']}: incomplete rig ({exc})")
    poses = kit.get("poses", [])
    if not poses:
        problems.append("no pose allowed")
    head = next((p for p in parts if p["kind"] == "head" and p["variant"] == kit.get("defaults", {}).get("head")), None)
    for pose in poses:
        for slot, k in (pose.get("legs") or {}).items():
            if slot not in LEG_SLOTS or int(k) not in (0, 1, 2):
                problems.append(f"pose {pose.get('pose_id')}: {slot} must be 0, 1 or 2")
        if head:
            problems += [f"pose {pose.get('pose_id')}: {x}" for x in clamp_head(pose, head.get("limits") or DEFAULT_HEAD_LIMITS)]
    if poses and kit.get("default_pose") not in {p.get("pose_id") for p in poses}:
        problems.append("the default pose is not in the allowed list")
    return problems


# --------------------------------------------------------------------------- composing a figure from a kit
def compose_plan(kit: dict[str, Any], variants: dict[str, str] | None = None, pose_id: str | None = None) -> dict[str, Any]:
    """Which mesh goes where for a committed kit, the chosen variants (defaults otherwise) and a pose (the kit's
    default otherwise): one entry per instance (the torso, the head, four legs, the tail), each with the 4x4 matrix
    (row-major, glTF frame) that takes the part's own coordinates to the figure, mirroring included for the right legs."""
    variants = {**kit["defaults"], **(variants or {})}
    by = {(p["kind"], p["variant"]): p for p in kit["parts"]}
    missing = [f"{k} {v}" for k, v in variants.items() if (k, v) not in by]
    if missing:
        raise ValueError(f"the kit has no {', '.join(missing)}")
    pid = pose_id or kit["default_pose"]
    pose = next((p for p in kit["poses"] if p["pose_id"] == pid), None)
    if pose is None:
        raise ValueError(f"pose {pid} is not in the kit's allowed list")
    torso = by[("torso", variants["torso"])]
    head = by[("head", variants["head"])]
    problems = clamp_head(pose, head.get("limits") or DEFAULT_HEAD_LIMITS)
    if problems:
        raise ValueError("; ".join(problems))
    entries = [{"slot": "torso", "kind": "torso", "variant": torso["variant"], "file": torso["mesh"]["file"],
                "matrix": np.eye(4).tolist(), "mirrored": False}]
    for slot in SLOTS:
        kind = SLOT_KIND[slot]
        part = by[(kind, variants[kind])]
        R, t = placement(Joint.of(part["joint"]), Joint.of(torso["attachments"][slot]), slot, pose)
        M = np.eye(4)
        M[:3, :3] = R @ (MIRROR if slot in MIRRORED else np.eye(3))
        M[:3, 3] = t
        entries.append({"slot": slot, "kind": kind, "variant": part["variant"], "file": part["mesh"]["file"],
                        "matrix": M.tolist(), "mirrored": slot in MIRRORED})
    return {"species": kit["species"], "breed_id": kit["breed_id"], "kit_version": kit["version"], "variants": variants,
            "pose_id": pid, "pose": pose, "parts": entries}
