"""GenAI profiles (config/genai/<profile>.yaml), selected with GENAI_PROFILE (default: mock).

A profile is the only place that names a GenAI model, a host, a quality setting, a residency rule, a stage
timeout or an expected timing. The worker asks the profile; it never hard-codes any of them.
TEXTURE_BACKEND overrides the profile's texture backend (projection | flat | hy_paint) when allowed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .paths import CONFIG, SCHEMA_DIR

PROFILE_DIR = CONFIG / "genai"
DEFAULT_PROFILE = "mock"
STAGES = ["A", "control", "B", "C", "D", "E", "F"]


class ProfileError(RuntimeError):
    pass


def profile_name() -> str:
    return os.environ.get("GENAI_PROFILE", DEFAULT_PROFILE).strip() or DEFAULT_PROFILE


def available() -> list[str]:
    return sorted(p.stem for p in PROFILE_DIR.glob("*.yaml"))


@lru_cache
def _raw(name: str) -> tuple[dict[str, Any], str]:
    path = PROFILE_DIR / f"{name}.yaml"
    if not path.exists():
        raise ProfileError(f"unknown GENAI_PROFILE {name!r}; available: {', '.join(available())}")
    text = path.read_text()
    doc = yaml.safe_load(text)
    schema = json.loads((SCHEMA_DIR / "genai-profile.schema.json").read_text())
    errors = [f"{'.'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
              for e in Draft202012Validator(schema).iter_errors(doc)]
    if errors:
        raise ProfileError(f"{path.name} is invalid: {errors[:5]}")
    if doc["profile"] != name:
        raise ProfileError(f"{path.name} declares profile {doc['profile']!r}")
    if doc["quality"]["default"] not in doc["quality"]["presets"]:
        raise ProfileError(f"{path.name}: quality.default is not a preset")
    if doc["texture"]["backend"] not in doc["texture"]["allowed"]:
        raise ProfileError(f"{path.name}: texture.backend is not in texture.allowed")
    return doc, hashlib.sha256(text.encode()).hexdigest()[:12]


class Profile:
    """Read-only view of one profile plus the environment overrides that apply to it."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or profile_name()
        doc, self.digest = _raw(self.name)
        self.doc = copy.deepcopy(doc)
        texture = os.environ.get("TEXTURE_BACKEND", "").strip()
        if texture:
            if texture not in self.doc["texture"]["allowed"]:
                raise ProfileError(f"TEXTURE_BACKEND={texture} is not allowed on profile {self.name} "
                                   f"(allowed: {self.doc['texture']['allowed']})")
            self.doc["texture"]["backend"] = texture

    def __getitem__(self, key: str) -> Any:
        return self.doc[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.doc.get(key, default)

    @property
    def mode(self) -> str:
        return self.doc["mode"]

    def quality(self, preset: str | None = None) -> dict[str, Any]:
        preset = preset or os.environ.get("PETPOP_QUALITY") or self.doc["quality"]["default"]
        presets = self.doc["quality"]["presets"]
        if preset not in presets:
            raise ProfileError(f"PETPOP_QUALITY={preset} is not a preset of profile {self.name} ({sorted(presets)})")
        return dict(presets[preset], preset=preset)

    def timeout(self, stage: str) -> float:
        return float(self.doc["timeouts_s"][stage])

    def expected(self, stage: str) -> float:
        return float(self.doc["expected_s"][stage])

    def url(self, service: str) -> str:
        svc = self.doc["services"].get(service)
        if not isinstance(svc, dict):
            raise ProfileError(f"profile {self.name} has no service {service!r}")
        return (os.environ.get(svc["env"]) or svc["default"]).rstrip("/")

    def auth_headers(self) -> dict[str, str]:
        env = self.doc["services"].get("auth_token_env")
        token = os.environ.get(env, "") if env else ""
        return {"Authorization": f"Bearer {token}"} if token else {}

    def summary(self) -> dict[str, Any]:
        """What the manifest records: profile identity plus every model id the job may use."""
        d = self.doc
        models: dict[str, Any] = {}
        if d["parser"].get("model"):
            models["parser"] = d["parser"]["model"]
        for k, v in (d["image"].get("models") or {}).items():
            if v:
                models[f"image.{k}"] = v
        if d["shape"].get("model"):
            models["shape"] = d["shape"]["model"]
        for k, v in (d["shape"].get("models") or {}).items():
            models[f"shape.{k}"] = v
        for adapter, key in (("image", "model"), ("shape", "model_version")):
            if d[adapter]["backend"] == "api":  # a provider: record the model the profile asks it for
                models[f"{adapter}.{d[adapter]['provider']}"] = (d[adapter].get("params") or {}).get(key) or "provider default"
        for name, cfg in (d.get("providers") or {}).items():  # which API version (manifest) answered
            if cfg.get("manifest"):
                path = CONFIG / "providers" / f"{cfg['manifest']}.yaml"
                version = (yaml.safe_load(path.read_text()) or {}).get("version") if path.exists() else "?"
                models[f"provider.{name}"] = f"{cfg['manifest']} v{version}"
        if (d["shape"].get("fallback") or {}).get("model"):
            models["shape.fallback"] = d["shape"]["fallback"]["model"]
        if d["texture"]["backend"] == "hy_paint":
            models["texture"] = d["texture"]["hy_paint"]["model"]
        return {
            "profile": self.name, "profile_version": d["version"], "profile_sha": self.digest,
            "host": d["host"]["kind"], "accelerator": d["host"]["accelerator"],
            "adapters": {"parser": d["parser"]["backend"], "image": d["image"]["backend"],
                         "shape": d["shape"]["backend"], "texture": d["texture"]["backend"]},
            "models": models, "model_pins": model_pins(models.values()),
        }


@lru_cache
def _pins() -> dict[str, dict[str, str]]:
    """Model pins (repo revision + sha256) from pipelines/comfy/models.yaml, keyed by deployed file name."""
    path = Path(CONFIG.parent) / "pipelines" / "comfy" / "models.yaml"
    if not path.exists():
        return {}
    doc = yaml.safe_load(path.read_text()) or {}
    out = {}
    for m in doc.get("models", []):
        ident = m.get("deploy_as") or m.get("name")
        out[ident] = {k: str(m.get(k)) for k in ("repo", "revision", "sha256") if m.get(k)}
    for tag in doc.get("ollama", []):
        out[str(tag.get("tag") if isinstance(tag, dict) else tag)] = {"source": "ollama"}
    return out


def model_pins(models) -> dict[str, dict[str, str]]:
    pins = _pins()
    return {m: pins[m] for m in models if m in pins}


def current() -> Profile:
    return Profile()
