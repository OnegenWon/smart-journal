"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import ACCESS, InvalidToken, decode_token

bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the logged-in user from the `Authorization: Bearer <token>` header."""
    if credentials is None:
        raise _unauthorized("Please log in.")
    try:
        user_id = decode_token(credentials.credentials, ACCESS)
    except InvalidToken:
        raise _unauthorized("Your session has expired. Please log in again.") from None

    user = db.get(User, user_id)
    if user is None or not user.is_verified:
        raise _unauthorized("Please log in.")
    return user
