"""Customer accounts (decision 126, API 3.10.0) against both servers: codes by email and phone, Sign in with Apple and
Google (fake tokens), one account per email and per phone, linking, profile, contacts, sign-out, deletion, and orders
placed as a guest (a contact is required) or as an account."""
from __future__ import annotations

from petpop_library.composition import sample

from .oas import check

A = "/api/v1/account"
K = "/api/v1/kiosk"


def code(client, channel: str, to: str) -> str:
    r = client.post(f"{A}/code", json={"channel": channel, "to": to})
    assert r.status_code == 202, r.text
    sent = check(f"{A}/code", "post", r)
    assert sent["dev_code"] and len(sent["dev_code"]) == 6
    return sent["dev_code"]


def sign_in(client, channel: str, to: str, name: str | None = None) -> dict:
    r = client.post(f"{A}/verify", json={"channel": channel, "to": to, "code": code(client, channel, to), "name": name})
    assert r.status_code == 200, r.text
    return check(f"{A}/verify", "post", r)


def auth(s: dict) -> dict:
    return {"Authorization": f"Bearer {s['token']}"}


def test_config_and_codes(client, monkeypatch):
    monkeypatch.setenv("PETPOP_CODE_RESEND_S", "30")
    cfg = check(f"{A}/config", "get", client.get(f"{A}/config"))
    assert cfg["email"] and cfg["phone"] and cfg["dev_codes"] and cfg["fake_providers"]
    assert client.post(f"{A}/code", json={"channel": "email", "to": "not-an-email"}).status_code == 422
    assert client.post(f"{A}/code", json={"channel": "phone", "to": "12"}).status_code == 422
    c = code(client, "email", "Mia@Example.com")
    assert client.post(f"{A}/code", json={"channel": "email", "to": "mia@example.com"}).status_code == 429  # 30 s
    monkeypatch.setenv("PETPOP_CODE_RESEND_S", "0")
    wrong = "000000" if c != "000000" else "111111"
    r = client.post(f"{A}/verify", json={"channel": "email", "to": "mia@example.com", "code": wrong})
    assert r.status_code == 400
    s = check(f"{A}/verify", "post", client.post(f"{A}/verify", json={"channel": "email", "to": "MIA@example.com", "code": c, "name": "Mia"}))
    assert s["created"] and s["account"]["email"] == "mia@example.com" and s["account"]["name"] == "Mia"
    assert client.post(f"{A}/verify", json={"channel": "email", "to": "mia@example.com", "code": c}).status_code == 400  # used


def test_one_account_per_email_and_phone_across_sign_in_methods(client):
    first = sign_in(client, "email", "leo@example.com", "Leo")
    assert sign_in(client, "email", "LEO@example.com")["account"]["account_id"] == first["account"]["account_id"]
    # Google with the same verified email: the same account, Google linked to it
    g = check(f"{A}/oauth/{{provider}}", "post", client.post(f"{A}/oauth/google", json={"id_token": "fake:g-leo:leo@example.com"}))
    assert g["account"]["account_id"] == first["account"]["account_id"] and g["linked"] == "google" and not g["created"]
    # Apple with a relay email: a new account
    ap = client.post(f"{A}/oauth/apple", json={"id_token": "fake:a-1:x1@privaterelay.appleid.com", "name": "Leo A"}).json()
    assert ap["created"] and ap["account"]["account_id"] != first["account"]["account_id"] and ap["account"]["name"] == "Leo A"
    # the same Apple identity signs in to the same account
    assert client.post(f"{A}/oauth/apple", json={"id_token": "fake:a-1:x1@privaterelay.appleid.com"}).json()["account"]["account_id"] == ap["account"]["account_id"]
    # a phone account; that phone cannot be added to another account
    ph = sign_in(client, "phone", "9123 4567")
    assert ph["account"]["phone"] == "+6591234567"
    c = code(client, "phone", "+65 9123 4567")
    r = client.post(f"{A}/me/contact", json={"channel": "phone", "to": "+6591234567", "code": c}, headers=auth(ap))
    assert r.status_code == 409
    # nor can the first account's email be added to the Apple one (the 30 s resend wait: use a fresh address first)
    assert client.post(f"{A}/me/contact", json={"channel": "email", "to": "leo@example.com", "code": "123456"},
                       headers=auth(ap)).status_code == 409


def test_profile_contacts_providers_sign_out_and_delete(client):
    s = sign_in(client, "email", "ava@example.com")
    me = check(f"{A}/me", "get", client.get(f"{A}/me", headers=auth(s)))
    assert me["providers"] == [] and me["phone"] is None
    assert client.get(f"{A}/me").status_code == 401
    me = check(f"{A}/me", "patch", client.patch(f"{A}/me", json={"name": "Ava"}, headers=auth(s)))
    assert me["name"] == "Ava"
    # add a phone with a code; it becomes a way to sign in
    c = code(client, "phone", "+6588880001")
    me = check(f"{A}/me/contact", "post", client.post(f"{A}/me/contact", json={"channel": "phone", "to": "+6588880001", "code": c}, headers=auth(s)))
    assert me["phone"] == "+6588880001"
    assert sign_in(client, "phone", "+6588880001")["account"]["account_id"] == me["account_id"]
    # link Google (a different Google email) and Apple, then unlink Google; the last way to sign in cannot be removed
    r = client.post(f"{A}/me/providers/google", json={"id_token": "fake:g-ava:ava.g@example.com"}, headers=auth(s))
    me = check(f"{A}/me/providers/{{provider}}", "post", r)
    assert me["providers"] == ["google"] and me["email"] == "ava@example.com"
    other = sign_in(client, "email", "zed@example.com")
    r = client.post(f"{A}/me/providers/google", json={"id_token": "fake:g-ava:ava.g@example.com"}, headers=auth(other))
    assert r.status_code == 409  # that Google sign-in is Ava's
    assert client.post(f"{A}/oauth/google", json={"id_token": "fake:g-ava:ava.g@example.com"}).json()["account"]["account_id"] == me["account_id"]
    me = check(f"{A}/me/providers/{{provider}}", "delete", client.delete(f"{A}/me/providers/google", headers=auth(s)))
    assert me["providers"] == []
    me = check(f"{A}/me/contact/{{channel}}", "delete", client.delete(f"{A}/me/contact/phone", headers=auth(s)))
    assert me["phone"] is None
    assert client.delete(f"{A}/me/contact/email", headers=auth(s)).status_code == 409  # the only way left
    # devices, sign-out, delete
    r = client.post(f"{A}/me/devices", json={"token": "fcm-token-123456", "platform": "ios"}, headers=auth(s))
    check(f"{A}/me/devices", "post", r)
    assert client.delete(f"{A}/me/devices", params={"token": "fcm-token-123456"}, headers=auth(s)).status_code == 204
    other = sign_in(client, "email", "ava@example.com")
    assert client.post(f"{A}/sign-out", headers=auth(other)).status_code == 204
    assert client.get(f"{A}/me", headers=auth(other)).status_code == 401
    assert client.delete(f"{A}/me", headers=auth(s)).status_code == 204
    assert client.get(f"{A}/me", headers=auth(s)).status_code == 401
    fresh = sign_in(client, "email", "ava@example.com")
    assert fresh["created"]  # the email is free again


def test_orders_need_a_contact_and_belong_to_their_account(client):
    sid = client.post(f"{K}/sessions", json={}).json()["session_id"]
    man = client.get(f"{K}/library/dog").json()["manifest"]
    new = lambda: client.post(f"{K}/compositions", json={"session_id": sid, "composition": sample(man)}).json()["composition_id"]  # noqa: E731
    guest = new()
    r = client.post(f"{K}/compositions/{guest}/export", json={})
    assert r.status_code == 422  # a guest must say how to reach them
    r = client.post(f"{K}/compositions/{guest}/export", json={"contact": {"phone": "+65 9000 1111"}})
    assert r.status_code == 202
    st = client.get(f"{K}/compositions/{guest}").json()
    assert st["contact"]["phone"].endswith("1111") and "•" in st["contact"]["phone"] and st["account_id"] is None
    s = sign_in(client, "email", "noah@example.com")
    mine = new()
    r = client.post(f"{K}/compositions/{mine}/export", json={}, headers=auth(s))  # the account's own email
    assert r.status_code == 202
    st = client.get(f"{K}/compositions/{mine}").json()
    assert st["account_id"] == s["account"]["account_id"] and st["contact"]["email"].endswith("@example.com")
    orders = check(f"{A}/me/orders", "get", client.get(f"{A}/me/orders", headers=auth(s)))
    assert [o["composition_id"] for o in orders["items"]] == [mine]
    staff = {"X-Staff-Token": "test-staff"}
    assert client.post(f"{K}/ops/orders/{mine}/ready").status_code == 403
    r = client.post(f"{K}/ops/orders/{mine}/ready", headers=staff)
    assert check(f"{K}/ops/orders/{{composition_id}}/ready", "post", r)["composition_id"] == mine
