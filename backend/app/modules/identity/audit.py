"""Audit-event writer (T-006, INF-06).

Call ``record_audit`` inside the same DB transaction as the action being
audited so the trail is consistent with the change. Never pass secrets or full
financial payloads in ``metadata``.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import AuditEvent
from app.observability import request_id_var


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    household_id: int | None = None,
    actor_user_id: int | None = None,
    target_type: str | None = None,
    target_public_id: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    """Append an audit event. The caller controls commit."""
    event = AuditEvent(
        household_id=household_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_public_id=target_public_id,
        request_id=request_id_var.get(),
        event_metadata=metadata,
    )
    session.add(event)
    return event
