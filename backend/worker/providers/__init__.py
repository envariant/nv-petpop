"""Commercial GenAI API providers, by profile name (see base.py). A vendor is a manifest in config/providers plus a
profile entry; a class here only for an API a manifest cannot describe."""
from __future__ import annotations

from .base import AwaitingOperator, Generated, Provider, ProviderError, ProviderUnsupported, provider_config  # noqa: F401

# A provider kind is a class; "manifest" (decision 109) runs any API described by config/providers/<manifest>.yaml.
# "manual" (decision 111) builds the same requests but hands them to the operator instead of sending them.
KINDS = {"manifest": "backend.worker.providers.manifest:ManifestProvider",
         "manual": "backend.worker.providers.manual:ManualProvider"}


def make_provider(profile, name: str) -> Provider:
    """The provider instance for the profile's providers.<name> entry (its `kind` picks the class)."""
    import importlib

    kind = provider_config(profile, name).get("kind", name)
    if kind not in KINDS:
        raise ProviderError(f"unknown provider kind {kind!r}; known: {sorted(KINDS)}")
    module, _, cls = KINDS[kind].partition(":")
    return getattr(importlib.import_module(module), cls)(profile, name)
