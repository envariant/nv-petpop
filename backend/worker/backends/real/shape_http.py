"""Shape service over HTTP (the Mac host's mac/shape_server, or any host serving the same API).

    POST {SHAPE_URL}/v1/shape                multipart: view_<name>=PNG ...; form field params=<json>
                                             -> 202 {"job_id", "status"}
    GET  {SHAPE_URL}/v1/shape/{job_id}       -> {"status": queued|running|done|failed, "error", "seconds"}
    GET  {SHAPE_URL}/v1/shape/{job_id}/mesh  -> model/gltf-binary
    GET  {SHAPE_URL}/health                  -> {"status": "ok", "engine": ..., "loaded": bool}

A mesh takes minutes and the tunnel in front of the host cuts a request off after about 100 s, so the adapter
submits a job and polls it, like ComfyUI's /prompt and /history; no request waits on the model. URL, model,
views and parameters come from the GenAI profile.
"""
from __future__ import annotations

import json
import time

import httpx

from ..base import ShapeResult
from .comfy import normalise_glb


POLL_S = 3.0  # seconds between status polls
REQUEST_S = 30.0  # every single request: far below the tunnel's ~100 s cut-off
MAX_POLL_ERRORS = 5  # consecutive failed polls (a tunnel blip) before the job is given up


class ShapeServiceError(RuntimeError):
    pass


class HttpShapeBackend:
    name = "http"

    def __init__(self, profile, cfg: dict | None = None) -> None:
        self.profile = profile
        self.cfg = cfg or profile["shape"]  # cfg: the profile's shape.fallback when this serves only the single view
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
                           timeout=REQUEST_S)
        except httpx.HTTPError as exc:
            raise ShapeServiceError(f"shape service unreachable: {exc}") from exc
        if r.status_code != 202:
            raise ShapeServiceError(f"shape service {r.status_code}: {r.text[:300]}")
        job_id = r.json()["job_id"]
        errors = 0
        while True:
            if ctx.remaining() <= POLL_S:
                raise ShapeServiceError(f"shape job {job_id} did not finish in time")
            time.sleep(POLL_S)
            try:
                st = httpx.get(f"{self.url}/v1/shape/{job_id}", headers=self.headers, timeout=REQUEST_S)
                st.raise_for_status()
            except httpx.HTTPError as exc:
                errors += 1
                if errors >= MAX_POLL_ERRORS:
                    raise ShapeServiceError(f"shape job {job_id}: status unavailable ({exc})") from exc
                continue
            errors = 0
            state = st.json()
            if state["status"] == "failed":
                raise ShapeServiceError(f"shape job {job_id} failed: {state.get('error')}")
            if state["status"] == "done":
                break
        try:
            r = httpx.get(f"{self.url}/v1/shape/{job_id}/mesh", headers=self.headers, timeout=REQUEST_S)
        except httpx.HTTPError as exc:
            raise ShapeServiceError(f"shape job {job_id}: mesh download failed ({exc})") from exc
        if r.status_code != 200:
            raise ShapeServiceError(f"shape job {job_id} mesh {r.status_code}: {r.text[:300]}")
        ctx.state.setdefault("workflows", {})["shape_service"] = r.headers.get("x-engine", "unknown")
        return ShapeResult(glb=normalise_glb(r.content, self.cfg), co=None, tris=None, backend="http")

    def multiview(self, ctx, spec, views):
        return self._call(ctx, {v: views[v] for v in self.cfg["views"]}, self.cfg["params"], int(spec["seed"]))

    def single_view(self, ctx, spec, front):
        fb = self.cfg.get("fallback", {})
        return self._call(ctx, {"front": front}, {**self.cfg["params"], **fb.get("params", {})},
                          int(spec["seed"]) + int(fb.get("seed_offset", 1)))
