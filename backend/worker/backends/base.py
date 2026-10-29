"""Adapter interfaces for the GenAI stages (BRIEF Section 13). The GenAI profile (GENAI_PROFILE) picks the
backend for each adapter and supplies every model id, host and parameter; the stages, API and SPA never
know which one runs. PETPOP_ADAPTERS can force single adapters back to mock during a host bring-up."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np


@dataclass
class ShapeResult:
    glb: bytes                  # Y-up GLB of the generated shape (height and orientation normalised)
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
    profile = settings.genai
    forced = {}
    for item in filter(None, os.environ.get("PETPOP_ADAPTERS", "").split(",")):
        k, _, v = item.partition("=")
        forced[k.strip()] = v.strip()

    def kind(adapter: str) -> str:
        if forced.get(adapter) == "mock":
            return "mock" if adapter != "parser" else "rules"
        return profile[adapter]["backend"]

    clients: dict[str, Any] = {}

    def comfy():
        from .real.comfy import ComfyClient

        if "comfy" not in clients:
            clients["comfy"] = ComfyClient(profile)
        return clients["comfy"]

    parser_kind, image_kind, shape_kind = kind("parser"), kind("image"), kind("shape")
    if parser_kind == "ollama":
        from .real.ollama import OllamaParser

        parser = OllamaParser(profile)
    else:
        from .mock.parser import RuleParser

        parser = RuleParser()
    if image_kind == "comfy":
        from .real.comfy import ComfyImageBackend

        image = ComfyImageBackend(comfy(), profile)
    else:
        from .mock.image import MockImageBackend

        image = MockImageBackend()
    if shape_kind == "comfy":
        from .real.comfy import ComfyShapeBackend

        shape = ComfyShapeBackend(comfy(), profile)
    elif shape_kind == "http":
        from .real.shape_http import HttpShapeBackend

        shape = HttpShapeBackend(profile)
    else:
        from .mock.shape import MockShapeBackend

        shape = MockShapeBackend(profile)
    from .texture import make_texture

    texture = make_texture(profile, comfy if profile["texture"]["backend"] == "hy_paint" else None)
    return Backends(parser, image, shape, texture)
