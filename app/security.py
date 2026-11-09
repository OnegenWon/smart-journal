"""Password hashing and signed tokens (JWT) for login and email verification."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app import config

ALGORITHM = "HS256"

# Token purposes. A verification token can't be used to log in, and vice versa.
ACCESS = "access"
VERIFY = "verify"


class InvalidToken(Exception):
    """The token is malformed, expired, forged or meant for something else."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# Checked against when the email doesn't exist, so a login for an unknown email
# takes as long as a real one and doesn't reveal which emails have accounts.
DUMMY_HASH = hash_password("not-a-real-password")


def create_token(user_id: int, purpose: str, expires_in: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "purpose": purpose, "iat": now, "exp": now + expires_in}
    return jwt.encode(payload, config.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, purpose: str) -> int:
    """Return the user id in a valid token of the given purpose, or raise InvalidToken."""
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidToken from exc
    if payload.get("purpose") != purpose:
        raise InvalidToken
    try:
        return int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidToken from exc
