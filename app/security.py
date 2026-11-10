"""Password hashing and signed tokens (JWT) for login, email verification and password reset."""

import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app import config

ALGORITHM = "HS256"

# Token purposes. A token made for one purpose is rejected everywhere else.
ACCESS = "access"
VERIFY = "verify"
RESET = "reset"


class InvalidToken(Exception):
    """The token is malformed, expired, forged, meant for something else, or no longer current."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# Checked against when the email doesn't exist, so a login for an unknown email
# takes as long as a real one and doesn't reveal which emails have accounts.
DUMMY_HASH = hash_password("not-a-real-password")


def password_fingerprint(password_hash: str) -> str:
    """A short value that changes whenever the password changes.

    Login and reset tokens carry it, so changing the password makes every older token
    invalid: a reset link works only once, and resetting logs out every other session.
    """
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def create_token(user_id: int, purpose: str, expires_in: timedelta, fingerprint: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "purpose": purpose, "iat": now, "exp": now + expires_in}
    if fingerprint is not None:
        payload["pwd"] = fingerprint
    return jwt.encode(payload, config.SECRET_KEY, algorithm=ALGORITHM)


def decode_token_payload(token: str, purpose: str) -> dict:
    """Return the claims of a valid token of the given purpose, or raise InvalidToken."""
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidToken from exc
    if payload.get("purpose") != purpose:
        raise InvalidToken
    try:
        payload["user_id"] = int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidToken from exc
    return payload


def decode_token(token: str, purpose: str) -> int:
    """Return the user id in a valid token of the given purpose, or raise InvalidToken."""
    return decode_token_payload(token, purpose)["user_id"]
