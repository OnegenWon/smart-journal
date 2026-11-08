"""Tests for the random suggestion endpoint."""

from app.routers.suggestions import ALL_SUGGESTIONS


def test_returns_a_known_suggestion(client):
    response = client.get("/api/suggestions/random")

    assert response.status_code == 200
    body = response.json()
    assert body["text"] in {s.text for s in ALL_SUGGESTIONS}
    assert body["category"] in {"outdoors", "social", "rest", "creative", "learning"}


def test_excluded_suggestion_is_never_returned(client):
    excluded = ALL_SUGGESTIONS[0].text
    for _ in range(50):
        response = client.get("/api/suggestions/random", params={"exclude": excluded})
        assert response.json()["text"] != excluded


def test_unknown_exclude_is_ignored(client):
    response = client.get("/api/suggestions/random", params={"exclude": "not a real suggestion"})
    assert response.status_code == 200
