"""Identity request/response schemas (T-010/T-011)."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class AuthAck(BaseModel):
    """Deliberately uniform, minimal ack — reveals no account existence."""

    status: str = "ok"


class MeResponse(BaseModel):
    """Non-sensitive profile for display. No internal integer ids."""

    user_public_id: str
    email: str
    household_public_id: str
    role: str


class HouseholdSettingsInput(BaseModel):
    """PATCH /household — only timezone and base currency are user-editable."""

    timezone: str | None = Field(None, max_length=64)
    base_currency: str | None = Field(None, min_length=3, max_length=3)
