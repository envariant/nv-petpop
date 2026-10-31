"""Manual mode (decision 111): the same manifest builds the same request the API would get, but instead of sending
it the provider writes it out as a manual task for the operator, who runs it in the vendor's own app (Tripo Studio,
with its own credits) and uploads the output in PetPop Studio. The job pauses (`waiting`) and, once the output is
in, resumes from its stored stages; this provider then hands the uploaded file back as if the API had returned it,
with a synthetic task record (`manual-...`, no credits).

Store layout per request, under the job:  manual/<request_id>/request.json   the packet the Studio inbox shows
                                          manual/<request_id>/<input>.png    files the operator uploads to the vendor
                                          manual/<request_id>/result         the operator's output
The request id hashes the capability, the request body and the inputs, so a resumed job finds its own result and a
different call (another seed, the single-view retry) is a new task.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from typing import Any

from .base import AwaitingOperator, Generated
from .manifest import ManifestProvider, _png

EXPECTS = {"text_to_image": "image", "image_to_model": "model", "multiview_to_model": "model"}
ACCEPT = {"image": [".png", ".jpg", ".jpeg", ".webp"], "model": [".glb"]}
INPUT_FIELDS = {"$image", "$views"}


def _settings(body: dict[str, Any], cap: dict[str, Any]) -> list[str]:
    """The request's options as 'field: value' lines (the prompt and inputs are shown on their own)."""
    skip = {k for k, v in cap["body"].items() if isinstance(v, str) and v.startswith("$")}
    return [f"{k}: {json.dumps(v) if not isinstance(v, str) else v}" for k, v in body.items() if k not in skip]


class ManualProvider(ManifestProvider):
    def __init__(self, profile, provider: str) -> None:
        super().__init__(profile, provider)
        self.name = f"{provider} (manual)"

    def _key(self, ctx, rid: str, name: str) -> str:
        return ctx.key(f"manual/{rid}/{name}")

    def _manual(self, ctx, capability: str, values: dict[str, Any], inputs: dict[str, bytes], params: dict[str, Any],
                seed: int | None) -> Generated:
        cap, body = self.request(capability, values, params, seed)
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode())
        for name in sorted(inputs):
            digest.update(name.encode() + hashlib.sha256(inputs[name]).digest())
        rid = f"{capability.replace('_', '-')}-{digest.hexdigest()[:10]}"
        kind = EXPECTS[capability]
        result_key = self._key(ctx, rid, "result")
        if ctx.store.exists(result_key):
            data = ctx.store.get(result_key)
            return Generated(_png(data) if kind == "image" else data, f"manual-{rid}", None,
                             {"output": {"manual": True, "result_key": result_key}})
        stored = []
        for name, data in inputs.items():
            key = self._key(ctx, rid, name)
            ctx.store.put(key, data)
            stored.append({"name": name, "key": key})
        manual = cap.get("manual") or {}
        packet = {
            "task_id": f"{ctx.job_id}.{rid}", "job_id": ctx.job_id, "request_id": rid, "capability": capability,
            "title": manual.get("title", capability.replace("_", " ")), "provider": self.name, "vendor": self.m["vendor"],
            "manifest": f"{self.m['manifest']} v{self.m['version']}", "route": cap["route"], "request": body,
            "prompt": values.get("prompt"), "negative_prompt": values.get("negative"),
            "settings": _settings(body, cap), "inputs": stored, "instructions": list(manual.get("steps", [])),
            "expects": {"kind": kind, "accept": ACCEPT[kind]}, "result_key": result_key,
            "created_at": datetime.now(UTC).isoformat(),
        }
        ctx.store.put(self._key(ctx, rid, "request.json"), json.dumps(packet, indent=1).encode())
        raise AwaitingOperator(packet)

    # ------------------------------------------------------------------ capabilities
    def text_to_image(self, ctx, prompt, negative, params, seed) -> Generated:
        return self._manual(ctx, "text_to_image", {"prompt": prompt, "negative": negative}, {}, params, None)

    def image_to_model(self, ctx, image, params, seed) -> Generated:
        name = "input.png"
        return self._manual(ctx, "image_to_model", {"image": f"<upload {name}>"}, {name: image}, params, seed)

    def multiview_to_model(self, ctx, views, params, seed) -> Generated:
        order = self.m["capabilities"].get("multiview_to_model", {}).get("views", ["front", "left", "back", "right"])
        tokens = [f"<upload {v}.png>" if v in views else None for v in order]
        return self._manual(ctx, "multiview_to_model", {"views": tokens}, {f"{v}.png": views[v] for v in views}, params, seed)

    def balance(self) -> dict[str, Any]:
        return {"mode": "manual", "note": "credits are spent in the vendor's own app"}


def check_output(kind: str, filename: str, data: bytes) -> str | None:
    """Why an uploaded output cannot be used, or None: an image must decode; a model must be a GLB with faces."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ACCEPT[kind]:
        return f"expected {' or '.join(ACCEPT[kind])}, got {ext or 'no extension'}"
    try:
        if kind == "image":
            from PIL import Image

            Image.open(io.BytesIO(data)).verify()
        else:
            import numpy as np
            import trimesh

            why = glb_extensions_problem(data)
            if why:
                return why
            m = trimesh.load(io.BytesIO(data), file_type="glb", force="mesh")
            if len(m.faces) == 0:
                return "the GLB has no faces"
            if float(np.ptp(np.asarray(m.vertices), axis=0).max()) <= 1e-9:
                return "the GLB's vertices did not decode (all at one point); export it without mesh compression"
    except Exception as exc:  # noqa: BLE001 - any unreadable upload is refused with the reason
        return f"unreadable {kind}: {exc}"[:200]
    return None


def glb_extensions_problem(data: bytes) -> str | None:
    """A required glTF extension the worker cannot decode (meshopt; Draco without DracoPy), as an operator hint."""
    import struct

    if len(data) < 20 or data[:4] != b"glTF":
        return "not a binary glTF (.glb) file"
    length, ctype = struct.unpack_from("<II", data, 12)
    if ctype != 0x4E4F534A:  # "JSON"
        return "the GLB has no JSON chunk"
    required = set(json.loads(data[20:20 + length]).get("extensionsRequired", []))
    if "EXT_meshopt_compression" in required:
        return "the GLB uses meshopt compression, which cannot be read here; export it without mesh compression"
    if "KHR_draco_mesh_compression" in required:
        try:
            import DracoPy  # noqa: F401
        except ImportError:
            return "the GLB uses Draco compression and DracoPy is not installed; export it without mesh compression"
    return None
