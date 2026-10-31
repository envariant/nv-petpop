"""The segmentation schema (decision 116) is valid and matches the template meshes that transfer it."""
import json

import jsonschema
import pytest

from petpop_core.paths import ROOT
from petpop_library.meshkit import load_base

SCHEMA = json.loads((ROOT / "data/schema/segmentation.schema.json").read_text())


@pytest.mark.parametrize("species", ["dog", "cat"])
def test_schema_matches_template(species):
    doc = json.loads((ROOT / f"data/segmentation/{species}.json").read_text())
    jsonschema.validate(doc, SCHEMA)
    base = load_base(species)
    parts = [p["name"] for p in doc["parts"]]
    assert sorted(parts) == sorted(base.group_names)
    assert sorted(doc["landmarks"]) == sorted(base.landmarks)
    assert sorted(doc["pattern_regions"]) == sorted(base.mask_names)
    for region, members in doc["regions"].items():
        assert set(members) <= set(parts), region
    for lm, allowed in doc["landmarks"].items():
        assert set(allowed) <= set(parts)
        assert any(base.group(p)[base.landmarks[lm]] > 0 for p in allowed), (lm, allowed)
    for sock in doc["sockets"].values():
        assert set(sock["landmarks"]) <= set(doc["landmarks"])
