"""Telling a customer about their order (decision 126): push to the account's app installs, email to the account's or
the guest's email, and SMS only when neither reached them (SMS is paid per message). Each event goes once per channel
(the notifications table), from a background thread so a slow sender never holds up an order or a webhook.

    order_confirmed   paid (or, with payments off, placed): the ticket
    order_ready       staff marked it ready for collection (kiosk ops panel)
    bespoke_ready     a "Make it unique" figurine came back from the studio: its result page
"""
from __future__ import annotations

import logging
import threading

from sqlalchemy import delete, select

from .accounts import normalise
from .contract import ApiError
from .db import AccountRow, CompositionRow, DeviceRow, JobRow, NotificationRow, utcnow
from .messaging import Messenger, PushGone

log = logging.getLogger("petpop.notify")


class Notifier:
    def __init__(self, db, messenger: Messenger, public_url: str = "") -> None:
        self.db, self.msg = db, messenger
        self.public_url = public_url.rstrip("/")
        self.inline = False  # tests: send in the caller's thread

    def _run(self, f, *args) -> None:
        if self.inline:
            f(*args)
        else:
            threading.Thread(target=self._safe, args=(f, *args), daemon=True).start()

    def _safe(self, f, *args) -> None:
        try:
            f(*args)
        except Exception:  # noqa: BLE001 - a notification never fails an order
            log.exception("notification failed")

    # -- events
    def order_confirmed(self, composition_id: str) -> None:
        self._run(self._order, composition_id, "order_confirmed")

    def order_ready(self, composition_id: str) -> None:
        self._run(self._order, composition_id, "order_ready")

    def bespoke_ready(self, job_id: str, result_url: str) -> None:
        self._run(self._bespoke, job_id, result_url)

    def _order(self, cid: str, event: str) -> None:
        with self.db() as db:
            row = db.get(CompositionRow, cid)
            if not row:
                return
            name, ticket = row.pet_name or "your figurine", row.ticket or ""
            account, email, phone = row.account_id, row.contact_email, row.contact_phone
        if event == "order_confirmed":
            title = "Order confirmed"
            text = f"Thank you! {name.title() if row.pet_name else 'Your figurine'} is being made. Your ticket is {ticket}."
        else:
            title = f"{name.title() if row.pet_name else 'Your figurine'} is ready"
            text = f"{name.title() if row.pet_name else 'Your figurine'} is ready to collect. Show ticket {ticket} at the counter."
        self.send(cid, event, title, text, account, email, phone, {"composition_id": cid, "event": event})

    def _bespoke(self, job_id: str, result_url: str) -> None:
        with self.db() as db:
            job = db.get(JobRow, job_id)
            comp = db.scalar(select(CompositionRow).where(CompositionRow.bespoke_job_id == job_id))
            if not job:
                return
            account = comp.account_id if comp else None
            email, phone = (comp.contact_email, comp.contact_phone) if comp else (None, None)
            raw = (job.contact or "").strip()
        for channel in ("email", "phone"):  # the free-text contact the customer gave at the kiosk
            if raw and not (email if channel == "email" else phone):
                try:
                    value = normalise(channel, raw)
                except ApiError:
                    continue
                email, phone = (value, phone) if channel == "email" else (email, value)
        text = f"Your one-off PetPop figurine is ready: {result_url}"
        self.send(job_id, "bespoke_ready", "Your one-off figurine is ready", text, account, email, phone,
                  {"job_id": job_id, "event": "bespoke_ready", "url": result_url})

    # -- delivery
    def _done(self, db, ref: str, event: str, channel: str) -> bool:
        return db.scalar(select(NotificationRow.id).where(NotificationRow.ref == ref, NotificationRow.event == event,
                                                          NotificationRow.channel == channel, NotificationRow.status == "sent")) is not None

    def _record(self, db, ref: str, event: str, channel: str, to: str, status: str, detail: str | None = None) -> None:
        db.add(NotificationRow(ref=ref, event=event, channel=channel, destination=to[:254], status=status, detail=detail,
                               created_at=utcnow()))
        db.commit()

    def send(self, ref: str, event: str, title: str, text: str, account_id: str | None, email: str | None,
             phone: str | None, data: dict[str, str]) -> list[str]:
        """Push, then email, then (only if neither went) SMS. Returns the channels that went."""
        went: list[str] = []
        with self.db() as db:
            if account_id:
                acc = db.get(AccountRow, account_id)
                email, phone = email or (acc.email if acc else None), phone or (acc.phone if acc else None)
                devices = db.scalars(select(DeviceRow).where(DeviceRow.account_id == account_id)).all()
                if devices and not self._done(db, ref, event, "push"):
                    for d in devices:
                        try:
                            self.msg.push(d.token, title, text, data)
                            went.append("push")
                        except PushGone:
                            db.execute(delete(DeviceRow).where(DeviceRow.token == d.token))
                        except Exception as exc:  # noqa: BLE001
                            self._record(db, ref, event, "push", d.token, "failed", str(exc)[:500])
                    if "push" in went:
                        self._record(db, ref, event, "push", account_id, "sent")
            if email and not self._done(db, ref, event, "email"):
                try:
                    self.msg.email(email, f"PetPop: {title}", text)
                    self._record(db, ref, event, "email", email, "sent")
                    went.append("email")
                except Exception as exc:  # noqa: BLE001
                    self._record(db, ref, event, "email", email, "failed", str(exc)[:500])
            if phone and not went and not self._done(db, ref, event, "sms"):
                try:
                    self.msg.sms(phone, f"PetPop: {text}")
                    self._record(db, ref, event, "sms", phone, "sent")
                    went.append("sms")
                except Exception as exc:  # noqa: BLE001
                    self._record(db, ref, event, "sms", phone, "failed", str(exc)[:500])
        return went
