"""A provider driven by a manifest (config/providers/<name>.yaml, data/schema/provider-manifest.schema.json): the
vendor's routes, auth, envelope, upload, task polling and field names are data, so an equivalent API is a new
manifest and a profile entry, not new code (decision 109). The retry and credit rules are TaskClient's (base.py).
"""
from __future__ import annotations

import io
import json
import time
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import yaml
from jsonschema import Draft202012Validator
from PIL import Image

from backend.core.paths import CONFIG, SCHEMA_DIR

from .base import Generated, ProviderError, ProviderUnsupported, TaskClient, provider_config

MANIFEST_DIR = CONFIG / "providers"


@lru_cache
def load_manifest(name: str) -> dict[str, Any]:
    path = MANIFEST_DIR / f"{name}.yaml"
    if not path.exists():
        raise ProviderError(f"no provider manifest {name!r} in config/providers")
    doc = yaml.safe_load(path.read_text())
    schema = json.loads((SCHEMA_DIR / "provider-manifest.schema.json").read_text())
    errors = [f"{'.'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in Draft202012Validator(schema).iter_errors(doc)]
    if errors:
        raise ProviderError(f"{path.name} is invalid: {errors[:5]}")
    if doc["manifest"] != name:
        raise ProviderError(f"{path.name} declares manifest {doc['manifest']!r}")
    return doc


def dig(obj: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _route(route: str, **fields) -> tuple[str, str]:
    method, _, path = route.partition(" ")
    return method, path.format(**fields)


class ManifestProvider:
    def __init__(self, profile, provider: str) -> None:
        cfg = provider_config(profile, provider)
        self.m = load_manifest(cfg["manifest"])
        self.name = provider
        self.api = TaskClient(cfg)

    # ------------------------------------------------------------------ plumbing
    def _data(self, r, what: str) -> Any:
        try:
            body = r.json()
        except ValueError as exc:
            raise ProviderError(f"{what}: HTTP {r.status_code}, not JSON: {r.text[:200]}") from exc
        env = self.m["envelope"]
        code = dig(body, env["code"]) if env.get("code") else None
        if r.status_code >= 400 or (env.get("code") and code not in env.get("ok", [0])):
            msg = " ".join(str(dig(body, k)) for k in env.get("message", []) if dig(body, k))
            raise ProviderError(f"{what}: HTTP {r.status_code} code {code}: {msg or r.text[:200]}")
        return dig(body, env["data"]) if env.get("data") else body

    def _call(self, route: str, what: str, **kw) -> Any:
        method, path = _route(route, **kw.pop("fields", {}))
        r = self.api.get(path) if method == "GET" else self.api.post(path, **kw)
        return self._data(r, what)

    def upload(self, data: bytes, name: str = "image.png") -> str:
        up = self.m["upload"]
        token = dig(self._call(up["route"], "upload", files={up["form_field"]: (name, data, "image/png")}), up["token"])
        if not token:
            raise ProviderError("upload returned no token")
        return str(token)

    def _wait(self, ctx, task_id: str) -> dict[str, Any]:
        t, n = self.m["tasks"], 0
        while True:
            task = self._call(t["poll"], f"task {task_id}", fields={"task_id": task_id})
            status = str(dig(task, t["status"]) or "").lower()
            if status in t["success"]:
                return task
            if status in t.get("failed", []):
                why = " ".join(str(dig(task, k)) for k in t.get("error", []) if dig(task, k) is not None)
                raise ProviderError(f"{self.name} task {task_id} {status}: {why}".strip())
            wait = self.api.poll_interval(n)
            if ctx.remaining() <= wait:
                raise ProviderError(f"{self.name} task {task_id} still {status} at the stage deadline "
                                    "(it keeps running and is charged)")
            time.sleep(wait)
            n += 1

    def _run(self, ctx, capability: str, values: dict[str, Any], params: dict[str, Any], seed: int | None) -> Generated:
        cap = self.m["capabilities"].get(capability)
        if cap is None:
            raise ProviderUnsupported(f"{self.name} ({self.m['manifest']}) has no {capability}")
        body = {k: values.get(v[1:]) if isinstance(v, str) and v.startswith("$") else v for k, v in cap["body"].items()}
        body = {k: v for k, v in body.items() if v not in (None, "")}
        rename = cap.get("rename", {})
        body.update({rename.get(k, k): v for k, v in params.items() if v is not None})
        for field in cap.get("seeds", []):
            if seed is not None and field not in body:
                body[field] = seed
        body.update(self.m.get("create_extras") or {})
        t = self.m["tasks"]
        task_id = dig(self._call(cap["route"], capability, json=body), t["id"])
        if not task_id:
            raise ProviderError(f"{capability} returned no task id")
        task = self._wait(ctx, str(task_id))
        output = dig(task, t["output"]) or {}
        url = next((u for u in (dig(output, k) for k in cap["result"])
                    if isinstance(u, str) and urlparse(u).scheme in ("http", "https")), None)
        if not url:
            raise ProviderError(f"{self.name} task {task_id} output has none of {cap['result']}: {sorted(output)}")
        credits = dig(task, t["credits"]) if t.get("credits") else None
        return Generated(self.api.download(url), str(task_id), float(credits) if credits is not None else None,
                         {"output": output})

    # ------------------------------------------------------------------ capabilities
    def text_to_image(self, ctx, prompt, negative, params, seed) -> Generated:
        g = self._run(ctx, "text_to_image", {"prompt": prompt, "negative": negative}, params, None)
        g.data = _png(g.data)
        return g

    def image_to_model(self, ctx, image, params, seed) -> Generated:
        return self._run(ctx, "image_to_model", {"image": self.upload(image)}, params, seed)

    def multiview_to_model(self, ctx, views, params, seed) -> Generated:
        order = self.m["capabilities"].get("multiview_to_model", {}).get("views", ["front", "left", "back", "right"])
        if "front" not in views:
            raise ProviderError("multiview_to_model needs the front view")
        tokens = [self.upload(views[v], f"{v}.png") if v in views else None for v in order]
        return self._run(ctx, "multiview_to_model", {"views": tokens}, params, seed)

    def balance(self) -> dict[str, Any]:
        if not self.m.get("balance"):
            raise ProviderUnsupported(f"{self.name} has no balance route")
        return self._call(self.m["balance"], "balance")

    def describe(self) -> dict[str, Any]:
        """What the manifest records about rights: private generation and commercial use."""
        return {"manifest": self.m["manifest"], "vendor": self.m["vendor"], "licence": self.m["licence"]}


def _png(data: bytes) -> bytes:
    """Generated images may come back as JPEG or WebP; the pipeline stores PNG."""
    img = Image.open(io.BytesIO(data))
    if img.format == "PNG":
        return data
    buf = io.BytesIO()
    img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(buf, format="PNG")
    return buf.getvalue()
