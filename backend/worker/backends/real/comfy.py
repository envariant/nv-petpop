"""ComfyUI adapters (BRIEF Section 8), host-agnostic: the GenAI profile supplies the URL, workflow files,
model names, parameters and residency rules; the workflow JSON's `meta.inputs` / `meta.outputs` say which
node input or output each named value maps to, so node ids never appear in code.

Each workflow's meta.validated says whether it has run cleanly on a live host.
"""
from __future__ import annotations

import copy
import io
import json
import logging
import time
import uuid
from typing import Any

import httpx

from backend.core.paths import PIPELINES

from ..base import ShapeResult

WORKFLOWS = PIPELINES / "comfy"
log = logging.getLogger("petpop.worker")


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, profile) -> None:
        self.profile = profile
        self.url = profile.url("comfy")
        self.client_id = uuid.uuid4().hex
        self.http = httpx.Client(timeout=60, headers=profile.auth_headers())

    def healthy(self) -> bool:
        try:
            return self.http.get(f"{self.url}/system_stats").status_code == 200
        except httpx.HTTPError:
            return False

    def free(self) -> None:
        try:
            self.http.post(f"{self.url}/free", json={"unload_models": True, "free_memory": True})
        except httpx.HTTPError as exc:
            log.warning("ComfyUI /free failed: %s", exc)

    def upload(self, name: str, data: bytes, mime: str = "image/png") -> str:
        r = self.http.post(f"{self.url}/upload/image", files={"image": (name, data, mime)}, data={"overwrite": "true"})
        r.raise_for_status()
        body = r.json()
        return f"{body['subfolder']}/{body['name']}" if body.get("subfolder") else body["name"]

    @staticmethod
    def load(workflow: str) -> tuple[dict[str, Any], dict[str, Any]]:
        doc = json.loads((WORKFLOWS / workflow).read_text())
        meta = doc.get("meta", {})
        graph = {k: v for k, v in doc.items() if k != "meta"}
        return graph, meta

    @staticmethod
    def fill(graph: dict[str, Any], meta: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        """Set each named value on the node input that meta.inputs binds it to; bypass optional nodes whose
        value is None (e.g. no LoRA yet)."""
        g = copy.deepcopy(graph)
        bindings = meta.get("inputs", {})
        for name, value in values.items():
            targets = bindings.get(name)
            if not targets or value is None:
                continue  # not used by this workflow (e.g. num_chunks on the single-view graph), or optional
            for node_id, field in (targets if isinstance(targets[0], list) else [targets]):
                g[node_id]["inputs"][field] = value
        for name, spec in meta.get("optional_nodes", {}).items():
            if values.get(name, "present") is None:
                node_id = spec["node"]
                rewire = spec["bypass"]  # {output_index: [source_node, source_output]}
                del g[node_id]
                for node in g.values():
                    for k, v in node["inputs"].items():
                        if isinstance(v, list) and len(v) == 2 and v[0] == node_id:
                            node["inputs"][k] = rewire[str(v[1])]
        missing = [n for n in meta.get("required", []) if values.get(n) is None]
        if missing:
            raise ComfyError(f"missing required workflow inputs {missing}")
        return g

    def run(self, workflow: str, values: dict[str, Any], timeout: float) -> tuple[dict[str, list[bytes]], dict[str, Any]]:
        graph, meta = self.load(workflow)
        if not meta.get("validated", False):
            log.warning("workflow %s is unvalidated (meta.validated=false)", workflow)
        g = self.fill(graph, meta, values)
        r = self.http.post(f"{self.url}/prompt", json={"prompt": g, "client_id": self.client_id})
        if r.status_code != 200:
            raise ComfyError(f"/prompt rejected {workflow}: {r.text[:500]}")
        prompt_id = r.json()["prompt_id"]
        t0 = time.monotonic()
        try:
            while time.monotonic() - t0 < timeout:
                h = self.http.get(f"{self.url}/history/{prompt_id}").json()
                if prompt_id in h:
                    entry = h[prompt_id]
                    if entry.get("status", {}).get("status_str") == "error":
                        raise ComfyError(f"{workflow} failed: {json.dumps(entry['status'])[:500]}")
                    return self._outputs(meta, entry), meta
                time.sleep(1.0)
            raise ComfyError(f"{workflow} timed out after {timeout:.0f} s")
        finally:
            if self.profile["residency"].get("free_comfy_after_call"):
                self.free()

    def _outputs(self, meta: dict[str, Any], entry: dict[str, Any]) -> dict[str, list[bytes]]:
        if not meta.get("outputs"):
            raise ComfyError("workflow meta declares no outputs")
        out: dict[str, list[bytes]] = {}
        by_node = {v: k for k, v in meta["outputs"].items()}
        for node_id, result in entry.get("outputs", {}).items():
            name = by_node.get(node_id)
            if not name:
                continue
            for key in ("images", "3d", "gltf", "meshes"):
                for item in result.get(key, []) or []:
                    if not isinstance(item, dict) or "filename" not in item:
                        continue
                    v = self.http.get(f"{self.url}/view", params={"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                                                                  "type": item.get("type", "output")})
                    v.raise_for_status()
                    out.setdefault(name, []).append(v.content)
        missing = set(meta.get("outputs", {})) - set(out)
        if missing:
            raise ComfyError(f"workflow produced no {sorted(missing)}")
        return out


def _version(ctx, workflow: str, meta: dict[str, Any]) -> None:
    v = str(meta.get("version", "0")) + ("" if meta.get("validated") else "-unvalidated")
    ctx.state.setdefault("workflows", {})[workflow.removesuffix(".json")] = v


class ComfyImageBackend:
    """Stages B and C. Which graph runs is the profile's choice (image.workflows); what to send it follows from the
    workflow's own meta.inputs, so a txt2img concept gets no control images and an MV-Adapter views graph gets the
    concept as its reference instead of per-view depth."""
    name = "comfy"

    def __init__(self, client: ComfyClient, profile) -> None:
        self.c = client
        self.cfg = profile["image"]

    def _positive(self, text: str) -> str:
        """Without a style LoRA its trigger word is noise: drop it (the S3 sweeps ran without it)."""
        trigger = self.cfg.get("lora_trigger")
        if trigger and not self.cfg["models"].get("lora") and text.startswith(f"{trigger}, "):
            return text[len(trigger) + 2:]
        return text

    def _common(self, spec, prompts) -> dict[str, Any]:
        m, p = self.cfg["models"], self.cfg["params"]
        return {"negative": prompts["negative"], "seed": int(spec["seed"]), "cfg": p["cfg"], "sampler": p["sampler"],
                "scheduler": p["scheduler"], "checkpoint": m["checkpoint"], "vae": m["vae"], "controlnet": m.get("controlnet_depth"),
                "controlnet_strength": p.get("controlnet_strength"), "lora": m.get("lora"),
                "lora_strength": p.get("lora_strength", 0.8) if m.get("lora") else None}

    def _matte(self, ctx, png: bytes, name: str, size: int) -> bytes:
        """The profile's matting: 'birefnet' runs the matte workflow on the host and applies its mask here;
        'alpha' and 'white_key' are local (backend/worker/imaging.py)."""
        from backend.worker.imaging import apply_mask, matte

        cfg = self.cfg["matting"]
        if cfg.get("method") != "birefnet":
            return matte(png, cfg, size)
        wf = self.cfg["workflows"]["matte"]
        out, meta = self.c.run(wf, {"image": self.c.upload(f"{ctx.job_id}_{name}_raw.png", png),
                                    "bg_model": self.cfg["models"]["bg_removal"]}, timeout=ctx.remaining())
        _version(ctx, wf, meta)
        return apply_mask(png, out["mask"][0], size)

    def concept(self, ctx, spec, prompts, control):
        wf = self.cfg["workflows"]["concept"]
        _, meta = self.c.load(wf)
        size = int(ctx.quality["concept_px"])
        values = {**self._common(spec, prompts), "positive": self._positive(prompts["positive"]),
                  "steps": self.cfg["params"]["concept_steps"], "width": size, "height": size}
        if "depth_image" in meta["inputs"]:  # proxy-controlled concept (img2img init + depth ControlNet)
            values.update(denoise=self.cfg["params"]["init_denoise"],
                          depth_image=self.c.upload(f"{ctx.job_id}_concept_depth.png", control["concept_front_depth"]),
                          init_image=self.c.upload(f"{ctx.job_id}_flat_front.png", control["flat_front"]))
        out, meta = self.c.run(wf, values, timeout=ctx.remaining())
        _version(ctx, wf, meta)
        return self._matte(ctx, out["concept"][0], "concept", size)

    def views(self, ctx, spec, prompts, control, concept):
        from backend.worker.imaging import on_white

        wf = self.cfg["workflows"]["views"]
        _, meta = self.c.load(wf)
        size = int(ctx.quality["view_px"])
        m, p = self.cfg["models"], self.cfg["params"]
        if "mv_base" in meta["inputs"]:  # multi-view diffusion from the concept alone (MV-Adapter)
            values = {"mv_base": m["mv_base"], "mv_vae": m["mv_vae"], "mv_adapter_repo": m["mv_adapter_repo"],
                      "mvadapter": m["mvadapter"], "concept_image": self.c.upload(f"{ctx.job_id}_concept.png", on_white(concept)),
                      "positive": self._positive(prompts["positive"]).replace(", front view", ""),
                      "negative": prompts["negative"], "width": size, "height": size, "steps": p["mv_steps"],
                      "cfg": p["mv_cfg"], "seed": int(spec["seed"])}
        else:  # per-view SDXL: depth ControlNet per view + IP-Adapter on the concept
            values = {**self._common(spec, prompts), "steps": p["view_steps"], "width": size, "height": size,
                      "ipadapter": m["ipadapter"], "clip_vision": m["clip_vision"], "ipadapter_weight": p["ipadapter_weight"],
                      "concept_image": self.c.upload(f"{ctx.job_id}_concept.png", concept)}
            for v in ("front", "left", "back", "right"):
                values[f"depth_{v}"] = self.c.upload(f"{ctx.job_id}_{v}_depth.png", control[f"{v}_depth"])
                values[f"positive_{v}"] = self._positive(prompts["views"][v])
        out, meta = self.c.run(wf, values, timeout=ctx.remaining())
        _version(ctx, wf, meta)
        return {v: self._matte(ctx, out[f"view_{v}"][0], f"view_{v}", size) for v in ("front", "left", "back", "right")}


class ComfyShapeBackend:
    name = "comfy"

    def __init__(self, client: ComfyClient, profile) -> None:
        self.c = client
        self.profile = profile
        self.cfg = profile["shape"]

    def _before(self) -> None:
        if "D" in (self.profile["residency"].get("free_comfy_before") or []):
            self.c.free()  # the image stack never co-resides with the shape model

    def _run(self, ctx, spec, kind: str, images: dict[str, bytes], params: dict[str, Any], seed: int) -> ShapeResult:
        wf = self.cfg["workflows"][kind]
        values = {"model": self.cfg["models"][kind], "seed": seed, "steps": params["steps"], "guidance": params["guidance"],
                  "octree_resolution": params["octree_resolution"]}
        for k in ("num_chunks", "latent_resolution", "threshold", "sampler", "scheduler", "mesh_algorithm"):
            if k in self.cfg["params"]:
                values[k] = self.cfg["params"][k]
        for v, data in images.items():
            values[f"view_{v}"] = self.c.upload(f"{ctx.job_id}_shape_{v}.png", data)
        out, meta = self.c.run(wf, values, timeout=ctx.remaining())
        _version(ctx, wf, meta)
        return ShapeResult(glb=normalise_glb(out["shape"][0], self.cfg), co=None, tris=None, backend=f"comfy:{kind}")

    def multiview(self, ctx, spec, views):
        self._before()
        imgs = {v: views[v] for v in self.cfg["views"]}
        kind = "multiview" if len(imgs) > 1 else "single_view"
        return self._run(ctx, spec, kind, imgs, self.cfg["params"], int(spec["seed"]))

    def single_view(self, ctx, spec, front):
        self._before()
        fb = self.cfg.get("fallback", {})
        return self._run(ctx, spec, "single_view", {"front": front}, {**self.cfg["params"], **fb.get("params", {})},
                         int(spec["seed"]) + int(fb.get("seed_offset", 1)))


def normalise_glb(data: bytes, cfg: dict[str, Any]) -> bytes:
    """Centre, rotate by the profile's yaw, scale to the profile height, decimate to the profile's max tris.
    Output stays glTF Y-up with the front facing +Z (the base-mesh convention after export)."""
    import numpy as np
    import trimesh

    m = trimesh.load(io.BytesIO(data), file_type="glb", force="mesh")
    v = np.asarray(m.vertices, dtype=np.float64)
    yaw = np.radians(float(cfg.get("orientation", {}).get("yaw_deg", 0)))
    if yaw:
        c, s = np.cos(yaw), np.sin(yaw)
        v = v @ np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]).T
    v -= [(v[:, 0].max() + v[:, 0].min()) / 2, v[:, 1].min(), (v[:, 2].max() + v[:, 2].min()) / 2]
    v *= float(cfg["height_mm"]) / max(float(np.ptp(v[:, 1])), 1e-6)
    m = trimesh.Trimesh(v, m.faces, process=True)
    if len(m.faces) > int(cfg.get("max_tris", 300000)):
        m = m.simplify_quadric_decimation(face_count=int(cfg["max_tris"]))
    return m.export(file_type="glb")
