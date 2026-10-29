"""Accessory anchor frames from landmark positions (BRIEF Section 10), shared by the Blender stages and the
numpy mock shape so both place collars, hats and glasses identically."""
from __future__ import annotations


from functools import lru_cache

import numpy as np

from petpop_core.paths import ACCESSORY_DIR


def accessory_anchors(co: np.ndarray, landmarks: dict[str, int], shell: np.ndarray) -> dict[str, dict]:
    """Anchor frames (position, scale) for each accessory from the current landmark positions."""
    lm = {k: co[v] for k, v in landmarks.items()}
    body = co[shell == 0]
    neck = lm["neck_front"]
    band = body[np.abs(body[:, 2] - neck[2]) < 2.0]
    centre_y = float(band[:, 1].mean()) if len(band) else float(neck[1] + 8)
    radius = float(np.percentile(np.hypot(band[:, 0], band[:, 1] - centre_y), 60)) if len(band) else 10.0
    head_top_z = float(co[(shell == 0)][:, 2].max())
    ear_mid = (lm["ear_base_L"] + lm["ear_base_R"]) / 2
    eyes = (lm["eye_L"] + lm["eye_R"]) / 2
    eye_span = float(abs(lm["eye_L"][0] - lm["eye_R"][0]))
    return {
        "collar": {"loc": (0.0, centre_y, float(neck[2])), "scale": (radius * 0.97, radius * 0.97, radius * 0.97)},
        "bandana": {"loc": (0.0, float(neck[1]) + 1.5, float(neck[2]) - 1.0), "scale": (radius, radius, radius)},
        "bow": {"loc": (0.0, float(ear_mid[1]) - 2.0, head_top_z - 1.5), "scale": (8.0, 8.0, 8.0)},
        "hat": {"loc": (0.0, float(ear_mid[1]), head_top_z - 3.0), "scale": (eye_span * 0.9, eye_span * 0.9, eye_span * 0.9)},
        "glasses": {"loc": (0.0, float(eyes[1]) - 2.5, float(eyes[2])), "scale": (eye_span / 2, eye_span / 2, eye_span / 2)},
    }


@lru_cache
def library():
    """Accessory meshes (unit frame, Z up) from assets/accessories/accessories.glb, keyed by type."""
    import trimesh

    scene = trimesh.load(ACCESSORY_DIR / "accessories.glb", file_type="glb", force="scene")
    out = {}
    for name, geom in scene.geometry.items():
        kind = name.replace("acc_", "").split(".")[0]
        v = np.asarray(geom.vertices)
        out[kind] = (np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1), np.asarray(geom.faces))  # Y-up -> Z-up
    return out


def placed(accessories: list[dict], co: np.ndarray, landmarks: dict[str, int], shell: np.ndarray):
    """(vertices, faces) of every accessory placed on this mesh, concatenated."""
    anchors = accessory_anchors(co, landmarks, shell)
    lib = library()
    vs, fs, n = [], [], 0
    for a in accessories:
        if a["type"] not in lib:
            continue
        v, f = lib[a["type"]]
        fr = anchors[a["type"]]
        vs.append(v * np.array(fr["scale"]) + np.array(fr["loc"]))
        fs.append(f + n)
        n += len(v)
    if not vs:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    return np.concatenate(vs), np.concatenate(fs)


