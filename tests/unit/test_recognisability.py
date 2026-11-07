"""scripts/recognisability.py: the manual half of gate 9 (BRIEF Section 16: 70 % breed recognisability). A sheet of
library figurines with four breed names each, the key kept apart, answers scored, the gate's check."""
import importlib.util
import json

from backend.core.paths import ROOT

spec = importlib.util.spec_from_file_location("recognisability", ROOT / "scripts/recognisability.py")
rec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rec)


def test_sheet_record_and_check(tmp_path, monkeypatch):
    monkeypatch.setattr(rec, "OUT", tmp_path / "gate9")
    monkeypatch.setattr(rec, "RESULT", tmp_path / "docs" / "recognisability.json")
    assert rec.check() == 2  # nothing recorded: the gate prints SKIPPED
    assert rec.sheet([str(ROOT / "fixtures/library/release-dog-1.tar"), "--n", "5"]) == 0
    key = json.loads((tmp_path / "gate9/key.json").read_text())
    page = (tmp_path / "gate9/sheet.html").read_text()
    assert list(key["items"]) == ["q01"] and key["items"]["q01"]["breed_id"] == "labrador"  # the fixture's one kit
    assert page.count('data-q="q01"') == 4 and "data:image/png;base64," in page
    assert "Labrador Retriever" in page and "breed_id" not in page  # the options, never the key
    right = {"sheet": key["sheet"], "who": "a", "answers": {"q01": "Labrador Retriever"}}
    wrong = {"sheet": key["sheet"], "who": "b", "answers": {"q01": "Pug"}}
    files = []
    for i, a in enumerate([right, right, right, wrong]):
        f = tmp_path / f"answers-{i}.json"
        f.write_text(json.dumps(a))
        files.append(str(f))
    assert rec.record(files) == 0
    result = json.loads((tmp_path / "docs/recognisability.json").read_text())
    assert (result["right"], result["total"], result["pass"]) == (3, 4, True)
    assert rec.check() == 0
    assert rec.record(files[3:]) == 0 and rec.check() == 1  # 0 of 1: below 70 %
