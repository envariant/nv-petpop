"""ArtefactStore: every file a job writes goes through here (local folder in dev, MinIO/S3 on the GPU host).
Stages never read another stage's local files, only keys from the store (BRIEF Section 12)."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ArtefactStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def path(self, key: str) -> Path | None: ...
    def list(self, prefix: str) -> list[str]: ...


class LocalStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise KeyError(key)
        return p

    def put(self, key: str, data: bytes) -> None:
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)

    def get(self, key: str) -> bytes:
        p = self._p(key)
        if not p.is_file():
            raise KeyError(key)
        return p.read_bytes()

    def exists(self, key: str) -> bool:
        return self._p(key).is_file()

    def path(self, key: str) -> Path | None:
        p = self._p(key)
        return p if p.is_file() else None

    def list(self, prefix: str) -> list[str]:
        base = self._p(prefix)
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file() and not p.name.endswith(".tmp"))


class S3Store:
    """MinIO / S3 (GPU host). Needs boto3 (pip install '.[gpu-host]')."""

    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str) -> None:
        import boto3  # noqa: PLC0415

        self.bucket = bucket
        self.s3 = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access_key,
                               aws_secret_access_key=secret_key)
        try:
            self.s3.head_bucket(Bucket=bucket)
        except Exception:  # noqa: BLE001
            self.s3.create_bucket(Bucket=bucket)

    def put(self, key: str, data: bytes) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.s3.exceptions.NoSuchKey as exc:
            raise KeyError(key) from exc

    def exists(self, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def path(self, key: str) -> Path | None:
        return None

    def list(self, prefix: str) -> list[str]:
        out, token = [], None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": prefix, **({"ContinuationToken": token} if token else {})}
            r = self.s3.list_objects_v2(**kw)
            out += [o["Key"] for o in r.get("Contents", [])]
            if not r.get("IsTruncated"):
                return out
            token = r["NextContinuationToken"]


def make_store(s) -> ArtefactStore:  # s: Settings
    import os

    if s.s3_endpoint:
        return S3Store(s.s3_endpoint, s.s3_bucket, os.environ.get("S3_ACCESS_KEY", ""),
                       os.environ.get("S3_SECRET_KEY", ""))
    return LocalStore(s.var / "artefacts")
