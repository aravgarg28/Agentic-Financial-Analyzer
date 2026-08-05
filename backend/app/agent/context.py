"""Request-scoped agent context (T-030, AGT-01).

The authenticated household id is injected here by the executor before any tool
runs, and read by tools from this contextvar. It is deliberately NOT a tool
parameter, so a (possibly prompt-injected) model cannot choose or override which
household's data a tool reads. Tools raise if the context was not set.
"""
from __future__ import annotations

from contextvars import ContextVar

_current_household_id: ContextVar[int | None] = ContextVar(
    "current_household_id", default=None
)


def set_household(household_id: int) -> object:
    """Bind the household for the current agent turn. Returns a reset token."""
    return _current_household_id.set(household_id)


def reset_household(token: object) -> None:
    _current_household_id.reset(token)  # type: ignore[arg-type]


def current_household_id() -> int:
    hid = _current_household_id.get()
    if hid is None:
        # A tool ran without an executor-established tenant context — refuse
        # rather than fall back to any default (which is exactly the AGT-01 bug).
        raise RuntimeError("No household context set for agent tool execution.")
    return hid
