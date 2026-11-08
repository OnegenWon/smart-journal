"""Shared test fixtures: an isolated in-memory database and a fake planner."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.routers.plans import get_planner
from app.schemas import PlanContent, PlanDay


@pytest.fixture
def client():
    # One shared in-memory SQLite connection per test, so every test starts empty.
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


class FakePlanner:
    """Stands in for Claude: records what it was asked and returns a fixed plan."""

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
