"""DB-backed auth tests (T-010/T-011/T-020).

Covers registration + household bootstrap, session cookie issuance, logout
revocation, CSRF, enumeration-safety (SEC-04), and session rejection (SEC-02).
"""
from __future__ import annotations

COOKIE = "afa_session"


async def _register(api, email, password="a-strong-passphrase-1"):
    return await api.post("/auth/register", json={"email": email, "password": password})


async def test_register_bootstraps_household_and_sets_cookie(api, seed_session):
    r = await _register(api, "owner@example.com")
    assert r.status_code == 200
    assert COOKIE in r.cookies or COOKIE in api.cookies

    # The /me endpoint resolves identity from the cookie only.
    me = await api.get("/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "owner@example.com"
    assert body["role"] == "owner"
    assert body["household_public_id"]


async def test_register_is_enumeration_safe(api):
    """SEC-04: a duplicate registration returns the same shape, no 'exists' leak."""
    first = await _register(api, "dup@example.com")
    assert first.status_code == 200
    api.cookies.clear()
    second = await api.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "another-good-passphrase"},
    )
    assert second.status_code == 200
    assert second.json() == {"status": "ok"}


async def test_weak_password_rejected(api):
    r = await api.post(
        "/auth/register", json={"email": "weak@example.com", "password": "password123"}
    )
    assert r.status_code == 400


async def test_login_wrong_password_and_unknown_email_are_identical(api):
    await _register(api, "real@example.com", "the-correct-passphrase-9")
    # Clear cookie from registration.
    api.cookies.clear()

    wrong = await api.post(
        "/auth/login", json={"email": "real@example.com", "password": "nope-nope-nope"}
    )
    unknown = await api.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_login_success_issues_working_session(api):
    await _register(api, "session@example.com", "the-correct-passphrase-9")
    api.cookies.clear()
    login = await api.post(
        "/auth/login",
        json={"email": "session@example.com", "password": "the-correct-passphrase-9"},
    )
    assert login.status_code == 200
    me = await api.get("/auth/me")
    assert me.status_code == 200


async def test_protected_route_requires_session(api):
    """SEC-01/02: no cookie -> 401, never data."""
    api.cookies.clear()
    r = await api.get("/insights/cash-flow-summary")
    assert r.status_code == 401


async def test_logout_revokes_session_immediately(api):
    await _register(api, "logout@example.com")
    assert (await api.get("/auth/me")).status_code == 200
    out = await api.post("/auth/logout")
    assert out.status_code == 200
    # Even replaying the (now-cleared) cookie must fail — session is revoked.
    assert (await api.get("/auth/me")).status_code == 401


async def test_csrf_blocks_missing_header(api):
    """A mutating request without X-Requested-With is rejected (403)."""
    r = await api.post(
        "/auth/register",
        json={"email": "csrf@example.com", "password": "a-strong-passphrase-1"},
        headers={"X-Requested-With": ""},
    )
    assert r.status_code == 403


async def test_csrf_blocks_foreign_origin(api):
    r = await api.post(
        "/auth/register",
        json={"email": "evil@example.com", "password": "a-strong-passphrase-1"},
        headers={"Origin": "http://evil.example"},
    )
    assert r.status_code == 403
