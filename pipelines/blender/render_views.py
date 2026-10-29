"""MockImageBackend renders (BRIEF Section 13): Cycles CPU renders of the morphed, flat-coloured base mesh
standing in for Stage B (concept, front) and Stage C (four turnaround views). Transparent background; the
worker does the matting/re-centring step that BiRefNet does on the GPU host."""
from pathlib import Path

from common import add_accessories, assign_material, image_material, load_base, ortho_camera, render_to, reset, scene_setup, set_coords

VIEWS = {"front": 0.0, "left": 90.0, "back": 180.0, "right": 270.0}


def main(job: dict) -> dict:
    from petpop_library.meshkit import load_base as np_base

    reset()
    base = np_base(job["species"])
    co = base.morph(job["weights"])
    obj = load_base(job["species"])
    set_coords(obj, co)
    assign_material(obj, image_material("albedo", job["albedo"]))
    add_accessories(job.get("accessories", []), co, base.landmarks, base.shell)
    q = job["quality"]
    out = Path(job["out_dir"])
    files = {}
    which = job.get("views", ["concept", *VIEWS])
    if "concept" in which:
        scene_setup(int(q["concept_px"]), int(q["samples"]), transparent=True)
        ortho_camera(0.0)
        render_to(str(out / "concept.png"))
        files["concept"] = str(out / "concept.png")
    for v, az in VIEWS.items():
        if v not in which:
            continue
        scene_setup(int(q["view_px"]), int(q["samples"]), transparent=True)
        ortho_camera(az)
        render_to(str(out / f"view_{v}.png"))
        files[v] = str(out / f"view_{v}.png")
    return {"files": files}
