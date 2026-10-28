"""StageRunner (BRIEF Section 9, 'Job orchestration').

Runs A, control, B, C, D, E, F in order. Each stage is idempotent and resumable from the artefacts already
in the store: a stage whose manifest entry is ok and whose files all exist is skipped, so a retry restarts at
the failed stage. Every stage retries once; hard per-stage timeouts fail the job with the stage name.
Fallbacks (Section 5): D low confidence or failure -> single-view D -> parametric (skip D, ship the morphed
base mesh); an invalid wrap ships the morphed base unwrapped. The user always gets a figurine unless A, B,
C or F fail twice.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import time
import traceback
from collections.abc import Callable
from typing import Any

import numpy as np

from backend.core.manifest import ManifestBuilder, now_iso
from backend.core.meshkit import load_base
from backend.core.paths import BASE_DIR

from . import control, stage_a, stage_b, stage_c, stage_d, stage_e, stage_f
from .context import StageContext, StageFailed

log = logging.getLogger("petpop.worker")

# Hard timeouts (s) from the brief; control renders are part of B's budget on the GPU host.
TIMEOUTS = {"A": 10, "control": 30, "B": 60, "C": 90, "D": 150, "E": 90, "F": 120}
# CPU (mock mode) runs Blender for real on a laptop-class CPU, so its budgets are scaled.
CPU_TIMEOUT_SCALE = 6.0
STAGES: list[tuple[str, Callable, int, str]] = [
    ("A", stage_a.run, 4, "Reading your description"),
    ("control", control.run, 8, "Shaping the base figure"),
    ("B", stage_b.run, 10, "Sketching the concept"),
    ("C", stage_c.run, 28, "Drawing four views"),
    ("D", stage_d.run, 50, "Sculpting the shape"),
    ("E", stage_e.run, 74, "Fitting the figurine template"),
    ("F", stage_f.run, 82, "Painting and preparing for print"),
]


class JobFailed(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"Stage {stage} failed: {message}")
        self.stage = stage


class StageRunner:
    def __init__(self, ctx: StageContext, spec: dict[str, Any],
                 on_stage: Callable[[str, str, int, str | None], None] = lambda *a: None) -> None:
        self.ctx = ctx
        self.spec = spec
        self.on_stage = on_stage  # (stage, status, ms, started_at)
        self.manifest = self._load_manifest()

    # ------------------------------------------------------------------ manifest / resume
    def _load_manifest(self) -> ManifestBuilder:
        key = self.ctx.key("manifest.json")
        if self.ctx.store.exists(key):
            return ManifestBuilder.load(json.loads(self.ctx.store.get(key)))
        base_meta = json.loads((BASE_DIR / self.spec["species"] / "morphs.json").read_text())
        return ManifestBuilder(self.ctx.job_id, self.spec, mode=self.ctx.settings.mode, fidelity="high",
                               base_mesh_version=base_meta.get("version", "unknown"))

    def _save_manifest(self) -> None:
        self.ctx.store.put(self.ctx.key("manifest.json"), self.manifest.to_json())

    def _done(self, stage: str) -> bool:
        entry = next((s for s in self.manifest.data["stages"] if s["stage"] == stage), None)
        if not entry or entry["status"] not in ("ok", "fallback"):
            return False
        files = [f for f in self.manifest.data["files"] if f["stage"] == stage]
        return all(self.ctx.store.exists(f["object_key"]) for f in files)

    # ------------------------------------------------------------------ execution
    def _timeout(self, stage: str) -> float:
        t = TIMEOUTS[stage]
        return t * CPU_TIMEOUT_SCALE if self.ctx.settings.mode == "mock" else t

    def _call(self, stage: str, fn: Callable, **kw) -> list[str]:
        self.ctx.deadline = time.monotonic() + self._timeout(stage)
        with cf.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn, self.ctx.job_id, self.spec, self.manifest, ctx=self.ctx, **kw)
            try:
                return fut.result(timeout=self._timeout(stage) + 5)
            except cf.TimeoutError as exc:
                raise StageFailed(stage, f"timed out after {self._timeout(stage):.0f} s") from exc

    def _attempt(self, stage: str, fn: Callable, retries: int = 1, **kw) -> tuple[bool, int, str]:
        err = ""
        for attempt in range(1, retries + 2):
            try:
                self._call(stage, fn, **kw)
                return True, attempt, ""
            except Exception as exc:  # noqa: BLE001 - every failure is recorded and retried once
                err = str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__
                log.warning("job %s stage %s attempt %d failed: %s", self.ctx.job_id, stage, attempt, err)
                log.debug(traceback.format_exc())
        return False, retries + 1, err

    def run(self) -> ManifestBuilder:
        ctx = self.ctx
        fallback = self.manifest.data.get("fallback", "none")
        for stage, fn, pct, message in STAGES:
            if self._done(stage):
                continue
            ctx.progress(stage, pct, message)
            started = now_iso()
            self.on_stage(stage, "running", 0, started)
            t0 = time.monotonic()
            status, notes, attempts = "ok", "", 1
            backend = {"A": ctx.backends.parser.name, "B": ctx.backends.image.name, "C": ctx.backends.image.name,
                       "D": ctx.backends.shape.name, "F": ctx.backends.texture.name}.get(stage, "blender")
            if stage == "D":
                ok, attempts, err = self._attempt("D", fn)
                if not ok:
                    ctx.progress("D", 56, "Views disagree, trying the front view alone")
                    ok, n, err2 = self._attempt("D", fn, retries=0, single_view=True)
                    attempts += n
                    if ok:
                        fallback, status, notes = "single_view", "fallback", f"multi-view failed ({err}); single view used"
                    else:
                        ctx.progress("D", 62, "Using the classic figure shape")
                        fallback, status, notes = "parametric", "fallback", f"{err}; single view: {err2}; parametric base mesh"
                        ctx.state.pop("iou", None)
                        ok = True  # D is skipped: the parametric base mesh ships
            elif stage == "E":
                ok, attempts, err = self._attempt("E", fn, parametric=(fallback == "parametric"))
                wrap = ctx.state.get("wrap", {})
                if ok and wrap.get("fallback") == "unwrapped" and fallback == "none":
                    fallback, status = "unwrapped", "fallback"
                notes = wrap.get("notes", err)
            else:
                ok, attempts, err = self._attempt(stage, fn)
            ms = int((time.monotonic() - t0) * 1000)
            if not ok:
                self.manifest.stage(stage, "failed", ms, attempts, backend, err, started, now_iso())
                self.on_stage(stage, "failed", ms, started)
                self._save_manifest()
                raise JobFailed(stage, err)
            self.manifest.stage(stage, status, ms, attempts, backend, notes, started, now_iso())
            self.manifest.data["fallback"] = fallback
            self._record(stage)
            self.on_stage(stage, status, ms, started)
            self._save_manifest()
        self._finish(fallback)
        return self.manifest

    def _record(self, stage: str) -> None:
        """Persist what a stage learned into the manifest so a resumed job keeps it."""
        st = self.ctx.state
        if st.get("fidelity") == "low":
            self.manifest.data["fidelity"] = "low"
        self.manifest.data["versions"]["workflows"].update(st.get("workflows", {}))
        if stage == "D":
            iou = st.get("iou") if self.manifest.data["fallback"] != "parametric" else None
            self.manifest.metric(iou_mean=round(float(np.mean(iou)), 4) if iou else None)
            if iou:
                self.manifest.metric(iou_views=iou)
        elif stage == "E":
            wrap = st.get("wrap", {})
            self.manifest.metric(wrap_valid=bool(wrap.get("valid", True)), wrap_notes=str(wrap.get("notes", ""))[:200])
        elif stage == "F":
            self.manifest.metric(**st.get("f_metrics", {}))

    def _finish(self, fallback: str) -> None:
        base = load_base(self.spec["species"])
        self.manifest.data["fallback"] = fallback
        self.manifest.metric(uv_layout_hash=base.uv_hash(), topology_hash=base.topology_hash())
        self.manifest.finish()
        errs = self.manifest.errors()
        if errs:
            raise JobFailed("F", f"manifest invalid: {errs[:3]}")
        self._save_manifest()
