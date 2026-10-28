"""Validate HTTP responses against the committed OpenAPI document."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from backend.core.paths import SCHEMA_DIR


@lru_cache
def doc() -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / "openapi.json").read_text())


def schema_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": doc()["components"]})


def response_schema(path: str, method: str, status: int) -> dict[str, Any] | None:
    op = doc()["paths"][path][method]
    resp = op["responses"].get(str(status))
    assert resp is not None, f"{method.upper()} {path} has no documented {status} response"
    content = resp.get("content", {}).get("application/json")
    return content["schema"] if content else None


def check(path: str, method: str, response) -> Any:
    """Assert the status is documented and the JSON body matches its schema; return the body."""
    schema = response_schema(path, method, response.status_code)
    if schema is None:
        return response.content
    body = response.json()
    v = Draft202012Validator({**schema, "components": doc()["components"]})
    errors = [f"{list(e.absolute_path)}: {e.message}" for e in v.iter_errors(body)]
    assert not errors, f"{method.upper()} {path} {response.status_code} violates the contract: {errors[:5]}"
    return body
