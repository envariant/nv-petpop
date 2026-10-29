"""Schema, vocabulary and preset invariants (BRIEF Sections 3 and 7)."""
from __future__ import annotations

from jsonschema import Draft202012Validator

from petpop_core.breeds import all_breeds
from petpop_core.schemas import enum_slots, load_schema
from petpop_core.spec import default_spec
from petpop_core.vocab import morph_weights, vocab


def test_schemas_are_valid_json_schema():
    for name in ("petspec.schema.json", "manifest.schema.json"):
        Draft202012Validator.check_schema(load_schema(name))


def test_every_enumeration_value_has_prompt_and_morph():
    v = vocab()
    slots = enum_slots()
    assert len(slots) >= 20
    for slot, values in slots.items():
        assert slot in v["slots"], f"vocab.json has no slot {slot}"
        for value in values:
            key = ("true" if value else "false") if isinstance(value, bool) else value
            entry = v["slots"][slot].get(key)
            assert entry is not None, f"{slot}={key} missing from vocab.json"
            assert "prompt" in entry and isinstance(entry["prompt"], str), f"{slot}={key} has no prompt phrase"
            assert "morph" in entry and isinstance(entry["morph"], dict), f"{slot}={key} has no morph mapping"
        extra = set(v["slots"][slot]) - {("true" if x else "false") if isinstance(x, bool) else x for x in values}
        assert not extra, f"vocab.json {slot} has values not in the schema: {extra}"


def test_morph_mappings_name_real_targets():
    v = vocab()
    known = set(v["morph_targets"]["dog"]) | set(v["morph_targets"]["cat"])
    for slot, values in v["slots"].items():
        for key, entry in values.items():
            for target in entry["morph"]:
                assert target in known, f"{slot}={key} maps to unknown morph {target}"
    assert len(v["morph_targets"]["dog"]) == 15 and len(v["morph_targets"]["cat"]) == 12


def test_palettes_cover_schema():
    schema = load_schema("petspec.schema.json")
    assert set(schema["$defs"]["palette_name"]["enum"]) == set(vocab()["palette"])
    assert set(schema["$defs"]["eye_colour"]["enum"]) == set(vocab()["eye_palette"])


def test_breed_preset_counts_and_validity():
    dogs, cats = all_breeds("dog"), all_breeds("cat")
    assert 55 <= len(dogs) <= 70 and 22 <= len(cats) <= 30
    for b in dogs + cats:
        assert b["prompt_hint"].count(".") >= 1 and len(b["prompt_hint"]) < 200
        spec = default_spec(b["species"], b["id"], seed=1)
        w = morph_weights(spec)
        assert set(w) == set(vocab()["morph_targets"][b["species"]])
        assert all(-1 <= x <= 1 for x in w.values())
