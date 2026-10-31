"""Library release bundles (BRIEF Section 17, contract 1: Studio to Kiosk).

A release is release-<species>-<n>.tar holding manifest.json (data/schema/release.schema.json), manifest.sig
(hex HMAC-SHA256 of manifest.json with the release key) and every file the manifest lists, each with its sha256.
Studio packs it from published content; the kiosk loads it at start, keeps the last two, switches atomically and
reads nothing else from Studio.

The release key is PETPOP_RELEASE_KEY. Unset, both sides fall back to a published development key, which is
what the committed proxy releases (fixtures/library/) are signed with; production sets its own key in both the
Studio and the Kiosk environments.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import shutil
import tarfile
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from petpop_core.schemas import load_schema

DEV_RELEASE_KEY = "petpop-dev-release-key"  # development and the committed proxy releases only
KEEP = 2


class ReleaseError(Exception):
    pass


def release_key() -> bytes:
    return (os.environ.get("PETPOP_RELEASE_KEY") or DEV_RELEASE_KEY).encode()


def sign(manifest_bytes: bytes, key: bytes | None = None) -> str:
    return hmac.new(key or release_key(), manifest_bytes, hashlib.sha256).hexdigest()


def release_errors(manifest: dict[str, Any]) -> list[str]:
    from jsonschema import Draft202012Validator

    v = Draft202012Validator(load_schema("release.schema.json"))
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in v.iter_errors(manifest)]


def pack(manifest: dict[str, Any], files: dict[str, bytes], key: bytes | None = None) -> bytes:
    """Fill in the file list, validate, sign and tar. Returns the bundle bytes."""
    manifest = dict(manifest)
    manifest["files"] = [{"path": p, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()} for p, b in sorted(files.items())]
    errs = release_errors(manifest)
    if errs:
        raise ReleaseError(f"invalid release manifest: {errs[:5]}")
    mbytes = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        def add(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0  # reproducible bundles
            tar.addfile(info, io.BytesIO(data))

        add("manifest.json", mbytes)
        add("manifest.sig", (sign(mbytes, key) + "\n").encode())
        for path, data in sorted(files.items()):
            add(path, data)
    return buf.getvalue()


def read(bundle: bytes, key: bytes | None = None) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Verify signature, schema and every file hash; return (manifest, files)."""
    try:
        with tarfile.open(fileobj=io.BytesIO(bundle), mode="r") as tar:
            members = {m.name: m for m in tar.getmembers() if m.isfile()}
            for name in members:
                if name.startswith("/") or ".." in Path(name).parts:
                    raise ReleaseError(f"unsafe path in bundle: {name}")
            data = {name: tar.extractfile(m).read() for name, m in members.items()}
    except tarfile.TarError as exc:
        raise ReleaseError(f"not a release bundle: {exc}") from exc
    mbytes, sig = data.pop("manifest.json", None), data.pop("manifest.sig", b"").decode().strip()
    if mbytes is None:
        raise ReleaseError("bundle has no manifest.json")
    if not hmac.compare_digest(sign(mbytes, key), sig):
        raise ReleaseError("bad release signature")
    manifest = json.loads(mbytes)
    errs = release_errors(manifest)
    if errs:
        raise ReleaseError(f"invalid release manifest: {errs[:5]}")
    listed = {f["path"]: f for f in manifest["files"]}
    if set(listed) != set(data):
        raise ReleaseError(f"bundle files differ from the manifest: {sorted(set(listed) ^ set(data))[:5]}")
    for path, f in listed.items():
        if hashlib.sha256(data[path]).hexdigest() != f["sha256"]:
            raise ReleaseError(f"{path}: sha256 mismatch")
    return manifest, data


@dataclass
class Release:
    manifest: dict[str, Any]
    root: Path

    @property
    def version(self) -> str:
        return self.manifest["release_version"]

    def file(self, path: str) -> bytes:
        if path not in {f["path"] for f in self.manifest["files"]}:
            raise KeyError(path)
        return (self.root / path).read_bytes()

    def mesh(self, mesh_id: str):
        """A release mesh as a figure mesh (petpop_library.figure), with its part weights and pattern regions."""
        from . import figure

        return figure.load(self.file(self.item("meshes", mesh_id)["package"]))

    def item(self, kind: str, item_id: str) -> dict[str, Any]:
        for it in self.manifest[kind]:
            if it["id"] == item_id:
                return it
        raise KeyError(f"{kind}/{item_id}")


class ReleaseStore:
    """The kiosk's installed releases: <root>/<species>/<release-version>/ plus an ACTIVE pointer per species."""

    def __init__(self, root: Path, segmentation: dict[str, str] | None = None) -> None:
        self.root = Path(root)
        self.segmentation = segmentation or {}  # species -> the schema version this kiosk paints and prints to
        self._lock = threading.Lock()
        self._cache: dict[str, Release] = {}

    def _species_dir(self, species: str) -> Path:
        return self.root / species

    def active(self, species: str) -> Release | None:
        ptr = self._species_dir(species) / "ACTIVE"
        if not ptr.exists():
            return None
        name = ptr.read_text().strip()
        cached = self._cache.get(species)
        if cached and cached.version == name:
            return cached
        d = self._species_dir(species) / name
        if not (d / "manifest.json").exists():
            return None
        rel = Release(json.loads((d / "manifest.json").read_text()), d)
        self._cache[species] = rel
        return rel

    def installed(self, species: str) -> list[str]:
        d = self._species_dir(species)
        if not d.exists():
            return []
        return sorted((p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith(".")),
                      key=lambda n: int(n.rsplit("-", 1)[1]))

    def install(self, bundle: bytes, key: bytes | None = None) -> Release:
        """Verify, extract beside the active release, switch ACTIVE atomically, keep the last KEEP releases."""
        manifest, files = read(bundle, key)
        species = manifest["species"]
        want = self.segmentation.get(species)
        if want and manifest["segmentation_version"] != want:
            raise ReleaseError(f"release is for segmentation {manifest['segmentation_version']}, this kiosk has {want}")
        with self._lock:
            sdir = self._species_dir(species)
            sdir.mkdir(parents=True, exist_ok=True)
            final = sdir / manifest["release_version"]
            if not final.exists():
                tmp = Path(tempfile.mkdtemp(prefix=".incoming-", dir=sdir))
                for path, data in files.items():
                    out = tmp / path
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(data)
                (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
                os.replace(tmp, final)
            ptr_tmp = sdir / ".ACTIVE.tmp"
            ptr_tmp.write_text(manifest["release_version"] + "\n")
            os.replace(ptr_tmp, sdir / "ACTIVE")  # the switch: readers see the old or the new release, never half
            self._cache.pop(species, None)
            for old in self.installed(species)[:-KEEP]:
                if old != manifest["release_version"]:
                    shutil.rmtree(sdir / old, ignore_errors=True)
        return self.active(species)

    def install_newer(self, bundle_paths: list[Path]) -> list[str]:
        """Install every bundle newer than the active release of its species, oldest first. Returns versions."""
        done = []
        for path in sorted(bundle_paths, key=lambda p: (p.name.split("-")[1], int(p.stem.rsplit("-", 1)[1]))):
            species, number = path.name.split("-")[1], int(path.stem.rsplit("-", 1)[1])
            cur = self.active(species)
            if cur and cur.manifest["number"] >= number:
                continue
            done.append(self.install(path.read_bytes()).version)
        return done


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
