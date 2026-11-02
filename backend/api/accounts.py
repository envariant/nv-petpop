"""Customer accounts (decision 126). No passwords: an account signs in with a one-time code sent to its email or phone,
or with Sign in with Apple or Google.

Uniqueness: an account's email and phone are stored only once verified (a code, or the provider's verified email) and
each belongs to one account. Apple or Google with a verified email that an account already holds signs in to that
account and links the provider to it; otherwise the first sign-in creates the account. An email or phone added later
must not belong to another account (409). An account keeps at least one way to sign in: removing the last one is
refused. Deleting an account removes its identities, sessions and devices and clears it from its orders.

    PETPOP_APPLE_CLIENT_IDS   the audiences Apple tokens may carry: the iOS bundle id, and the Services ID for the web
    PETPOP_GOOGLE_CLIENT_IDS  the OAuth client ids Google tokens may carry (web, iOS, Android); the first is the web one
    PETPOP_AUTH_FAKE=1        tests only: tokens "fake:<subject>:<email>" stand in for Apple and Google
    PETPOP_DEFAULT_COUNTRY_CODE  for phone numbers given without one (default 65, Singapore)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update

from . import models as m
from .contract import ApiError
from .db import AccountRow, AccountSessionRow, CompositionRow, DeviceRow, IdentityRow, OtpRow, utcnow
from .messaging import Messenger

SESSION_DAYS = 90
CODE_TTL_S = 600
CODE_TRIES = 5
RESEND_S = 30
CODES_PER_HOUR = 10
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
ISSUERS = {"apple": ("https://appleid.apple.com",), "google": ("https://accounts.google.com", "accounts.google.com")}
JWKS = {"apple": "https://appleid.apple.com/auth/keys", "google": "https://www.googleapis.com/oauth2/v3/certs"}


# --------------------------------------------------------------------------- normalising and masking
def normalise(channel: str, raw: str) -> str:
    """A canonical email (lower case) or phone number (E.164); 422 when it is not one."""
    raw = raw.strip()
    if channel == "email":
        email = raw.lower()
        if not EMAIL_RE.match(email):
            raise ApiError(422, "that does not look like an email address")
        return email
    digits = re.sub(r"[\s\-().]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        cc = os.environ.get("PETPOP_DEFAULT_COUNTRY_CODE", "65")
        digits = f"+{cc}{digits.lstrip('0')}"
    if not re.fullmatch(r"\+[1-9]\d{7,14}", digits):
        raise ApiError(422, "that does not look like a phone number")
    return digits


def mask(channel: str, value: str | None) -> str | None:
    if not value:
        return None
    if channel == "email":
        user, _, domain = value.partition("@")
        return f"{user[:1]}{'•' * max(1, len(user) - 1)}@{domain}"
    return f"{value[:3]}{'•' * max(0, len(value) - 7)}{value[-4:]}"


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=UTC) if d and d.tzinfo is None else d


# --------------------------------------------------------------------------- Apple and Google id tokens
class TokenVerifier:
    """Checks an Apple or Google id token: signature against the provider's published keys (cached), issuer,
    audience (our client ids), expiry and, for Apple, the nonce."""

    def __init__(self) -> None:
        self.fake = os.environ.get("PETPOP_AUTH_FAKE", "0") == "1"
        self.audiences = {p: [x.strip() for x in os.environ.get(f"PETPOP_{p.upper()}_CLIENT_IDS", "").split(",") if x.strip()]
                          for p in ("apple", "google")}
        self._jwks: dict[str, Any] = {}

    def enabled(self, provider: str) -> bool:
        return self.fake or bool(self.audiences[provider])

    def verify(self, provider: str, token: str, nonce: str | None) -> dict[str, Any]:
        if self.fake and token.startswith("fake:"):
            _, sub, email = (token.split(":", 2) + [""])[:3]
            return {"sub": f"{provider}-{sub}", "email": email or None, "email_verified": bool(email)}
        if not self.audiences[provider]:
            raise ApiError(404, f"Sign in with {provider.title()} is not set up on this server")
        import jwt  # noqa: PLC0415

        try:
            client = self._jwks.get(provider) or jwt.PyJWKClient(JWKS[provider], cache_keys=True, lifespan=3600)
            self._jwks[provider] = client
            key = client.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audiences[provider], issuer=ISSUERS[provider],
                                options={"require": ["exp", "iat", "sub", "aud", "iss"]})
        except jwt.PyJWTError as exc:
            raise ApiError(401, f"the {provider.title()} sign-in could not be verified: {exc}") from exc
        if nonce and claims.get("nonce") not in (nonce, hashlib.sha256(nonce.encode()).hexdigest()):
            raise ApiError(401, "the sign-in nonce does not match")
        claims["email_verified"] = str(claims.get("email_verified", "")).lower() == "true"
        return claims


# --------------------------------------------------------------------------- the account service
class Accounts:
    def __init__(self, s, db, messenger: Messenger, verifier: TokenVerifier | None = None) -> None:
        self.s, self.db, self.msg = s, db, messenger
        self.secret = s.secret
        self.verifier = verifier or TokenVerifier()
        self.channels = {"email": True, "phone": True}

    # -- configuration
    def config(self) -> m.AuthConfig:
        apple, google = self.verifier.audiences["apple"], self.verifier.audiences["google"]
        return m.AuthConfig(email=self.channels["email"], phone=self.channels["phone"],
                            apple_client_id=apple[-1] if apple else ("fake" if self.verifier.fake else None),
                            google_client_id=google[0] if google else ("fake" if self.verifier.fake else None),
                            dev_codes=self.msg.dev, fake_providers=self.verifier.fake)

    # -- models
    def model(self, db, row: AccountRow) -> m.Account:
        providers = sorted(db.scalars(select(IdentityRow.provider).where(IdentityRow.account_id == row.id)).all())
        return m.Account(account_id=row.id, name=row.name, email=row.email, phone=row.phone, providers=providers,
                         created_at=_aware(row.created_at))

    def _session(self, db, row: AccountRow, created: bool = False, linked: str | None = None) -> m.AccountSession:
        token = "pa_" + secrets.token_urlsafe(32)
        db.add(AccountSessionRow(token_hash=_hash(token), account_id=row.id, created_at=utcnow(),
                                 expires_at=utcnow() + timedelta(days=SESSION_DAYS)))
        db.commit()
        return m.AccountSession(token=token, account=self.model(db, row), created=created, linked=linked)

    # -- codes
    def send_code(self, body: m.CodeRequest) -> m.CodeSent:
        to = normalise(body.channel, body.to)
        now = utcnow()
        with self.db() as db:
            recent = db.scalars(select(OtpRow.created_at).where(OtpRow.channel == body.channel, OtpRow.destination == to,
                                                                 OtpRow.created_at > now - timedelta(hours=1))).all()
            wait = int(os.environ.get("PETPOP_CODE_RESEND_S", RESEND_S))  # tests set 0
            if wait and recent and max(recent) > now - timedelta(seconds=wait):
                raise ApiError(429, f"a code was just sent; ask again in {wait} seconds")
            if len(recent) >= CODES_PER_HOUR:
                raise ApiError(429, "too many codes for this address; try again in an hour")
            code = f"{secrets.randbelow(10**6):06d}"
            db.add(OtpRow(channel=body.channel, destination=to, code_hash=_hash(self.secret, to, code), created_at=now,
                          expires_at=now + timedelta(seconds=CODE_TTL_S)))
            db.commit()
        text = f"Your PetPop code is {code}. It expires in 10 minutes."
        if body.channel == "email":
            self.msg.email(to, "Your PetPop code", text)
        else:
            self.msg.sms(to, text)
        return m.CodeSent(channel=body.channel, to=mask(body.channel, to), expires_in=CODE_TTL_S,
                          dev_code=code if self.msg.dev else None)

    def _check_code(self, db, channel: str, to: str, code: str) -> None:
        row = db.scalar(select(OtpRow).where(OtpRow.channel == channel, OtpRow.destination == to, OtpRow.used.is_(False))
                        .order_by(OtpRow.created_at.desc(), OtpRow.id.desc()))
        if not row or _aware(row.expires_at) < datetime.now(UTC):
            raise ApiError(400, "that code has expired; ask for a new one")
        if row.attempts >= CODE_TRIES:
            raise ApiError(429, "too many tries; ask for a new code")
        row.attempts += 1
        if not hmac.compare_digest(row.code_hash, _hash(self.secret, to, code)):
            db.commit()
            raise ApiError(400, "that code is not right")
        row.used = True
        db.commit()

    def verify_code(self, body: m.CodeVerify) -> m.AccountSession:
        """Sign in with a code; the first verified sign-in to an email or phone creates its account."""
        to = normalise(body.channel, body.to)
        col = AccountRow.email if body.channel == "email" else AccountRow.phone
        with self.db() as db:
            self._check_code(db, body.channel, to, body.code)
            row = db.scalar(select(AccountRow).where(col == to))
            created = row is None
            if created:
                row = AccountRow(id="a_" + uuid.uuid4().hex[:16], name=(body.name or "").strip() or None, created_at=utcnow(),
                                 **{"email" if body.channel == "email" else "phone": to})
                db.add(row)
                db.commit()
            return self._session(db, row, created=created)

    # -- Apple and Google
    def provider_sign_in(self, provider: str, body: m.ProviderSignIn) -> m.AccountSession:
        claims = self.verifier.verify(provider, body.id_token, body.nonce)
        sub = str(claims["sub"])
        email = str(claims["email"]).lower() if claims.get("email") and claims.get("email_verified") else None
        with self.db() as db:
            ident = db.get(IdentityRow, (provider, sub))
            linked = None
            created = False
            if ident:
                row = db.get(AccountRow, ident.account_id)
                ident.email = email or ident.email
            else:
                row = db.scalar(select(AccountRow).where(AccountRow.email == email)) if email else None
                if row:
                    linked = provider  # the same verified email: one account (decision 126)
                else:
                    row = AccountRow(id="a_" + uuid.uuid4().hex[:16], email=email, created_at=utcnow())
                    db.add(row)
                    created = True
                db.add(IdentityRow(provider=provider, subject=sub, account_id=row.id, email=email, created_at=utcnow()))
            if body.name and not row.name:
                row.name = body.name.strip()[:60]
            db.commit()
            return self._session(db, row, created=created, linked=linked)

    # -- who is asking
    def account_for(self, token: str | None, required: bool = True) -> AccountRow | None:
        if not token:
            if required:
                raise ApiError(401, "sign in first")
            return None
        with self.db() as db:
            sess = db.get(AccountSessionRow, _hash(token))
            if not sess or _aware(sess.expires_at) < datetime.now(UTC):
                if required:
                    raise ApiError(401, "your sign-in has expired; sign in again")
                return None
            row = db.get(AccountRow, sess.account_id)
            db.expunge(row)
            return row

    def me(self, token: str | None) -> m.Account:
        acc = self.account_for(token)
        with self.db() as db:
            return self.model(db, db.get(AccountRow, acc.id))

    def patch(self, token: str | None, body: m.AccountPatch) -> m.Account:
        acc = self.account_for(token)
        with self.db() as db:
            row = db.get(AccountRow, acc.id)
            if body.name is not None:
                row.name = body.name.strip() or None
            db.commit()
            return self.model(db, row)

    def add_contact(self, token: str | None, body: m.CodeVerify) -> m.Account:
        """Add or change the account's email or phone, proven with a code sent to it."""
        acc = self.account_for(token)
        to = normalise(body.channel, body.to)
        col = AccountRow.email if body.channel == "email" else AccountRow.phone
        with self.db() as db:
            other = db.scalar(select(AccountRow).where(col == to, AccountRow.id != acc.id))
            if other:
                raise ApiError(409, f"that {'email' if body.channel == 'email' else 'phone number'} belongs to another account")
            self._check_code(db, body.channel, to, body.code)
            row = db.get(AccountRow, acc.id)
            setattr(row, "email" if body.channel == "email" else "phone", to)
            db.commit()
            return self.model(db, row)

    def _ways(self, db, row: AccountRow) -> int:
        idents = db.scalar(select(func.count()).select_from(IdentityRow).where(IdentityRow.account_id == row.id)) or 0
        return idents + (1 if row.email else 0) + (1 if row.phone else 0)

    def remove_contact(self, token: str | None, channel: str) -> m.Account:
        acc = self.account_for(token)
        with self.db() as db:
            row = db.get(AccountRow, acc.id)
            if not getattr(row, channel if channel == "email" else "phone"):
                raise ApiError(404, f"the account has no {channel}")
            if self._ways(db, row) <= 1:
                raise ApiError(409, "that is your only way to sign in; add another first")
            setattr(row, "email" if channel == "email" else "phone", None)
            db.commit()
            return self.model(db, row)

    def link(self, token: str | None, provider: str, body: m.ProviderSignIn) -> m.Account:
        """Link Apple or Google to the signed-in account. 409 when that identity, or its verified email, is another
        account's."""
        acc = self.account_for(token)
        claims = self.verifier.verify(provider, body.id_token, body.nonce)
        sub = str(claims["sub"])
        email = str(claims["email"]).lower() if claims.get("email") and claims.get("email_verified") else None
        with self.db() as db:
            ident = db.get(IdentityRow, (provider, sub))
            if ident and ident.account_id != acc.id:
                raise ApiError(409, f"that {provider.title()} sign-in belongs to another account")
            if email and db.scalar(select(AccountRow.id).where(AccountRow.email == email, AccountRow.id != acc.id)):
                raise ApiError(409, f"the email of that {provider.title()} sign-in belongs to another account")
            row = db.get(AccountRow, acc.id)
            if not ident:
                db.add(IdentityRow(provider=provider, subject=sub, account_id=acc.id, email=email, created_at=utcnow()))
            if email and not row.email:
                row.email = email  # a verified email the account did not have
            db.commit()
            return self.model(db, row)

    def unlink(self, token: str | None, provider: str) -> m.Account:
        acc = self.account_for(token)
        with self.db() as db:
            row = db.get(AccountRow, acc.id)
            idents = db.scalars(select(IdentityRow).where(IdentityRow.account_id == row.id, IdentityRow.provider == provider)).all()
            if not idents:
                raise ApiError(404, f"{provider.title()} is not linked")
            if self._ways(db, row) - len(idents) < 1:
                raise ApiError(409, "that is your only way to sign in; add another first")
            for i in idents:
                db.delete(i)
            db.commit()
            return self.model(db, row)

    def sign_out(self, token: str | None) -> None:
        if token:
            with self.db() as db:
                db.execute(delete(AccountSessionRow).where(AccountSessionRow.token_hash == _hash(token)))
                db.commit()

    def delete(self, token: str | None) -> None:
        """Delete the account (App Store guideline 5.1.1(v)): its sign-ins, sessions and devices go, and its orders
        keep no link to it or its contact details."""
        acc = self.account_for(token)
        with self.db() as db:
            for T in (AccountSessionRow, IdentityRow, DeviceRow):
                db.execute(delete(T).where(T.account_id == acc.id))
            db.execute(update(CompositionRow).where(CompositionRow.account_id == acc.id)
                       .values(account_id=None, contact_email=None, contact_phone=None))
            db.execute(delete(AccountRow).where(AccountRow.id == acc.id))
            db.commit()

    # -- devices
    def add_device(self, token: str | None, body: m.Device) -> m.Device:
        acc = self.account_for(token)
        with self.db() as db:
            row = db.get(DeviceRow, body.token)
            if row:  # a device moves to whoever signed in on it last
                row.account_id, row.platform = acc.id, body.platform
            else:
                db.add(DeviceRow(token=body.token, account_id=acc.id, platform=body.platform, created_at=utcnow()))
            db.commit()
        return body

    def remove_device(self, token: str | None, device: str) -> None:
        acc = self.account_for(token)
        with self.db() as db:
            db.execute(delete(DeviceRow).where(DeviceRow.token == device, DeviceRow.account_id == acc.id))
            db.commit()

    # -- orders
    def order_contact(self, acc: AccountRow | None, contact: m.OrderContact | None) -> tuple[str | None, str | None]:
        """The email and phone to tell about an order: the given contact (normalised), else the account's own."""
        email = normalise("email", contact.email) if contact and contact.email else None
        phone = normalise("phone", contact.phone) if contact and contact.phone else None
        if acc and not (email or phone):
            email, phone = acc.email, acc.phone
        if not (email or phone or acc):
            raise ApiError(422, "an email or a phone number is needed so we can tell you when it is ready")
        return email, phone
