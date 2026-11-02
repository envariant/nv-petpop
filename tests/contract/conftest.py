import pytest

from .impls import IMPLS


def _impl(request, monkeypatch, tmp_path):
    monkeypatch.setenv("PETPOP_MOCK_SPEED", "0")
    monkeypatch.setenv("PETPOP_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("PETPOP_STAFF_TOKEN", "test-staff")
    monkeypatch.setenv("PETPOP_SECRET", "test-secret")
    monkeypatch.setenv("PETPOP_QUALITY", "test")
    monkeypatch.setenv("PETPOP_STUDIO_PASSWORD", "test-studio")
    monkeypatch.setenv("KIOSK_BESPOKE", "1")
    monkeypatch.setenv("PETPOP_AUTH_FAKE", "1")
    monkeypatch.setenv("PETPOP_CODE_RESEND_S", "0")  # test_config_and_codes checks the 30 s wait itself  # decision 126: fake Apple/Google tokens, codes in the response
    for k in ("PETPOP_EMAIL", "PETPOP_SMS", "PETPOP_PUSH", "PETPOP_APPLE_CLIENT_IDS", "PETPOP_GOOGLE_CLIENT_IDS"):
        monkeypatch.delenv(k, raising=False)
    with IMPLS[request.param]() as c:
        c.impl_name = request.param
        yield c


@pytest.fixture(params=sorted(IMPLS))
def client(request, monkeypatch, tmp_path):
    monkeypatch.setenv("PETPOP_PAYMENTS", "off")
    yield from _impl(request, monkeypatch, tmp_path)


@pytest.fixture(params=sorted(IMPLS))
def paying_client(request, monkeypatch, tmp_path):
    """Payments on, with the fake provider (decision 125)."""
    monkeypatch.setenv("PETPOP_PAYMENTS", "fake")
    monkeypatch.setenv("PETPOP_PRICE_SGD", "39.00")
    yield from _impl(request, monkeypatch, tmp_path)
