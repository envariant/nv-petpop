"""StageContext: everything a stage function needs besides (job_id, spec, manifest)."""
from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config import Settings
from petpop_core.manifest import ManifestBuilder


class StageFailed(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass
class StageContext:
    job_id: str
    settings: Settings
    store: Any
    backends: Any
    progress: Callable[..., None]
    on_artefact: Callable[[str, str, str, str, int], None] = lambda *a: None
    tmp: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="pp-job-")))
    deadline: float = 0.0
    state: dict[str, Any] = field(default_factory=dict)
    kind: str = "pipeline"  # pipeline | bespoke | batch: picks the profile's path (paths.by_kind)

    @property
    def path(self) -> dict[str, Any]:
        """The profile's path for this job: library quality by default, a faster one for some job kinds."""
        paths = self.settings.genai.get("paths") or {}
        name = (paths.get("by_kind") or {}).get(self.kind, paths.get("default", "library"))
        return {"name": name, **(paths.get(name) or {})}

    @property
    def quality(self) -> dict[str, Any]:
        return self.settings.quality

    def key(self, name: str) -> str:
        return f"jobs/{self.job_id}/{name}"

    def put(self, manifest: ManifestBuilder, name: str, kind: str, stage: str, data: bytes) -> str:
        key = self.key(name)
        self.store.put(key, data)
        manifest.file(name, kind, stage, key, data)
        self.on_artefact(name, kind, stage, key, len(data))
        return key

    def get(self, name: str) -> bytes:
        return self.store.get(self.key(name))

    def fetch(self, name: str) -> Path:
        """Download an artefact into the job temp dir (stages read only from the store, never local files)."""
        p = self.tmp / "in" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.get(name))
        return p

    def workdir(self, stage: str) -> Path:
        d = self.tmp / f"stage_{stage}_{int(time.time() * 1000)}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def remaining(self) -> float:
        return max(1.0, self.deadline - time.monotonic())

    def check_fault(self, stage: str) -> None:
        if self.settings.fail_stage == stage:
            raise StageFailed(stage, f"fault injection PETPOP_FAIL_STAGE={stage}")
