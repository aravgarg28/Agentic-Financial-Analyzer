"""Rate limiting (T-012, SEC-04, INF-05).

A fixed-window counter kept in a bounded LRU map, exposed as FastAPI
dependencies. Design notes:

- **In-process, single instance.** Render free tier runs one instance, so an
  in-memory store is correct and costs no Upstash quota (ADR-12). The
  ``RateLimitStore`` interface is the seam for a shared store later.
- **Bounded memory (INF-05).** The old limiter used an unbounded dict keyed by
  IP. Here an ``OrderedDict`` caps the number of tracked keys and evicts the
  least-recently-used, so a flood of distinct IPs cannot exhaust memory.
- **Correct 429 (INF-05).** Limits raise ``HTTPException(429)`` with a
  ``Retry-After`` header — verified by test — instead of leaking as a 500.

Login *lockout* (surviving restarts) is handled separately in the Postgres
``users.locked_until`` column (service.authenticate); this module governs
per-window request rates.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass

from fastapi import Request
from fastapi import status as http_status
from fastapi.exceptions import HTTPException


@dataclass(frozen=True)
class Limit:
    """A rate rule: at most ``max_events`` per ``window_seconds`` per key."""

    max_events: int
    window_seconds: int


class RateLimitStore:
    """Bounded fixed-window counter store (LRU eviction of stale keys)."""

    def __init__(self, max_keys: int = 10_000) -> None:
        self._max_keys = max_keys
        # key -> (window_start_epoch, count)
        self._windows: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def hit(self, key: str, limit: Limit, now: float | None = None) -> tuple[bool, int]:
        """Register one event. Returns ``(allowed, retry_after_seconds)``."""
        now = time.monotonic() if now is None else now
        window_start, count = self._windows.get(key, (now, 0))

        if now - window_start >= limit.window_seconds:
            # Window elapsed — reset.
            window_start, count = now, 0

        count += 1
        self._windows[key] = (window_start, count)
        self._windows.move_to_end(key)
        self._evict()

        if count > limit.max_events:
            retry_after = int(limit.window_seconds - (now - window_start)) + 1
            return False, max(retry_after, 1)
        return True, 0

    def _evict(self) -> None:
        while len(self._windows) > self._max_keys:
            self._windows.popitem(last=False)

    def reset(self) -> None:
        self._windows.clear()


# Process-wide store. Swap the instance (or the class) to move to a shared
# backend without touching call sites.
store = RateLimitStore()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce(key: str, limit: Limit) -> None:
    allowed, retry_after = store.hit(key, limit)
    if not allowed:
        raise HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please retry later.",
            headers={"Retry-After": str(retry_after)},
        )


# ── Named scopes (security-model §9) ──────────────────────────────────────────

LOGIN_PER_IP = Limit(max_events=20, window_seconds=3600)
REGISTER_PER_IP = Limit(max_events=5, window_seconds=3600)
AGENT_PER_USER = Limit(max_events=30, window_seconds=60)
GENERAL_PER_IP = Limit(max_events=300, window_seconds=60)


def limit_login(request: Request) -> None:
    """Per-IP throttle on login (paired with per-account DB lockout)."""
    _enforce(f"login:ip:{_client_ip(request)}", LOGIN_PER_IP)


def limit_register(request: Request) -> None:
    _enforce(f"register:ip:{_client_ip(request)}", REGISTER_PER_IP)


def limit_general(request: Request) -> None:
    _enforce(f"general:ip:{_client_ip(request)}", GENERAL_PER_IP)
