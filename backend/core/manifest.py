"""Builder for jobs/{job_id}/manifest.json (validated against data/schema/manifest.schema.json)."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .schemas import manifest_errors
from .vocab import vocab

PIPELINE_VERSION = "0.2.0"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ManifestBuilder:
    def __init__(self, job_id: str, spec: dict[str, Any], mode: str, fidelity: str = "high",
                 base_mesh_version: str = "proxy-1.0", workflows: dict[str, str] | None = None,
                 genai: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = {
            "manifest_version": "1.1",
            "job_id": job_id,
            "species": spec["species"],
            "pet_name": spec.get("pet_name", ""),
            "seed": int(spec["seed"]),
            "mode": mode,
            "fidelity": fidelity,
            "fallback": "none",
            "created_at": now_iso(),
            "finished_at": None,
            "versions": {
                "pipeline": PIPELINE_VERSION,
                "spec": spec.get("spec_version", "1.0"),
                "vocab": vocab()["vocab_version"],
                "base_mesh": base_mesh_version,
                "workflows": workflows or {},
            },
            "genai": genai or {"profile": "unknown"},
            "seeds": {"job": int(spec["seed"])},
            "stages": [],
            "files": [],
            "metrics": {},
        }

    @classmethod
    def load(cls, data: dict[str, Any]) -> "ManifestBuilder":
        obj = cls.__new__(cls)
        obj.data = data
        return obj

    def stage(self, stage: str, status: str, ms: int, attempts: int, backend: str, notes: str = "",
              started_at: str | None = None, ended_at: str | None = None) -> None:
        self.data["stages"] = [s for s in self.data["stages"] if s["stage"] != stage]
        entry: dict[str, Any] = {"stage": stage, "status": status, "ms": int(ms), "attempts": attempts,
                                 "backend": backend}
        if notes:
            entry["notes"] = notes
        if started_at:
            entry["started_at"] = started_at
        if ended_at:
            entry["ended_at"] = ended_at
        self.data["stages"].append(entry)

    def file(self, name: str, kind: str, stage: str, object_key: str, data: bytes) -> None:
        self.data["files"] = [f for f in self.data["files"] if f["name"] != name]
        self.data["files"].append({
            "name": name, "kind": kind, "stage": stage, "object_key": object_key, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    def metric(self, **kw: Any) -> None:
        self.data["metrics"].update(kw)

    def finish(self) -> None:
        self.data["finished_at"] = now_iso()
        self.data["metrics"]["total_ms"] = int(sum(s["ms"] for s in self.data["stages"]))

    def errors(self) -> list[str]:
        return manifest_errors(self.data)

    def to_json(self) -> bytes:
        return (json.dumps(self.data, indent=1) + "\n").encode()
