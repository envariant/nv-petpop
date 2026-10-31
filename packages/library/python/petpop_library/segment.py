"""Stage E segmentation (BRIEF Section 6.5, decision 116): label a generated mesh to the species schema without
moving any of its vertices.

1. Fit the morphed template to the generated mesh: similarity ICP on the body, a landmark pull propagated by RBF
   within each shell, a rigid fit of ears and tail, then a partial nearest-point projection. The fit is only a
   measuring tool.
2. Transfer the schema by nearest surface point: the fitted template's surface is sampled densely, each sample
   carrying its interpolated part weights and pattern-region values, and every vertex of the generated mesh takes
   the values of its nearest sample.
3. Clean the labels on the generated mesh (each part keeps its largest connected piece, strays join the
   neighbouring part), feather the part weights over the mesh, and place the landmarks on the nearest vertex
   inside the parts the schema allows.
4. Validate: every part present, left parts on the pet's left (+X), landmarks inside their parts.
"""
from __future__ import annotations

import numpy as np

from .figure import schema
from .meshkit import BaseMesh

WRAP_SHELLS = (0, 1, 2, 3)  # body, ears, tail; eye inserts and nose cap ride with the head


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


def fit_template(base: BaseMesh, morphed: np.ndarray, co: np.ndarray, strength: float = 0.7) -> np.ndarray:
    """The morphed template moved onto the generated mesh (vertex positions only)."""
    from scipy.spatial import cKDTree

    tgt = co[:: max(1, len(co) // 60000)]
    tree = cKDTree(tgt)
    body = morphed[base.shell == 0]
    s, r, t = icp(body[:: max(1, len(body) // 2500)], tgt[:: max(1, len(tgt) // 8000)])
    fit = s * morphed @ r.T + t
    disp, wsum = np.zeros_like(fit), np.zeros(len(fit))
    for vi in base.landmarks.values():
        if base.shell[vi] not in WRAP_SHELLS:
            continue
        _, j = tree.query(fit[vi])
        d = tgt[j] - fit[vi]
        if np.linalg.norm(d) > 12:
            continue
        w = np.exp(-np.sum((fit - fit[vi]) ** 2, axis=1) / (2 * 8.0 ** 2)) * (base.shell == base.shell[vi])
        disp += w[:, None] * d
        wsum += w
    fit = fit + disp / np.maximum(wsum, 1.0)[:, None] * np.isin(base.shell, WRAP_SHELLS)[:, None]
    for shell in (1, 2, 3):  # ears and tail: rigid translation onto their counterpart
        m = base.shell == shell
        for _ in range(3):
            _, j = tree.query(fit[m])
            fit[m] += np.median(tgt[j] - fit[m], axis=0)
    head = base.shell == 0
    before = fit.copy()
    _, j = tree.query(fit)
    fit = fit + (tgt[j] - fit) * np.where(np.isin(base.shell, WRAP_SHELLS), strength, 0.0)[:, None]
    for shell in (4, 5, 6):  # inserts follow the head vertices around them
        m = base.shell == shell
        if not m.any():
            continue
        centre = before[m].mean(0)
        near = head & (np.linalg.norm(before - centre, axis=1) < 9.0)
        if near.any():
            fit[m] += (fit[near] - before[near]).mean(0)
    return fit


def _surface_samples(base: BaseMesh, co: np.ndarray, per_tri: int = 10, seed: int = 0):
    """Points on the template surface with the barycentric weights of their triangle's corners."""
    rng = np.random.default_rng(seed)
    t = base.tri_verts
    r1, r2 = rng.random((len(t), per_tri)), rng.random((len(t), per_tri))
    flip = r1 + r2 > 1
    r1, r2 = np.where(flip, 1 - r1, r1), np.where(flip, 1 - r2, r2)
    bary = np.stack([1 - r1 - r2, r1, r2], axis=-1)  # (t, k, 3)
    bary = np.concatenate([bary, np.full((len(t), 1, 3), 1 / 3)], axis=1)  # plus each centroid
    pts = np.einsum("tkc,tcd->tkd", bary, co[t])
    return pts.reshape(-1, 3), np.repeat(np.arange(len(t)), bary.shape[1]), bary.reshape(-1, 3)


def _adjacency(n: int, tris: np.ndarray):
    import scipy.sparse as sp

    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    a = sp.coo_matrix((np.ones(len(e) * 2), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    a.data[:] = 1.0
    return a


def _clean_labels(labels: np.ndarray, adj, n_parts: int, rounds: int = 4) -> tuple[np.ndarray, float]:
    """Each part keeps its largest connected piece; vertices of smaller pieces take their neighbours' part.
    Returns the labels and the fraction of vertices that were relabelled."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components

    out = labels.copy()
    moved = np.zeros(len(labels), bool)
    for _ in range(rounds):
        stray = np.zeros(len(out), bool)
        for p in range(n_parts):
            idx = np.nonzero(out == p)[0]
            if len(idx) == 0:
                continue
            sub = adj[idx][:, idx]
            k, comp = connected_components(sub, directed=False)
            if k > 1:
                keep = np.argmax(np.bincount(comp))
                stray[idx[comp != keep]] = True
        if not stray.any():
            break
        onehot = sp.csr_matrix((np.ones((~stray).sum()), (np.nonzero(~stray)[0], out[~stray])), shape=(len(out), n_parts))
        votes = (adj @ onehot).toarray()
        has = votes.sum(1) > 0
        upd = stray & has
        out[upd] = np.argmax(votes[upd], axis=1)
        moved |= upd
    return out, float(moved.mean())


def _feather(labels: np.ndarray, adj, n_parts: int, iters: int = 3) -> np.ndarray:
    """(g, n) part weights: one-hot labels averaged over the mesh's neighbourhoods, so boundaries are soft."""
    w = np.zeros((len(labels), n_parts), np.float64)
    w[np.arange(len(labels)), labels] = 1.0
    deg = np.asarray(adj.sum(1)).ravel() + 1.0
    for _ in range(iters):
        w = (adj @ w + w) / deg[:, None]
    rows = np.arange(len(labels))
    w[rows, labels] = np.maximum(w[rows, labels], w.max(axis=1) + 1e-3)  # a vertex's own part stays its strongest
    return np.clip(w, 0, 1).T.astype(np.float32)


def segment(base: BaseMesh, morphed: np.ndarray, co: np.ndarray, tris: np.ndarray) -> dict:
    """Part weights, pattern-region values and landmarks for the generated mesh (co, tris), from the template."""
    from scipy.spatial import cKDTree

    sch = schema(base.species)
    names = base.group_names
    fit = fit_template(base, morphed, co)
    pts, tri_id, bary = _surface_samples(base, fit)
    corners = base.tri_verts[tri_id]  # (k, 3)
    _, nearest = cKDTree(pts).query(co)
    c, b = corners[nearest], bary[nearest]
    groups = np.einsum("kc,gkc->gk", b, base.groups[:, c])
    masks = np.einsum("kc,mkc->mk", b, base.masks[:, c])
    # Template parts overlap (an eye insert is also in `head`): the insert parts win where they are dominant.
    inserts = [names.index(p["name"]) for p in sch["parts"] if p["shell"] in ("eye_L", "eye_R", "nose")]
    ranked = groups.copy()
    ranked[inserts] += 0.5 * (groups[inserts] >= 0.5)
    adj = _adjacency(len(co), tris)
    labels, relabelled = _clean_labels(np.argmax(ranked, axis=0), adj, len(names))
    weights = _feather(labels, adj, len(names))
    landmarks, notes = {}, []
    tree_all = cKDTree(co)
    for lm, vi in base.landmarks.items():
        allowed = [names.index(p) for p in sch["landmarks"][lm]]
        inside = np.nonzero(np.isin(labels, allowed))[0]
        if len(inside):
            _, j = cKDTree(co[inside]).query(fit[vi])
            landmarks[lm] = int(inside[j])
        else:
            landmarks[lm] = int(tree_all.query(fit[vi])[1])
            notes.append(f"{lm} outside {'/'.join(sch['landmarks'][lm])}")
    counts = {n: int((labels == i).sum()) for i, n in enumerate(names)}
    missing = [n for n, k in counts.items() if k == 0]
    sides = []
    for left in [p["name"] for p in sch["parts"] if p["side"] == "L"]:
        right = left[:-1] + "R"
        if counts.get(left) and counts.get(right):
            if co[labels == names.index(left), 0].mean() <= co[labels == names.index(right), 0].mean():
                sides.append(left)
    valid = not missing and not sides and not notes
    note = "; ".join([*(f"missing {', '.join(missing)}" for _ in [0] if missing),
                      *(f"left/right swapped: {', '.join(sides)}" for _ in [0] if sides), *notes]) or "ok"
    return {"group_names": names, "groups": weights, "mask_names": base.mask_names, "masks": masks.astype(np.float32),
            "landmarks": landmarks, "labels": labels, "fit": fit,
            "info": {"valid": bool(valid), "notes": note, "relabelled_pct": round(relabelled * 100, 2),
                     "parts": counts}}
