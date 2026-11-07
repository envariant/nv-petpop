"""Variable pricing (decision 137) on both servers: POST /kiosk/quote prices a design as it stands, line by line,
the same as the order's quote; extras by kind, options by rule, free choices add no line."""
from __future__ import annotations

from petpop_library.composition import sample, sample_kit

from .oas import check

K = "/api/v1/kiosk"


def test_a_design_is_priced_line_by_line(client):
    man = client.get(f"{K}/library/dog").json()["manifest"]
    comp = {**sample(man, layers=2), "shells": []}
    q = check(f"{K}/quote", "post", client.post(f"{K}/quote", json={"composition": comp}))
    assert [i["label"] for i in q["items"]] == ["Figurine"] and q["total"] == {"amount": "39.00", "currency": "SGD"}
    collar = next(s for s in man["shell_parts"] if s["kind"] == "collar")
    hat = next(s for s in man["shell_parts"] if s["kind"] == "hat")
    rich = {**sample(man, layers=5, stamps=3), "shells": [{"part_id": collar["id"], "colour": "#DD3333"}, {"part_id": hat["id"], "colour": "#3366CC"}]}
    q = client.post(f"{K}/quote", json={"composition": rich}).json()
    assert q["items"] == [{"label": "Figurine", "amount": "39.00"}, {"label": "Collar", "amount": "4.00"},
                          {"label": "Party hat", "amount": "5.00"}, {"label": "Hand-painted details", "amount": "3.00"}]
    assert q["total"]["amount"] == "51.00"  # five markings are within the free ones
    # a figure of part kits: a shape and the default pose are free (no line) at the placeholder prices
    kit = {**sample_kit(man, "labrador"), "preset_id": "stocky"}
    q = client.post(f"{K}/quote", json={"composition": kit}).json()
    assert q["total"]["amount"] == "39.00" and len(q["items"]) == 1
    assert client.post(f"{K}/quote", json={"composition": {"species": "fish"}}).status_code == 422
