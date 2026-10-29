"""PetSpec -> image prompts (BRIEF Section 7).

Only vocabulary from the enumerations reaches the image model: every slot is replaced by its vocab.json
phrase, the breed hint comes from the preset file, personality is mapped through a fixed word list, and
the user's free text is never included.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from petpop_core.breeds import get_breed
from petpop_core.vocab import phrase, vocab

TEMPLATES = Path(__file__).parent / "templates"
VIEW_SUFFIX = {
    "front": "front view",
    "left": "left side view, profile",
    "back": "back view, from behind, tail visible",
    "right": "right side view, profile",
}
BANNED = re.compile(r"funko|pop!", re.I)


def _words(value: str) -> str:
    return str(value).replace("_", " ")


def _expression_words(personality: list[str]) -> str:
    words = vocab()["personality_words"]
    out = []
    for p in personality or []:
        key = p.strip().lower()
        if key in words and words[key] not in out:
            out.append(words[key])
    return ", ".join(out) or "friendly expression"


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), undefined=StrictUndefined, trim_blocks=True,
                      lstrip_blocks=True, autoescape=False)
    env.filters["words"] = _words
    env.filters["expression_words"] = _expression_words
    return env


def _slot(spec: dict[str, Any], slot: str) -> str:
    section, key = slot.split(".")
    value = spec[section][key]
    return phrase(slot, value) or ""


def vocab_view(spec: dict[str, Any]) -> dict[str, Any]:
    """A copy of the spec where every enumerated value is replaced by its vocab phrase."""
    v = vocab()
    breed = get_breed(spec["species"], spec["breed"]["id"]) or {"label": spec["breed"]["label"], "prompt_hint": ""}
    col = spec["colour"]
    acc = [{"type": phrase("accessories.type", a["type"]), "colour_name": v["palette"][a.get("colour_name") or "red"]["prompt"]}
           for a in spec.get("accessories", [])]
    return {
        "species": phrase("species", spec["species"]),
        "breed": {"label": breed["label"], "prompt_hint": breed["prompt_hint"].rstrip(".")},
        "coat": {"length": _slot(spec, "coat.length"), "texture": _slot(spec, "coat.texture")},
        "colour": {
            "base": {"name": v["palette"][col["base"]["name"]]["prompt"]},
            "secondary": {"name": v["palette"][col["secondary"]["name"]]["prompt"]} if col.get("secondary") else None,
            "pattern": phrase("colour.pattern", col["pattern"]),
        },
        "ears": {"size": _slot(spec, "ears.size"), "shape": _slot(spec, "ears.shape")},
        "tail": {"type": phrase("tail.type", spec["tail"]["type"])},
        "head": {"muzzle_length": _slot(spec, "head.muzzle_length")},
        "eyes": {"colour": v["eye_palette"][spec["eyes"]["colour"]]["prompt"]},
        "nose": {"colour": phrase("nose.colour", spec["nose"]["colour"])},
        "accessories": acc,
        "personality": spec.get("personality", []),
    }


def tidy(text: str) -> str:
    text = re.sub(r"\s+", " ", text.replace("\n", " "))
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",(\s*,)+", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    return BANNED.sub("", text).strip(" ,")


def compile_prompts(spec: dict[str, Any]) -> dict[str, Any]:
    env = _env()
    positive = tidy(env.get_template("positive.j2").render(**vocab_view(spec)))
    negative = tidy((TEMPLATES / "negative.txt").read_text())
    base = positive.replace(", front view, orthographic,", ", orthographic,")
    views = {k: f"{base}, {suffix}" for k, suffix in VIEW_SUFFIX.items()}
    return {"positive": positive, "negative": negative, "views": views}
