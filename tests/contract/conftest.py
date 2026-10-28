import pytest

from .impls import IMPLS


@pytest.fixture(params=sorted(IMPLS))
def client(request, monkeypatch, tmp_path):
    monkeypatch.setenv("PETPOP_MOCK_SPEED", "0")
    monkeypatch.setenv("PETPOP_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("PETPOP_STAFF_TOKEN", "test-staff")
    monkeypatch.setenv("PETPOP_SECRET", "test-secret")
    monkeypatch.setenv("PETPOP_PROFILE", "test")
    with IMPLS[request.param]() as c:
        c.impl_name = request.param
        yield c
