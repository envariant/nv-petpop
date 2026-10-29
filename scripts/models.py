#!/usr/bin/env python3
"""Pin, fetch and verify GenAI model weights from pipelines/comfy/models.yaml.

    python scripts/models.py --pin --from-hub                                     # anywhere: write pins, no weights
    python scripts/models.py --fetch  --dest ~/petpop-models --profile mac-m4pro  # Mac: `make -C mac models`
    python scripts/models.py --fetch  --dest /srv/models    --profile nvidia-24gb # NVIDIA: `make models`
    python scripts/models.py --verify --dest ~/petpop-models --profile mac-m4pro  # re-hash what is on disk
    python scripts/models.py --pin    --dest ~/petpop-models --profile mac-m4pro  # local files (the S4 LoRA)

--pin --from-hub resolves every Hugging Face entry at its pinned revision into pipelines/comfy/models.lock.json
(each file's path, size and SHA256, from Hugging Face's LFS metadata; small non-LFS files such as config.yaml are
read and hashed) and writes the entry's sha256 into models.yaml. It downloads no weights, so it runs in the cloud
VM. Commit both files.

--fetch downloads each missing file of the profile's entries from its pinned revision and checks every file
against the lock, so a host gets exactly the committed bytes or fails. --verify only re-hashes. --pin hashes
files already on disk and writes the pins; it is for `repo: local` entries, which have no upstream to ask.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODELS_YAML = ROOT / "pipelines" / "comfy" / "models.yaml"
LOCK = ROOT / "pipelines" / "comfy" / "models.lock.json"
HF = "https://huggingface.co"
SMALL_FILE = 2 << 20  # non-LFS files up to 2 MB are read to hash them; anything bigger is refused


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def aggregate(files: dict[str, dict]) -> str:
    """The entry's pin: the file's sha256, or the sha256 of the sorted 'path sha256' lines for several files."""
    if len(files) == 1:
        return next(iter(files.values()))["sha256"]
    return hashlib.sha256("\n".join(sorted(f"{p} {f['sha256']}" for p, f in files.items())).encode()).hexdigest()


def hf_headers() -> dict[str, str]:
    tok = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def hf_tree(repo: str, revision: str, folder: str = "") -> list[dict]:
    """Every file under `folder` (recursively) at `revision`, following the API's pagination."""
    url = f"{HF}/api/models/{repo}/tree/{revision}" + (f"/{folder}" if folder else "")
    out: list[dict] = []
    params: dict | None = {"recursive": "true", "expand": "false"}
    while url:
        r = httpx.get(url, params=params, headers=hf_headers(), timeout=60, follow_redirects=True)
        r.raise_for_status()
        out += [i for i in r.json() if i["type"] == "file"]
        url, params = r.links.get("next", {}).get("url"), None
    return out


def wanted_paths(m: dict) -> list[str]:
    if "file" in m:
        return [m["file"]]
    if "files" in m:
        return list(m["files"])
    out = []
    for pattern in m["files_glob"]:
        folder = pattern.split("/")[0]
        out += [i["path"] for i in hf_tree(m["repo"], m["revision"], folder) if fnmatch.fnmatch(i["path"], pattern)]
    return sorted(out)


def resolve_from_hub(m: dict) -> dict[str, dict]:
    """path -> {sha256, size} for every file of an entry, at its pinned revision, without downloading weights."""
    paths = wanted_paths(m)
    tree: dict[str, dict] = {}
    for folder in sorted({p.rsplit("/", 1)[0] if "/" in p else "" for p in paths}):
        tree.update({i["path"]: i for i in hf_tree(m["repo"], m["revision"], folder)})
    out = {}
    for p in paths:
        item = tree.get(p)
        if item is None:
            raise SystemExit(f"{m['repo']}@{m['revision']}: {p} not found")
        if item.get("lfs"):
            out[p] = {"sha256": item["lfs"]["oid"], "size": item["lfs"]["size"]}
            continue
        if item["size"] > SMALL_FILE:
            raise SystemExit(f"{m['repo']}/{p}: {item['size']} bytes and not in LFS; refusing to read it here")
        r = httpx.get(f"{HF}/{m['repo']}/resolve/{m['revision']}/{p}", headers=hf_headers(), timeout=60, follow_redirects=True)
        r.raise_for_status()
        out[p] = {"sha256": hashlib.sha256(r.content).hexdigest(), "size": len(r.content)}
    return out


def target(m: dict, root: Path, path: str) -> Path:
    """Where a pinned file lands. `rename` maps a repo path to another name under dest (the hash is the file's own),
    e.g. diffusers' .fp16 weights saved under the plain names a loader that passes no variant looks for."""
    return root / m["dest"] if "file" in m else root / m["dest"] / m.get("rename", {}).get(path, path)


def is_optional(m: dict, profile: str) -> bool:
    """`optional: true` on every profile, or a list of the profiles it is optional on."""
    opt = m.get("optional", False)
    return profile in opt if isinstance(opt, list) else bool(opt)


def download(repo: str, revision: str, path: str, dest: Path, want: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    url = f"{HF}/{repo}/resolve/{revision}/{path}"
    print(f"  downloading {repo}/{path} -> {dest}", flush=True)
    h = hashlib.sha256()
    with httpx.stream("GET", url, headers=hf_headers(), follow_redirects=True, timeout=None) as r, tmp.open("wb") as f:
        r.raise_for_status()
        for chunk in r.iter_bytes(1 << 22):
            f.write(chunk)
            h.update(chunk)
    if h.hexdigest() != want:
        tmp.unlink()
        raise SystemExit(f"[BAD] {repo}/{path}: sha256 {h.hexdigest()} is not the pinned {want}; nothing kept")
    tmp.replace(dest)


def write_pin(name: str, sha: str) -> None:
    text = MODELS_YAML.read_text()
    block = re.search(rf"(  - name: {re.escape(name)}\n(?:    .*\n)*)", text)
    if not block:
        raise SystemExit(f"entry {name} not found in models.yaml")
    new_block = re.sub(r"sha256: \S+", f"sha256: {sha}", block.group(1), count=1)
    MODELS_YAML.write_text(text.replace(block.group(1), new_block, 1))


def load_lock() -> dict:
    return json.loads(LOCK.read_text()) if LOCK.exists() else {"entries": {}}


def pin_from_hub(doc: dict) -> int:
    lock = {"note": "Generated by scripts/models.py --pin --from-hub. Do not edit.", "entries": {}}
    for m in doc["models"]:
        if m["repo"] == "local":
            continue
        files = resolve_from_hub(m)
        sha = aggregate(files)
        lock["entries"][m["name"]] = {"repo": m["repo"], "revision": m["revision"], "dest": m["dest"],
                                      "files": files, "sha256": sha}
        write_pin(m["name"], sha)
        print(f"[PINNED] {m['name']} {sha} ({len(files)} file{'s' * (len(files) > 1)}, "
              f"{sum(f['size'] for f in files.values()) / 1e9:.2f} GB)")
    LOCK.write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.environ.get("PETPOP_MODELS", "/srv/models"))
    ap.add_argument("--profile", default=os.environ.get("GENAI_PROFILE", "mock"))
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pin", action="store_true", help="write sha256 pins (with --from-hub: from Hugging Face metadata)")
    mode.add_argument("--fetch", action="store_true", help="download missing files and check every file against the lock")
    mode.add_argument("--verify", action="store_true", help="re-hash present files against the lock")
    ap.add_argument("--from-hub", action="store_true", help="with --pin: resolve pins from Hugging Face, download no weights")
    ap.add_argument("--with-optional", action="store_true")
    args = ap.parse_args()
    doc = yaml.safe_load(MODELS_YAML.read_text())
    if args.pin and args.from_hub:
        return pin_from_hub(doc)
    if args.profile == "mock":
        print("models.py --fetch/--verify is for a GenAI host (GENAI_PROFILE=mac-m4pro or nvidia-24gb); mock needs no weights")
        return 2
    root = Path(args.dest).expanduser()
    lock = load_lock()["entries"]
    bad = 0
    for m in doc["models"]:
        if args.profile not in m.get("profiles", []) or (is_optional(m, args.profile) and not args.with_optional):
            continue
        if m["repo"] == "local":
            path = root / m["dest"]
            sha = sha256_file(path) if path.exists() else None
            if args.pin and sha:
                write_pin(m["name"], sha)
                m["sha256"] = sha
            ok = sha is not None and sha == m["sha256"]
            print(f"[{'OK' if ok else 'SKIP'}] {m['name']}: local file, copy to {path}, then --pin and commit")
            continue
        entry = lock.get(m["name"])
        if not entry or entry["revision"] != m["revision"] or entry["sha256"] != m["sha256"]:
            print(f"[UNPINNED] {m['name']}: run `scripts/models.py --pin --from-hub` and commit models.yaml + models.lock.json")
            bad += 1
            continue
        problems = 0
        for path, f in entry["files"].items():
            dest = target(m, root, path)
            if args.fetch and not dest.exists():
                download(m["repo"], m["revision"], path, dest, f["sha256"])
            elif not dest.exists():
                print(f"[MISSING] {m['name']}: {dest}")
                problems += 1
            elif sha256_file(dest) != f["sha256"]:
                print(f"[BAD] {m['name']}: {dest} does not match its pin")
                problems += 1
        print(f"[{'OK' if not problems else 'FAIL'}] {m['name']}")
        bad += problems
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
