"""Outgoing messages (decision 126): sign-in codes by email or SMS, and order notifications by push, email or SMS.

    PETPOP_EMAIL   log (default: written to the log and kept in an outbox for tests) | ses (Amazon SES; PETPOP_EMAIL_FROM,
                   a verified sender; credentials from the EC2 instance role)
    PETPOP_SMS     log (default) | sns (Amazon SNS, transactional SMS; PETPOP_SMS_SENDER_ID optional)
    PETPOP_PUSH    log (default) | fcm (Firebase Cloud Messaging HTTP v1; PETPOP_FCM_CREDENTIALS, the path of a service
                   account JSON with the Firebase Cloud Messaging role; never committed)

SES, SNS and SMS are paid per message (cheap, but paid): each is off until Nishant switches it on (CLAUDE.md). Firebase
Cloud Messaging is free.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("petpop.messaging")


@dataclass
class Sent:
    channel: str  # email | sms | push
    to: str
    subject: str
    text: str
    data: dict[str, str] = field(default_factory=dict)


class Outbox:
    """Every message the log senders 'sent' (development and tests); a bounded list."""

    def __init__(self) -> None:
        self.items: list[Sent] = []
        self._lock = threading.Lock()

    def add(self, s: Sent) -> None:
        with self._lock:
            self.items.append(s)
            del self.items[:-200]

    def last(self, to: str) -> Sent | None:
        with self._lock:
            return next((s for s in reversed(self.items) if s.to == to), None)


class PushGone(Exception):
    """The device token is no longer valid (the app was uninstalled): forget it."""


class Messenger:
    def __init__(self, outbox: Outbox | None = None, client: httpx.Client | None = None) -> None:
        self.outbox = outbox or Outbox()
        self.email_mode = os.environ.get("PETPOP_EMAIL", "log")
        self.sms_mode = os.environ.get("PETPOP_SMS", "log")
        self.push_mode = os.environ.get("PETPOP_PUSH", "log")
        self.email_from = os.environ.get("PETPOP_EMAIL_FROM", "PetPop <hello@petpop.sg>")
        self.client = client or httpx.Client(timeout=15)
        self._fcm: FcmAuth | None = None

    @property
    def dev(self) -> bool:
        """Codes can be shown to the developer: nothing goes out by email or SMS."""
        return self.email_mode == "log" and self.sms_mode == "log"

    # -- email and SMS
    def email(self, to: str, subject: str, text: str) -> None:
        if self.email_mode == "ses":
            import boto3  # noqa: PLC0415

            boto3.client("sesv2").send_email(FromEmailAddress=self.email_from, Destination={"ToAddresses": [to]},
                                             Content={"Simple": {"Subject": {"Data": subject}, "Body": {"Text": {"Data": text}}}})
        else:
            log.info("email to %s: %s | %s", to, subject, text)
        self.outbox.add(Sent("email", to, subject, text))

    def sms(self, to: str, text: str) -> None:
        if self.sms_mode == "sns":
            import boto3  # noqa: PLC0415

            attrs: dict[str, Any] = {"AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"}}
            sender = os.environ.get("PETPOP_SMS_SENDER_ID")
            if sender:
                attrs["AWS.SNS.SMS.SenderID"] = {"DataType": "String", "StringValue": sender}
            boto3.client("sns").publish(PhoneNumber=to, Message=text, MessageAttributes=attrs)
        else:
            log.info("sms to %s: %s", to, text)
        self.outbox.add(Sent("sms", to, "", text))

    # -- push
    def push(self, token: str, title: str, body: str, data: dict[str, str] | None = None) -> None:
        data = data or {}
        if self.push_mode == "fcm":
            self._fcm = self._fcm or FcmAuth(Path(os.environ["PETPOP_FCM_CREDENTIALS"]), self.client)
            r = self.client.post(f"https://fcm.googleapis.com/v1/projects/{self._fcm.project}/messages:send",
                                 headers={"Authorization": f"Bearer {self._fcm.token()}"},
                                 json={"message": {"token": token, "notification": {"title": title, "body": body}, "data": data}})
            if r.status_code == 404 or "UNREGISTERED" in r.text:  # FCM: the app was uninstalled or the token rotated
                raise PushGone(token)
            r.raise_for_status()
        else:
            log.info("push to %s…: %s | %s", token[:12], title, body)
        self.outbox.add(Sent("push", token, title, body, data))


class FcmAuth:
    """An OAuth access token for FCM from a service account key (a signed JWT exchanged at Google's token endpoint),
    refreshed before it expires."""

    def __init__(self, path: Path, client: httpx.Client) -> None:
        self.info = json.loads(path.read_text())
        self.project = self.info["project_id"]
        self.client = client
        self._token = ""
        self._until = 0.0

    def token(self) -> str:
        if time.time() < self._until - 120:
            return self._token
        import jwt  # noqa: PLC0415

        now = int(time.time())
        assertion = jwt.encode({"iss": self.info["client_email"], "scope": "https://www.googleapis.com/auth/firebase.messaging",
                                "aud": self.info["token_uri"], "iat": now, "exp": now + 3600},
                               self.info["private_key"], algorithm="RS256")
        r = self.client.post(self.info["token_uri"], data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                                           "assertion": assertion})
        r.raise_for_status()
        body = r.json()
        self._token, self._until = body["access_token"], time.time() + int(body.get("expires_in", 3600))
        return self._token
