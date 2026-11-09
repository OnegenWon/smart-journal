"""Tests for the planner endpoints and the Claude integration (no real API calls)."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import config
from app.main import app
from app.models import Entry
from app.routers.plans import get_planner
from app.services.llm import ClaudePlanner, GeminiPlanner, PlannerError, build_prompt


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
    monkeypatch.setattr(config, "LLM_PROVIDER", "claude")
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


# ---------- Provider selection ----------

def test_missing_gemini_key_returns_503(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")

    response = client.post("/api/plans", json={"scope": "week", "ideas": "x"})
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_unknown_provider_returns_503(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "mystery")

    response = client.post("/api/plans", json={"scope": "week", "ideas": "x"})
    assert response.status_code == 503
    assert "Unknown LLM_PROVIDER" in response.json()["detail"]


# ---------- GeminiPlanner response handling (fake client, no network) ----------

def fake_gemini_client(text):
    response = SimpleNamespace(text=text)
    models = SimpleNamespace(generate_content=lambda **kwargs: response)
    return SimpleNamespace(models=models)


def test_gemini_planner_reads_json():
    import json

    planner = GeminiPlanner(client=fake_gemini_client(json.dumps(VALID_PLAN)), model="test-model")
    plan = planner.generate("week", "x", [])

    assert plan.summary == "Balanced week."
    assert plan.days[0].day == "Monday"


def test_gemini_planner_rejects_empty_response():
    planner = GeminiPlanner(client=fake_gemini_client(""), model="test-model")
    with pytest.raises(PlannerError, match="did not return a plan"):
        planner.generate("week", "x", [])


def test_gemini_planner_rejects_wrong_shape():
    planner = GeminiPlanner(client=fake_gemini_client('{"summary": "No days"}'), model="test-model")
    with pytest.raises(PlannerError, match="wrong shape"):
        planner.generate("week", "x", [])


def test_gemini_planner_turns_timeouts_into_a_clear_error():
    class SlowModels:
        def generate_content(self, **kwargs):
            raise TimeoutError("The read operation timed out")

    planner = GeminiPlanner(client=SimpleNamespace(models=SlowModels()), model="test-model", sleep=lambda s: None)
    with pytest.raises(PlannerError, match="took too long"):
        planner.generate("week", "x", [])



# ---------- Deleting plans ----------

def test_delete_plan(client, fake_planner):
    plan = client.post("/api/plans", json={"scope": "week", "ideas": "x"}).json()

    assert client.delete(f"/api/plans/{plan['id']}").status_code == 204
    assert client.get("/api/plans").json() == []


def test_delete_missing_plan_returns_404(client):
    assert client.delete("/api/plans/999").status_code == 404



# ---------- Deleting single tasks ----------

def test_delete_one_task(client, fake_planner):
    plan = client.post("/api/plans", json={"scope": "weekend", "ideas": "x"}).json()
    # FakePlanner's Saturday has ["Long walk", "Food shop"].

    response = client.delete(f"/api/plans/{plan['id']}/days/0/tasks/0")

    assert response.status_code == 200
    assert response.json()["content"]["days"][0]["tasks"] == ["Food shop"]
    # The change is saved, not just returned.
    saved = client.get("/api/plans").json()[0]
    assert saved["content"]["days"][0]["tasks"] == ["Food shop"]
    assert saved["content"]["days"][1]["tasks"] == ["Plan meals"]


def test_delete_task_out_of_range_returns_404(client, fake_planner):
    plan = client.post("/api/plans", json={"scope": "weekend", "ideas": "x"}).json()

    assert client.delete(f"/api/plans/{plan['id']}/days/9/tasks/0").status_code == 404
    assert client.delete(f"/api/plans/{plan['id']}/days/0/tasks/9").status_code == 404
    assert client.delete("/api/plans/999/days/0/tasks/0").status_code == 404



# ---------- Retries and friendly errors ----------

from google.genai import errors as genai_errors  # noqa: E402

from app.services.llm import call_with_retries, friendly_message  # noqa: E402


def gemini_error(code):
    """Build a real google-genai error with the given status code (ClientError for 4xx, ServerError for 5xx)."""
    cls = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return cls(code, {"error": {"code": code, "message": "test", "status": "TEST"}})


class FlakyModels:
    """Fails with the given status codes in order, then succeeds."""

    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        if self.failures:
            raise gemini_error(self.failures.pop(0))
        return SimpleNamespace(text=__import__("json").dumps(VALID_PLAN))


def test_gemini_retries_when_busy_then_succeeds():
    models = FlakyModels([503, 429])
    waits = []
    planner = GeminiPlanner(client=SimpleNamespace(models=models), model="m", sleep=waits.append)

    plan = planner.generate("week", "x", [])

    assert plan.summary == "Balanced week."
    assert models.calls == 3
    assert waits == [1.0, 2.0]  # exponential backoff


def test_gemini_gives_up_after_three_attempts_with_a_friendly_message():
    models = FlakyModels([503, 503, 503, 503])
    planner = GeminiPlanner(client=SimpleNamespace(models=models), model="m", sleep=lambda s: None)

    with pytest.raises(PlannerError, match="busy right now"):
        planner.generate("week", "x", [])
    assert models.calls == 3


def test_gemini_does_not_retry_errors_that_wont_fix_themselves():
    models = FlakyModels([400])
    planner = GeminiPlanner(client=SimpleNamespace(models=models), model="m", sleep=lambda s: None)

    with pytest.raises(PlannerError, match="ClientError \\(400\\)"):
        planner.generate("week", "x", [])
    assert models.calls == 1


def test_friendly_messages():
    assert "busy" in friendly_message(503, "ServerError")
    assert "usage limit" in friendly_message(429, "ClientError")
    assert friendly_message(400, "ClientError") == "The planning service failed: ClientError (400)"


def test_call_with_retries_returns_first_success_without_waiting():
    waits = []
    assert call_with_retries(lambda: "ok", lambda e: None, sleep=waits.append) == "ok"
    assert waits == []
