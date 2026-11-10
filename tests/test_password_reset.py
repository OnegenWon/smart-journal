"""Tests for "Forgot password?": reset emails, one-time links and logging out old sessions."""

from datetime import timedelta

from app import config
from app.security import RESET, create_token
from tests.conftest import PASSWORD, sign_up

EMAIL = "ada@smartjournal.app"
NEW_PASSWORD = "brand-new-pass-7"


def forgot(client, email=EMAIL):
    return client.post("/api/auth/forgot-password", json={"email": email})


def reset(client, token, password=NEW_PASSWORD):
    return client.post("/api/auth/reset-password", json={"token": token, "password": password})


def login(client, password, email=EMAIL):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_forgot_password_sends_a_reset_email(client, emails):
    response = forgot(client)

    assert response.status_code == 202
    assert emails.sent[-1]["to"] == EMAIL
    assert "/?reset=" in emails.sent[-1]["body"]


def test_forgot_password_does_not_reveal_unknown_emails(anon_client, emails):
    response = forgot(anon_client, email="nobody@smartjournal.app")

    assert response.status_code == 202
    assert emails.sent == []


def test_reset_changes_the_password(client, emails):
    forgot(client)

    response = reset(client, emails.last_token(kind="reset"))

    assert response.status_code == 200
    assert login(client, PASSWORD).status_code == 401
    assert login(client, NEW_PASSWORD).status_code == 200


def test_reset_link_works_only_once(client, emails):
    forgot(client)
    token = emails.last_token(kind="reset")

    assert reset(client, token).status_code == 200
    assert reset(client, token, password="another-pass-9").status_code == 400
    assert login(client, NEW_PASSWORD).status_code == 200


def test_reset_logs_out_existing_sessions(client, emails):
    assert client.get("/api/entries").status_code == 200  # logged in

    forgot(client)
    reset(client, emails.last_token(kind="reset"))

    response = client.get("/api/entries")  # same old token
    assert response.status_code == 401
    assert "password was changed" in response.json()["detail"]


def test_bad_reset_tokens_are_rejected(client, emails):
    user_id = client.get("/api/auth/me").json()["id"]
    expired = create_token(user_id, RESET, timedelta(seconds=-1), fingerprint="anything")
    verify_token = emails.last_token(kind="verify")  # from sign-up

    for token in [expired, verify_token, "not-a-real-token"]:
        assert reset(client, token).status_code == 400, token


def test_reset_requires_a_valid_new_password(client, emails):
    forgot(client)
    token = emails.last_token(kind="reset")

    assert reset(client, token, password="short").status_code == 422
    assert reset(client, token, password=" spaced-out ").status_code == 422


def test_reset_also_verifies_an_unverified_account(anon_client, emails):
    anon_client.post("/api/auth/register", json={"email": "new@smartjournal.app", "password": PASSWORD})
    forgot(anon_client, email="new@smartjournal.app")

    reset(anon_client, emails.last_token(to="new@smartjournal.app", kind="reset"))

    assert login(anon_client, NEW_PASSWORD, email="new@smartjournal.app").status_code == 200


def test_other_users_are_not_affected(anon_client, emails):
    sign_up(anon_client, emails, EMAIL)
    sign_up(anon_client, emails, "bob@smartjournal.app")

    forgot(anon_client)
    reset(anon_client, emails.last_token(to=EMAIL, kind="reset"))

    assert login(anon_client, PASSWORD, email="bob@smartjournal.app").status_code == 200


def test_settings_report_how_emails_are_delivered(anon_client, monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "")
    assert anon_client.get("/api/auth/settings").json() == {"email_delivery": "log"}

    monkeypatch.setattr(config, "SMTP_HOST", "smtp-relay.brevo.com")
    assert anon_client.get("/api/auth/settings").json() == {"email_delivery": "email"}
