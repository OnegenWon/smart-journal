"""Pydantic schemas: what the API accepts and returns."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Mood = Literal["great", "good", "okay", "low", "rough"]
Scope = Literal["week", "weekend"]


def as_utc(value: datetime) -> datetime:
    """SQLite drops timezone info, so treat naive timestamps as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------- Journal entries ----------

class EntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    mood: Mood | None = None


class EntryUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20_000)
    mood: Mood | None = None

    @model_validator(mode="after")
    def title_and_body_cannot_be_null(self) -> "EntryUpdate":
        for name in ("title", "body"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    mood: Mood | None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return as_utc(value)


# ---------- Planner ----------

class PlanRequest(BaseModel):
    scope: Scope
    ideas: str = Field(default="", max_length=4_000)
    entry_ids: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def needs_something_to_plan_from(self) -> "PlanRequest":
        if not self.ideas.strip() and not self.entry_ids:
            raise ValueError("Add some ideas or choose at least one journal entry")
        return self


class PlanDay(BaseModel):
    day: str
    focus: str
    tasks: list[str]


class PlanContent(BaseModel):
    """The structured plan the LLM must return."""

    summary: str
    days: list[PlanDay] = Field(min_length=1)
    tips: list[str] = Field(default_factory=list)


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: Scope
    ideas: str
    content: PlanContent
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return as_utc(value)


# ---------- Accounts ----------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        # bcrypt only uses the first 72 bytes; reject longer ones rather than silently truncating.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password is too long")
        if value.strip() != value or not value.strip():
            raise ValueError("Password can't start or end with spaces")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class VerifyRequest(BaseModel):
    token: str = Field(min_length=10, max_length=2_000)


class ResendRequest(BaseModel):
    email: EmailStr


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_verified: bool
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class MessageResponse(BaseModel):
    detail: str
