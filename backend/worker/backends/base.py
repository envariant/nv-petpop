"""Adapter interfaces for the three GPU services (BRIEF Section 13). PETPOP_MODE picks mock or real
implementations; the stages, API and SPA never know which one runs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np


@dataclass
class ShapeResult:
    glb: bytes                  # Y-up GLB of the generated shape (90 mm, front -Y before export)
    co: np.ndarray | None       # Z-up vertex positions when the backend knows them (mock), for the IoU check
    tris: np.ndarray | None
    backend: str


class Parser(Protocol):
    name: str
    def available(self) -> bool: ...
    def parse(self, text: str, species: str, current: dict[str, Any], tapped: list[str]) -> Any: ...


class ImageBackend(Protocol):
    name: str
    def concept(self, ctx, spec: dict[str, Any], prompts: dict[str, Any], control: dict[str, bytes]) -> bytes: ...
    def views(self, ctx, spec: dict[str, Any], prompts: dict[str, Any], control: dict[str, bytes], concept: bytes) -> dict[str, bytes]: ...


class ShapeBackend(Protocol):
    name: str
    def multiview(self, ctx, spec: dict[str, Any], views: dict[str, bytes]) -> ShapeResult: ...
    def single_view(self, ctx, spec: dict[str, Any], front: bytes) -> ShapeResult: ...


class TextureBackend(Protocol):
    name: str
    def paint(self, ctx, spec: dict[str, Any], wrapped_obj: bytes, coords: np.ndarray, views: dict[str, bytes]) -> bytes: ...


@dataclass
class Backends:
    parser: Parser
    image: ImageBackend
    shape: ShapeBackend
    texture: TextureBackend


def make_backends(settings) -> Backends:
    """PETPOP_MODE picks mock or real for all four adapters; PETPOP_ADAPTERS overrides them one by one for
    the S3 bring-up order (B, then C, D, texture), e.g. PETPOP_ADAPTERS=image=real,parser=real."""
    import os

    choice = {k: settings.mode for k in ("parser", "image", "shape", "texture")}
    for item in filter(None, os.environ.get("PETPOP_ADAPTERS", "").split(",")):
        k, _, v = item.partition("=")
        if k.strip() in choice and v.strip() in ("mock", "real"):
            choice[k.strip()] = v.strip()
    client = None
    if "real" in (choice["image"], choice["shape"], choice["texture"]):
        from .real.comfy import ComfyClient

        client = ComfyClient(settings.comfy_url)

    def pick(kind: str):
        if choice[kind] == "real":
            from .real import comfy, ollama

            return {"parser": lambda: ollama.OllamaParser(settings.ollama_url, settings.ollama_model),
                    "image": lambda: comfy.ComfyImageBackend(client), "shape": lambda: comfy.ComfyShapeBackend(client),
                    "texture": lambda: comfy.ComfyTextureBackend(client)}[kind]()
        from .mock import image, parser, shape, texture

        return {"parser": parser.RuleParser, "image": image.MockImageBackend, "shape": shape.MockShapeBackend,
                "texture": texture.MockTextureBackend}[kind]()

    return Backends(pick("parser"), pick("image"), pick("shape"), pick("texture"))
