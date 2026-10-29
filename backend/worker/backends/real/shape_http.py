"""Shape service over HTTP (the Mac host's mac/shape_server, or any host serving the same API).

    POST {SHAPE_URL}/v1/shape   multipart: view_<name>=PNG ...; form field params=<json>
    -> 200 model/gltf-binary
    GET  {SHAPE_URL}/health     -> {"status": "ok", "engine": ..., "loaded": bool}

URL, model, views and parameters come from the GenAI profile.
"""
from __future__ import annotations

import json

import httpx

from ..base import ShapeResult
from .comfy import normalise_glb


class ShapeServiceError(RuntimeError):
    pass


class HttpShapeBackend:
    name = "http"

    def __init__(self, profile) -> None:
        self.profile = profile
        self.cfg = profile["shape"]
        self.url = profile.url(self.cfg["service"])
        self.headers = profile.auth_headers()

    def healthy(self) -> bool:
        try:
            return httpx.get(f"{self.url}/health", headers=self.headers, timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    def _call(self, ctx, images: dict[str, bytes], params: dict, seed: int) -> ShapeResult:
        body = {**params, "seed": seed, "unload_after": bool(self.profile["residency"].get("shape_unload_after_call")),
                "model": self.cfg.get("model")}
        files = {f"view_{v}": (f"{v}.png", data, "image/png") for v, data in images.items()}
        try:
            r = httpx.post(f"{self.url}/v1/shape", files=files, data={"params": json.dumps(body)}, headers=self.headers,
                           timeout=ctx.remaining())
        except httpx.HTTPError as exc:
            raise ShapeServiceError(f"shape service unreachable: {exc}") from exc
        if r.status_code != 200:
            raise ShapeServiceError(f"shape service {r.status_code}: {r.text[:300]}")
        ctx.state.setdefault("workflows", {})["shape_service"] = r.headers.get("x-engine", "unknown")
        return ShapeResult(glb=normalise_glb(r.content, self.cfg), co=None, tris=None, backend="http")

    def multiview(self, ctx, spec, views):
        return self._call(ctx, {v: views[v] for v in self.cfg["views"]}, self.cfg["params"], int(spec["seed"]))

    def single_view(self, ctx, spec, front):
        fb = self.cfg.get("fallback", {})
        return self._call(ctx, {"front": front}, {**self.cfg["params"], **fb.get("params", {})},
                          int(spec["seed"]) + int(fb.get("seed_offset", 1)))
