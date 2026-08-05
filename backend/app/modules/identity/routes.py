"""Identity HTTP routes (T-010/T-011/T-020).

Register/login return uniform acks and set an HttpOnly session cookie. Every
mutating route is CSRF-guarded and rate-limited. No route accepts a user_id or
household_id from the client — identity comes only from the session (SEC-01/02).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.modules.common import ratelimit
from app.modules.identity import service
from app.modules.identity.deps import csrf_guard, require_principal
from app.modules.identity.models import Household
from app.modules.identity.schemas import (
    AuthAck,
    HouseholdSettingsInput,
    LoginInput,
    MeResponse,
    RegisterInput,
)
from app.modules.identity.security import WeakPasswordError
from app.modules.identity.service import Principal

router = APIRouter(prefix="/auth", tags=["Authentication"])
household_router = APIRouter(prefix="/household", tags=["Household"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        secure=settings.cookie_secure_effective,
        samesite="lax",
        domain=settings.cookie_domain or None,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.cookie_domain or None,
        path="/",
    )


@router.post("/register", response_model=AuthAck)
async def register(
    data: RegisterInput,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(csrf_guard),
    _rl: None = Depends(ratelimit.limit_register),
) -> AuthAck:
    """Register a new user + household. Response is identical whether or not the
    email was already taken, so registration cannot enumerate accounts (SEC-04).
    """
    try:
        user = await service.register_user(
            db, email=str(data.email).lower(), password=data.password
        )
    except WeakPasswordError as exc:
        # Password policy is the one thing we DO surface — it's about the input
        # the user just chose, not about any existing account.
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except service.RegistrationConflict:
        # Uniform success-shaped ack; no session issued, nothing leaked.
        return AuthAck()

    membership = await service.load_membership(db, user.id)
    token = await service.create_session(
        db,
        user=user,
        membership=membership,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    _set_session_cookie(response, token)
    return AuthAck()


@router.post("/login", response_model=AuthAck)
async def login(
    data: LoginInput,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(csrf_guard),
    _rl: None = Depends(ratelimit.limit_login),
) -> AuthAck:
    """Authenticate and issue a session cookie. All failures return one generic
    401 with uniform timing (SEC-04)."""
    try:
        user = await service.authenticate(
            db, email=str(data.email).lower(), password=data.password
        )
    except service.AuthenticationError:
        await db.commit()  # persist failed-attempt counter / lockout
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from None

    membership = await service.load_membership(db, user.id)
    token = await service.create_session(
        db,
        user=user,
        membership=membership,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    _set_session_cookie(response, token)
    return AuthAck()


@router.post("/logout", response_model=AuthAck)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> AuthAck:
    await service.revoke_session(db, session_id=principal.session_id)
    await db.commit()
    _clear_session_cookie(response)
    return AuthAck()


@router.post("/logout-all", response_model=AuthAck)
async def logout_all(
    response: Response,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> AuthAck:
    await service.revoke_all_sessions(db, user_id=principal.user_id)
    await db.commit()
    _clear_session_cookie(response)
    return AuthAck()


@router.get("/me", response_model=MeResponse)
async def me(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
) -> MeResponse:
    result = await db.execute(
        select(service.User.email).where(service.User.id == principal.user_id)
    )
    email = result.scalar_one()
    return MeResponse(
        user_public_id=principal.user_public_id,
        email=email,
        household_public_id=principal.household_public_id,
        role=principal.role,
    )


@household_router.patch("", response_model=MeResponse)
async def update_household(
    data: HouseholdSettingsInput,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_principal),
    _csrf: None = Depends(csrf_guard),
) -> MeResponse:
    """Update household timezone / base currency (owner only). Only these two
    fields are ever client-editable (T-020)."""
    if principal.role != "owner":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="Owner role required"
        )
    result = await db.execute(
        select(Household).where(Household.id == principal.household_id)
    )
    household = result.scalar_one()
    if data.timezone is not None:
        household.timezone = data.timezone
    if data.base_currency is not None:
        household.base_currency = data.base_currency.upper()
    await service.record_audit(
        db,
        action="household.update_settings",
        household_id=principal.household_id,
        actor_user_id=principal.user_id,
        target_type="household",
        target_public_id=principal.household_public_id,
    )
    await db.commit()

    email_result = await db.execute(
        select(service.User.email).where(service.User.id == principal.user_id)
    )
    return MeResponse(
        user_public_id=principal.user_public_id,
        email=email_result.scalar_one(),
        household_public_id=principal.household_public_id,
        role=principal.role,
    )
