"""Shared test fixtures: an isolated database, captured emails, logged-in users and a fake planner."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.routers.plans import get_planner
from app.schemas import PlanContent, PlanDay
from app.services.email import get_email_sender

PASSWORD = "correct-horse-42"


class FakeEmailSender:
    """Collects emails instead of sending them, so tests can read the verification link."""

    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})

    def last_token(self, to=None):
        emails = [e for e in self.sent if to is None or e["to"] == to]
        assert emails, "no email was sent"
        return re.search(r"verify=([\w.\-]+)", emails[-1]["body"]).group(1)


@pytest.fixture
def emails():
    sender = FakeEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: sender
    return sender


@pytest.fixture
def anon_client(emails):
    """A client with a fresh in-memory database and nobody logged in."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def sign_up(client, emails, email, password=PASSWORD):
    """Register, verify and log in through the real API. Returns auth headers."""
    assert client.post("/api/auth/register", json={"email": email, "password": password}).status_code == 201
    token = emails.last_token(to=email)
    assert client.post("/api/auth/verify", json={"token": token}).status_code == 200
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def client(anon_client, emails):
    """A client logged in as ada@smartjournal.app."""
    anon_client.headers.update(sign_up(anon_client, emails, "ada@smartjournal.app"))
    return anon_client


@pytest.fixture
def other_user(anon_client, emails):
    """Auth headers for a second user, to check that data stays private."""
    return sign_up(anon_client, emails, "bob@smartjournal.app")


class FakePlanner:
    """Stands in for the LLM: records what it was asked and returns a fixed plan."""

    def __init__(self):
        self.calls = []

    def generate(self, scope, ideas, entries):
        self.calls.append({"scope": scope, "ideas": ideas, "entry_ids": [e.id for e in entries]})
        return PlanContent(
            summary="A gentle weekend with one focused block.",
            days=[
                PlanDay(day="Saturday", focus="Rest and errands", tasks=["Long walk", "Food shop"]),
                PlanDay(day="Sunday", focus="Prep the week", tasks=["Plan meals"]),
            ],
            tips=["Keep Sunday evening free"],
        )


@pytest.fixture
def fake_planner():
    planner = FakePlanner()
    app.dependency_overrides[get_planner] = lambda: planner
    return planner


@pytest.fixture
def make_entry(client):
    def _make(title="Monday", body="Felt tired but got the report done.", mood="okay"):
        response = client.post("/api/entries", json={"title": title, "body": body, "mood": mood})
        assert response.status_code == 201
        return response.json()

    return _make
