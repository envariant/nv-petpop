#!/usr/bin/env python3
"""Download, pin and verify GenAI model weights from pipelines/comfy/models.yaml (GenAI hosts only).

    python scripts/models.py --pin    --dest ~/petpop-models --profile mac-m4pro   # Mac: `make -C mac models`
    python scripts/models.py --verify --dest /srv/models    --profile nvidia-24gb  # NVIDIA: `make models`

--pin downloads every non-optional entry of the profile (add --with-optional for the rest) from its pinned
revision, checks each file's SHA256 against Hugging Face's own LFS sha256, then writes the value into
models.yaml in place of `sha256: TODO` (commit the change). --verify only re-hashes files already present and
fails on any mismatch or unpinned entry. Never run in the cloud VM (CLAUDE.md: no weights there).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import re
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODELS_YAML = ROOT / "pipelines" / "comfy" / "models.yaml"
HF = "https://huggingface.co"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def hf_headers() -> dict[str, str]:
    tok = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def hf_tree(repo: str, revision: str, folder: str = "") -> list[dict]:
    url = f"{HF}/api/models/{repo}/tree/{revision}" + (f"/{folder}" if folder else "")
    r = httpx.get(url, headers=hf_headers(), timeout=60, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def hf_lfs_sha(repo: str, revision: str, path: str) -> str | None:
    folder = path.rsplit("/", 1)[0] if "/" in path else ""
    for item in hf_tree(repo, revision, folder):
        if item["path"] == path:
            return (item.get("lfs") or {}).get("oid")
    raise SystemExit(f"{repo}@{revision}: {path} not found")


def download(repo: str, revision: str, path: str, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    url = f"{HF}/{repo}/resolve/{revision}/{path}"
    print(f"  downloading {repo}/{path} -> {dest}", flush=True)
    with httpx.stream("GET", url, headers=hf_headers(), follow_redirects=True, timeout=None) as r, tmp.open("wb") as f:
        r.raise_for_status()
        for chunk in r.iter_bytes(1 << 22):
            f.write(chunk)
    tmp.replace(dest)


def entry_files(m: dict) -> list[str]:
    if "file" in m:
        return [m["file"]]
    if "files" in m:
        return list(m["files"])
    out = []
    for pattern in m["files_glob"]:
        folder = pattern.split("/")[0]
        out += [i["path"] for i in hf_tree(m["repo"], m["revision"], folder) if i["type"] == "file" and fnmatch.fnmatch(i["path"], pattern)]
    return sorted(out)


def digest(m: dict, root: Path) -> tuple[str, list[str]]:
    """sha256 of a single file, or of the sorted 'path sha256' lines for a directory entry."""
    dest = root / m["dest"]
    if "file" in m:
        return sha256_file(dest), []
    lines = [f"{p} {sha256_file(dest / p)}" for p in entry_files(m)]
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest(), lines


def write_pin(name: str, sha: str) -> None:
    text = MODELS_YAML.read_text()
    block = re.search(rf"(  - name: {re.escape(name)}\n(?:    .*\n)*)", text)
    if not block:
        raise SystemExit(f"entry {name} not found in models.yaml")
    new_block = re.sub(r"sha256: \S+", f"sha256: {sha}", block.group(1), count=1)
    MODELS_YAML.write_text(text.replace(block.group(1), new_block, 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.environ.get("PETPOP_MODELS", "/srv/models"))
    ap.add_argument("--profile", default=os.environ.get("GENAI_PROFILE", "mock"))
    ap.add_argument("--pin", action="store_true", help="download, check against Hugging Face, write sha256 pins")
    ap.add_argument("--verify", action="store_true", help="re-hash present files against the pins")
    ap.add_argument("--with-optional", action="store_true")
    args = ap.parse_args()
    if args.profile == "mock":
        print("models.py is for a GenAI host (GENAI_PROFILE=mac-m4pro or nvidia-24gb); the mock profile needs no weights")
        return 2
    root = Path(args.dest).expanduser()
    doc = yaml.safe_load(MODELS_YAML.read_text())
    bad = 0
    for m in doc["models"]:
        if args.profile not in m.get("profiles", []) or (m.get("optional") and not args.with_optional):
            continue
        if m["repo"] == "local":
            ok = (root / m["dest"]).exists() and m["sha256"] != "TODO" and sha256_file(root / m["dest"]) == m["sha256"]
            print(f"[{'OK' if ok else 'SKIP'}] {m['name']}: local file, copy to {root / m['dest']} and pin by hand")
            continue
        files = entry_files(m)
        if args.pin:
            for f in files:
                target = root / m["dest"] if "file" in m else root / m["dest"] / f
                download(m["repo"], m["revision"], f, target)
                want = hf_lfs_sha(m["repo"], m["revision"], f)
                if want and sha256_file(target) != want:
                    print(f"[BAD] {m['name']}: {f} does not match Hugging Face's sha256 {want}")
                    bad += 1
        present = all(((root / m["dest"]) if "file" in m else (root / m["dest"] / f)).exists() for f in files)
        if not present:
            print(f"[MISSING] {m['name']} -> {root / m['dest']}")
            bad += 1
            continue
        sha, _ = digest(m, root)
        if args.pin:
            write_pin(m["name"], sha)
            print(f"[PINNED] {m['name']} {sha}")
        elif m["sha256"] in ("TODO", None):
            print(f"[UNPINNED] {m['name']} (run --pin on the host and commit models.yaml)")
            bad += 1
        else:
            ok = sha == m["sha256"]
            print(f"[{'OK' if ok else 'BAD'}] {m['name']}")
            bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
