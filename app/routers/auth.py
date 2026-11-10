"""Account endpoints: create an account, verify the email, log in, and see who's logged in."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    PublicSettings,
    RegisterRequest,
    ResendRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserRead,
    VerifyRequest,
)
from app.security import (
    ACCESS,
    DUMMY_HASH,
    RESET,
    VERIFY,
    InvalidToken,
    create_token,
    decode_token,
    decode_token_payload,
    hash_password,
    password_fingerprint,
    verify_password,
)
from app.services.email import EmailSender, email_delivery_mode, get_email_sender

router = APIRouter(prefix="/api/auth", tags=["auth"])


def normalise_email(email: str) -> str:
    return email.strip().lower()


def send_verification_email(user: User, sender: EmailSender) -> None:
    token = create_token(user.id, VERIFY, timedelta(hours=config.VERIFY_TOKEN_HOURS))
    link = f"{config.APP_BASE_URL}/?verify={token}"
    body = (
        "Welcome to Smart Journal!\n\n"
        f"Open this link to verify your email (it expires in {config.VERIFY_TOKEN_HOURS} hours):\n"
        f"{link}\n\n"
        "If you didn't create an account, you can ignore this email."
    )
    sender.send(user.email, "Verify your Smart Journal account", body)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    email = normalise_email(payload.email)
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two sign-ups with the same email at the same moment
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from None
    db.refresh(user)

    send_verification_email(user, sender)
    return user


@router.post("/verify", response_model=UserRead)
def verify_email(payload: VerifyRequest, db: Session = Depends(get_db)):
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This verification link is invalid or has expired. Request a new one.",
    )
    try:
        user_id = decode_token(payload.token, VERIFY)
    except InvalidToken:
        raise invalid from None

    user = db.get(User, user_id)
    if user is None:
        raise invalid
    if not user.is_verified:  # clicking the link twice is fine
        user.is_verified = True
        db.commit()
        db.refresh(user)
    return user


@router.post("/resend-verification", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    payload: ResendRequest,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    user = db.scalar(select(User).where(User.email == normalise_email(payload.email)))
    if user is not None and not user.is_verified:
        send_verification_email(user, sender)
    # Same answer either way, so this can't be used to find out who has an account.
    return MessageResponse(detail="If that account exists and isn't verified yet, we've sent a new link.")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == normalise_email(payload.email)))
    wrong = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")

    if user is None:
        verify_password(payload.password, DUMMY_HASH)  # keep timing the same as a real check
        raise wrong
    if not verify_password(payload.password, user.password_hash):
        raise wrong
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in.",
        )

    minutes = config.ACCESS_TOKEN_MINUTES
    token = create_token(
        user.id, ACCESS, timedelta(minutes=minutes), fingerprint=password_fingerprint(user.password_hash)
    )
    return TokenResponse(access_token=token, expires_in=minutes * 60)


# ---------- Forgotten passwords ----------

def send_reset_email(user: User, sender: EmailSender) -> None:
    token = create_token(
        user.id,
        RESET,
        timedelta(minutes=config.RESET_TOKEN_MINUTES),
        fingerprint=password_fingerprint(user.password_hash),
    )
    link = f"{config.APP_BASE_URL}/?reset={token}"
    body = (
        "Someone asked to reset the password for your Smart Journal account.\n\n"
        f"Open this link to choose a new password (it expires in {config.RESET_TOKEN_MINUTES} minutes "
        "and works once):\n"
        f"{link}\n\n"
        "If this wasn't you, you can ignore this email. Your password won't change."
    )
    sender.send(user.email, "Reset your Smart Journal password", body)


@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    user = db.scalar(select(User).where(User.email == normalise_email(payload.email)))
    if user is not None:
        send_reset_email(user, sender)
    # Same answer either way, so this can't be used to find out who has an account.
    return MessageResponse(detail="If an account exists for that email, we've sent a link to reset the password.")


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This reset link is invalid, has expired or has already been used. Request a new one.",
    )
    try:
        claims = decode_token_payload(payload.token, RESET)
    except InvalidToken:
        raise invalid from None

    user = db.get(User, claims["user_id"])
    # The fingerprint no longer matches once the password has changed, so each link works once.
    if user is None or claims.get("pwd") != password_fingerprint(user.password_hash):
        raise invalid

    user.password_hash = hash_password(payload.password)
    # Opening a link sent to the inbox proves the email belongs to them.
    user.is_verified = True
    db.commit()
    return MessageResponse(detail="Your password has been changed. You can log in now.")


@router.get("/settings", response_model=PublicSettings)
def public_settings():
    return PublicSettings(email_delivery=email_delivery_mode())


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user
