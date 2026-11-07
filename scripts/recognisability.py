#!/usr/bin/env python3
"""Gate 9's breed recognisability (BRIEF Section 16: 70 % on library figurines), the manual half of the gate.

    python scripts/recognisability.py sheet [--n 20] [--seed 0] [release bundles or species ...]
    python scripts/recognisability.py record var/gate9/answers-*.json
    python scripts/recognisability.py check

`sheet` picks up to N figurines from the newest releases (dog and cat by default): every breed's part kit, composed
in its default design and rendered, and families on generated meshes, by their thumbnails. It writes
var/gate9/sheet.html, a page to show people who do not know the breeds: each figurine with four breed names to choose
from, one right. The answer key stays in var/gate9/key.json, not in the page. At the end the page offers the answers
as a file. `record` scores any number of those files against the key and writes docs/gate9/recognisability.json,
which the gate reads; `check` exits 0 at 70 % or more, 1 below it and 2 when nothing is recorded yet (the gate prints
SKIPPED: the final manual pass).
"""
from __future__ import annotations

import base64
import html
import io
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend  # noqa: E402,F401  (puts packages/*/python on sys.path)

from petpop_core.breeds import all_breeds  # noqa: E402
from petpop_library import release  # noqa: E402

OUT = ROOT / "var" / "gate9"
RESULT = ROOT / "docs" / "gate9" / "recognisability.json"
PASS = 0.70


def newest(species: str) -> Path:
    found = [p for d in (ROOT / "var" / "releases" / "inbox", ROOT / "fixtures" / "library") for p in d.glob(f"release-{species}-*.tar")]
    if not found:
        raise SystemExit(f"no release bundle for {species}")
    return max(found, key=lambda p: int(p.stem.rsplit("-", 1)[1]))


def kit_render(manifest: dict, files: dict[str, bytes], kit: dict, size: int = 320) -> bytes:
    """A kit's default design (its defaults, standard shape, default pose and texture) composed and painted as the
    print is, rendered at a three-quarter view."""
    from PIL import Image

    from petpop_library import kit_figure
    from petpop_library.composition import sample_kit
    from petpop_library.meshkit import render

    class Mem(release.Release):
        def file(self, path: str) -> bytes:
            return files[path]

    rel = Mem(manifest, Path("."))
    comp = sample_kit(manifest, kit["breed_id"])
    mesh, co, atlas = kit_figure.build(manifest["species"], kit, comp, rel.file, rel.mask_file, tile=128)
    t = len(mesh.tri_verts)
    corner_co = co[mesh.tri_verts].reshape(-1, 3)
    uv = mesh.uv.reshape(-1, 2)
    h, w, _ = atlas.shape
    px = atlas[np.clip(((1 - uv[:, 1]) * h).astype(int), 0, h - 1), np.clip((uv[:, 0] * w).astype(int), 0, w - 1)]
    lo, hi = corner_co.min(axis=0), corner_co.max(axis=0)
    extent = float(max(hi - lo)) * 1.15
    r = render(corner_co, np.arange(t * 3).reshape(t, 3), 30.0, size, colours=px.astype(np.float64) / 255.0,
               extent=extent, centre_z=float((lo[2] + hi[2]) / 2))
    rgb = (np.clip(r["rgb"], 0, 1) * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(np.dstack([rgb, (r["alpha"] * 255).astype(np.uint8)]), "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def candidates(paths: list[Path]) -> list[dict]:
    """Every figurine a customer could start from: a kit per breed, else a family on a generated mesh."""
    out = []
    for path in paths:
        manifest, files = release.read(path.read_bytes())
        species = manifest["species"]
        labels = {b["id"]: b["label"] for b in all_breeds(species)}
        kits = {k["breed_id"] for k in manifest.get("kits") or []}
        for kit in manifest.get("kits") or []:
            out.append({"species": species, "breed_id": kit["breed_id"], "label": labels.get(kit["breed_id"], kit["breed_id"]),
                        "source": f"kit {kit['breed_id']} v{kit['version']} ({manifest['release_version']})",
                        "image": lambda m=manifest, f=files, k=kit: kit_render(m, f, k)})
        generated = {m["id"] for m in manifest["meshes"] if m.get("source") == "generated"}
        for fam in manifest["families"]:
            if fam["mesh_id"] not in generated or not fam.get("thumbnail"):
                continue
            for b in fam["breeds"]:
                if b in kits or b not in labels:
                    continue
                out.append({"species": species, "breed_id": b, "label": labels[b], "source": f"family {fam['id']} ({manifest['release_version']})",
                            "image": lambda f=files, t=fam["thumbnail"]: f[t]})
    return out


def sheet(args: list[str]) -> int:
    n, seed, targets = 20, 0, []
    it = iter(args)
    for a in it:
        if a == "--n":
            n = int(next(it))
        elif a == "--seed":
            seed = int(next(it))
        else:
            targets.append(a)
    paths = [Path(t) if t.endswith(".tar") else newest(t) for t in (targets or ["dog", "cat"])]
    pool = candidates(paths)
    if not pool:
        print("no figurines to rate yet: no part kit and no family on a generated mesh in " + ", ".join(p.name for p in paths))
        return 1
    rng = random.Random(seed)
    picked = rng.sample(pool, min(n, len(pool)))
    OUT.mkdir(parents=True, exist_ok=True)
    items, key = [], {}
    for i, c in enumerate(picked, 1):
        others = [b["label"] for b in all_breeds(c["species"]) if b["id"] not in (c["breed_id"], "mixed")]
        options = rng.sample(others, 3) + [c["label"]]
        rng.shuffle(options)
        qid = f"q{i:02d}"
        key[qid] = {"breed_id": c["breed_id"], "label": c["label"], "source": c["source"]}
        items.append((qid, base64.b64encode(c["image"]()).decode(), options))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (OUT / "key.json").write_text(json.dumps({"sheet": stamp, "items": key}, indent=1) + "\n")
    (OUT / "sheet.html").write_text(page(stamp, items))
    print(f"{OUT / 'sheet.html'}: {len(items)} figurines from {len(pool)} ({', '.join(p.name for p in paths)}); key in {OUT / 'key.json'}")
    return 0


def page(stamp: str, items: list[tuple[str, str, list[str]]]) -> str:
    cards = []
    for qid, img, options in items:
        buttons = "".join(f'<button type="button" data-q="{qid}" data-a="{html.escape(o)}">{html.escape(o)}</button>' for o in options)
        cards.append(f'<section><img alt="figurine {qid[1:]}" src="data:image/png;base64,{img}"><p>Which breed is this?</p>'
                     f'<div class="opts">{buttons}</div></section>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Which breed?</title>
<style>
:root {{ --bg: #fbf6f1; --card: #ffffff; --ink: #2a2522; --accent: #f08a3c; --line: #e6ddd4; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #1d1a18; --card: #2a2623; --ink: #f3ede7; --line: #3d3733; }} }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font: 17px/1.4 system-ui, sans-serif; }}
main {{ max-width: 720px; margin: 0 auto; padding: 16px; }}
section {{ background: var(--card); border-radius: 18px; padding: 16px; margin: 0 0 16px; text-align: center; }}
img {{ width: 100%; max-width: 320px; height: auto; }}
.opts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
button {{ font: inherit; padding: 12px; border-radius: 12px; border: 2px solid var(--line); background: transparent; color: inherit; }}
button[aria-pressed=true] {{ border-color: var(--accent); background: var(--accent); color: #fff; }}
#done {{ display: block; width: 100%; background: var(--accent); color: #fff; border: 0; }}
</style></head>
<body><main>
<h1>Which breed?</h1>
<p>Look at each figurine and pick the breed you think it is. Go with your first guess.</p>
<label>Your name or initials (optional) <input id="who"></label>
{''.join(cards)}
<button id="done" type="button">Finish and save my answers</button>
<p id="saved"></p>
</main>
<script>
const answers = {{}};
document.querySelectorAll('button[data-q]').forEach((b) => b.addEventListener('click', () => {{
  answers[b.dataset.q] = b.dataset.a;
  document.querySelectorAll(`button[data-q="${{b.dataset.q}}"]`).forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
}}));
document.getElementById('done').addEventListener('click', () => {{
  const who = document.getElementById('who').value.trim() || 'anonymous';
  const blob = new Blob([JSON.stringify({{ sheet: '{stamp}', who, answers }}, null, 1)], {{ type: 'application/json' }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `answers-${{who.replace(/[^a-z0-9]+/gi, '_')}}-${{Date.now()}}.json`;
  a.click();
  document.getElementById('saved').textContent = `Saved ${{Object.keys(answers).length}} answers. Thank you!`;
}});
</script>
</body></html>
"""


def record(files: list[str]) -> int:
    key = json.loads((OUT / "key.json").read_text())
    right = total = 0
    people = []
    for f in files:
        a = json.loads(Path(f).read_text())
        if a.get("sheet") != key["sheet"]:
            print(f"{f}: answers to another sheet ({a.get('sheet')}), skipped")
            continue
        got = sum(1 for q, item in key["items"].items() if a["answers"].get(q) == item["label"])
        right += got
        total += len(key["items"])
        people.append({"who": a.get("who", "anonymous"), "right": got, "of": len(key["items"])})
    if not total:
        print("no answers to this sheet")
        return 1
    share = right / total
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps({"sheet": key["sheet"], "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                                  "people": people, "right": right, "total": total, "share": round(share, 4),
                                  "pass": share >= PASS, "threshold": PASS}, indent=1) + "\n")
    print(f"{right}/{total} right ({share * 100:.1f} %) from {len(people)} people: {'PASS' if share >= PASS else 'below 70 %'} -> {RESULT}")
    return 0


def check() -> int:
    if not RESULT.exists():
        print("no recognisability result recorded yet (scripts/recognisability.py sheet, then record)")
        return 2
    r = json.loads(RESULT.read_text())
    print(f"recognisability {r['right']}/{r['total']} ({r['share'] * 100:.1f} %) from {len(r['people'])} people on sheet {r['sheet']}")
    return 0 if r["share"] >= PASS else 1


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("sheet", "record", "check"):
        print(__doc__)
        return 2
    cmd, rest = sys.argv[1], sys.argv[2:]
    return sheet(rest) if cmd == "sheet" else record(rest) if cmd == "record" else check()


if __name__ == "__main__":
    raise SystemExit(main())
