"""Tests for small config helpers."""

from app.config import normalise_database_url


def test_postgres_urls_get_the_psycopg_driver():
    assert normalise_database_url("postgres://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    assert normalise_database_url("postgresql://u:p@host/db") == "postgresql+psycopg://u:p@host/db"


def test_other_urls_are_left_alone():
    assert normalise_database_url("sqlite:///./journal.db") == "sqlite:///./journal.db"
    assert normalise_database_url("postgresql+psycopg://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
