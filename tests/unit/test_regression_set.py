import json

from backend.core.paths import ROOT
from petpop_core.schemas import enum_slots, spec_errors


def test_regression_set_covers_every_ear_tail_and_coat_value():
    pets = json.loads((ROOT / "tests/regression/pets.json").read_text())["pets"]
    assert len(pets) == 30
    assert sum(p["spec"]["species"] == "dog" for p in pets) == 15
    slots = enum_slots()
    for slot in ("ears.shape", "tail.type", "coat.length", "coat.texture"):
        section, key = slot.split(".")
        seen = {p["spec"][section][key] for p in pets}
        assert seen == set(slots[slot]), f"{slot} missing {set(slots[slot]) - seen}"
    for p in pets:
        assert spec_errors(p["spec"]) == [], p["id"]
