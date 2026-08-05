"""Identity service layer (T-010/T-011/T-020).

Pure data/logic operations on the identity aggregate. HTTP concerns (cookies,
status codes) live in ``routes.py``; this module returns domain objects and
raises typed errors. All session state is server-side (SEC-02).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.identity import security
from app.modules.identity.audit import record_audit
from app.modules.identity.models import (
    AuthSession,
    Household,
    Membership,
    User,
)


def _now() -> datetime:
    return datetime.now(UTC)


class RegistrationConflict(Exception):
    """Email already registered. Surfaced uniformly to avoid enumeration."""


class AuthenticationError(Exception):
    """Login failed (bad credentials, locked, or disabled)."""


class AccountLocked(AuthenticationError):
    """Account is temporarily locked due to failed attempts (SEC-04)."""


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, resolved from a session — never from client input.

    Carries both internal ids (for tenant-scoped queries) and public ids (for
    responses). ``household_id`` is the tenant key enforced on every data route.
    """

    user_id: int
    household_id: int
    user_public_id: str
    household_public_id: str
    role: str
    session_id: int


# ── Registration + household bootstrap (T-010 + T-020) ────────────────────────

async def register_user(
    session: AsyncSession, *, email: str, password: str
) -> User:
    """Create a user, their household, and an owner membership atomically.

    Enforces the password policy first. On duplicate email raises
    RegistrationConflict. The caller commits; on any error the whole unit rolls
    back so a user never exists without a household (T-020 atomicity).
    """
    security.validate_password(password)  # raises WeakPasswordError

    user = User(
        email=email,
        password_hash=security.hash_password(password),
        password_algo="argon2id",
        status="active",
    )
    session.add(user)
    try:
        await session.flush()  # assigns user.id; surfaces unique-email violation
    except IntegrityError as exc:
        await session.rollback()
        raise RegistrationConflict() from exc

    household = Household(base_currency="USD", timezone="America/New_York")
    session.add(household)
    await session.flush()  # assigns household.id

    membership = Membership(
        user_id=user.id, household_id=household.id, role="owner"
    )
    session.add(membership)

    await record_audit(
        session,
        action="user.register",
        household_id=household.id,
        actor_user_id=user.id,
        target_type="user",
        target_public_id=user.public_id,
    )
    return user


# ── Login (T-010) ─────────────────────────────────────────────────────────────

# Lockout policy (Postgres-backed so it survives restarts — SEC-04, T-012).
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> User:
    """Verify credentials. Raises AuthenticationError on any failure.

    Timing and error responses are uniform across "no such user", "wrong
    password", and "locked" so the endpoint cannot be used for enumeration
    (SEC-04). The route maps every failure to one generic 401.
    """
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        # Spend equivalent argon2 work so timing matches the real path.
        security.dummy_verify(password)
        raise AuthenticationError("invalid credentials")

    now = _now()
    if user.locked_until is not None and user.locked_until > now:
        security.dummy_verify(password)
        raise AccountLocked("account temporarily locked")

    if user.status != "active":
        security.dummy_verify(password)
        raise AuthenticationError("account not active")

    ok, new_hash = security.verify_password(user.password_hash, password)
    if not ok:
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        await record_audit(
            session,
            action="user.login_failed",
            actor_user_id=user.id,
            target_type="user",
            target_public_id=user.public_id,
        )
        raise AuthenticationError("invalid credentials")

    # Success — reset counters, opportunistically upgrade the hash.
    user.failed_login_count = 0
    user.locked_until = None
    if new_hash is not None:
        user.password_hash = new_hash
    return user


async def load_membership(session: AsyncSession, user_id: int) -> Membership:
    """Return the user's (single, beta) membership. Raises if none exists."""
    result = await session.execute(
        select(Membership).where(Membership.user_id == user_id)
    )
    membership = result.scalars().first()
    if membership is None:
        raise AuthenticationError("user has no household membership")
    return membership


# ── Sessions (T-011) ──────────────────────────────────────────────────────────

async def create_session(
    session: AsyncSession,
    *,
    user: User,
    membership: Membership,
    ip: str | None,
    user_agent: str | None,
) -> str:
    """Create a server-side session and return the RAW token (cookie value).

    Only the token's SHA-256 hash is persisted (SEC-02). The raw token is
    returned once and never stored.
    """
    raw_token = security.generate_session_token()
    now = _now()
    row = AuthSession(
        token_hash=security.hash_token(raw_token),
        user_id=user.id,
        household_id=membership.household_id,
        idle_expires_at=now + timedelta(seconds=settings.session_idle_seconds),
        absolute_expires_at=now + timedelta(seconds=settings.session_absolute_seconds),
        last_seen_at=now,
        ip_hash=security.hash_ip(ip) if ip else None,
        user_agent=(user_agent or "")[:1024] or None,
    )
    session.add(row)
    await record_audit(
        session,
        action="session.login",
        household_id=membership.household_id,
        actor_user_id=user.id,
        target_type="user",
        target_public_id=user.public_id,
    )
    return raw_token


async def resolve_session(
    session: AsyncSession, *, raw_token: str
) -> Principal | None:
    """Validate a session token and return a Principal, or None if invalid.

    A session is valid iff it exists, is not revoked, and is within both idle
    and absolute expiry. On success the idle window slides forward.
    """
    token_hash = security.hash_token(raw_token)
    result = await session.execute(
        select(AuthSession, User, Membership, Household)
        .join(User, User.id == AuthSession.user_id)
        .join(
            Membership,
            (Membership.user_id == AuthSession.user_id)
            & (Membership.household_id == AuthSession.household_id),
        )
        .join(Household, Household.id == AuthSession.household_id)
        .where(AuthSession.token_hash == token_hash)
    )
    row = result.first()
    if row is None:
        return None
    auth_session, user, membership, household = row

    now = _now()
    if (
        auth_session.revoked_at is not None
        or auth_session.idle_expires_at <= now
        or auth_session.absolute_expires_at <= now
        or user.status != "active"
        or household.deleted_at is not None
    ):
        return None

    # Slide the idle window forward (capped by the absolute expiry).
    new_idle = min(
        now + timedelta(seconds=settings.session_idle_seconds),
        auth_session.absolute_expires_at,
    )
    auth_session.idle_expires_at = new_idle
    auth_session.last_seen_at = now

    return Principal(
        user_id=user.id,
        household_id=membership.household_id,
        user_public_id=user.public_id,
        household_public_id=household.public_id,
        role=membership.role,
        session_id=auth_session.id,
    )


async def revoke_session(session: AsyncSession, *, session_id: int) -> None:
    """Revoke a single session (logout)."""
    result = await session.execute(
        select(AuthSession).where(AuthSession.id == session_id)
    )
    row = result.scalar_one_or_none()
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        await record_audit(
            session,
            action="session.logout",
            household_id=row.household_id,
            actor_user_id=row.user_id,
        )


async def revoke_all_sessions(session: AsyncSession, *, user_id: int) -> int:
    """Revoke every active session for a user (logout-all). Returns count."""
    result = await session.execute(
        select(AuthSession).where(
            AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
        )
    )
    rows = result.scalars().all()
    now = _now()
    for row in rows:
        row.revoked_at = now
    if rows:
        await record_audit(
            session,
            action="session.logout_all",
            household_id=rows[0].household_id,
            actor_user_id=user_id,
        )
    return len(rows)


async def purge_expired_sessions(session: AsyncSession) -> int:
    """Delete sessions past their absolute expiry. Registered as a job handler
    for the future worker (T-011); safe to call directly meanwhile.
    """
    from sqlalchemy import delete

    result = await session.execute(
        delete(AuthSession).where(AuthSession.absolute_expires_at <= _now())
    )
    return result.rowcount or 0
