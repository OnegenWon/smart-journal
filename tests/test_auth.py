"""Tests for accounts: sign-up, email verification, login, sessions and data privacy."""

from datetime import timedelta

from app.security import ACCESS, VERIFY, create_token
from tests.conftest import PASSWORD

EMAIL = "new.user@smartjournal.app"


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---------- Registration ----------

def test_register_creates_unverified_user_and_sends_email(anon_client, emails):
    response = register(anon_client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert body["is_verified"] is False
    assert "password" not in body and "password_hash" not in body

    assert len(emails.sent) == 1
    assert emails.sent[0]["to"] == EMAIL
    assert "/?verify=" in emails.sent[0]["body"]


def test_email_is_case_insensitive(anon_client):
    register(anon_client, email="Mixed.Case@SmartJournal.app")
    assert register(anon_client, email="mixed.case@smartjournal.app").status_code == 409


def test_duplicate_email_is_rejected(anon_client):
    register(anon_client)
    response = register(anon_client)
    assert response.status_code == 409


def test_register_validation(anon_client):
    assert register(anon_client, email="not-an-email").status_code == 422
    assert register(anon_client, password="short").status_code == 422
    assert register(anon_client, password="x" * 73).status_code == 422
    assert register(anon_client, password=" padded-password ").status_code == 422


# ---------- Verification ----------

def test_cannot_log_in_before_verifying(anon_client):
    register(anon_client)
    response = login(anon_client)

    assert response.status_code == 403
    assert "verify" in response.json()["detail"].lower()


def test_verify_then_log_in(anon_client, emails):
    register(anon_client)

    verified = anon_client.post("/api/auth/verify", json={"token": emails.last_token()})
    assert verified.status_code == 200
    assert verified.json()["is_verified"] is True

    response = login(anon_client)
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_verify_link_can_be_used_twice(anon_client, emails):
    register(anon_client)
    token = emails.last_token()
    assert anon_client.post("/api/auth/verify", json={"token": token}).status_code == 200
    assert anon_client.post("/api/auth/verify", json={"token": token}).status_code == 200


def test_invalid_verify_tokens_are_rejected(anon_client, emails):
    register(anon_client)
    user_id = anon_client.post("/api/auth/register", json={"email": "x@smartjournal.app", "password": PASSWORD}).json()["id"]

    expired = create_token(user_id, VERIFY, timedelta(seconds=-1))
    wrong_purpose = create_token(user_id, ACCESS, timedelta(hours=1))
    tampered = emails.last_token()[:-3] + "abc"

    for token in [expired, wrong_purpose, tampered, "not-a-real-token"]:
        response = anon_client.post("/api/auth/verify", json={"token": token})
        assert response.status_code == 400, token


def test_resend_verification(anon_client, emails):
    register(anon_client)
    response = anon_client.post("/api/auth/resend-verification", json={"email": EMAIL})

    assert response.status_code == 202
    assert len(emails.sent) == 2


def test_resend_does_not_reveal_unknown_emails(anon_client, emails):
    response = anon_client.post("/api/auth/resend-verification", json={"email": "nobody@smartjournal.app"})

    assert response.status_code == 202
    assert emails.sent == []


# ---------- Login ----------

def test_wrong_password_and_unknown_email_get_the_same_error(anon_client, emails):
    register(anon_client)
    anon_client.post("/api/auth/verify", json={"token": emails.last_token()})

    wrong_password = login(anon_client, password="wrong-password-1")
    unknown_email = login(anon_client, email="nobody@smartjournal.app")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_me_returns_the_logged_in_user(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "ada@smartjournal.app"


# ---------- Protecting the API ----------

def test_journal_and_plans_need_a_login(anon_client):
    for method, path in [
        ("get", "/api/entries"),
        ("post", "/api/entries"),
        ("get", "/api/entries/1"),
        ("get", "/api/plans"),
        ("post", "/api/plans"),
        ("delete", "/api/plans/1"),
        ("get", "/api/auth/me"),
    ]:
        response = getattr(anon_client, method)(path)
        assert response.status_code == 401, (method, path)


def test_bad_or_expired_session_is_rejected(anon_client):
    expired = create_token(1, ACCESS, timedelta(seconds=-1))
    for token in [expired, "garbage"]:
        response = anon_client.get("/api/entries", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_verification_token_cannot_be_used_to_log_in(anon_client, emails):
    register(anon_client)
    verify_token = emails.last_token()

    response = anon_client.get("/api/entries", headers={"Authorization": f"Bearer {verify_token}"})
    assert response.status_code == 401


# ---------- Privacy between users ----------

def test_users_only_see_their_own_entries(client, other_user, make_entry):
    mine = make_entry(title="Ada's entry")

    assert client.get("/api/entries", headers=other_user).json() == []
    assert client.get(f"/api/entries/{mine['id']}", headers=other_user).status_code == 404
    assert client.patch(f"/api/entries/{mine['id']}", json={"title": "Hacked"}, headers=other_user).status_code == 404
    assert client.delete(f"/api/entries/{mine['id']}", headers=other_user).status_code == 404

    # Still there, unchanged, for the owner.
    assert client.get(f"/api/entries/{mine['id']}").json()["title"] == "Ada's entry"


def test_users_cannot_plan_with_someone_elses_entries(client, other_user, make_entry, fake_planner):
    mine = make_entry()

    response = client.post("/api/plans", json={"scope": "week", "entry_ids": [mine["id"]]}, headers=other_user)
    assert response.status_code == 404
    assert fake_planner.calls == []


def test_users_only_see_their_own_plans(client, other_user, fake_planner):
    client.post("/api/plans", json={"scope": "week", "ideas": "Ada's plan"})

    assert len(client.get("/api/plans").json()) == 1
    assert client.get("/api/plans", headers=other_user).json() == []


def test_users_cannot_delete_someone_elses_plan(client, other_user, fake_planner):
    plan = client.post("/api/plans", json={"scope": "week", "ideas": "Ada's plan"}).json()

    assert client.delete(f"/api/plans/{plan['id']}", headers=other_user).status_code == 404
    assert client.delete(f"/api/plans/{plan['id']}/days/0/tasks/0", headers=other_user).status_code == 404
    assert len(client.get("/api/plans").json()) == 1
    assert client.get("/api/plans").json()[0]["content"]["days"][0]["tasks"] == ["Long walk", "Food shop"]



def test_smtp_sender_sends_a_message(monkeypatch):
    from app.services import email as email_module

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, username, password):
            sent["login"] = username

        def send_message(self, message):
            sent["to"] = message["To"]
            sent["subject"] = message["Subject"]

    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    sender = email_module.SmtpEmailSender("smtp.example.org", 587, "me@example.org", "pw", "me@example.org")
    sender.send("you@example.org", "Hello", "Body")

    assert sent == {
        "server": ("smtp.example.org", 587),
        "tls": True,
        "login": "me@example.org",
        "to": "you@example.org",
        "subject": "Hello",
    }
