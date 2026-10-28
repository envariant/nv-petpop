"""Implementations that must pass the identical contract test (mock server now, backend from S2)."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient


@contextmanager
def mock_client() -> Iterator[TestClient]:
    from mock_server.app import create_app

    with TestClient(create_app()) as c:
        yield c


IMPLS: dict[str, Callable] = {"mock": mock_client}
