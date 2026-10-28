"""Implementations that must pass the identical contract test: the mock server and the real backend
(`make dev` mode: SQLite, local store, embedded worker, mock adapters, Blender CPU stages)."""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient


@contextmanager
def mock_client() -> Iterator[TestClient]:
    from mock_server.app import create_app

    with TestClient(create_app()) as c:
        yield c


@contextmanager
def backend_client() -> Iterator[TestClient]:
    os.environ.setdefault("PETPOP_PROFILE", "test")
    from backend.api.app import create_app

    app = create_app(embed_worker=True)
    with TestClient(app) as c:
        yield c


IMPLS: dict[str, Callable] = {"mock": mock_client, "backend": backend_client}
