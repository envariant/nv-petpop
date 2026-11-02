"""Notifications (decision 126): an account's app installs get a push and its email a message; a guest who gave only a
phone gets an SMS; each event goes once per channel; a stale push token is forgotten; staff marking an order ready
sends the "ready to collect" message."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.api.app import create_app
from backend.api.db import DeviceRow, NotificationRow
from backend.api.messaging import PushGone
from backend.core.config import settings
from petpop_library.composition import sample

A, K = "/api/v1/account", "/api/v1/kiosk"


@pytest.fixture
def api(monkeypatch, tmp_path):
    for k, v in {"PETPOP_VAR": str(tmp_path / "var"), "PETPOP_PAYMENTS": "fake", "GENAI_PROFILE": "mock", "PETPOP_SECRET": "s",
                 "PETPOP_STAFF_TOKEN": "staff", "PETPOP_STUDIO_PASSWORD": "pw", "PETPOP_CODE_RESEND_S": "0"}.items():
        monkeypatch.setenv(k, v)
    for k in ("PETPOP_DEPLOY", "PETPOP_EMAIL", "PETPOP_SMS", "PETPOP_PUSH"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(create_app(embed_worker=False, s=settings())) as c:
        c.app.state.impl.notifier.inline = True
        yield c


def order(c, headers=None, contact=None) -> str:
    sid = c.post(f"{K}/sessions", json={}).json()["session_id"]
    man = c.get(f"{K}/library/dog").json()["manifest"]
    cid = c.post(f"{K}/compositions", json={"session_id": sid, "composition": sample(man, pet_name="Rex")}).json()["composition_id"]
    r = c.post(f"{K}/compositions/{cid}/export", json={"contact": contact} if contact else {}, headers=headers or {})
    assert r.status_code == 202, r.text
    c.post(f"{K}/compositions/{cid}/payment", json={"method": "paynow"})
    return cid


def test_an_account_gets_a_push_and_an_email_once(api):
    c = api
    code = c.post(f"{A}/code", json={"channel": "email", "to": "rex@example.com"}).json()["dev_code"]
    tok = c.post(f"{A}/verify", json={"channel": "email", "to": "rex@example.com", "code": code}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    c.post(f"{A}/me/devices", json={"token": "fcm-device-aaaaaaaa", "platform": "android"}, headers=h)
    impl = c.app.state.impl
    box = impl.messenger.outbox
    cid = order(c, h)
    assert box.last("fcm-device-aaaaaaaa") is None  # not paid yet: nothing sent
    c.post(f"{K}/compositions/{cid}/payment/simulate")
    push = box.last("fcm-device-aaaaaaaa")
    assert push and push.subject == "Order confirmed" and push.data["composition_id"] == cid
    mail = box.last("rex@example.com")
    assert mail.channel == "email" and "ticket" in mail.text.lower()
    n = len(box.items)
    impl.notifier.order_confirmed(cid)  # a repeat sends nothing
    assert len(box.items) == n
    assert c.post(f"{K}/ops/orders/{cid}/ready", headers={"X-Staff-Token": "staff"}).status_code == 200
    assert box.last("rex@example.com").subject == "PetPop: Rex is ready"


def test_a_guest_with_only_a_phone_gets_an_sms(api):
    c = api
    cid = order(c, contact={"phone": "9123 4567"})
    c.post(f"{K}/compositions/{cid}/payment/simulate")
    sms = c.app.state.impl.messenger.outbox.last("+6591234567")
    assert sms and sms.channel == "sms" and "PP-" in sms.text
    with c.app.state.impl.db() as db:
        assert [r.channel for r in db.scalars(select(NotificationRow).where(NotificationRow.ref == cid))] == ["sms"]


def test_a_stale_push_token_is_forgotten_and_email_still_goes(api, monkeypatch):
    c = api
    code = c.post(f"{A}/code", json={"channel": "email", "to": "mia@example.com"}).json()["dev_code"]
    tok = c.post(f"{A}/verify", json={"channel": "email", "to": "mia@example.com", "code": code}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    c.post(f"{A}/me/devices", json={"token": "fcm-uninstalled-xx", "platform": "ios"}, headers=h)
    impl = c.app.state.impl

    def gone(token, *a, **k):
        raise PushGone(token)

    monkeypatch.setattr(impl.messenger, "push", gone)
    cid = order(c, h)
    c.post(f"{K}/compositions/{cid}/payment/simulate")
    with impl.db() as db:
        assert db.get(DeviceRow, "fcm-uninstalled-xx") is None
    assert impl.messenger.outbox.last("mia@example.com").channel == "email"
