"""Stage E: template wrap (BRIEF Section 6.5). The species base mesh is wrapped onto the Stage D shape so
every figurine keeps the base mesh's vertex order, edge loops and UVs.

1 morph  2 ICP rigid+scale  3 landmark pull (RBF-propagated, the Surface Deform coarse fit)
4 shrinkwrap (nearest surface point, 3 passes of rising strength)  5 group-weighted corrective smoothing that
protects the eyes and mouth  6 eye inserts and nose cap ride rigidly with the head (never wrapped)
7 validate (inverted faces, self-intersections, Laplacian smoothness <= 2x base median); retry with more
smoothing, then fall back to the morphed base without wrap.
"""
from pathlib import Path

import bpy  # noqa: I001
import numpy as np
from mathutils.bvhtree import BVHTree

from common import activate, get_coords, load_base, reset, set_coords

WRAP_SHELLS = (0, 1, 2, 3)  # body, ears, tail; eyes (4, 5) and nose (6) are inserts


def import_target(path: str):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in new:
        o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    tgt = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    tgt.name = "shape_target"
    return tgt


def umeyama(src: np.ndarray, dst: np.ndarray):
    """Similarity transform (s, R, t) minimising |s R src + t - dst|."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    cov = xd.T @ xs / len(src)
    u, d, vt = np.linalg.svd(cov)
    sign = np.eye(3)
    if np.linalg.det(u @ vt) < 0:
        sign[2, 2] = -1
    r = u @ sign @ vt
    s = np.trace(np.diag(d) @ sign) / xs.var(0).sum()
    return s, r, mu_d - s * r @ mu_s


def icp(src: np.ndarray, tgt: np.ndarray, iters: int = 15):
    from scipy.spatial import cKDTree

    tree = cKDTree(tgt)
    cur = src.copy()
    s_tot, r_tot, t_tot = 1.0, np.eye(3), np.zeros(3)
    for _ in range(iters):
        _, idx = tree.query(cur)
        s, r, t = umeyama(cur, tgt[idx])
        s = float(np.clip(s, 0.9, 1.1))
        cur = s * cur @ r.T + t
        s_tot, r_tot, t_tot = s * s_tot, r @ r_tot, s * r @ t_tot + t
    return s_tot, r_tot, t_tot


def adjacency(obj):
    ev = np.empty(len(obj.data.edges) * 2, dtype=np.int64)
    obj.data.edges.foreach_get("vertices", ev)
    return ev.reshape(-1, 2)


def laplacian(co: np.ndarray, ev: np.ndarray) -> np.ndarray:
    n = len(co)
    acc = np.zeros_like(co)
    deg = np.zeros(n)
    np.add.at(acc, ev[:, 0], co[ev[:, 1]])
    np.add.at(acc, ev[:, 1], co[ev[:, 0]])
    np.add.at(deg, ev.ravel(), 1)
    return acc / np.maximum(deg, 1)[:, None] - co


def smooth(co, ev, weight, iters, factor):
    out = co.copy()
    for _ in range(iters):
        out = out + laplacian(out, ev) * (factor * weight)[:, None]
    return out


def tri_normals(co, tris):
    n = np.cross(co[tris[:, 1]] - co[tris[:, 0]], co[tris[:, 2]] - co[tris[:, 0]])
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


def self_intersections(co, tris, mask) -> int:
    sub = tris[mask]
    bvh = BVHTree.FromPolygons([tuple(map(float, p)) for p in co], [tuple(map(int, t)) for t in sub], all_triangles=True)
    pairs = bvh.overlap(bvh)
    bad = 0
    for a, b in pairs:
        if a >= b:
            continue
        if set(sub[a]) & set(sub[b]):
            continue  # adjacent triangles touch by construction
        bad += 1
    return bad


def validate(base, morphed, wrapped, ev) -> tuple[bool, str, dict]:
    tris = base.tri_verts
    body_tri = np.isin(base.shell[tris[:, 0]], WRAP_SHELLS)
    n0, n1 = tri_normals(morphed, tris), tri_normals(wrapped, tris)
    inverted = int(((n0 * n1).sum(1) < -0.2)[body_tri].sum())
    lap0 = np.linalg.norm(laplacian(morphed, ev), axis=1)
    lap1 = np.linalg.norm(laplacian(wrapped, ev), axis=1)
    ratio = float(np.median(lap1) / max(np.median(lap0), 1e-9))
    inter = self_intersections(wrapped, tris, base.shell[tris[:, 0]] == 0)
    inter0 = self_intersections(morphed, tris, base.shell[tris[:, 0]] == 0)
    stats = {"inverted_faces": inverted, "laplacian_ratio": round(ratio, 3), "self_intersections": inter,
             "self_intersections_morphed": inter0}
    # The wrap must not make the mesh worse than the morphed template it started from.
    ok = inverted <= max(3, int(0.002 * body_tri.sum())) and ratio <= 2.0 and inter <= inter0 + 25
    return ok, f"inverted {inverted}, laplacian x{ratio:.2f}, self-intersections {inter}", stats


def wrap_once(job, base, obj, morphed, target, tgt_pts, ev, smoothing):
    from scipy.spatial import cKDTree

    wrap_mask = np.isin(base.shell, WRAP_SHELLS)
    # 2. ICP on the body region.
    body = morphed[base.shell == 0]
    pick = body[:: max(1, len(body) // 2500)]
    s, r, t = icp(pick, tgt_pts[:: max(1, len(tgt_pts) // 8000)])
    co = s * morphed @ r.T + t
    # 3. Landmark pull: nearest target point per landmark, RBF-propagated displacement.
    tree = cKDTree(tgt_pts)
    disp = np.zeros_like(co)
    wsum = np.zeros(len(co))
    for name, vi in base.landmarks.items():
        if base.shell[vi] not in WRAP_SHELLS:
            continue
        _, j = tree.query(co[vi])
        d = tgt_pts[j] - co[vi]
        if np.linalg.norm(d) > 12:
            continue
        w = np.exp(-np.sum((co - co[vi]) ** 2, axis=1) / (2 * 8.0 ** 2)) * (base.shell == base.shell[vi])
        disp += w[:, None] * d
        wsum += w
    co = co + disp / np.maximum(wsum, 1.0)[:, None] * wrap_mask[:, None]
    # 3b. Ears and tail are separate shells: rigid translation onto their counterpart first.
    for shell in (1, 2, 3):
        m = base.shell == shell
        for _ in range(3):
            _, j = tree.query(co[m])
            off = np.median(tgt_pts[j] - co[m], axis=0)
            co[m] += off
    # 4. Shrinkwrap passes with rising strength: projection along normals, both directions, limited.
    set_coords(obj, co)
    vg = obj.vertex_groups.get("wrap") or obj.vertex_groups.new(name="wrap")
    # Only the body shell is shrinkwrapped; ears and tail keep their morph shape and rigid fit (Section 14:
    # "ears and tail are protected by morph targets in the wrap").
    vg.add([int(i) for i in np.nonzero(base.shell == 0)[0]], 1.0, "REPLACE")
    for strength in (0.5, 0.8, 1.0):
        mod = obj.modifiers.new("shrink", "SHRINKWRAP")
        mod.target = target
        mod.wrap_method = "PROJECT"
        mod.use_negative_direction = True
        mod.use_positive_direction = True
        mod.cull_face = "OFF"
        mod.project_limit = 3.0
        mod.vertex_group = "wrap"
        activate(obj)
        before = get_coords(obj)
        bpy.ops.object.modifier_apply(modifier=mod.name)
        after = get_coords(obj)
        set_coords(obj, before + (after - before) * strength)
    co = get_coords(obj)
    # 5. Corrective smoothing, protecting eye and mouth loops (face mask) and the base.
    protect = np.clip(base.mask("face_mask") * 0.8 + base.group("base"), 0, 1)
    weight = wrap_mask * (1 - protect)
    co = smooth(co, ev, weight, smoothing, 0.35)
    # 6. Inserts ride rigidly with nearby head vertices.
    for shell in (4, 5, 6):
        m = base.shell == shell
        centre = morphed[m].mean(0)
        near = (base.shell == 0) & (np.linalg.norm(morphed - centre, axis=1) < 9.0)
        if near.any():
            delta = (co[near] - (s * morphed[near] @ r.T + t)).mean(0)
            co[m] = s * morphed[m] @ r.T + t + delta
        else:
            co[m] = s * morphed[m] @ r.T + t
    return co


def main(job: dict) -> dict:
    from backend.core.meshkit import load_base as np_base, write_obj

    reset()
    base = np_base(job["species"])
    morphed = base.morph(job["weights"])
    obj = load_base(job["species"])
    set_coords(obj, morphed)
    target = import_target(job["shape_glb"])
    tgt_pts = get_coords(target) @ np.array(target.matrix_world)[:3, :3].T + np.array(target.matrix_world)[:3, 3]
    ev = adjacency(obj)
    attempts, notes, stats = 0, "", {}
    wrapped, valid, fallback = morphed, False, "unwrapped"
    for smoothing in (2, 6):
        attempts += 1
        if job.get("fail"):
            notes = "fault injection"
            continue
        co = wrap_once(job, base, obj, morphed, target, tgt_pts, ev, smoothing)
        valid, notes, stats = validate(base, morphed, co, ev)
        if valid:
            wrapped, fallback = co, "none"
            break
    out = Path(job["out_dir"])
    np.save(out / "wrapped.npy", wrapped.astype(np.float32))
    write_obj(out / "figure_wrapped.obj", base, wrapped)
    return {"valid": bool(valid), "fallback": fallback, "attempts": attempts, "notes": notes, **stats,
            "coords": str(out / "wrapped.npy"), "obj": str(out / "figure_wrapped.obj")}
