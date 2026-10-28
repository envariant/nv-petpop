"""ComfyUI adapters for the GPU host (BRIEF Section 8). Not exercised in the cloud session (S3 work).

Each stage is one API-format workflow under pipelines/comfy/; editable inputs are PrimitiveNodes found by
title and filled before POST /prompt. Progress comes from /ws, outputs from /history + /view. Between the
image stages and Stage D the worker calls /free with unload_models so SDXL and Hunyuan3D never co-reside.
"""
from __future__ import annotations

import io
import json
import time
import uuid

from typing import Any

import httpx

from backend.core.paths import PIPELINES

from ..base import ShapeResult

WORKFLOWS = PIPELINES / "comfy"


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.client_id = uuid.uuid4().hex
        self.http = httpx.Client(timeout=30)

    def healthy(self) -> bool:
        try:
            return self.http.get(f"{self.url}/system_stats").status_code == 200
        except httpx.HTTPError:
            return False

    def free(self) -> None:
        self.http.post(f"{self.url}/free", json={"unload_models": True, "free_memory": True})

    def upload(self, name: str, data: bytes) -> str:
        r = self.http.post(f"{self.url}/upload/image", files={"image": (name, data, "image/png")},
                           data={"overwrite": "true"})
        r.raise_for_status()
        return r.json()["name"]

    def load(self, workflow: str) -> tuple[dict[str, Any], str]:
        doc = json.loads((WORKFLOWS / workflow).read_text())
        version = str(doc.get("meta", {}).get("version", "0"))
        graph = {k: v for k, v in doc.items() if k != "meta"}
        return graph, version

    @staticmethod
    def fill(graph: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        """Set PrimitiveNode values by node title (never by node id)."""
        found = set()
        for node in graph.values():
            title = node.get("_meta", {}).get("title")
            if title in inputs:
                key = "value" if "value" in node.get("inputs", {}) else next(iter(node.get("inputs", {})), "value")
                node["inputs"][key] = inputs[title]
                found.add(title)
        missing = set(inputs) - found
        if missing:
            raise ComfyError(f"workflow has no PrimitiveNode titled {sorted(missing)}")
        return graph

    def run(self, workflow: str, inputs: dict[str, Any], timeout: float, progress=None) -> tuple[dict[str, list[bytes]], str]:
        graph, version = self.load(workflow)
        graph = self.fill(graph, inputs)
        r = self.http.post(f"{self.url}/prompt", json={"prompt": graph, "client_id": self.client_id})
        if r.status_code != 200:
            raise ComfyError(f"/prompt rejected: {r.text[:500]}")
        prompt_id = r.json()["prompt_id"]
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            h = self.http.get(f"{self.url}/history/{prompt_id}").json()
            if prompt_id in h:
                entry = h[prompt_id]
                if entry.get("status", {}).get("status_str") == "error":
                    raise ComfyError(f"{workflow} failed: {entry['status']}")
                outputs: dict[str, list[bytes]] = {}
                for node_id, out in entry.get("outputs", {}).items():
                    title = graph.get(node_id, {}).get("_meta", {}).get("title", node_id)
                    for item in out.get("images", []) + out.get("gltf", []) + out.get("3d", []):
                        v = self.http.get(f"{self.url}/view", params={"filename": item["filename"],
                                                                      "subfolder": item.get("subfolder", ""),
                                                                      "type": item.get("type", "output")})
                        outputs.setdefault(title, []).append(v.content)
                return outputs, version
            if progress:
                progress()
            time.sleep(0.5)
        raise ComfyError(f"{workflow} timed out after {timeout:.0f} s")


class ComfyImageBackend:
    name = "comfy-sdxl"

    def __init__(self, client: ComfyClient) -> None:
        self.c = client

    def concept(self, ctx, spec, prompts, control):
        depth = self.c.upload(f"{ctx.job_id}_concept_depth.png", control["concept_front_depth"])
        init = self.c.upload(f"{ctx.job_id}_flat.png", control["flat_front"])
        out, version = self.c.run("01_concept_front.json", {
            "positive": prompts["positive"], "negative": prompts["negative"], "seed": int(spec["seed"]),
            "depth_image": depth, "init_image": init,
        }, timeout=ctx.remaining())
        ctx.state.setdefault("workflows", {})["01_concept_front"] = version
        return out["concept"][0]

    def views(self, ctx, spec, prompts, control, concept):
        names = {v: self.c.upload(f"{ctx.job_id}_{v}_depth.png", control[f"{v}_depth"]) for v in ("front", "left", "back", "right")}
        ref = self.c.upload(f"{ctx.job_id}_concept.png", concept)
        inputs = {"concept_image": ref, "seed": int(spec["seed"]), "negative": prompts["negative"]}
        for v in names:
            inputs[f"depth_{v}"] = names[v]
            inputs[f"positive_{v}"] = prompts["views"][v]
        out, version = self.c.run("02_views_ipadapter.json", inputs, timeout=ctx.remaining())
        ctx.state.setdefault("workflows", {})["02_views_ipadapter"] = version
        return {v: out[f"view_{v}"][0] for v in names}


class ComfyShapeBackend:
    name = "comfy-hunyuan3d"

    def __init__(self, client: ComfyClient) -> None:
        self.c = client

    def multiview(self, ctx, spec, views):
        self.c.free()  # SDXL + ControlNet + IP-Adapter out before Hunyuan3D-2mv comes in
        inputs = {f"view_{v}": self.c.upload(f"{ctx.job_id}_view_{v}.png", b) for v, b in views.items()}
        inputs["seed"] = int(spec["seed"])
        out, version = self.c.run("03_shape_hy2mv.json", inputs, timeout=ctx.remaining())
        ctx.state.setdefault("workflows", {})["03_shape_hy2mv"] = version
        return ShapeResult(glb=normalise_glb(out["shape"][0]), co=None, tris=None, backend=self.name)

    def single_view(self, ctx, spec, front):
        inputs = {"view_front": self.c.upload(f"{ctx.job_id}_front.png", front), "seed": int(spec["seed"])}
        out, version = self.c.run("03b_shape_hy21_single.json", inputs, timeout=ctx.remaining())
        ctx.state.setdefault("workflows", {})["03b_shape_hy21_single"] = version
        return ShapeResult(glb=normalise_glb(out["shape"][0]), co=None, tris=None, backend="comfy-hunyuan3d-2.1")


class ComfyTextureBackend:
    name = "comfy-hy-paint"

    def __init__(self, client: ComfyClient) -> None:
        self.c = client

    def paint(self, ctx, spec, wrapped_obj, coords, views):
        inputs = {f"view_{v}": self.c.upload(f"{ctx.job_id}_tex_{v}.png", b) for v, b in views.items()}
        inputs["mesh_obj"] = self.c.upload(f"{ctx.job_id}_wrapped.obj", wrapped_obj)
        inputs["resolution"] = int(ctx.quality["albedo_px"])
        out, version = self.c.run("04_texture_hy_paint.json", inputs, timeout=ctx.remaining())
        ctx.state.setdefault("workflows", {})["04_texture_hy_paint"] = version
        return out["albedo"][0]


def normalise_glb(data: bytes) -> bytes:
    """Centre, scale to 90 mm height, front = -Y / up = +Z (exported Y-up), decimate to ~300 k tris."""
    import numpy as np
    import trimesh

    scene = trimesh.load(io.BytesIO(data), file_type="glb", force="mesh")
    m = scene if isinstance(scene, trimesh.Trimesh) else scene.dump(concatenate=True)
    v = m.vertices.copy()  # glTF Y-up
    v -= [(v[:, 0].max() + v[:, 0].min()) / 2, v[:, 1].min(), (v[:, 2].max() + v[:, 2].min()) / 2]
    v *= 90.0 / max(np.ptp(v[:, 1]), 1e-6)
    m.vertices = v
    if len(m.faces) > 300_000:
        m = m.simplify_quadric_decimation(face_count=300_000)
    return m.export(file_type="glb")


