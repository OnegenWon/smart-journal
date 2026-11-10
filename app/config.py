"""App settings, read from environment variables (and a local .env file in development)."""

import os

from dotenv import load_dotenv

load_dotenv()



def normalise_database_url(url: str) -> str:
    """Hosts like Render give `postgres://` or `postgresql://` URLs; SQLAlchemy needs the driver named."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = normalise_database_url(os.getenv("DATABASE_URL", "sqlite:///./journal.db"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# Which LLM the planner uses: "claude" or "gemini".
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Give up on the LLM after this many seconds, so the page never spins forever.
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

# ---------- Accounts ----------
# Signs login and verification tokens. Set a long random value in .env, e.g. from:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
DEV_SECRET_KEY = "dev-only-insecure-secret-change-me-in-your-env-file-0123456789"
SECRET_KEY = os.getenv("SECRET_KEY") or DEV_SECRET_KEY
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
VERIFY_TOKEN_HOURS = int(os.getenv("VERIFY_TOKEN_HOURS", "24"))
RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "30"))
# Used to build the link in verification emails.
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# ---------- Email ----------
# Leave SMTP_HOST empty to print emails to the server log instead (fine for local development).
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "") or SMTP_USERNAME
