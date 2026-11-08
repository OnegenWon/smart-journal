"""Tests for the journal entry endpoints."""


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_create_and_get_entry(client, make_entry):
    created = make_entry(title="First day", body="Started the new routine.", mood="good")

    assert created["id"] > 0
    assert created["title"] == "First day"
    assert created["mood"] == "good"

    fetched = client.get(f"/api/entries/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_list_returns_newest_first(client, make_entry):
    first = make_entry(title="Older")
    second = make_entry(title="Newer")

    ids = [entry["id"] for entry in client.get("/api/entries").json()]
    assert ids == [second["id"], first["id"]]


def test_search_matches_title_and_body(client, make_entry):
    make_entry(title="Gym day", body="Leg day.")
    make_entry(title="Quiet day", body="Read a book about the gym.")
    make_entry(title="Work", body="Meetings all day.")

    titles = {entry["title"] for entry in client.get("/api/entries", params={"q": "gym"}).json()}
    assert titles == {"Gym day", "Quiet day"}


def test_search_treats_input_as_text_not_sql(client, make_entry):
    make_entry(title="Normal entry")

    response = client.get("/api/entries", params={"q": "' OR 1=1 --"})
    assert response.status_code == 200
    assert response.json() == []


def test_update_changes_only_sent_fields(client, make_entry):
    created = make_entry(title="Draft", body="Original body", mood="low")

    response = client.patch(f"/api/entries/{created['id']}", json={"title": "Final"})
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Final"
    assert updated["body"] == "Original body"
    assert updated["mood"] == "low"


def test_update_rejects_null_title(client, make_entry):
    created = make_entry()
    response = client.patch(f"/api/entries/{created['id']}", json={"title": None})
    assert response.status_code == 422


def test_delete_entry(client, make_entry):
    created = make_entry()

    assert client.delete(f"/api/entries/{created['id']}").status_code == 204
    assert client.get(f"/api/entries/{created['id']}").status_code == 404


def test_missing_entry_returns_404(client):
    assert client.get("/api/entries/999").status_code == 404
    assert client.patch("/api/entries/999", json={"title": "x"}).status_code == 404
    assert client.delete("/api/entries/999").status_code == 404


def test_validation_errors(client):
    assert client.post("/api/entries", json={"title": "", "body": "x"}).status_code == 422
    assert client.post("/api/entries", json={"title": "x"}).status_code == 422
    assert client.post("/api/entries", json={"title": "x", "body": "y", "mood": "ecstatic"}).status_code == 422
