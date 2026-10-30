#!/usr/bin/env python3
"""Stage B/C settings sweep on the GenAI host: run concept and view variants for a fixed set of breeds and seeds,
write labelled contact sheets. Re-run unchanged once the style LoRA exists (--lora) for a before/after.

    python scripts/image_sweep.py [--stage concept|views|all] [--breeds dog:golden_retriever,...] [--seed 101]
                                  [--refs DIR] [--lora FILE --lora-strength 0.8] [--out var/sweeps/NAME]

The generated workflows (pipelines/comfy/01, 02) are loaded and changed in memory per variant; the files on disk
are never edited. Model names come from the GenAI profile. Every image gets a white-border score: the share of
the outer 4 % border at or above the profile's white_key threshold (matting needs it near 1.0).
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.genai import Profile  # noqa: E402
from petpop_library.meshkit import load_base  # noqa: E402
from petpop_core.spec import default_spec  # noqa: E402
from petpop_core.vocab import morph_weights  # noqa: E402
from petpop_core.prompts.compiler import compile_prompts  # noqa: E402
from backend.worker.backends.real.comfy import ComfyClient, ComfyError  # noqa: E402

BREEDS = "dog:golden_retriever,dog:dachshund,dog:french_bulldog,dog:border_collie"
WHITE_BG = ", isolated on a pure white seamless background"
VIEWS = ("front", "left", "back", "right")

# Concept variants. init: start from the proxy's flat-colour render (img2img) at this denoise, ("white", d) for a plain
# white canvas at denoise d (biases the background to white), else an empty latent.
# depth: ControlNet (strength, end_percent) from the proxy's depth, or None. style_ref: IP-Adapter on --refs.
CONCEPT = {
    "c1_current": dict(init=0.7, depth=(0.7, 1.0), style_ref=None, white=False),
    "c2_weak_depth": dict(init=None, depth=(0.35, 0.35), style_ref=None, white=True),
    "c3_txt2img": dict(init=None, depth=None, style_ref=None, white=True),
    "c4_style_ref": dict(init=None, depth=None, style_ref=("style transfer", 0.6), white=True),
    "c5_style_light_wc": dict(init=("white", 0.92), depth=None, style_ref=("style transfer", 0.4), white=True),
    "c6_style_precise_wc": dict(init=("white", 0.92), depth=None, style_ref=("style transfer precise", 0.5), white=True),
    "c7_txt2img_wc": dict(init=("white", 0.92), depth=None, style_ref=None, white=True),
}
# MV-Adapter (workflow 02b) on the Mac: diffusers folders by path under ComfyUI's petpop-models symlink (mac/setup.sh).
# Experimental; these move into the profile once the path is integrated.
MV = {"mv_base": "petpop-models/diffusers/stable-diffusion-xl-base-1.0", "mv_vae": "petpop-models/diffusers/sdxl-vae-fp16-fix",
      "mv_adapter_repo": "petpop-models/hf/huanngzh/mv-adapter", "mvadapter": "mvadapter_i2mv_sdxl.safetensors"}
# Hunyuan3D-2mv (workflow 03) through ComfyUI's built-in nodes.
SHAPE = {"full": {"model": "hunyuan3d-dit-v2-mv.fp16.safetensors", "steps": 50, "guidance": 5.5},
         "turbo": {"model": "hunyuan3d-dit-v2-mv-turbo.fp16.safetensors", "steps": 5, "guidance": 5.0}}

# View variants: ControlNet (strength, end_percent) from the proxy's depth per view; IP-Adapter (type, weight) on the concept.
VIEW_VARIANTS = {
    "v1_current": dict(depth=(0.7, 1.0), ipa=("linear", 0.7), white=False),
    "v2_rebalanced": dict(depth=(0.45, 0.5), ipa=("linear", 0.9), white=True),
    # Identity early, viewpoint late: IP-Adapter only over the first half of the steps, depth strong to 90 %, a back
    # prompt that rules out a face, and a white canvas start.
    "v3_identity_early": dict(depth=(0.7, 0.9), ipa=("linear", 0.8, 0.5), white=True, canvas=0.92,
                              back=", seen from directly behind, back of the head and back of the body, no face visible",
                              back_negative=", face, eyes, nose, muzzle, looking at viewer"),
}


def control_images(species: str, spec: dict, px: int) -> dict[str, bytes]:
    """Depth for the five cameras and the flat front render of the morphed proxy, as the control stage makes them."""
    from backend.core import lowfi
    from petpop_library.colouring import vertex_colours
    from backend.core.config import settings
    from backend.worker import blender

    base = load_base(species)
    weights = morph_weights(spec)
    co = base.morph(weights)
    s = settings()
    out: dict[str, bytes] = {}
    if blender.available(s.bpy_python):
        work = ROOT / "var/sweeps/_control" / f"{species}_{spec['breed']['id']}"
        work.mkdir(parents=True, exist_ok=True)
        res = blender.run(s.bpy_python, ["render_control"], {"species": species, "weights": weights, "accessories": [],
                          "quality": {"control_px": px}, "out_dir": str(work)}, timeout=600)
        out.update({f"{cam}_depth": Path(p).read_bytes() for cam, p in res["depth"].items()})
    else:
        out.update({f"{cam}_depth": r["depth"] for cam, r in lowfi.control_renders(base, co, px).items()})
    front = lowfi.flat_render(base, co, vertex_colours(base, spec, co), 0.0, px, False)
    out["flat_front"] = lowfi.png_bytes(front)
    buf = io.BytesIO()
    Image.new("RGB", (px, px), "white").save(buf, format="PNG")
    out["white"] = buf.getvalue()
    return out


def strip_trigger(text: str) -> str:
    return text.removeprefix("petpop_style, ")


def new_id(g: dict) -> str:
    return str(max(int(k) for k in g) + 1)


def add_style_ref(g: dict, model_src: list, refs: list[str], m: dict, weight_type: str, weight: float) -> list:
    """Insert IP-Adapter on a batch of reference images in front of the sampler; returns the new model output."""
    ipa, cv = new_id(g), None
    g[ipa] = {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": m["ipadapter"]}}
    cv = new_id(g)
    g[cv] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": m["clip_vision"]}}
    batch = None
    for name in refs:
        li = new_id(g)
        g[li] = {"class_type": "LoadImage", "inputs": {"image": name}}
        sc = new_id(g)
        g[sc] = {"class_type": "ImageScale", "inputs": {"image": [li, 0], "upscale_method": "lanczos", "crop": "center",
                                                         "width": 1024, "height": 1024}}
        if batch is None:
            batch = [sc, 0]
        else:
            b = new_id(g)
            g[b] = {"class_type": "ImageBatch", "inputs": {"image1": batch, "image2": [sc, 0]}}
            batch = [b, 0]
    adv = new_id(g)
    g[adv] = {"class_type": "IPAdapterAdvanced", "inputs": {
        "model": model_src, "ipadapter": [ipa, 0], "image": batch, "clip_vision": [cv, 0], "weight": weight,
        "weight_type": weight_type, "combine_embeds": "average", "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only"}}
    return [adv, 0]


def concept_graph(c: ComfyClient, p: dict, v: dict, prompts: dict, ctrl: dict[str, str], refs: list[str],
                  lora: tuple[str, float] | None, seed: int, px: int) -> dict:
    graph, meta = c.load(p["workflows"]["concept"])
    m, prm = p["models"], p["params"]
    pos = strip_trigger(prompts["positive"]) if not lora else prompts["positive"]
    values = {"checkpoint": m["checkpoint"], "vae": m["vae"], "controlnet": m["controlnet_depth"],
              "lora": lora[0] if lora else None, "lora_strength": lora[1] if lora else None,
              "positive": pos + (WHITE_BG if v["white"] else ""), "negative": prompts["negative"],
              "depth_image": ctrl["concept_front_depth"], "init_image": ctrl["flat_front"],
              "controlnet_strength": (v["depth"] or (0.7, 1.0))[0], "width": px, "height": px, "seed": seed,
              "steps": prm["concept_steps"], "cfg": prm["cfg"], "sampler": prm["sampler"], "scheduler": prm["scheduler"],
              "denoise": (v["init"][1] if isinstance(v["init"], tuple) else v["init"]) or 1.0}
    if isinstance(v["init"], tuple):
        values["init_image"] = ctrl["white"]
    g = c.fill(graph, meta, values)
    ks = meta["inputs"]["seed"][0]
    sampler = g[ks]["inputs"]
    cn = next(k for k, n in g.items() if n["class_type"] == "ControlNetApplyAdvanced")
    if v["depth"]:
        g[cn]["inputs"]["end_percent"] = v["depth"][1]
    else:  # no ControlNet: the sampler takes the text conditioning directly
        sampler["positive"], sampler["negative"] = g[cn]["inputs"]["positive"], g[cn]["inputs"]["negative"]
        del g[cn]
    if v["init"] is None:  # empty latent instead of the encoded flat render
        lat = new_id(g)
        g[lat] = {"class_type": "EmptyLatentImage", "inputs": {"width": px, "height": px, "batch_size": 1}}
        sampler["latent_image"] = [lat, 0]
    if v["style_ref"]:
        if not refs:
            raise SystemExit("variant c4_style_ref needs --refs")
        sampler["model"] = add_style_ref(g, sampler["model"], refs, m, *v["style_ref"])
    return prune(g)


def views_graph(c: ComfyClient, p: dict, v: dict, prompts: dict, ctrl: dict[str, str], concept: str,
                lora: tuple[str, float] | None, seed: int, px: int) -> dict:
    graph, meta = c.load(p["workflows"]["views"])
    m, prm = p["models"], p["params"]
    values = {"checkpoint": m["checkpoint"], "vae": m["vae"], "controlnet": m["controlnet_depth"],
              "lora": lora[0] if lora else None, "lora_strength": lora[1] if lora else None,
              "ipadapter": m["ipadapter"], "clip_vision": m["clip_vision"], "ipadapter_weight": v["ipa"][1],
              "concept_image": concept, "negative": prompts["negative"], "controlnet_strength": v["depth"][0],
              "width": px, "height": px, "seed": seed, "steps": prm["view_steps"], "cfg": prm["cfg"],
              "sampler": prm["sampler"], "scheduler": prm["scheduler"]}
    for view in VIEWS:
        text = prompts["views"][view] if lora else strip_trigger(prompts["views"][view])
        if view == "back":
            text += v.get("back", "")
        values[f"positive_{view}"] = text + (WHITE_BG if v["white"] else "")
        values[f"depth_{view}"] = ctrl[f"{view}_depth"]
    g = c.fill(graph, meta, values)
    for n in g.values():
        if n["class_type"] == "ControlNetApplyAdvanced":
            n["inputs"]["end_percent"] = v["depth"][1]
        if n["class_type"] == "IPAdapterAdvanced":
            n["inputs"]["weight_type"] = v["ipa"][0]
            if len(v["ipa"]) > 2:
                n["inputs"]["end_at"] = v["ipa"][2]
    if v.get("back_negative"):  # the back view gets its own negative; the other views keep the shared one
        back_pos = meta["inputs"]["positive_back"][0]
        cn = next(k for k, n in g.items() if n["class_type"] == "ControlNetApplyAdvanced" and n["inputs"]["positive"][0] == back_pos)
        neg = new_id(g)
        g[neg] = {"class_type": "CLIPTextEncode", "inputs": {"clip": g[back_pos]["inputs"]["clip"],
                                                            "text": prompts["negative"] + v["back_negative"]}}
        g[cn]["inputs"]["negative"] = [neg, 0]
    if v.get("canvas"):  # start every view from a white canvas so the background stays white
        li, enc = new_id(g), None
        g[li] = {"class_type": "LoadImage", "inputs": {"image": ctrl["white"]}}
        enc = new_id(g)
        g[enc] = {"class_type": "VAEEncode", "inputs": {"pixels": [li, 0], "vae": [meta["inputs"]["vae"][0], 0]}}
        for n in g.values():
            if n["class_type"] == "KSampler":
                n["inputs"]["latent_image"], n["inputs"]["denoise"] = [enc, 0], v["canvas"]
    return prune(g)


def mv_graph(c: ComfyClient, p: dict, prompts: dict, concept: str, seed: int, px: int, steps: int, cfg: float) -> dict:
    graph, meta = c.load(p["workflows"].get("views_alt", "02b_views_mvadapter.json"))
    base = strip_trigger(prompts["positive"]).replace(", front view", "")
    values = {**MV, "concept_image": concept, "positive": base + WHITE_BG, "negative": prompts["negative"],
              "width": px, "height": px, "steps": steps, "cfg": cfg, "seed": seed}
    return c.fill(graph, meta, values)


def shape_graph(c: ComfyClient, views: dict[str, str], variant: dict, seed: int, octree: int) -> dict:
    graph, meta = c.load("03_shape_hy2mv.json")
    values = {"model": variant["model"], "seed": seed, "steps": variant["steps"], "guidance": variant["guidance"],
              "octree_resolution": octree, "num_chunks": 8000, "latent_resolution": 3072, "threshold": 0.6,
              **{f"view_{v}": name for v, name in views.items()}}
    return c.fill(graph, meta, values)


def mesh_preview(glb: bytes, px: int = 256) -> list[tuple[str, bytes]]:
    """Shaded grey renders of a mesh from front, left, back and right (CPU z-buffer, no Blender)."""
    import trimesh

    from petpop_library.meshkit import CENTRE_Z_DEFAULT, EXTENT_DEFAULT, render

    m = trimesh.load(io.BytesIO(glb), file_type="glb", force="mesh")
    v = np.asarray(m.vertices, dtype=np.float64)
    v = np.stack([v[:, 0], -v[:, 2], v[:, 1]], axis=1)  # glTF Y-up -> the base mesh's Z-up
    v -= [(v[:, 0].max() + v[:, 0].min()) / 2, (v[:, 1].max() + v[:, 1].min()) / 2, v[:, 2].min()]
    v *= 0.85 * EXTENT_DEFAULT / max(float(np.ptp(v, axis=0).max()), 1e-6)
    v[:, 2] += CENTRE_Z_DEFAULT - (v[:, 2].max() / 2)
    tris = np.asarray(m.faces)
    out = []
    for name, az in (("front", 0.0), ("left", 90.0), ("back", 180.0), ("right", 270.0)):
        r = render(v, tris, az, px, colours=np.full((len(v), 3), 0.85))
        buf = io.BytesIO()
        Image.fromarray((np.clip(r["rgb"], 0, 1) * 255).astype(np.uint8), "RGB").save(buf, format="PNG")
        out.append((name, buf.getvalue()))
    return out


def prune(g: dict) -> dict:
    """Drop nodes nothing reads any more (ComfyUI rejects e.g. a LoadImage with no consumer only if invalid, but
    unused loaders still cost a model load)."""
    while True:
        used = {v[0] for n in g.values() for v in n["inputs"].values() if isinstance(v, list) and len(v) == 2}
        dead = [k for k, n in g.items() if k not in used and n["class_type"] not in ("SaveImage",)]
        if not dead:
            return g
        for k in dead:
            del g[k]


def get(c: ComfyClient, path: str, **kw):
    """GET through the tunnel, riding out a dropped connection (a quick tunnel drops one now and then)."""
    import httpx

    for attempt in range(6):
        try:
            r = c.http.get(f"{c.url}{path}", **kw)
            r.raise_for_status()
            return r
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 5:
                raise
            time.sleep(5 * (attempt + 1))


def submit(c: ComfyClient, g: dict, timeout: float = 1200) -> tuple[dict[str, bytes], float]:
    import httpx

    for attempt in range(4):  # a dropped connection may re-queue a prompt once; harmless for a sweep
        try:
            r = c.http.post(f"{c.url}/prompt", json={"prompt": g, "client_id": c.client_id})
            break
        except httpx.TransportError:
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))
    if r.status_code != 200:
        raise ComfyError(f"/prompt rejected: {r.text[:800]}")
    pid, t0 = r.json()["prompt_id"], time.monotonic()
    # the timeout runs from when the host starts the prompt, not from queueing behind others
    try:
        return _wait(c, g, pid, t0, timeout)
    except BaseException:
        cancel(c, pid)
        raise


def cancel(c: ComfyClient, pid: str) -> None:
    """Take an abandoned prompt off the host: drop it from the queue, or interrupt it if it is running."""
    try:
        q = get(c, "/queue").json()
        if any(it[1] == pid for it in q.get("queue_running", [])):
            c.http.post(f"{c.url}/interrupt")
        else:
            c.http.post(f"{c.url}/queue", json={"delete": [pid]})
    except Exception:  # noqa: BLE001 - best effort; the host may be unreachable
        pass


def _wait(c: ComfyClient, g: dict, pid: str, t0: float, timeout: float) -> tuple[dict[str, bytes], float]:
    started = None
    while started is None or time.monotonic() - started < timeout:
        if started is None:
            q = get(c, "/queue").json()
            if not any(it[1] == pid for it in q.get("queue_pending", [])):
                started = time.monotonic()
        h = get(c, f"/history/{pid}").json()
        if pid in h:
            entry = h[pid]
            if entry.get("status", {}).get("status_str") == "error":
                raise ComfyError(json.dumps(entry["status"])[:800])
            out = {}
            for node, res in entry.get("outputs", {}).items():
                for im in [x for key in ("images", "3d", "gltf", "meshes") for x in (res.get(key) or [])
                           if isinstance(x, dict) and "filename" in x]:
                    v = get(c, "/view", params={"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                                                            "type": im.get("type", "output")})
                    out[g[node]["inputs"].get("filename_prefix", node)] = v.content
            return out, time.monotonic() - (started or t0)
        time.sleep(2)
    raise ComfyError(f"timed out after {timeout:.0f} s")


def border_matte(png: bytes, size: int) -> bytes:
    """Evaluation-only matte for views on a plain non-white backdrop: key the top/side border colour (the floor is
    left out of the estimate), open away speckle, keep the largest subject, fill holes, re-centre on white.
    A stand-in until a background-removal model is pinned on the host (decision 87)."""
    from scipy import ndimage

    from backend.worker.imaging import matte_square

    a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(np.int16)
    b = max(2, a.shape[0] // 25)
    bg = np.median(np.concatenate([a[:b].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)]), axis=0)
    fg = ndimage.binary_opening(np.abs(a - bg).max(axis=2) > 40, iterations=3)
    lab, n = ndimage.label(fg)
    if n:
        fg = lab == (1 + int(np.argmax(ndimage.sum(fg, lab, range(1, n + 1)))))
    fg = ndimage.binary_fill_holes(fg)
    buf = io.BytesIO()
    Image.fromarray(np.dstack([a.astype(np.uint8), (fg * 255).astype(np.uint8)]), "RGBA").save(buf, format="PNG")
    return matte_square(buf.getvalue(), size)


def white_border(png: bytes, threshold: int) -> float:
    a = np.asarray(Image.open(io.BytesIO(png)).convert("L"))
    b = max(2, a.shape[0] // 25)
    edge = np.concatenate([a[:b].ravel(), a[-b:].ravel(), a[:, :b].ravel(), a[:, -b:].ravel()])
    return round(float((edge >= threshold).mean()), 3)


def subject_frac(png: bytes) -> float:
    """Share of the frame that differs from the background colour (the border median): low means a tiny or blank
    subject, which the white-border score alone rewards."""
    a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(np.int16)
    b = max(2, a.shape[0] // 25)
    edge = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    bg = np.median(edge, axis=0)
    return round(float((np.abs(a - bg).max(axis=2) > 30).mean()), 3)


def embed(prof, pngs: list[bytes]) -> list[np.ndarray] | None:
    """DINOv2 embeddings from the shape server's /v1/embed (L2-normalised), or None if the host has no endpoint yet."""
    import httpx

    url = prof.url((prof.doc.get("embed") or {}).get("service", "embed")) + "/v1/embed"
    files = [("image", (f"{i}.png", b, "image/png")) for i, b in enumerate(pngs)]
    for attempt in range(10):
        try:
            r = httpx.post(url, files=files, headers=prof.auth_headers(), timeout=120)
        except httpx.TransportError:
            time.sleep(5)
            continue
        if r.status_code == 409:  # a mesh holds the model slot
            time.sleep(15)
            continue
        if r.status_code in (404, 503):
            print(f"  (no embeddings: {r.status_code} {r.text[:120]})", flush=True)
            return None
        r.raise_for_status()
        return [np.asarray(v, dtype=np.float32) for v in r.json()["embeddings"]]
    return None


def view_scores(prof, concept: bytes, views: list[bytes]) -> dict:
    """Identity: DINOv2 cosine of each view to the concept. Viewpoint: how different the back is from the front
    (a back that is a copy of the front scores high on identity and near zero here). Fill: subject_frac."""
    vecs = embed(prof, [concept, *views])
    out = {"fill": [subject_frac(v) for v in views]}
    if vecs:
        c, vs = vecs[0], vecs[1:]
        out["to_concept"] = [round(float(c @ v), 3) for v in vs]
        out["front_back"] = round(float(vs[0] @ vs[VIEWS.index("back")]), 3)
    return out


def caption(view: str, sc: dict, i: int) -> str:
    sim = f" sim {sc['to_concept'][i]}" if "to_concept" in sc else ""
    return f"{view}{sim} fill {sc['fill'][i]}"


def sheet(rows: list[tuple[str, list[tuple[str, bytes | None]]]], path: Path, cell: int = 320) -> None:
    cols = max(len(r[1]) for r in rows)
    lab_w, head = 170, 24
    img = Image.new("RGB", (lab_w + cols * (cell + 6), len(rows) * (cell + head + 6) + 4), "white")
    d = ImageDraw.Draw(img)
    for ri, (label, cells) in enumerate(rows):
        y = 4 + ri * (cell + head + 6)
        d.text((6, y + head + cell // 2), label, fill="black")
        for ci, (cap, png) in enumerate(cells):
            x = lab_w + ci * (cell + 6)
            d.text((x, y + 4), cap, fill="black")
            if png:
                im = ImageOps.contain(Image.open(io.BytesIO(png)).convert("RGB"), (cell, cell))
                img.paste(im, (x, y + head))
            else:
                d.rectangle([x, y + head, x + cell, y + head + cell], outline="red")
                d.text((x + 8, y + head + 8), "failed", fill="red")
    img.save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["concept", "views", "all", "mv", "shape", "score"], default="all")
    ap.add_argument("--score-sets", default="", help="--stage score: label=dir:variant,... (files <breed>__<variant>__<view>.png)")
    ap.add_argument("--mv-steps", type=int, default=30)
    ap.add_argument("--mv-cfg", type=float, default=3.0)
    ap.add_argument("--mv-px", type=int, default=768)
    ap.add_argument("--shape", default="full", help="Hunyuan3D-2mv variant(s) for --stage shape: full,turbo")
    ap.add_argument("--octree", type=int, default=256)
    ap.add_argument("--matte", choices=["profile", "border"], default="profile",
                    help="--stage shape: the profile's matting, or border_matte for views on a grey backdrop")
    ap.add_argument("--shape-views-from", help="folder holding <breed>__mv__<view>.png (default: --out)")
    ap.add_argument("--breeds", default=BREEDS)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--px", type=int, default=1024)
    ap.add_argument("--refs", help="folder of style reference images (c4_style_ref)")
    ap.add_argument("--concepts", default="c1_current,c2_weak_depth,c3_txt2img,c4_style_ref")
    ap.add_argument("--view-variants", default=",".join(VIEW_VARIANTS))
    ap.add_argument("--views-from", default="c4_style_ref", help="concept variant the view sweep starts from")
    ap.add_argument("--lora", help="LoRA file name on the host (default: the profile's image.models.lora)")
    ap.add_argument("--lora-strength", type=float)
    ap.add_argument("--out")
    args = ap.parse_args()

    prof = Profile()
    p = prof["image"]
    lora_name = args.lora or p["models"].get("lora")
    lora = (lora_name, args.lora_strength or p["params"]["lora_strength"]) if lora_name else None
    threshold = int(p["matting"].get("threshold", 236))
    out = Path(args.out or ROOT / "var/sweeps" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    c = ComfyClient(prof)
    refs = []
    if args.refs:
        for f in sorted(Path(args.refs).iterdir()):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                refs.append(c.upload(f"sweep_ref_{f.stem}{f.suffix.lower()}", f.read_bytes(), "image/png"))
    concepts = [k for k in args.concepts.split(",") if k in CONCEPT and (CONCEPT[k]["style_ref"] is None or refs)]
    report = {"profile": prof.name, "seed": args.seed, "px": args.px, "lora": lora, "refs": len(refs), "items": []}
    concept_rows, view_rows = [], []
    try:
        for item in args.breeds.split(","):
            species, breed = item.split(":")
            spec = default_spec(species, breed, seed=args.seed)
            if spec["breed"]["id"] != breed:
                raise SystemExit(f"unknown breed {breed!r} for {species}")
            prompts = compile_prompts(spec)
            ctrl = {}
            if args.stage in ("concept", "views", "all"):  # only the SDXL graphs read the proxy's control images
                ctrl = {k: c.upload(f"sweep_{breed}_{k}.png", v) for k, v in control_images(species, spec, args.px).items()}
            cells, concept_png = [], {}
            if args.stage in ("concept", "all"):
                for name in concepts:
                    try:
                        imgs, dt = submit(c, concept_graph(c, p, CONCEPT[name], prompts, ctrl, refs, lora, args.seed, args.px))
                        png = next(iter(imgs.values()))
                        wb = white_border(png, threshold)
                        (out / f"{breed}__{name}.png").write_bytes(png)
                        concept_png[name] = png
                        cells.append((f"{name}  white {wb}  {dt:.0f}s", png))
                        report["items"].append({"breed": breed, "variant": name, "s": round(dt), "white_border": wb})
                    except ComfyError as exc:
                        cells.append((f"{name}  FAILED", None))
                        report["items"].append({"breed": breed, "variant": name, "error": str(exc)[:400]})
                    print(report["items"][-1], flush=True)
                concept_rows.append((breed, cells))
            if args.stage == "mv":
                found = [d / f"{breed}__{args.views_from}.png" for d in (out, out.parent)]
                src = next(f for f in found if f.exists()).read_bytes()
                cref = c.upload(f"sweep_{breed}_concept.png", src)
                try:
                    imgs, dt = submit(c, mv_graph(c, p, prompts, cref, args.seed, args.mv_px, args.mv_steps, args.mv_cfg), timeout=3600)
                    pngs = [next(b for k, b in imgs.items() if k.endswith(f"mv_{view}")) for view in VIEWS]
                    for view, png in zip(VIEWS, pngs):
                        (out / f"{breed}__mv__{view}.png").write_bytes(png)
                    sc = view_scores(prof, src, pngs)
                    row = [("concept", src)] + [(caption(v, sc, i), b) for i, (v, b) in enumerate(zip(VIEWS, pngs))]
                    report["items"].append({"breed": breed, "variant": "mv", "s": round(dt), **sc,
                                            "white_border": [white_border(b, threshold) for b in pngs]})
                except (ComfyError, StopIteration) as exc:
                    row = [("concept", src)] + [(f"{view}  FAILED", None) for view in VIEWS]
                    report["items"].append({"breed": breed, "variant": "mv", "error": str(exc)[:600]})
                print(report["items"][-1], flush=True)
                view_rows.append((f"{breed}\nmv-adapter", row))
            if args.stage == "shape":
                from backend.worker.imaging import matte

                vdir = Path(args.shape_views_from) if args.shape_views_from else out
                matted = {}
                for v in VIEWS:
                    raw = (vdir / f"{breed}__mv__{v}.png").read_bytes()
                    matted[v] = (border_matte(raw, args.mv_px) if args.matte == "border"
                                 else matte(raw, p["matting"], args.mv_px))
                    (out / f"{breed}__mv_matted__{v}.png").write_bytes(matted[v])
                names = {v: c.upload(f"sweep_{breed}_mv_{v}.png", png) for v, png in matted.items()}
                view_rows.append((f"{breed}\n2mv input ({args.matte})", [(f"{v}  matted", matted[v]) for v in VIEWS]))
                for sv in args.shape.split(","):
                    try:
                        imgs, dt = submit(c, shape_graph(c, names, SHAPE[sv], args.seed, args.octree), timeout=3600)
                        glb = next(iter(imgs.values())) if imgs else None
                        if glb is None:
                            raise ComfyError("no GLB in the outputs")
                        (out / f"{breed}__2mv_{sv}.glb").write_bytes(glb)
                        row = [(f"{v}  {dt:.0f}s" if v == "front" else v, png) for v, png in mesh_preview(glb)]
                        report["items"].append({"breed": breed, "variant": f"2mv_{sv}", "s": round(dt), "glb_bytes": len(glb)})
                    except (ComfyError, StopIteration) as exc:
                        row = [(f"{v}  FAILED", None) for v in VIEWS]
                        report["items"].append({"breed": breed, "variant": f"2mv_{sv}", "error": str(exc)[:600]})
                    print(report["items"][-1], flush=True)
                    view_rows.append((f"{breed}\n2mv {sv} {args.octree}", row))
            if args.stage == "score":  # score view sets already on disk: --score-sets label=dir:variant,...
                src = next(f for f in (out / f"{breed}__{args.views_from}.png", out.parent / f"{breed}__{args.views_from}.png")
                           if f.exists()).read_bytes()
                for item in args.score_sets.split(","):
                    label, _, rest = item.partition("=")
                    vdir, _, vname = rest.partition(":")
                    files = [Path(vdir) / f"{breed}__{vname}__{v}.png" for v in VIEWS]
                    if not all(f.exists() for f in files):
                        continue
                    pngs = [f.read_bytes() for f in files]
                    sc = view_scores(prof, src, pngs)
                    report["items"].append({"breed": breed, "variant": label, **sc})
                    print(report["items"][-1], flush=True)
                    view_rows.append((f"{breed}\n{label}", [("concept", src)] + [(caption(v, sc, i), b) for i, (v, b) in
                                                                                 enumerate(zip(VIEWS, pngs))]))
            if args.stage in ("views", "all"):
                found = [d / f"{breed}__{args.views_from}.png" for d in (out, out.parent)]
                src = concept_png.get(args.views_from) or next(f for f in found if f.exists()).read_bytes()
                cref = c.upload(f"sweep_{breed}_concept.png", src)
                for name, v in ((k, VIEW_VARIANTS[k]) for k in args.view_variants.split(",")):
                    try:
                        imgs, dt = submit(c, views_graph(c, p, v, prompts, ctrl, cref, lora, args.seed, args.px))
                        row = [("concept", src)]
                        for view in VIEWS:
                            png = next(b for k, b in imgs.items() if k.endswith(f"view_{view}"))
                            (out / f"{breed}__{name}__{view}.png").write_bytes(png)
                            row.append((f"{view}  white {white_border(png, threshold)}", png))
                        report["items"].append({"breed": breed, "variant": name, "s": round(dt),
                                                "white_border": [white_border(b, threshold) for _, b in row[1:]]})
                    except (ComfyError, StopIteration) as exc:
                        row = [("concept", src)] + [(f"{view}  FAILED", None) for view in VIEWS]
                        report["items"].append({"breed": breed, "variant": name, "error": str(exc)[:400]})
                    print(report["items"][-1], flush=True)
                    view_rows.append((f"{breed}\n{name}", row))
    finally:
        c.free()
        (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
        if concept_rows:
            sheet(concept_rows, out / "concepts.png")
        if view_rows:
            sheet(view_rows, out / "views.png", cell=256)
        print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
