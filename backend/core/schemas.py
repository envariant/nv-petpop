"""JSON Schema loading and validation for PetSpec and the job manifest."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from .paths import SCHEMA_DIR


@lru_cache
def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text())


@lru_cache
def validator(name: str) -> Draft202012Validator:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def spec_errors(spec: dict[str, Any]) -> list[str]:
    return [f"{'.'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in validator("petspec.schema.json").iter_errors(spec)]


def manifest_errors(manifest: dict[str, Any]) -> list[str]:
    return [f"{'.'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in validator("manifest.schema.json").iter_errors(manifest)]


def enum_slots() -> dict[str, list[Any]]:
    """Every closed enumeration (and boolean) in PetSpec, keyed by vocab slot path."""
    schema = load_schema("petspec.schema.json")
    defs = schema["$defs"]
    out: dict[str, list[Any]] = {}

    def resolve(node: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in node:
            node = defs[node["$ref"].split("/")[-1]]
        return node

    def walk(node: dict[str, Any], path: str) -> None:
        node = resolve(node)
        if path in ("colour.base", "colour.secondary", "eyes.second_colour", "accessories.colour_name"):
            return  # palettes are covered by vocab.palette / vocab.eye_palette
        if "enum" in node:
            out[path] = list(node["enum"])
        elif node.get("type") == "boolean":
            out[path] = [True, False]
        elif node.get("type") == "object":
            for k, v in node.get("properties", {}).items():
                walk(v, f"{path}.{k}" if path else k)
        elif node.get("type") == "array" and "items" in node:
            walk(node["items"], path)

    walk(schema, "")
    out.pop("spec_version", None)
    out.pop("eyes.colour", None)
    out.pop("eyes.second_colour", None)
    out["eyes.colour"] = list(resolve(defs["eye_colour"])["enum"])
    return out
