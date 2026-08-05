"""Unit tests for security primitives — no database required.

Covers SEC-03 (argon2id), SEC-05 (password policy), token hashing (SEC-02),
the rate limiter's 429 behaviour (INF-05), and the agent tenant-context guard
(AGT-01).
"""
from __future__ import annotations

import pytest

from app.agent import context as agent_context
from app.modules.common import ratelimit
from app.modules.identity import security


def test_password_hash_is_argon2id():
    """SEC-03: hashes are argon2id, salted, and verify correctly."""
    h = security.hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    # Salted: two hashes of the same password differ.
    assert h != security.hash_password("correct horse battery")
    ok, _ = security.verify_password(h, "correct horse battery")
    assert ok
    bad, _ = security.verify_password(h, "wrong password here")
    assert not bad


def test_password_policy_rejects_short_and_common():
    """SEC-05: min length + common-password rejection."""
    with pytest.raises(security.WeakPasswordError):
        security.validate_password("short")
    with pytest.raises(security.WeakPasswordError):
        security.validate_password("password123")  # common
    # A long, uncommon password passes.
    security.validate_password("a-perfectly-fine-passphrase")


def test_token_hash_is_stable_and_not_the_token():
    token = security.generate_session_token()
    assert security.hash_token(token) == security.hash_token(token)
    assert security.hash_token(token) != token
    assert len(security.hash_token(token)) == 64  # sha256 hex


def test_rate_limiter_returns_429_not_500():
    """INF-05: exceeding the window raises HTTPException(429) with Retry-After."""
    from fastapi.exceptions import HTTPException

    store = ratelimit.RateLimitStore()
    limit = ratelimit.Limit(max_events=2, window_seconds=60)
    assert store.hit("k", limit)[0] is True
    assert store.hit("k", limit)[0] is True
    allowed, retry_after = store.hit("k", limit)
    assert allowed is False
    assert retry_after >= 1

    # And the dependency helper surfaces a real 429.
    ratelimit.store.reset()
    tiny = ratelimit.Limit(max_events=1, window_seconds=60)
    ratelimit._enforce("x", tiny)  # first ok
    with pytest.raises(HTTPException) as exc:
        ratelimit._enforce("x", tiny)
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


def test_rate_limiter_bounded_memory():
    """INF-05: the store evicts LRU keys and never grows without bound."""
    store = ratelimit.RateLimitStore(max_keys=100)
    limit = ratelimit.Limit(max_events=1, window_seconds=60)
    for i in range(1000):
        store.hit(f"key-{i}", limit)
    assert len(store._windows) <= 100


def test_agent_context_refuses_without_tenant():
    """AGT-01: a tool reading the household id with no context set must fail
    closed, never fall back to a default tenant."""
    with pytest.raises(RuntimeError):
        agent_context.current_household_id()

    token = agent_context.set_household(42)
    try:
        assert agent_context.current_household_id() == 42
    finally:
        agent_context.reset_household(token)
    with pytest.raises(RuntimeError):
        agent_context.current_household_id()


def test_agent_tools_expose_no_identity_params():
    """AGT-01: no registered tool accepts a user_id/household_id argument."""
    from app.agent.tools import ALL_TOOLS

    for t in ALL_TOOLS:
        arg_names = set(t.args.keys())
        assert "user_id" not in arg_names, t.name
        assert "household_id" not in arg_names, t.name


def test_no_mutation_tools_registered():
    """AGT-02: the agent has no write tools."""
    from app.agent.tools import ALL_TOOLS

    names = {t.name for t in ALL_TOOLS}
    assert "update_budget" not in names
    assert all("update" not in n and "set_" not in n for n in names)
