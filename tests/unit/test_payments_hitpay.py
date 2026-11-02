"""HitPay (decision 125) against a stubbed HTTP transport: the request each payment method sends, the status mapping,
and webhook signatures (hex HMAC-SHA256 of the raw body keyed with the salt); then the webhook through a backend that
takes payments, marking the order paid and sending its print bundle to the fulfilment folder."""
from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qs

import httpx
import pytest

from backend.api import models as m
from backend.api.payments import SANDBOX_URL, HitPayProvider

PRICE = m.Price(amount="39.00", currency="SGD")


def stub(seen: list[httpx.Request], status: str = "pending") -> httpx.Client:
    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.method == "POST":
            form = parse_qs(req.content.decode())
            body = {"id": "9a1b2c3d-pr", "status": "pending", "url": "https://securecheckout.sandbox.hit-pay.com/payment-request/9a1b2c3d-pr"}
            if form.get("generate_qr") == ["true"]:
                body["qr_code_data"] = {"qr_code": "00020101021226...6304ABCD", "qr_code_expiry": "2026-11-02T10:15:00Z"}
            return httpx.Response(201, json=body)
        return httpx.Response(200, json={"id": req.url.path.rsplit("/", 1)[1], "status": status})

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_paynow_asks_for_a_qr_and_card_for_the_hosted_checkout():
    seen: list[httpx.Request] = []
    hp = HitPayProvider(SANDBOX_URL, "key-123", "salt", stub(seen))
    made = hp.create("c_abc", "paynow", PRICE, "https://petpop.sg/paid")
    req = seen[-1]
    assert str(req.url) == f"{SANDBOX_URL}/payment-requests"
    assert req.headers["X-BUSINESS-API-KEY"] == "key-123"
    form = parse_qs(req.content.decode())
    assert form == {"amount": ["39.00"], "currency": ["sgd"], "payment_methods[]": ["paynow_online"], "reference_number": ["c_abc"],
                    "purpose": ["PetPop figurine"], "generate_qr": ["true"]}
    assert made.ref == "9a1b2c3d-pr" and made.qr.startswith("000201") and made.checkout_url is None
    assert made.expires_at and made.expires_at.isoformat().startswith("2026-11-02T10:15")

    made = hp.create("c_abc", "card", PRICE, "https://petpop.sg/paid")
    form = parse_qs(seen[-1].content.decode())
    assert form["payment_methods[]"] == ["card"] and form["redirect_url"] == ["https://petpop.sg/paid"] and "generate_qr" not in form
    assert made.qr is None and made.checkout_url.startswith("https://securecheckout")


@pytest.mark.parametrize("status,state", [("pending", "pending"), ("completed", "paid"), ("failed", "failed"), ("expired", "expired")])
def test_status_maps_hitpay_states(status, state):
    hp = HitPayProvider(SANDBOX_URL, "key", "salt", stub([], status))
    assert hp.status("9a1b2c3d-pr") == state


def test_webhook_signature_is_checked_on_the_raw_body():
    hp = HitPayProvider(SANDBOX_URL, "key", "the-salt", stub([]))
    raw = json.dumps({"id": "9a1b2c3d-pr", "status": "completed", "reference_number": "c_abc"}).encode()
    good = hmac.new(b"the-salt", raw, hashlib.sha256).hexdigest()
    assert hp.webhook(raw, good) == ("9a1b2c3d-pr", "paid")
    assert hp.webhook(raw, "0" * 64) is None
    assert hp.webhook(raw, None) is None
    assert hp.webhook(raw.replace(b"completed", b"failed"), good) is None  # a tampered body


def test_keys_come_from_the_environment():
    with pytest.raises(ValueError, match="HITPAY_API_KEY"):
        HitPayProvider(SANDBOX_URL, "", "", stub([]))


def test_a_webhook_marks_the_order_paid_and_prints_it(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from backend.api.app import create_app
    from backend.api.db import JobRow
    from backend.core.config import settings

    for k, v in {"PETPOP_VAR": str(tmp_path / "var"), "PETPOP_PAYMENTS": "hitpay", "HITPAY_API_KEY": "key", "HITPAY_SALT": "the-salt",
                 "GENAI_PROFILE": "mock", "PETPOP_SECRET": "s", "PETPOP_STAFF_TOKEN": "t", "PETPOP_STUDIO_PASSWORD": "pw"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("PETPOP_DEPLOY", raising=False)
    seen: list[httpx.Request] = []
    with TestClient(create_app(embed_worker=False, s=settings())) as c:
        impl = c.app.state.impl
        impl.payments.client = stub(seen)
        sess = c.post("/api/v1/kiosk/sessions", json={}).json()
        assert sess["payment"]["provider"] == "hitpay"
        lib = c.get("/api/v1/kiosk/library/dog").json()["manifest"]
        from petpop_library.composition import sample

        cid = c.post("/api/v1/kiosk/compositions", json={"session_id": sess["session_id"], "composition": sample(lib)}).json()["composition_id"]
        acc = c.post(f"/api/v1/kiosk/compositions/{cid}/export", json={"contact": {"phone": "+6591234567"}}).json()
        pay = c.post(f"/api/v1/kiosk/compositions/{cid}/payment", json={"method": "paynow"}).json()
        assert pay["qr"].startswith("000201") and pay["status"] == "pending"
        assert c.post(f"/api/v1/kiosk/compositions/{cid}/payment/simulate").status_code == 403  # a real provider
        with impl.db() as db:  # the export finished (the worker is not running here): the bundle waits for payment
            for name in ("figure.3mf", "albedo.png"):
                impl.store.put(f"jobs/{acc['job_id']}/{name}", b"x")
            db.get(JobRow, acc["job_id"]).status = "done"
            db.commit()
        raw = json.dumps({"id": "9a1b2c3d-pr", "status": "completed", "reference_number": cid}).encode()
        assert c.post("/api/v1/payments/hitpay/webhook", content=raw, headers={"Hitpay-Signature": "forged"}).status_code == 401
        sig = hmac.new(b"the-salt", raw, hashlib.sha256).hexdigest()
        assert c.post("/api/v1/payments/hitpay/webhook", content=raw, headers={"Hitpay-Signature": sig}).status_code == 200
        st = c.get(f"/api/v1/kiosk/compositions/{cid}").json()
        assert st["payment"]["status"] == "paid" and st["result_url"]
        folder = impl.s.fulfil_dir / f"{acc['ticket']}_{acc['job_id']}"
        assert sorted(p.name for p in folder.iterdir()) == ["albedo.png", "figure.3mf"]
