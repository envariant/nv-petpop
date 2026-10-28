"""Build a proxy base mesh for one species in bpy (BRIEF Section 13, "Proxy base meshes").

Run under the bpy interpreter:  python proxy_base_bpy.py <species> <out_dir>

Primitives (head, body, legs, haunches, muzzle) are unioned by voxel remesh, QuadriFlow-remeshed,
mirrored for exact symmetry, then joined with the separate shells (ears, tail, eye inserts, nose cap).
Writes base.blend, base.glb (morph targets), base_raw.npz (for the numpy side) and landmarks.json.
Units are millimetres; front faces -Y, up is +Z, origin at the base centre, 90 mm tall.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy  # noqa: I001  (bpy must be imported before bmesh/mathutils)
import bmesh
import numpy as np
from mathutils import Matrix, Vector

SPECIES = sys.argv[-2]
OUT = Path(sys.argv[-1])
OUT.mkdir(parents=True, exist_ok=True)

MORPHS = {
    "dog": ["head_scale", "muzzle_len", "muzzle_width", "brachy", "ear_erect", "ear_drop", "ear_fold", "ear_size",
            "tail_len", "tail_curl", "tail_plume", "body_stocky", "body_slim", "leg_len", "fluff"],
    "cat": ["head_scale", "muzzle_len", "muzzle_width", "ear_erect", "ear_fold", "ear_size", "ear_tuft",
            "tail_len", "tail_plume", "body_stocky", "body_slim", "fluff"],
}[SPECIES]

GROUPS = ["head", "muzzle", "ear_L", "ear_R", "body", "leg_FL", "leg_FR", "leg_BL", "leg_BR", "tail", "base",
          "eye_L", "eye_R", "nose"]
SHELLS = ["body", "ear_L", "ear_R", "tail", "eye_L", "eye_R", "nose"]

# Part layout in mm before height normalisation. (centre, radii) ellipsoids.
if SPECIES == "dog":
    HEAD = ((0, -2, 60), (23, 21, 21))
    MUZZLE = ((0, -20, 53), (8.5, 9, 6.5))
    BODY = ((0, 3, 24), (15, 17, 22))
    FRONT_LEG = ((7.5, -11, 13), (4.6, 4.6, 13.5))
    HAUNCH = ((11, 7, 9), (8, 11, 8.5))
    HIND_PAW = ((12, -5, 2.5), (4.5, 6.5, 2.8))
    EAR = dict(base=(12, -1, 74), radii=(6.5, 2.4, 11), tilt=35.0)
    TAIL = dict(root=(0, 15, 7), radii=(3.2, 3.2, 12), pitch=-55.0)
    EYE = ((9, -19.5, 63), 4.3)
    NOSE = ((0, -28.3, 55.5), 2.9)
else:
    HEAD = ((0, -1, 58), (22, 19, 19))
    MUZZLE = ((0, -16.5, 52), (7.5, 6.5, 5.5))
    BODY = ((0, 3, 23), (14, 16, 21))
    FRONT_LEG = ((6.5, -10, 13), (4.0, 4.0, 13.5))
    HAUNCH = ((10.5, 7, 9), (7.5, 10.5, 8.5))
    HIND_PAW = ((11, -5, 2.5), (4.0, 6.0, 2.6))
    EAR = dict(base=(11.5, 0, 71), radii=(6.0, 2.0, 9.5), tilt=18.0)
    TAIL = dict(root=(0, 14, 6), radii=(2.6, 2.6, 16), pitch=-80.0)
    EYE = ((8.5, -16.8, 61), 4.4)
    NOSE = ((0, -22.6, 54.5), 2.2)


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def activate(obj) -> None:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def quad_sphere(name: str, centre, radii, cuts: int = 6, rot=None):
    """All-quad sphere: subdivided cube cast to a sphere, scaled to an ellipsoid."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    for v in bm.verts:
        v.co = v.co.normalized()
    for v in bm.verts:
        v.co = Vector((v.co.x * radii[0], v.co.y * radii[1], v.co.z * radii[2]))
    if rot is not None:
        bmesh.ops.transform(bm, matrix=rot, verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=Vector(centre), verts=bm.verts[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def mirror_x(c):
    return (-c[0], c[1], c[2])


def apply_modifier(obj, mod) -> None:
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=mod.name)


def build_body_shell():
    parts = [
        quad_sphere("head", *HEAD, cuts=10),
        quad_sphere("muzzle", *MUZZLE, cuts=6),
        quad_sphere("torso", *BODY, cuts=10),
    ]
    for side in (1, -1):
        for (c, r) in (FRONT_LEG, HAUNCH, HIND_PAW):
            cc = (c[0] * side, c[1], c[2])
            parts.append(quad_sphere("part", cc, r, cuts=6))
    # Neck bridge so head and torso fuse into one smooth shell.
    parts.append(quad_sphere("neck", (0, -2, 42), (11, 11, 10), cuts=6))
    for p in parts:
        p.select_set(True)
    activate(parts[0])
    for p in parts:
        p.select_set(True)
    bpy.ops.object.join()
    shell = bpy.context.view_layer.objects.active
    shell.name = "body"
    # Sink slightly so the bisect below gives a flat sitting base.
    for v in shell.data.vertices:
        v.co.z -= 1.2
    mod = shell.modifiers.new("vox", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = 1.1
    apply_modifier(shell, mod)
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0),
                                 plane_no=(0, 0, -1), clear_outer=True)
    edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    bm.to_mesh(shell.data)
    bm.free()
    activate(shell)
    target = 3000  # per half after mirroring: ~6k quads total
    try:
        bpy.ops.object.quadriflow_remesh(target_faces=target * 2, seed=7, use_mesh_symmetry=False,
                                         use_preserve_sharp=True, use_preserve_boundary=False)
    except Exception as exc:  # pragma: no cover - QuadriFlow is best-effort
        print("QuadriFlow failed, keeping voxel quads:", exc)
    # Exact X symmetry: keep +X half, mirror.
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0),
                           plane_no=(-1, 0, 0), clear_outer=True)
    for v in bm.verts:
        if abs(v.co.x) < 1e-4:
            v.co.x = 0.0
    # Flatten the base: everything below 0.4 mm snaps to z = 0.
    for v in bm.verts:
        if v.co.z < 0.4:
            v.co.z = 0.0
    bm.to_mesh(shell.data)
    bm.free()
    mm = shell.modifiers.new("mirror", "MIRROR")
    mm.use_axis[0] = True
    mm.use_clip = True
    mm.use_mirror_merge = True
    mm.merge_threshold = 1e-3
    apply_modifier(shell, mm)
    return shell


def build_ear(side: int):
    bx, by, bz = EAR["base"]
    rx, ry, rz = EAR["radii"]
    tilt = math.radians(EAR["tilt"]) * side
    rot = Matrix.Rotation(tilt, 3, "Y")
    centre = Vector((0, 0, rz * 0.85))
    obj = quad_sphere("ear", (0, 0, 0), (rx, ry, rz), cuts=5)
    for v in obj.data.vertices:
        co = v.co + centre
        # Taper towards the tip: triangular ear.
        t = max(0.0, min(1.0, co.z / (2 * rz)))
        co.x *= (1.0 - 0.75 * t) if SPECIES == "cat" else (1.0 - 0.45 * t)
        v.co = rot @ co + Vector((bx * side, by, bz))
    obj.name = "ear_L" if side > 0 else "ear_R"
    return obj


def build_tail():
    root = Vector(TAIL["root"])
    rx, ry, rz = TAIL["radii"]
    obj = quad_sphere("tail", (0, 0, 0), (rx, ry, rz), cuts=8)
    rot = Matrix.Rotation(math.radians(TAIL["pitch"]), 3, "X")
    for v in obj.data.vertices:
        co = v.co + Vector((0, 0, rz * 0.75))  # root end sunk into the body so the print fuses
        v.co = rot @ co + root
    obj.name = "tail"
    return obj


def build_shells():
    shells = {"body": build_body_shell()}
    shells["ear_L"] = build_ear(1)
    shells["ear_R"] = build_ear(-1)
    shells["tail"] = build_tail()
    (ec, er) = EYE
    shells["eye_L"] = quad_sphere("eye_L", ec, (er, er, er), cuts=4)
    shells["eye_R"] = quad_sphere("eye_R", mirror_x(ec), (er, er, er), cuts=4)
    (nc, nr) = NOSE
    shells["nose"] = quad_sphere("nose", nc, (nr * 1.25, nr, nr * 0.9), cuts=3)
    return shells


def ellipsoid_dist(co, centre, radii):
    d = Vector(((co[0] - centre[0]) / radii[0], (co[1] - centre[1]) / radii[1], (co[2] - centre[2]) / radii[2]))
    return d.length


def join_shells(shells):
    """Join shells into one object; return it plus per-vertex shell index."""
    counts = []
    order = []
    for name in SHELLS:
        o = shells[name]
        counts.append(len(o.data.vertices))
        order.append(o)
    for i, o in enumerate(order):
        mat_name = {"eye_L": "eye", "eye_R": "eye", "nose": "nose"}.get(SHELLS[i], "coat")
        mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
        o.data.materials.append(mat)
    activate(order[0])
    for o in order:
        o.select_set(True)
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = f"petpop_base_{SPECIES}"
    obj.data.name = obj.name
    shell_idx = np.concatenate([np.full(c, i) for i, c in enumerate(counts)])
    return obj, shell_idx


def compute_groups(obj, shell_idx):
    co = np.array([v.co[:] for v in obj.data.vertices])
    n = len(co)
    w = {g: np.zeros(n) for g in GROUPS}
    body = shell_idx == 0
    # Region scores on the body shell from the part ellipsoids (smaller = closer).
    scores = {}
    scores["head"] = np.array([ellipsoid_dist(c, *HEAD) for c in co])
    scores["muzzle"] = np.array([ellipsoid_dist(c, *MUZZLE) for c in co]) * 0.92
    scores["body"] = np.array([ellipsoid_dist(c, *BODY) for c in co]) * 1.05
    neck = np.array([ellipsoid_dist(c, (0, -2, 42), (11, 11, 10)) for c in co])
    scores["body"] = np.minimum(scores["body"], neck * 1.2)
    for name, part, side in (("leg_FL", FRONT_LEG, 1), ("leg_FR", FRONT_LEG, -1)):
        c = (part[0][0] * side, part[0][1], part[0][2])
        scores[name] = np.array([ellipsoid_dist(p, c, part[1]) for p in co]) * 0.9
    for name, side in (("leg_BL", 1), ("leg_BR", -1)):
        c1 = (HAUNCH[0][0] * side, HAUNCH[0][1], HAUNCH[0][2])
        c2 = (HIND_PAW[0][0] * side, HIND_PAW[0][1], HIND_PAW[0][2])
        scores[name] = np.minimum(np.array([ellipsoid_dist(p, c1, HAUNCH[1]) for p in co]),
                                  np.array([ellipsoid_dist(p, c2, HIND_PAW[1]) for p in co]) * 0.9)
    names = list(scores)
    stack = np.stack([scores[k] for k in names])
    best = np.argmin(stack, axis=0)
    for i, k in enumerate(names):
        w[k] = ((best == i) & body).astype(float)
    shell_names = {1: "ear_L", 2: "ear_R", 3: "tail", 4: "eye_L", 5: "eye_R", 6: "nose"}
    for si, g in shell_names.items():
        w[g] = (shell_idx == si).astype(float)
    # Eyes and nose ride with the head; nose also with the muzzle.
    w["head"] = np.maximum(w["head"], ((shell_idx == 4) | (shell_idx == 5)).astype(float))
    w["muzzle"] = np.maximum(w["muzzle"], w["nose"])
    w["base"] = ((co[:, 2] < 1.5) & body).astype(float)
    # Feather three edge loops at every boundary (body shell only).
    adj = [[] for _ in range(n)]
    for e in obj.data.edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)
    feather = ["head", "muzzle", "body", "leg_FL", "leg_FR", "leg_BL", "leg_BR"]
    for _ in range(3):
        for g in feather:
            src = w[g]
            new = src.copy()
            for i in np.nonzero(body)[0]:
                nb = adj[i]
                if nb:
                    new[i] = 0.5 * src[i] + 0.5 * np.mean(src[nb])
            w[g] = new
    return co, w


def smooth_weights(obj, w, shell_idx, iters):
    """Wider feathering for shape-key deformation so region seams never tear."""
    ev = np.array([e.vertices[:] for e in obj.data.edges])
    n = len(shell_idx)
    deg = np.bincount(ev.ravel(), minlength=n).astype(float)
    body = shell_idx == 0
    out = dict(w)
    for g in ("head", "muzzle", "body", "leg_FL", "leg_FR", "leg_BL", "leg_BR"):
        v = w[g].copy()
        for _ in range(iters):
            acc = np.zeros(n)
            np.add.at(acc, ev[:, 0], v[ev[:, 1]])
            np.add.at(acc, ev[:, 1], v[ev[:, 0]])
            nv = 0.5 * v + 0.5 * acc / np.maximum(deg, 1)
            v = np.where(body, nv, v)
        out[g] = v
    return out


def landmarks(co, w, shell_idx):
    def argbest(mask, key):
        idx = np.nonzero(mask)[0]
        return int(idx[np.argmax(key[idx])])

    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    body = shell_idx == 0
    lm = {
        "nose_tip": argbest(shell_idx == 6, -y),
        "eye_L": argbest(shell_idx == 4, -y),
        "eye_R": argbest(shell_idx == 5, -y),
        "ear_tip_L": argbest(shell_idx == 1, z),
        "ear_tip_R": argbest(shell_idx == 2, z),
        "ear_base_L": argbest(shell_idx == 1, -z),
        "ear_base_R": argbest(shell_idx == 2, -z),
        "chin": argbest(body & (w["muzzle"] > 0.3), -z - 0.2 * np.abs(x)),
        "back_of_head": argbest(body & (w["head"] > 0.5), y - 0.2 * np.abs(x)),
        "tail_tip": argbest(shell_idx == 3, -np.linalg.norm(co - np.array(TAIL["root"]), axis=1) * -1),
        "paw_FL": argbest(body & (w["leg_FL"] > 0.5), -y - 2 * z),
        "paw_FR": argbest(body & (w["leg_FR"] > 0.5), -y - 2 * z),
        "base_centre": argbest(body & (z < 0.5), -np.abs(x) - np.abs(y - 3)),
        "neck_front": argbest(body & (np.abs(x) < 3) & (z > 30) & (z < 48), -y),
    }
    return lm


def morph_offsets(co, w, shell_idx, lm):
    """Return {morph: (n,3) target positions}."""
    n = len(co)
    out = {}
    head_c = np.array(HEAD[0])
    muz_c = np.array(MUZZLE[0])

    def blend(target, weight):
        return co + (target - co) * weight[:, None]

    out["head_scale"] = blend(head_c + (co - head_c) * 1.18, w["head"] + w["muzzle"] * 0.6
                              + 0.0 * w["eye_L"])
    # Ears are separate shells: move them with the head so they stay attached.
    ear_w = w["ear_L"] + w["ear_R"]
    out["head_scale"] = out["head_scale"] + ((co - head_c) * 0.18) * ear_w[:, None]
    hf = HEAD[0][1] - HEAD[1][1] * 0.85  # head front surface (y)
    front = np.clip((hf - co[:, 1]) / 2.0, 0, 1)  # only what sticks out of the head moves
    ml = co.copy()
    ml[:, 1] = hf + (co[:, 1] - hf) * 1.9
    out["muzzle_len"] = blend(ml, w["muzzle"] * front)
    mw = co.copy()
    mw[:, 0] = co[:, 0] * 1.35
    mw[:, 2] = muz_c[2] + (co[:, 2] - muz_c[2]) * 1.1
    out["muzzle_width"] = blend(mw, w["muzzle"])
    if "brachy" in MORPHS:
        br = co.copy()
        br[:, 1] = hf + (co[:, 1] - hf) * 0.35
        br[:, 0] = co[:, 0] * 1.15
        out["brachy"] = blend(br, w["muzzle"] * front)

    def ear_rot(axis: str, deg: float, side: int, scale: float = 1.0):
        sid = 1 if side > 0 else 2
        mask = (shell_idx == sid).astype(float)
        base = co[lm["ear_base_L" if side > 0 else "ear_base_R"]]
        a = math.radians(deg)
        if axis == "Y":
            r = np.array(Matrix.Rotation(a * side, 3, "Y"))
        else:
            r = np.array(Matrix.Rotation(a, 3, "X"))
        tgt = (co - base) @ r.T * scale + base
        return tgt, mask

    def ears(axis, deg, scale=1.0):
        res = co.copy()
        for side in (1, -1):
            tgt, mask = ear_rot(axis, deg, side, scale)
            res = res + (tgt - co) * mask[:, None]
        return res

    out["ear_erect"] = ears("Y", -EAR["tilt"] * 0.9)
    if "ear_drop" in MORPHS:
        out["ear_drop"] = ears("Y", 115.0)
    out["ear_fold"] = ears("X", 62.0 if SPECIES == "dog" else 55.0, 0.8)
    out["ear_size"] = ears("Y", 0.0, 1.45)
    if "ear_tuft" in MORPHS:
        res = co.copy()
        for side, sid in ((1, 1), (-1, 2)):
            tip = co[lm["ear_tip_L" if side > 0 else "ear_tip_R"]]
            d = np.linalg.norm(co - tip, axis=1)
            m = (shell_idx == sid) * np.clip(1 - d / 6.0, 0, 1)
            res[:, 2] += 5.0 * m
        out["ear_tuft"] = res
    root = np.array(TAIL["root"])
    tail_w = (shell_idx == 3).astype(float)
    dist = np.linalg.norm(co - root, axis=1)
    tl = root + (co - root) * 1.6
    out["tail_len"] = blend(tl, tail_w)
    if "tail_curl" in MORPHS:
        tc = co.copy()
        maxd = dist[shell_idx == 3].max()
        for i in np.nonzero(shell_idx == 3)[0]:
            t = dist[i] / maxd
            r = np.array(Matrix.Rotation(math.radians(150.0 * t), 3, "X"))
            tc[i] = (co[i] - root) @ r.T + root
        out["tail_curl"] = tc
    tp = co.copy()
    tip = co[lm["tail_tip"]]
    axis = (tip - root) / np.linalg.norm(tip - root)
    rel = co - root
    along = (rel @ axis)[:, None] * axis
    radial = rel - along
    tp = root + along + radial * 1.9
    out["tail_plume"] = blend(tp, tail_w)
    body_w = w["body"] + w["leg_BL"] * 0.6 + w["leg_BR"] * 0.6
    bs = co.copy()
    bs[:, 0] *= 1.2
    bs[:, 1] = BODY[0][1] + (co[:, 1] - BODY[0][1]) * 1.12
    out["body_stocky"] = blend(bs, body_w)
    sl = co.copy()
    sl[:, 0] *= 0.82
    sl[:, 1] = BODY[0][1] + (co[:, 1] - BODY[0][1]) * 0.9
    out["body_slim"] = blend(sl, body_w)
    if "leg_len" in MORPHS:
        # Continuous vertical stretch of everything up to the top of the front legs (no folds).
        leg_top = FRONT_LEG[0][2] + FRONT_LEG[1][2]
        ll = co.copy()
        ll[:, 2] = co[:, 2] + 0.3 * np.minimum(co[:, 2], leg_top)
        out["leg_len"] = ll
    # fluff: push coat shells outwards along vertex normals.
    return out


def vertex_normals(obj):
    obj.data.update()
    return np.array([v.normal[:] for v in obj.data.vertices])


def masks(co, w, shell_idx):
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    body = shell_idx == 0
    s = lambda v, a, b: np.clip((v - a) / (b - a), 0, 1)  # noqa: E731
    head_z = HEAD[0][2]
    chest = body * s(-y, 4, 10) * s(z, 6, 14) * (1 - s(z, head_z - 12, head_z - 6)) * (1 - s(np.abs(x), 7, 11))
    chest = np.maximum(chest, body * w["muzzle"] * s(-z, -MUZZLE[0][2] + 1, -MUZZLE[0][2] + 4))
    socks = body * (w["leg_FL"] + w["leg_FR"] + w["leg_BL"] + w["leg_BR"]) * (1 - s(z, 6, 10))
    blaze = body * (1 - s(np.abs(x), 2.5, 4.5)) * s(-y, 6, 12) * s(z, MUZZLE[0][2] - 2, MUZZLE[0][2] + 2)
    points = np.clip(w["ear_L"] + w["ear_R"] + w["tail"] + w["muzzle"] * body + socks, 0, 1)
    saddle = body * w["body"] * s(y, 0, 6) * s(z, 14, 22)
    face_mask = body * np.clip(w["muzzle"] + w["head"] * s(-y, 12, 18) * (1 - s(z, 70, 74)), 0, 1)
    coat = (shell_idx <= 3).astype(float)
    eye = ((shell_idx == 4) | (shell_idx == 5)).astype(float)
    nose = (shell_idx == 6).astype(float)
    return {"chest": chest, "socks": socks, "blaze": blaze, "points": points,
            "saddle": saddle, "face_mask": face_mask, "coat": coat, "eye": eye, "nose": nose}


def main() -> None:
    reset()
    shells = build_shells()
    obj, shell_idx = join_shells(shells)
    # Normalise height to 90 mm with the base at z = 0.
    co = np.array([v.co[:] for v in obj.data.vertices])
    zmin, zmax = co[:, 2].min(), co[:, 2].max()
    scale = 90.0 / (zmax - zmin)
    global HEAD, MUZZLE, BODY, FRONT_LEG, HAUNCH, HIND_PAW, TAIL, EYE, NOSE
    for v in obj.data.vertices:
        v.co = Vector((v.co.x * scale, v.co.y * scale, (v.co.z - zmin) * scale))

    def sc(part):
        return (tuple(c * scale if i != 2 else (c - zmin) * scale for i, c in enumerate(part[0])),
                tuple(r * scale for r in part[1]))

    HEAD, MUZZLE, BODY, FRONT_LEG, HAUNCH, HIND_PAW = map(sc, (HEAD, MUZZLE, BODY, FRONT_LEG, HAUNCH, HIND_PAW))
    TAIL = dict(TAIL, root=tuple(c * scale if i != 2 else (c - zmin) * scale for i, c in enumerate(TAIL["root"])))
    EAR["base"] = tuple(c * scale if i != 2 else (c - zmin) * scale for i, c in enumerate(EAR["base"]))

    co, w = compute_groups(obj, shell_idx)
    for g in GROUPS:
        vg = obj.vertex_groups.new(name=g)
        for i in np.nonzero(w[g] > 1e-4)[0]:
            vg.add([int(i)], float(w[g][i]), "REPLACE")
    lm = landmarks(co, w, shell_idx)
    normals = vertex_normals(obj)
    targets = morph_offsets(co, smooth_weights(obj, w, shell_idx, 14), shell_idx, lm)
    fluff_w = np.clip((shell_idx <= 3).astype(float) - w["base"], 0, 1)
    # Smoothed normals so neighbouring offsets never cross in creases (neck, leg roots).
    ev = np.array([e.vertices[:] for e in obj.data.edges])
    sn = normals.copy()
    for _ in range(12):
        acc = sn.copy()
        np.add.at(acc, ev[:, 0], sn[ev[:, 1]])
        np.add.at(acc, ev[:, 1], sn[ev[:, 0]])
        sn = acc / (np.linalg.norm(acc, axis=1, keepdims=True) + 1e-12)
    targets["fluff"] = co + sn * 1.8 * fluff_w[:, None]
    obj.shape_key_add(name="Basis", from_mix=False)
    for name in MORPHS:
        kb = obj.shape_key_add(name=name, from_mix=False)
        kb.slider_min = -1.0
        kb.slider_max = 1.0
        tgt = targets[name]
        for i, p in enumerate(tgt):
            kb.data[i].co = Vector(p)

    # UVs: Smart UV project, 8 px margin at 2048.
    activate(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=8 / 2048, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.data.uv_layers[0].name = "UVMap"

    # Landmark empties parented to the mesh (vertex parent keeps them on the surface).
    for name, vi in lm.items():
        e = bpy.data.objects.new(f"LM_{name}", None)
        e.empty_display_size = 2.0
        bpy.context.scene.collection.objects.link(e)
        e.location = obj.data.vertices[vi].co
        e.parent = obj
        e["vertex_index"] = vi

    m = masks(co, w, shell_idx)
    # Raw dump for the numpy side.
    me = obj.data
    me.calc_loop_triangles()
    loops_v = np.array([lp.vertex_index for lp in me.loops])
    uv = np.array([d.uv[:] for d in me.uv_layers[0].data])
    poly_start = np.array([p.loop_start for p in me.polygons])
    poly_total = np.array([p.loop_total for p in me.polygons])
    poly_mat = np.array([p.material_index for p in me.polygons])
    tri_loops = np.array([t.loops[:] for t in me.loop_triangles])
    tri_verts = np.array([t.vertices[:] for t in me.loop_triangles])
    tri_poly = np.array([t.polygon_index for t in me.loop_triangles])
    np.savez_compressed(
        OUT / "base_raw.npz",
        species=SPECIES,
        co=co.astype(np.float32),
        loops_v=loops_v.astype(np.int32),
        uv=uv.astype(np.float32),
        poly_start=poly_start.astype(np.int32),
        poly_total=poly_total.astype(np.int32),
        poly_mat=poly_mat.astype(np.int8),
        tri_loops=tri_loops.astype(np.int32),
        tri_verts=tri_verts.astype(np.int32),
        tri_poly=tri_poly.astype(np.int32),
        shell=shell_idx.astype(np.int8),
        group_names=np.array(GROUPS),
        groups=np.stack([w[g] for g in GROUPS]).astype(np.float32),
        morph_names=np.array(MORPHS),
        morph_deltas=np.stack([targets[k] - co for k in MORPHS]).astype(np.float32),
        mask_names=np.array(list(m)),
        masks=np.stack(list(m.values())).astype(np.float32),
        materials=np.array([mt.name for mt in me.materials]),
    )
    (OUT / "landmarks.json").write_text(json.dumps(
        {"species": SPECIES, "landmarks": {k: {"vertex": v, "co": [round(c, 4) for c in co[v]]}
                                            for k, v in lm.items()}}, indent=1) + "\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "base.blend"), compress=True)
    activate(obj)
    bpy.ops.export_scene.gltf(filepath=str(OUT / "base.glb"), use_selection=True, export_morph=True,
                              export_morph_normal=False, export_apply=False, export_yup=True,
                              export_extras=False, export_materials="EXPORT")
    print("PROXY_OK", SPECIES, len(me.vertices), len(me.polygons))


main()
