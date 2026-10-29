"""Stage F: texture bake and export (BRIEF Section 6.6): albedo in the fixed UV layout with per-region colour
correction and seam padding, figure_uv.obj, the print mesh (STL + 3MF), the paint check mask, the Draco GLB,
thumbnail and turntable."""
from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from backend.core import lowfi
from petpop_library.meshkit import dilate, load_base, raster_uv, to_trimesh, write_obj

from . import blender
from .backends.mock.pacing import Pace



def encode_mp4(frames_dir: Path, fps: int, out: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not any(frames_dir.glob("f*.png")):
        return False
    r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames_dir / "f%03d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        "-movflags", "+faststart", str(out)], capture_output=True, timeout=120)
    return r.returncode == 0 and out.exists()


def repair(mesh):
    """Drop degenerate slivers left by the exact booleans, merge, fill pin-holes, fix winding."""
    import trimesh

    mesh.update_faces(mesh.nondegenerate_faces(height=1e-6))
    mesh.remove_unreferenced_vertices()
    mesh.merge_vertices()
    if not mesh.is_watertight:
        parts = mesh.split(only_watertight=False)
        keep = [p for p in parts if len(p.faces) >= 0.005 * len(mesh.faces)]
        mesh = trimesh.util.concatenate(keep) if len(keep) > 1 else keep[0]
        trimesh.repair.fill_holes(mesh)
    trimesh.repair.fix_normals(mesh)
    return mesh


def albedo_vertex_colours(base, albedo_png: bytes) -> np.ndarray:
    """(n, 3) per-vertex colours sampled from the albedo at each vertex's UVs (low-fidelity thumbnails)."""
    img = np.asarray(Image.open(io.BytesIO(albedo_png)).convert("RGB"), dtype=np.float32) / 255.0
    h, w = img.shape[:2]
    uv = base.uv[base.tri_loops.reshape(-1)]
    px = np.clip((uv[:, 0] * w).astype(int), 0, w - 1)
    py = np.clip(((1 - uv[:, 1]) * h).astype(int), 0, h - 1)
    acc = np.zeros((len(base.co), 3))
    cnt = np.zeros(len(base.co))
    np.add.at(acc, base.tri_verts.reshape(-1), img[py, px])
    np.add.at(cnt, base.tri_verts.reshape(-1), 1)
    return acc / np.maximum(cnt, 1)[:, None]


def run(job_id, spec, manifest, *, ctx) -> list[str]:
    ctx.check_fault("F")
    spec = json.loads(ctx.get("spec.json"))
    base = load_base(spec["species"])
    coords = np.load(io.BytesIO(ctx.get("wrapped_coords.npy"))).astype(np.float64)
    keys: list[str] = []
    with Pace("F"):
        views = {v: ctx.get(f"views/{v}.png") for v in ("front", "left", "back", "right")}
        albedo_png = ctx.backends.texture.paint(ctx, spec, ctx.get("figure_wrapped.obj"), coords, views)
        keys.append(ctx.put(manifest, "albedo.png", "albedo", "F", albedo_png))
        from petpop_library.colouring import vertex_colours

        metrics, more = finish_export(ctx, manifest, spec, base, coords, albedo_png,
                                      thumb_colours=lambda: vertex_colours(base, spec, coords))
        keys += more
        ctx.state["f_metrics"] = metrics
    return keys


def finish_export(ctx, manifest, spec, base, coords, albedo_png: bytes, thumb_colours=None) -> tuple[dict, list[str]]:
    """The print half of Stage F, shared by the pipeline and the kiosk's library export (BRIEF Section 16): the UV
    OBJ, the print mesh with base disc and mandrel socket (accessories and shell parts fused), the print and paint
    checks, the GLB, thumbnail and turntable. Returns (metrics, artefact keys)."""
    q = ctx.quality
    keys: list[str] = []
    work = ctx.workdir("export")
    write_obj(work / "figure_uv.obj", base, coords)
    keys.append(ctx.put(manifest, "figure_uv.obj", "uv_obj", "F", (work / "figure_uv.obj").read_bytes()))
    ctx.progress("F", 86, "Preparing the print file")
    albedo_path = work / "albedo.png"
    albedo_path.write_bytes(albedo_png)
    np.save(work / "coords.npy", coords.astype(np.float32))
    metrics: dict = {}
    import trimesh

    if blender.available(ctx.settings.bpy_python):
        res = blender.run(ctx.settings.bpy_python, ["export_print", "paint_check", "preview"], {
            "species": spec["species"], "coords": str(work / "coords.npy"), "albedo": str(albedo_path),
            "accessories": spec.get("accessories", []), "quality": q, "out_dir": str(work)}, timeout=ctx.remaining())
        stl = Path(res["stl"]).read_bytes()
        flags = np.load(res["flags"]).astype(np.float32)
        glb = Path(res["glb"]).read_bytes()
        thumb = Path(res["thumbnail"]).read_bytes()
        metrics.update(print_tris=int(res["tris"]), print_height_mm=float(res["height_mm"]),
                       min_wall_mm=None if np.isnan(res["min_wall_mm"]) else float(res["min_wall_mm"]),
                       min_wall_ok=bool(res["min_wall_ok"]))
        mp4 = work / "turntable.mp4"
        turntable = encode_mp4(Path(res["frames_dir"]), int(res["fps"]), mp4)
    else:
        ctx.state["fidelity"] = "low"
        pm = lowfi.print_mesh(base, coords)
        stl = pm.export(file_type="stl")
        mask_img, _ = lowfi.paint_check(base, coords, int(q["mask_px"]))
        flags = None
        glb = to_trimesh(base, coords, texture=Image.open(io.BytesIO(albedo_png)), yup=True).export(file_type="glb")
        colours = thumb_colours() if thumb_colours else albedo_vertex_colours(base, albedo_png)
        thumb = lowfi.png_bytes(lowfi.flat_render(base, coords, colours, 25, 256, False))
        metrics.update(print_tris=int(len(pm.faces)), print_height_mm=round(float(pm.extents[2]), 2),
                       min_wall_mm=None, min_wall_ok=True)
        turntable = False
    pm = repair(trimesh.load(io.BytesIO(stl), file_type="stl"))
    stl = pm.export(file_type="stl")
    metrics["print_watertight"] = bool(pm.is_watertight)
    keys.append(ctx.put(manifest, "figure.stl", "stl", "F", stl))
    keys.append(ctx.put(manifest, "figure.3mf", "3mf", "F", pm.export(file_type="3mf")))
    if flags is not None:
        img, cov = raster_uv(base, flags[:, None], int(q["mask_px"]), per_face=True)
        img = dilate(img, cov, 2)
        mask_img = Image.fromarray((img[..., 0] > 0.5).astype(np.uint8) * 255, "L")
        metrics["paint_mask_pct"] = round(float(flags.mean() * 100), 2)
    else:
        metrics["paint_mask_pct"] = round(float(np.asarray(mask_img).mean() / 255 * 100), 2)
    keys.append(ctx.put(manifest, "paint_mask.png", "mask", "F", lowfi.png_bytes(mask_img)))
    keys.append(ctx.put(manifest, "thumbnail.png", "thumbnail", "F", thumb))
    if turntable:
        keys.append(ctx.put(manifest, "turntable.mp4", "turntable", "F", (work / "turntable.mp4").read_bytes()))
    key = ctx.put(manifest, "figure.glb", "glb", "F", glb)
    keys.append(key)
    ctx.progress("F", 98, "Finishing touches", preview=("glb", key))
    return metrics, keys
