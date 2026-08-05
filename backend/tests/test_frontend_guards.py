"""Repo-level guards for frontend security regressions (no DB needed).

SEC-06: the login form must ship with no prefilled credentials, and the client
must never send a user_id/household_id (SEC-01). These greps fail loudly if a
future edit reintroduces either.
"""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


def test_login_form_has_no_prefilled_credentials():
    page = _read("app/page.tsx")
    assert "player1" not in page
    assert 'password: "password"' not in page
    # The initial credential state must be empty strings.
    assert 'useState({ email: "", password: "" })' in page


def test_api_client_sends_no_client_identity():
    api = _read("lib/api.ts")
    # No identity is sent as a query param or JSON key (comments may mention
    # the words when explaining the policy; usage is what matters).
    assert "?user_id=" not in api
    assert "user_id:" not in api
    assert "household_id:" not in api
    assert "&user_id=" not in api
    # Cookie-based auth is in force.
    assert 'credentials: "include"' in api
