"""Manual mode in the mock server (decision 111, API 3.2.0): two demo tasks a Tripo manual run would raise, the
concept request and the 3D request, built by the real manifest from a fixture pet; submitting checks the upload
with the backend's own check and marks the task submitted. Enough for the Studio Manual inbox and its tests."""
from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Any

from backend.api import models as m
from backend.api.contract import ApiError, signed_file_url
from backend.core.paths import FIXTURES
from backend.worker.providers.manifest import load_manifest
from backend.worker.providers.manual import ACCEPT, EXPECTS, _settings, check_output

PET = "biscuit"
PARAMS = {"model": "v3.1-20260211", "texture": True, "pbr": False, "texture_quality": "detailed",
          "texture_alignment": "original_image", "orientation": "default", "face_limit": 200000}


class MockManual:
    def __init__(self, secret: str, store) -> None:
        self.secret, self.store = secret, store
        self.tasks: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()
        self._seed()

    def _seed(self) -> None:
        man = load_manifest("tripo-v3")
        prompts = json.loads((FIXTURES / PET / "prompts.json").read_text())
        prompts = prompts.get("prompts", prompts)
        spec = json.loads((FIXTURES / PET / "spec.json").read_text()) if (FIXTURES / PET / "spec.json").exists() else {}
        concept_key = "manual-demo/input.png"
        self.store.put(concept_key, (FIXTURES / PET / "concept.png").read_bytes())
        demo = [
            ("j_manual_demo.text-to-image-demo", "text_to_image", {"prompt": prompts["positive"].removeprefix("petpop_style, "),
                                                                    "negative_prompt": prompts["negative"]}, []),
            ("j_manual_demo.image-to-model-demo", "image_to_model", {"input": "<upload input.png>", **PARAMS, "model_seed": 7,
                                                                      "texture_seed": 7}, [{"name": "input.png", "key": concept_key}]),
        ]
        for task_id, capability, body, inputs in demo:
            cap = man["capabilities"][capability]
            kind = EXPECTS[capability]
            self.tasks[task_id] = {
                "task_id": task_id, "job_id": "j_manual_demo", "status": "pending", "capability": capability,
                "title": cap["manual"]["title"], "provider": "tripo (manual)", "vendor": man["vendor"],
                "manifest": f"{man['manifest']} v{man['version']}", "route": cap["route"], "request": body,
                "prompt": body.get("prompt"), "negative_prompt": body.get("negative_prompt"), "settings": _settings(body, cap),
                "inputs": inputs, "instructions": cap["manual"]["steps"], "expects": {"kind": kind, "accept": ACCEPT[kind]},
                "species": spec.get("species", "dog"), "pet_name": spec.get("pet_name") or "Biscuit",
                "breed_label": (spec.get("breed") or {}).get("label"), "created_at": datetime.now(UTC),
                "submitted_at": None, "result_name": None,
            }

    def _view(self, t: dict[str, Any]) -> m.ManualTask:
        inputs = [m.ManualInput(name=i["name"], url=signed_file_url(self.secret, i["key"])) for i in t["inputs"]]
        return m.ManualTask(**{**{k: v for k, v in t.items() if k not in ("inputs", "expects")}, "inputs": inputs,
                               "expects": m.ManualExpects(**t["expects"])})

    def list(self, status: str) -> m.ManualTaskList:
        items = [self._view(t) for t in self.tasks.values() if status == "all" or t["status"] == status]
        return m.ManualTaskList(pending=sum(t["status"] == "pending" for t in self.tasks.values()), items=items)

    def get(self, task_id: str) -> m.ManualTask:
        if task_id not in self.tasks:
            raise ApiError(404, f"unknown manual task {task_id}")
        return self._view(self.tasks[task_id])

    def submit(self, task_id: str, filename: str, data: bytes) -> m.ManualTask:
        with self.lock:
            t = self.tasks.get(task_id)
            if t is None:
                raise ApiError(404, f"unknown manual task {task_id}")
            if t["status"] != "pending":
                raise ApiError(409, "this task already has its output")
            why = check_output(t["expects"]["kind"], filename, data)
            if why:
                raise ApiError(422, why)
            self.store.put(f"manual-demo/{task_id}/result", data)
            t.update(status="submitted", submitted_at=datetime.now(UTC), result_name=filename[:120])
            return self._view(t)
