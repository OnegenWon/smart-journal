"""App entry point: wires up the routers, creates tables and serves the frontend."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.database import Base, engine
from app.routers import entries, plans, suggestions

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Smart Journal",
    description="A journal with an LLM planner that turns ideas and entries into a weekly or weekend plan.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(entries.router)
app.include_router(plans.router)
app.include_router(suggestions.router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# Mounted last so the /api routes above take priority.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
