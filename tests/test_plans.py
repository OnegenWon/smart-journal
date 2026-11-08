"""Tests for the planner endpoints and the Claude integration (no real API calls)."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import config
from app.main import app
from app.models import Entry
from app.routers.plans import get_planner
from app.services.llm import ClaudePlanner, PlannerError, build_prompt


# ---------- Endpoint tests (planner faked) ----------

def test_create_plan_from_ideas(client, fake_planner):
    response = client.post("/api/plans", json={"scope": "weekend", "ideas": "Climbing, call mum"})

    assert response.status_code == 201
    plan = response.json()
    assert plan["scope"] == "weekend"
    assert [day["day"] for day in plan["content"]["days"]] == ["Saturday", "Sunday"]
    assert fake_planner.calls == [{"scope": "weekend", "ideas": "Climbing, call mum", "entry_ids": []}]


def test_create_plan_passes_chosen_entries(client, fake_planner, make_entry):
    first = make_entry(title="Mon")
    second = make_entry(title="Tue")

    response = client.post("/api/plans", json={"scope": "week", "entry_ids": [second["id"], first["id"]]})

    assert response.status_code == 201
    # Entries reach the planner oldest first, whatever order they were sent in.
    assert fake_planner.calls[0]["entry_ids"] == [first["id"], second["id"]]


def test_plans_are_saved_and_listed(client, fake_planner):
    client.post("/api/plans", json={"scope": "week", "ideas": "Study for AWS"})
    plans = client.get("/api/plans").json()

    assert len(plans) == 1
    assert plans[0]["ideas"] == "Study for AWS"


def test_unknown_entry_ids_return_404(client, fake_planner):
    response = client.post("/api/plans", json={"scope": "week", "entry_ids": [42]})

    assert response.status_code == 404
    assert fake_planner.calls == []


def test_empty_request_is_rejected(client, fake_planner):
    response = client.post("/api/plans", json={"scope": "week", "ideas": "   "})
    assert response.status_code == 422


def test_invalid_scope_is_rejected(client, fake_planner):
    response = client.post("/api/plans", json={"scope": "month", "ideas": "x"})
    assert response.status_code == 422


def test_planner_failure_returns_502(client):
    class FailingPlanner:
        def generate(self, scope, ideas, entries):
            raise PlannerError("The planning service failed: APIConnectionError")

    app.dependency_overrides[get_planner] = lambda: FailingPlanner()

    response = client.post("/api/plans", json={"scope": "week", "ideas": "x"})
    assert response.status_code == 502
    assert "planning service failed" in response.json()["detail"]
    assert client.get("/api/plans").json() == []  # nothing saved


def test_missing_api_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")

    response = client.post("/api/plans", json={"scope": "week", "ideas": "x"})
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


# ---------- Prompt building ----------

def make_entry_model(**overrides):
    values = {
        "id": 1,
        "title": "Long day",
        "body": "Stressed about deadlines.",
        "mood": "low",
        "created_at": datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return Entry(**values)


def test_prompt_lists_the_right_days():
    assert "Friday evening, Saturday, Sunday" in build_prompt("weekend", "Rest", [])
    assert "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday" in build_prompt("week", "Rest", [])


def test_prompt_wraps_user_text_in_tags():
    prompt = build_prompt("week", "Go running", [make_entry_model()])

    assert "<ideas>\nGo running\n</ideas>" in prompt
    assert "<journal_entries>" in prompt
    assert 'date="Monday 02 November" mood=low' in prompt
    assert "Stressed about deadlines." in prompt


def test_prompt_truncates_long_entries():
    prompt = build_prompt("week", "", [make_entry_model(body="a" * 5_000)])
    assert "a" * 2_000 in prompt
    assert "a" * 2_001 not in prompt


# ---------- ClaudePlanner response handling (fake client, no network) ----------

def fake_client(content):
    response = SimpleNamespace(content=content)
    messages = SimpleNamespace(create=lambda **kwargs: response)
    return SimpleNamespace(messages=messages)


VALID_PLAN = {
    "summary": "Balanced week.",
    "days": [{"day": "Monday", "focus": "Deep work", "tasks": ["Finish report"]}],
    "tips": [],
}


def test_claude_planner_reads_the_tool_call():
    content = [SimpleNamespace(type="tool_use", name="save_plan", input=VALID_PLAN)]
    plan = ClaudePlanner(client=fake_client(content), model="test-model").generate("week", "x", [])

    assert plan.summary == "Balanced week."
    assert plan.days[0].tasks == ["Finish report"]


def test_claude_planner_rejects_missing_tool_call():
    content = [SimpleNamespace(type="text", text="Here is your plan...")]
    with pytest.raises(PlannerError, match="did not return a plan"):
        ClaudePlanner(client=fake_client(content), model="test-model").generate("week", "x", [])


def test_claude_planner_rejects_wrong_shape():
    content = [SimpleNamespace(type="tool_use", name="save_plan", input={"summary": "No days"})]
    with pytest.raises(PlannerError, match="wrong shape"):
        ClaudePlanner(client=fake_client(content), model="test-model").generate("week", "x", [])
