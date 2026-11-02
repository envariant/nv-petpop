"""Payment for an order (decision 125). PETPOP_PAYMENTS picks the provider:

    off     (default) no payment in the app: the shop takes payment at the counter; orders print when exported
    fake    a stand-in for tests and demos: PayNow and card payments stay pending until simulated (the app shows a
            "simulate payment" button for it)
    hitpay  HitPay (Singapore): PayNow as a QR the app renders (a banking app scans it), cards on HitPay's hosted
            checkout. HITPAY_API_KEY and HITPAY_SALT come from the environment only, never committed;
            HITPAY_API_URL defaults to the sandbox

HitPay's wire format: POST {api}/payment-requests (form fields amount, currency, payment_methods[], reference_number,
purpose; generate_qr for PayNow, redirect_url for the hosted card checkout), GET {api}/payment-requests/{id} for the
status, and a webhook registered in the HitPay dashboard (JSON body, `Hitpay-Signature` = hex HMAC-SHA256 of the raw
body keyed with the salt). The webhook marks a payment paid; while a payment is pending the status call is the
fallback, so a missed webhook only delays the order.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx
from sqlalchemy import select

from . import models as m
from .db import CompositionRow, PaymentRow, utcnow

SANDBOX_URL = "https://api.sandbox.hit-pay.com/v1"
HITPAY_METHOD = {"paynow": "paynow_online", "card": "card"}
HITPAY_STATE = {"completed": "paid", "succeeded": "paid", "failed": "failed", "expired": "expired", "canceled": "failed"}


@dataclass
class Created:
    ref: str
    qr: str | None
    checkout_url: str | None
    expires_at: datetime | None


class Provider(Protocol):
    name: str

    def create(self, composition_id: str, method: str, price: m.Price, redirect_url: str) -> Created: ...
    def status(self, ref: str) -> str: ...  # pending | paid | failed | expired


class FakeProvider:
    name = "fake"

    def create(self, composition_id: str, method: str, price: m.Price, redirect_url: str) -> Created:
        ref = "fake_" + uuid.uuid4().hex[:12]
        if method == "paynow":  # not a real PayNow payload: no banking app would pay it
            return Created(ref, f"PETPOP-FAKE-PAYNOW|{ref}|{price.currency}{price.amount}", None, utcnow() + timedelta(minutes=15))
        return Created(ref, None, f"{redirect_url}?fake_checkout={ref}", None)

    def status(self, ref: str) -> str:
        return "pending"  # until simulated


class HitPayProvider:
    name = "hitpay"

    def __init__(self, api_url: str, api_key: str, salt: str, client: httpx.Client | None = None) -> None:
        if not api_key or not salt:
            raise ValueError("PETPOP_PAYMENTS=hitpay needs HITPAY_API_KEY and HITPAY_SALT in the environment")
        self.api = api_url.rstrip("/")
        self.salt = salt
        self.client = client or httpx.Client(timeout=20)
        self.headers = {"X-BUSINESS-API-KEY": api_key, "X-Requested-With": "XMLHttpRequest"}

    def create(self, composition_id: str, method: str, price: m.Price, redirect_url: str) -> Created:
        form: dict[str, Any] = {"amount": price.amount, "currency": price.currency.lower(), "payment_methods[]": HITPAY_METHOD[method],
                                "reference_number": composition_id, "purpose": "PetPop figurine"}
        if method == "paynow":
            form["generate_qr"] = "true"
        else:
            form["redirect_url"] = redirect_url
        r = self.client.post(f"{self.api}/payment-requests", data=form, headers=self.headers)
        r.raise_for_status()
        body = r.json()
        qr_data = body.get("qr_code_data") or {}
        return Created(ref=str(body["id"]), qr=qr_data.get("qr_code"), checkout_url=None if method == "paynow" else body.get("url"),
                       expires_at=_when(qr_data.get("qr_code_expiry") or body.get("expiry_date")))

    def status(self, ref: str) -> str:
        r = self.client.get(f"{self.api}/payment-requests/{ref}", headers=self.headers)
        r.raise_for_status()
        return HITPAY_STATE.get(str(r.json().get("status", "")).lower(), "pending")

    def webhook(self, raw: bytes, signature: str | None) -> tuple[str, str] | None:
        """(payment request id, state) for a genuine webhook, None for a forged or unrelated one."""
        want = hmac.new(self.salt.encode(), raw, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(want, signature.strip()):
            return None
        body = json.loads(raw)
        ref = body.get("id") or body.get("payment_request_id")
        return (str(ref), HITPAY_STATE.get(str(body.get("status", "")).lower(), "pending")) if ref else None


def _when(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d


# --------------------------------------------------------------------------- settings and the order ledger
def payments_mode() -> str:
    mode = os.environ.get("PETPOP_PAYMENTS", "off").strip() or "off"
    if mode not in ("off", "fake", "hitpay"):
        raise ValueError(f"PETPOP_PAYMENTS={mode!r}: use off, fake or hitpay")
    return mode


def price() -> m.Price:
    return m.Price(amount=os.environ.get("PETPOP_PRICE_SGD", "39.00"), currency="SGD")


def make_provider(client: httpx.Client | None = None) -> Provider | None:
    mode = payments_mode()
    if mode == "fake":
        return FakeProvider()
    if mode == "hitpay":
        return HitPayProvider(os.environ.get("HITPAY_API_URL", SANDBOX_URL), os.environ.get("HITPAY_API_KEY", ""),
                              os.environ.get("HITPAY_SALT", ""), client)
    return None


def offer(provider: Provider | None) -> m.PaymentOffer | None:
    return m.PaymentOffer(price=price(), methods=["paynow", "card"], provider=provider.name) if provider else None


def latest(db, composition_id: str) -> PaymentRow | None:
    return db.scalar(select(PaymentRow).where(PaymentRow.composition_id == composition_id)
                     .order_by(PaymentRow.created_at.desc(), PaymentRow.id.desc()))


def payable(db, composition_id: str, on: bool | None = None) -> bool:
    """Whether an order may be printed and its result shown: paid, or payments are off (`on`: whether this process
    takes payments; None reads PETPOP_PAYMENTS, as the export worker does)."""
    if not (payments_mode() != "off" if on is None else on):
        return True
    return db.scalar(select(PaymentRow.id).where(PaymentRow.composition_id == composition_id, PaymentRow.status == "paid")) is not None


def model(row: PaymentRow) -> m.Payment:
    aware = lambda d: d.replace(tzinfo=UTC) if d and d.tzinfo is None else d  # noqa: E731
    return m.Payment(payment_id=row.id, composition_id=row.composition_id, method=row.method, status=row.status,
                     price=m.Price(amount=row.amount, currency=row.currency), provider=row.provider, qr=row.qr,
                     checkout_url=row.checkout_url, created_at=aware(row.created_at), expires_at=aware(row.expires_at),
                     paid_at=aware(row.paid_at))


def order_row(db, composition_id: str) -> CompositionRow | None:
    return db.get(CompositionRow, composition_id)
