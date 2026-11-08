"""Endpoints for the LLM planner."""

from anthropic import Anthropic
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.models import Entry, Plan
from app.schemas import PlanRead, PlanRequest
from app.services.llm import ClaudePlanner, Planner, PlannerError

router = APIRouter(prefix="/api/plans", tags=["plans"])


def get_planner() -> Planner:
    """Dependency that builds the real planner. Tests override this with a fake."""
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The planner needs an API key. Add ANTHROPIC_API_KEY to your .env file and restart the server.",
        )
    return ClaudePlanner(client=Anthropic(api_key=config.ANTHROPIC_API_KEY), model=config.ANTHROPIC_MODEL)


@router.post("", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    request: PlanRequest,
    db: Session = Depends(get_db),
    planner: Planner = Depends(get_planner),
):
    entries: list[Entry] = []
    if request.entry_ids:
        entries = list(db.scalars(select(Entry).where(Entry.id.in_(request.entry_ids))))
        missing = set(request.entry_ids) - {entry.id for entry in entries}
        if missing:
            raise HTTPException(status_code=404, detail=f"Entries not found: {sorted(missing)}")
        entries.sort(key=lambda entry: entry.created_at)

    try:
        content = planner.generate(request.scope, request.ideas, entries)
    except PlannerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    plan = Plan(scope=request.scope, ideas=request.ideas, content=content.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("", response_model=list[PlanRead])
def list_plans(limit: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)):
    stmt = select(Plan).order_by(Plan.created_at.desc(), Plan.id.desc()).limit(limit)
    return db.scalars(stmt).all()
