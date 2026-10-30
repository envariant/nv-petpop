#!/usr/bin/env python3
"""Author the six ComfyUI workflows (API format) in pipelines/comfy/ (M2.5).

Node ids are generated here, never hand-edited. Workflows carry no model names or tunables: every value the
GenAI profile supplies (model files, prompts, seeds, steps, sizes, strengths) is bound by name in
`meta.inputs` -> [node_id, input] and filled by backend/worker/backends/real/comfy.py at run time. Outputs
are bound by name in `meta.outputs`. All six are `meta.validated: false` until they have run on a live host;
node class and input names were checked against the node packs' source at the commits in requirements.txt.

    python scripts/make_comfy_workflows.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pipelines" / "comfy"
VIEWS = ["front", "left", "back", "right"]


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.inputs: dict[str, list] = {}
        self.outputs: dict[str, str] = {}
        self.optional: dict[str, dict] = {}

    def add(self, class_type: str, title: str, **inputs) -> str:
        nid = str(len(self.nodes) + 1)
        self.nodes[nid] = {"class_type": class_type, "inputs": inputs, "_meta": {"title": title}}
        return nid

    def bind(self, name: str, node: str, field: str, placeholder=None) -> None:
        """Expose node input `field` as the named workflow input `name` (filled from the profile)."""
        self.nodes[node]["inputs"][field] = placeholder
        self.inputs.setdefault(name, []).append([node, field])

    def doc(self, version: str, stage: str, packs: list[str], notes: str, required: list[str]) -> dict:
        meta = {"version": version, "validated": False, "validated_against": None, "stage": stage, "node_packs": packs,
                # an input bound to [] is accepted and unused by this graph
                "inputs": {k: (v[0] if len(v) == 1 else v) for k, v in self.inputs.items()}, "outputs": self.outputs,
                "optional_nodes": self.optional, "required": required, "notes": notes}
        return {"meta": meta, **self.nodes}


def sdxl_base(g: Graph):
    ckpt = g.add("CheckpointLoaderSimple", "checkpoint")
    g.bind("checkpoint", ckpt, "ckpt_name", "")
    lora = g.add("LoraLoader", "style lora", model=[ckpt, 0], clip=[ckpt, 1])
    g.bind("lora", lora, "lora_name", "")
    g.bind("lora_strength", lora, "strength_model", 0.8)
    g.bind("lora_strength", lora, "strength_clip", 0.8)
    g.optional["lora"] = {"node": lora, "bypass": {"0": [ckpt, 0], "1": [ckpt, 1]}}
    vae = g.add("VAELoader", "vae")
    g.bind("vae", vae, "vae_name", "")
    neg = g.add("CLIPTextEncode", "negative", clip=[lora, 1])
    g.bind("negative", neg, "text", "")
    cn = g.add("ControlNetLoader", "controlnet depth")
    g.bind("controlnet", cn, "control_net_name", "")
    return ckpt, lora, vae, neg, cn


def sampler(g: Graph, title: str, model, pos, neg, latent, denoise_bound: bool):
    k = g.add("KSampler", title, model=model, positive=pos, negative=neg, latent_image=latent, denoise=1.0)
    for name, field, ph in (("seed", "seed", 0), ("steps", "steps", 25), ("cfg", "cfg", 6.0),
                            ("sampler", "sampler_name", "dpmpp_2m"), ("scheduler", "scheduler", "karras")):
        g.bind(name, k, field, ph)
    if denoise_bound:
        g.bind("denoise", k, "denoise", 0.7)
    return k


def concept() -> dict:
    g = Graph()
    _, lora, vae, neg, cn = sdxl_base(g)
    pos = g.add("CLIPTextEncode", "positive", clip=[lora, 1])
    g.bind("positive", pos, "text", "")
    depth = g.add("LoadImage", "depth image")
    g.bind("depth_image", depth, "image", "")
    apply = g.add("ControlNetApplyAdvanced", "apply depth", positive=[pos, 0], negative=[neg, 0], control_net=[cn, 0],
                  image=[depth, 0], start_percent=0.0, end_percent=1.0, vae=[vae, 0])
    g.bind("controlnet_strength", apply, "strength", 0.7)
    init = g.add("LoadImage", "init image (flat-colour base mesh render)")
    g.bind("init_image", init, "image", "")
    scale = g.add("ImageScale", "init to size", image=[init, 0], upscale_method="lanczos", crop="center")
    g.bind("width", scale, "width", 1024)
    g.bind("height", scale, "height", 1024)
    enc = g.add("VAEEncode", "init latent", pixels=[scale, 0], vae=[vae, 0])
    k = sampler(g, "sampler", [lora, 0], [apply, 0], [apply, 1], [enc, 0], denoise_bound=True)
    dec = g.add("VAEDecode", "decode", samples=[k, 0], vae=[vae, 0])
    g.outputs["concept"] = g.add("SaveImage", "concept", images=[dec, 0], filename_prefix="petpop/concept")
    return g.doc("1", "B", ["core"], "SDXL + optional style LoRA + depth ControlNet + img2img init from the flat-colour "
                 "base-mesh render (init weight 0.3 => denoise 0.7). Background is keyed by the worker.",
                 ["checkpoint", "vae", "controlnet", "positive", "negative", "depth_image", "init_image", "seed"])


def views_ipadapter() -> dict:
    g = Graph()
    _, lora, vae, neg, cn = sdxl_base(g)
    ipm = g.add("IPAdapterModelLoader", "ip-adapter model")
    g.bind("ipadapter", ipm, "ipadapter_file", "")
    clipv = g.add("CLIPVisionLoader", "clip vision")
    g.bind("clip_vision", clipv, "clip_name", "")
    ref = g.add("LoadImage", "concept reference")
    g.bind("concept_image", ref, "image", "")
    ipa = g.add("IPAdapterAdvanced", "ip-adapter plus", model=[lora, 0], ipadapter=[ipm, 0], image=[ref, 0],
                weight_type="linear", combine_embeds="concat", start_at=0.0, end_at=1.0, embeds_scaling="V only",
                clip_vision=[clipv, 0])
    g.bind("ipadapter_weight", ipa, "weight", 0.7)
    latent = g.add("EmptyLatentImage", "latent", batch_size=1)
    g.bind("width", latent, "width", 768)
    g.bind("height", latent, "height", 768)
    for v in VIEWS:
        pos = g.add("CLIPTextEncode", f"positive {v}", clip=[lora, 1])
        g.bind(f"positive_{v}", pos, "text", "")
        depth = g.add("LoadImage", f"depth {v}")
        g.bind(f"depth_{v}", depth, "image", "")
        apply = g.add("ControlNetApplyAdvanced", f"apply depth {v}", positive=[pos, 0], negative=[neg, 0],
                      control_net=[cn, 0], image=[depth, 0], start_percent=0.0, end_percent=1.0, vae=[vae, 0])
        g.bind("controlnet_strength", apply, "strength", 0.7)
        k = sampler(g, f"sampler {v}", [ipa, 0], [apply, 0], [apply, 1], [latent, 0], denoise_bound=False)
        dec = g.add("VAEDecode", f"decode {v}", samples=[k, 0], vae=[vae, 0])
        g.outputs[f"view_{v}"] = g.add("SaveImage", f"view_{v}", images=[dec, 0], filename_prefix=f"petpop/view_{v}")
    return g.doc("1", "C", ["core", "ComfyUI_IPAdapter_plus"], "Four views in one graph: per-view depth ControlNet, "
                 "IP-Adapter Plus SDXL on the concept, shared seed and latent size. Background keyed by the worker.",
                 ["checkpoint", "vae", "controlnet", "ipadapter", "clip_vision", "concept_image", "negative", "seed"]
                 + [f"depth_{v}" for v in VIEWS] + [f"positive_{v}" for v in VIEWS])


def views_mvadapter() -> dict:
    g = Graph()
    pipe = g.add("DiffusersMVPipelineLoader", "mv base pipeline", pipeline_name="MVAdapterI2MVSDXLPipeline")
    g.bind("mv_base", pipe, "ckpt_name", "")
    vae = g.add("DiffusersMVVaeLoader", "mv vae")
    g.bind("mv_vae", vae, "vae_name", "")
    sched = g.add("DiffusersMVSchedulerLoader", "mv scheduler", pipeline=[pipe, 0], scheduler_name="DPMSolverMultistep",
                  shift_snr=True, shift_mode="interpolated", shift_scale=8.0)
    # VAE slicing off: the node calls pipeline.enable_vae_slicing(), which diffusers 0.42 no longer has (decision 95).
    model = g.add("DiffusersMVModelMakeup", "mv adapter", pipeline=[pipe, 0], scheduler=[sched, 0], autoencoder=[vae, 0],
                  load_mvadapter=True, num_views=4, enable_vae_slicing=False, enable_vae_tiling=False)
    g.bind("mv_adapter_repo", model, "adapter_path", "")
    g.bind("mvadapter", model, "adapter_name", "")
    ref = g.add("LoadImage", "concept reference")
    g.bind("concept_image", ref, "image", "")
    views = g.add("ViewSelector", "azimuths 0/90/180/270", front_view=True, front_right_view=False, right_view=True,
                  back_view=True, left_view=True, front_left_view=False)
    s = g.add("DiffusersMVSampler", "mv sampler", pipeline=[model, 0], num_views=4, reference_image=[ref, 0],
              azimuth_degrees=[views, 0])
    for name, field, ph in (("positive", "prompt", ""), ("negative", "negative_prompt", ""), ("width", "width", 768),
                            ("height", "height", 768), ("steps", "steps", 30), ("cfg", "cfg", 6.0), ("seed", "seed", 0)):
        g.bind(name, s, field, ph)
    # ViewSelector keeps azimuths 0, 90, 180, 270 in that order. MV-Adapter's 90 shows the pet's left side (nose
    # toward image left), which is the brief's left view (camera at +X) and Hunyuan3D-2mv's (decision 96).
    for i, v in enumerate(["front", "left", "back", "right"]):
        one = g.add("ImageFromBatch", f"pick {v}", image=[s, 0], batch_index=i, length=1)
        g.outputs[f"view_{v}"] = g.add("SaveImage", f"view_{v}", images=[one, 0], filename_prefix=f"petpop/mv_{v}")
    return g.doc("1", "C (alt)", ["ComfyUI-MVAdapter"], "MV-Adapter image-to-multiview SDXL conditioned on the concept; "
                 "azimuth 90 is the pet's left (checked on the Mac 2026-10-30).",
                 ["mv_base", "mv_vae", "mv_adapter_repo", "mvadapter", "concept_image", "positive", "negative", "seed"])


def shape_hy2mv() -> dict:
    g = Graph()
    ckpt = g.add("ImageOnlyCheckpointLoader", "hunyuan3d-2mv")
    g.bind("model", ckpt, "ckpt_name", "")
    enc = {}
    for v in VIEWS:
        img = g.add("LoadImage", f"view {v}")
        g.bind(f"view_{v}", img, "image", "")
        enc[v] = g.add("CLIPVisionEncode", f"encode {v}", clip_vision=[ckpt, 1], image=[img, 0], crop="none")
    cond = g.add("Hunyuan3Dv2ConditioningMultiView", "multi-view conditioning", **{v: [enc[v], 0] for v in VIEWS})
    latent = g.add("EmptyLatentHunyuan3Dv2", "latent", batch_size=1)
    g.bind("latent_resolution", latent, "resolution", 3072)
    k = g.add("KSampler", "sampler", model=[ckpt, 0], positive=[cond, 0], negative=[cond, 1], latent_image=[latent, 0],
              sampler_name="euler", scheduler="normal", denoise=1.0)
    g.bind("seed", k, "seed", 0)
    g.bind("steps", k, "steps", 50)
    g.bind("guidance", k, "cfg", 5.5)
    dec = g.add("VAEDecodeHunyuan3D", "decode voxels", samples=[k, 0], vae=[ckpt, 2])
    g.bind("num_chunks", dec, "num_chunks", 8000)
    g.bind("octree_resolution", dec, "octree_resolution", 384)
    mesh = g.add("VoxelToMeshBasic", "voxels to mesh", voxel=[dec, 0])
    g.bind("threshold", mesh, "threshold", 0.6)
    g.outputs["shape"] = g.add("SaveGLB", "shape", mesh=[mesh, 0], filename_prefix="petpop/shape")
    return g.doc("1", "D", ["core"], "ComfyUI core Hunyuan3D-2mv nodes (comfy_extras/nodes_hunyuan3d.py).",
                 ["model", "seed"] + [f"view_{v}" for v in VIEWS])


def shape_hy21_single() -> dict:
    g = Graph()
    img = g.add("LoadImage", "view front")
    g.bind("view_front", img, "image", "")
    gen = g.add("Hy3D_2_1SimpleMeshGen", "hunyuan3d-2.1 single view", image=[img, 0])
    g.bind("model", gen, "model", "")
    g.bind("steps", gen, "steps", 50)
    g.bind("guidance", gen, "guidance_scale", 5.0)
    g.bind("octree_resolution", gen, "octree_resolution", 384)
    mesh = g.add("TrimeshToMESH", "to MESH", trimesh=[gen, 0])
    g.outputs["shape"] = g.add("SaveGLB", "shape", mesh=[mesh, 0], filename_prefix="petpop/shape_single")
    g.inputs.setdefault("seed", [])  # the wrapper's simple node has no seed input; accepted and ignored
    return g.doc("1", "D (fallback)", ["ComfyUI-Hunyuan3DWrapper"], "Hunyuan3D-2.1 single-view fallback through kijai's "
                 "wrapper (Hy3D_2_1SimpleMeshGen); the model file goes in models/diffusion_models.", ["model", "view_front"])


def texture_hy_paint() -> dict:
    g = Graph()
    mesh = g.add("Hy3DLoadMesh", "wrapped mesh (fixed UVs)")
    g.bind("mesh_path", mesh, "glb_path", "")
    cams = g.add("Hy3DCameraConfig", "cameras", camera_azimuths="0, 90, 180, 270, 0, 180",
                 camera_elevations="0, 0, 0, 0, 90, -90", view_weights="1, 0.1, 0.5, 0.1, 0.05, 0.05",
                 camera_distance=1.45, ortho_scale=1.2)
    render = g.add("Hy3DRenderMultiView", "render normals/positions", trimesh=[mesh, 0], camera_config=[cams, 0],
                   normal_space="world")
    g.bind("render_size", render, "render_size", 1024)
    g.bind("texture_size", render, "texture_size", 2048)
    paint = g.add("DownloadAndLoadHy3DPaintModel", "paint model")
    g.bind("model", paint, "model", "")
    ref = g.add("LoadImage", "front view reference")
    g.bind("ref_image", ref, "image", "")
    sample = g.add("Hy3DSampleMultiView", "sample views", pipeline=[paint, 0], ref_image=[ref, 0], normal_maps=[render, 0],
                   position_maps=[render, 1], camera_config=[cams, 0])
    g.bind("view_size", sample, "view_size", 512)
    g.bind("steps", sample, "steps", 30)
    g.bind("seed", sample, "seed", 0)
    bake = g.add("Hy3DBakeFromMultiview", "bake to UVs", images=[sample, 0], renderer=[render, 2], camera_config=[cams, 0])
    fill = g.add("Hy3DMeshVerticeInpaintTexture", "vertex inpaint", texture=[bake, 0], mask=[bake, 1], renderer=[bake, 2])
    cv = g.add("CV2InpaintTexture", "inpaint", texture=[fill, 0], mask=[fill, 1], inpaint_radius=3, inpaint_method="ns")
    g.outputs["albedo"] = g.add("SaveImage", "albedo", images=[cv, 0], filename_prefix="petpop/albedo")
    return g.doc("1", "F (texture, optional)", ["ComfyUI-Hunyuan3DWrapper"], "Hunyuan3D-Paint 2.0 baked into the wrapped "
                 "mesh's own UVs (no UV re-wrap). NVIDIA only; projection is the default texture backend.",
                 ["mesh_path", "model", "ref_image"])


def main() -> None:
    files = {"01_concept_front.json": concept(), "02_views_ipadapter.json": views_ipadapter(),
             "02b_views_mvadapter.json": views_mvadapter(), "03_shape_hy2mv.json": shape_hy2mv(),
             "03b_shape_hy21_single.json": shape_hy21_single(), "04_texture_hy_paint.json": texture_hy_paint()}
    for name, doc in files.items():
        (OUT / name).write_text(json.dumps(doc, indent=1) + "\n")
        print(f"pipelines/comfy/{name}: {len(doc) - 1} nodes, inputs {len(doc['meta']['inputs'])}")


if __name__ == "__main__":
    main()
