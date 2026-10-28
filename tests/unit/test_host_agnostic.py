"""The worker must never name a model or a host (M2.5): every endpoint, model id, port and model file lives in
config/genai/<profile>.yaml. Scans string literals (docstrings excluded) in the worker and the settings."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from backend.core.paths import ROOT

FORBIDDEN = [
    (re.compile(r"https?://"), "URL"),
    (re.compile(r"\b(localhost|127\.0\.0\.1|comfyui|ollama:)\b"), "host"),
    (re.compile(r"\b(8188|8190|11434)\b"), "port"),
    (re.compile(r"\.(safetensors|ckpt|gguf|bin)\b"), "model file"),
    (re.compile(r"qwen|llama|hunyuan|sdxl|sd_xl|ip-adapter|controlnet|mvadapter|birefnet", re.I), "model name"),
    (re.compile(r"\b0[1-4]b?_[a-z0-9_]+\.json\b"), "workflow file"),
]
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
SCANNED = [*sorted((ROOT / "backend" / "worker").rglob("*.py")), ROOT / "backend" / "core" / "config.py"]


def docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def test_worker_names_no_model_or_host():
    problems = []
    for path in SCANNED:
        tree = ast.parse(path.read_text())
        docs = docstring_nodes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                for rx, what in FORBIDDEN:
                    if what == "model name" and IDENTIFIER.match(node.value):
                        continue  # config keys and backend kinds (controlnet_strength, ollama) are roles, not models
                    if rx.search(node.value):
                        problems.append(f"{path.relative_to(ROOT)}:{node.lineno}: {what} in {node.value[:60]!r}")
    assert not problems, "\n".join(problems)


def test_scan_covers_the_adapters():
    names = {p.name for p in SCANNED}
    assert {"comfy.py", "ollama.py", "shape_http.py", "runner.py", "texture.py", "config.py"} <= names
