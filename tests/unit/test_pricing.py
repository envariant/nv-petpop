"""The price list's rules (decision 137): extras by kind with a fallback, options, free lines left out, the
environment's figurine price."""
from __future__ import annotations

import json

from backend.api import pricing


def test_rules(tmp_path, monkeypatch):
    pl = json.loads(pricing.CONFIG.read_text())
    pl["options"][1]["free"] = 3
    pl["options"][2]["prices"] = {"stocky": "6.00", "*": "0.00"}
    pl["options"][3]["prices"] = {"*": "2.50"}
    p = tmp_path / "pricing.json"
    p.write_text(json.dumps(pl))
    monkeypatch.setenv("PETPOP_PRICING", str(p))
    monkeypatch.delenv("PETPOP_PRICE_SGD", raising=False)
    kit = {"composition_version": "3.0", "species": "dog", "preset_id": "stocky", "pose_id": "play_bow",
           "texture": {"base": {"hex": "#000000"}, "markings": ["a", "b", "c", "d"]}, "shells": [{"part_id": "x_umbrella", "colour": "#000000"}]}
    q = pricing.quote(kit)
    assert [(i.label, i.amount) for i in q.items] == [("Figurine", "39.00"), ("X umbrella", "4.00"), ("Extra markings (1)", "1.00"),
                                                       ("Shape: Stocky", "6.00"), ("Pose: Play bow", "2.50")]
    assert q.total.amount == "52.50"
    monkeypatch.setenv("PETPOP_PRICE_SGD", "45")
    assert pricing.quote({"species": "dog", "pose_id": "sitting", "composition_version": "3.0"}).total.amount == "45.00"
