"""Security primitives for identity (T-010/T-011).

- Password hashing: argon2id via argon2-cffi (SEC-03).
- Password policy: min length + common-password rejection (SEC-05).
- Session tokens: 256-bit opaque tokens; only their SHA-256 hash is stored
  server-side (SEC-02, ADR-02). The raw token lives only in the client cookie.
- IP hashing for session records (avoid storing raw IPs).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions

# argon2id with library defaults (time_cost=3, memory_cost=64MiB, parallelism=4).
# Defaults are a sensible interactive-login cost; tune only with benchmarks.
_hasher = PasswordHasher()

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 200  # bound the work argon2 must do; also DoS guard

# A small, embedded set of the most common/breached passwords. Zero-budget: no
# external list download. Compared case-insensitively; the policy also rejects
# anything too short, which already screens most weak inputs.
_COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "passw0rd", "123456", "1234567",
        "12345678", "123456789", "1234567890", "qwerty", "qwertyuiop", "abc123",
        "letmein", "welcome", "welcome1", "iloveyou", "admin", "administrator",
        "changeme", "monkey", "dragon", "sunshine", "princess", "football",
        "baseball", "trustno1", "whatever", "starwars", "computer", "michael",
        "superman", "batman", "master", "hello123", "freedom", "test1234",
        "login", "passw0rd1", "qazwsx", "zaq12wsx", "1q2w3e4r", "1qaz2wsx",
        "asdfghjkl", "111111", "000000", "121212", "654321", "666666",
        "aaaaaa", "abcdefg", "abcd1234", "p@ssword", "p@ssw0rd",
    }
)


class WeakPasswordError(ValueError):
    """Raised when a password fails the policy (SEC-05)."""


def validate_password(password: str) -> None:
    """Enforce the password policy. Raises WeakPasswordError on violation."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise WeakPasswordError(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise WeakPasswordError(
            f"Password must be at most {PASSWORD_MAX_LENGTH} characters."
        )
    if password.lower() in _COMMON_PASSWORDS:
        raise WeakPasswordError("Password is too common; choose a less predictable one.")


def hash_password(password: str) -> str:
    """Return an argon2id PHC-format hash string."""
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> tuple[bool, str | None]:
    """Verify a password against a stored argon2id hash.

    Returns ``(ok, new_hash)``. ``new_hash`` is a rehashed value when argon2's
    parameters have since changed (caller should persist it), else ``None``.
    Verification is timing-safe within argon2; callers must still perform a
    dummy verify on unknown accounts to equalise timing (see service layer).
    """
    try:
        _hasher.verify(stored_hash, password)
    except (
        argon2_exceptions.VerifyMismatchError,
        argon2_exceptions.VerificationError,
        argon2_exceptions.InvalidHashError,
    ):
        return False, None
    new_hash = _hasher.hash(password) if _hasher.check_needs_rehash(stored_hash) else None
    return True, new_hash


# A precomputed argon2id hash of a random throwaway secret. Verifying against it
# on unknown-account login paths keeps timing indistinguishable from the
# known-account path (SEC-04 account enumeration / timing).
_DUMMY_HASH = _hasher.hash(secrets.token_hex(16))


def dummy_verify(password: str) -> None:
    """Spend argon2 work on a nonexistent account to equalise login timing."""
    try:
        _hasher.verify(_DUMMY_HASH, password)
    except argon2_exceptions.VerifyMismatchError:
        pass


# ── Session tokens ────────────────────────────────────────────────────────────

TOKEN_BYTES = 32  # 256 bits of entropy


def generate_session_token() -> str:
    """Return a URL-safe opaque session token (raw secret, never stored)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hex of a session token — this is what lands in the DB.

    SHA-256 is appropriate here (unlike passwords): the token already carries
    256 bits of entropy, so it is not brute-forceable and needs no slow KDF.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_ip(ip: str) -> str:
    """Non-reversible fingerprint of a client IP for session records."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    """Constant-time comparison for token hashes."""
    return hmac.compare_digest(a, b)
