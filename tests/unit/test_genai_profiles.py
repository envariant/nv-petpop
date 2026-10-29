"""GenAI profiles (config/genai/*.yaml) and how the backend applies them."""
from __future__ import annotations

import pytest

from backend.core.genai import Profile, ProfileError, available


def test_three_profiles_ship_and_validate():
    assert set(available()) >= {"mock", "mac-m4pro", "nvidia-24gb"}
    for name in available():
        p = Profile(name)
        assert p.quality()["preset"] == p["quality"]["default"]
        assert p["texture"]["backend"] == "projection"  # the default on every profile
        assert set(p["timeouts_s"]) == {"A", "control", "B", "C", "D", "E", "F"}


def test_mock_is_the_default(monkeypatch):
    monkeypatch.delenv("GENAI_PROFILE", raising=False)
    p = Profile()
    assert p.name == "mock" and p.mode == "mock"
    assert p["services"] == {}


def test_mac_profile_rules():
    p = Profile("mac-m4pro")
    assert p["host"]["accelerator"] == "mps"
    assert p["residency"]["max_resident_models"] == 1 and p["residency"]["free_comfy_after_call"]
    assert p["residency"]["ollama_keep_alive_s"] == 0 and p["residency"]["shape_unload_after_call"]
    assert p["latency"]["enforce"] is False and p["expected_s"]["total"] == [720, 960]
    assert p["shape"]["backend"] == "http" and p["shape"]["params"]["octree_resolution"] == 192
    assert p["shape"]["params"]["steps"] == 30
    assert "hy_paint" not in p["texture"]["allowed"]  # Hunyuan3D-Paint stays NVIDIA-only


def test_nvidia_profile_rules():
    p = Profile("nvidia-24gb")
    assert p["shape"]["params"]["octree_resolution"] == 384 and p["shape"]["params"]["steps"] == 50
    assert p["latency"] == {"target_s": 240, "enforce": True}
    assert "hy_paint" in p["texture"]["allowed"] and p["image"]["precision"]["fp8_allowed"]


def test_texture_override(monkeypatch):
    monkeypatch.setenv("TEXTURE_BACKEND", "flat")
    assert Profile("mock")["texture"]["backend"] == "flat"
    monkeypatch.setenv("TEXTURE_BACKEND", "hy_paint")
    with pytest.raises(ProfileError):
        Profile("mac-m4pro")
    assert Profile("nvidia-24gb")["texture"]["backend"] == "hy_paint"


def test_urls_come_from_env_with_profile_defaults(monkeypatch):
    p = Profile("mac-m4pro")
    monkeypatch.setenv("COMFY_URL", "https://tunnel.example/comfy/")
    monkeypatch.setenv("GENAI_TOKEN", "t0k")
    assert p.url("comfy") == "https://tunnel.example/comfy"
    assert p.auth_headers() == {"Authorization": "Bearer t0k"}


def test_unknown_profile_and_quality(monkeypatch):
    with pytest.raises(ProfileError):
        Profile("amd-404")
    monkeypatch.setenv("PETPOP_QUALITY", "nope")
    with pytest.raises(ProfileError):
        Profile("mock").quality()


def test_manifest_records_profile_and_models():
    s = Profile("nvidia-24gb").summary()
    assert s["profile"] == "nvidia-24gb" and s["adapters"]["shape"] == "comfy"
    assert s["models"]["parser"] == "qwen2.5:7b-instruct-q4_K_M"
    assert s["models"]["shape.multiview"].startswith("hunyuan3d-dit-v2-mv")
