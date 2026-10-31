"""Manual mode (decision 111): the request a manual task shows is the API request, byte for byte; a resumed job
finds its own output; uploads are checked before a waiting job is resumed with them."""
from __future__ import annotations

import io
import json
import struct

import numpy as np
import pytest
import trimesh
from PIL import Image

from backend.api.store import LocalStore
from backend.core.genai import Profile
from backend.worker.providers.base import AwaitingOperator
from backend.worker.providers.manifest import ManifestProvider
from backend.worker.providers.manual import ManualProvider, check_output


class Ctx:
    job_id = "j_unit"

    def __init__(self, store) -> None:
        self.store = store

    def key(self, name: str) -> str:
        return f"jobs/{self.job_id}/{name}"

    def remaining(self) -> float:
        return 600.0


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_the_manual_request_is_the_api_request(tmp_path):
    prof = Profile("tripo-manual")
    params = dict(prof["shape"]["params"])
    manual = ManualProvider(prof, "tripo")
    _, api_body = ManifestProvider(Profile("tripo"), "tripo").request("image_to_model", {"image": "<upload input.png>"}, params, 5)
    ctx = Ctx(LocalStore(tmp_path))
    with pytest.raises(AwaitingOperator) as w:
        manual.image_to_model(ctx, png(), params, 5)
    p = w.value.packet
    assert p["request"] == api_body and p["route"] == "POST /v3/generation/image-to-model"
    assert p["expects"] == {"kind": "model", "accept": [".glb"], "slots": []} and p["inputs"][0]["name"] == "input.png"
    assert json.loads(ctx.store.get(ctx.key(f"manual/{p['request_id']}/request.json")))["task_id"] == p["task_id"]
    # The operator's output is found by the same call when the job resumes; a different seed is a new task.
    glb = trimesh.creation.box().export(file_type="glb")
    ctx.store.put(p["result_key"], glb)
    g = manual.image_to_model(ctx, png(), params, 5)
    assert g.data == glb and g.task_id == f"manual-{p['request_id']}" and g.credits is None
    with pytest.raises(AwaitingOperator):
        manual.image_to_model(ctx, png(), params, 6)


def glb_with(required: list[str]) -> bytes:
    doc = json.dumps({"asset": {"version": "2.0"}, "extensionsRequired": required}).encode()
    doc += b" " * (-len(doc) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(doc)) + struct.pack("<II", len(doc), 0x4E4F534A) + doc


def test_uploads_are_checked():
    assert check_output("image", "concept.png", png()) is None
    assert "expected" in check_output("image", "concept.glb", png())
    assert "unreadable image" in check_output("image", "concept.png", b"nope")
    assert check_output("model", "figure.glb", trimesh.creation.box().export(file_type="glb")) is None
    assert "meshopt" in check_output("model", "figure.glb", glb_with(["EXT_meshopt_compression"]))
    assert "not a binary glTF" in check_output("model", "figure.glb", b"{}")
    flat = trimesh.Trimesh(np.zeros((3, 3)), [[0, 1, 2]], process=False).export(file_type="glb")
    assert "did not decode" in check_output("model", "figure.glb", flat)


def test_manual_multiview_waits_for_all_four_views(tmp_path):
    prof = Profile("tripo-manual")
    manual = ManualProvider(prof, "tripo")
    ctx = Ctx(LocalStore(tmp_path))
    with pytest.raises(AwaitingOperator) as w:
        manual.image_to_multiview(ctx, png(), {}, 5)
    p = w.value.packet
    assert p["expects"] == {"kind": "views", "accept": [".png", ".jpg", ".jpeg", ".webp"], "slots": ["front", "left", "back", "right"]}
    assert p["route"] == "POST /v3/generation/image-to-multiview" and set(p["result_keys"]) == {"front", "left", "back", "right"}
    for slot in ("front", "left", "back"):
        ctx.store.put(p["result_keys"][slot], png())
    with pytest.raises(AwaitingOperator):  # three of four is not enough
        manual.image_to_multiview(ctx, png(), {}, 5)
    ctx.store.put(p["result_keys"]["right"], png())
    g = manual.image_to_multiview(ctx, png(), {}, 5)
    assert set(g.files) == {"front", "left", "back", "right"} and g.task_id == f"manual-{p['request_id']}"
