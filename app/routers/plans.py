"""Endpoints for the LLM planner."""

from anthropic import Anthropic
from google import genai
from google.genai import types as genai_types
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.database import get_db
from app.deps import get_current_user
from app.models import Entry, Plan, User
from app.schemas import PlanContent, PlanRead, PlanRequest
from app.services.llm import ClaudePlanner, GeminiPlanner, Planner, PlannerError

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _missing_key(name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"The planner needs an API key. Add {name} to your .env file and restart the server.",
    )


def get_planner() -> Planner:
    """Dependency that builds the real planner for the configured provider. Tests override this with a fake."""
    if config.LLM_PROVIDER == "gemini":
        if not config.GEMINI_API_KEY:
            raise _missing_key("GEMINI_API_KEY")
        client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=genai_types.HttpOptions(timeout=config.LLM_TIMEOUT_SECONDS * 1000),  # milliseconds
        )
        return GeminiPlanner(client=client, model=config.GEMINI_MODEL)

    if config.LLM_PROVIDER != "claude":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unknown LLM_PROVIDER '{config.LLM_PROVIDER}'. Use 'claude' or 'gemini'.",
        )
    if not config.ANTHROPIC_API_KEY:
        raise _missing_key("ANTHROPIC_API_KEY")
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=config.LLM_TIMEOUT_SECONDS)
    return ClaudePlanner(client=client, model=config.ANTHROPIC_MODEL)


@router.post("", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    request: PlanRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    planner: Planner = Depends(get_planner),
):
    entries: list[Entry] = []
    if request.entry_ids:
        stmt = select(Entry).where(Entry.user_id == user.id, Entry.id.in_(request.entry_ids))
        entries = list(db.scalars(stmt))
        missing = set(request.entry_ids) - {entry.id for entry in entries}
        if missing:
            raise HTTPException(status_code=404, detail=f"Entries not found: {sorted(missing)}")
        entries.sort(key=lambda entry: entry.created_at)

    try:
        content = planner.generate(request.scope, request.ideas, entries)
    except PlannerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    plan = Plan(user_id=user.id, scope=request.scope, ideas=request.ideas, content=content.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("", response_model=list[PlanRead])
def list_plans(
    limit: int = Query(default=10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Plan).where(Plan.user_id == user.id).order_by(Plan.created_at.desc(), Plan.id.desc()).limit(limit)
    return db.scalars(stmt).all()


def get_plan_or_404(plan_id: int, user: User, db: Session) -> Plan:
    plan = db.get(Plan, plan_id)
    # Someone else's plan gets the same 404 as a missing one.
    if plan is None or plan.user_id != user.id:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return plan


@router.delete("/{plan_id}/days/{day_index}/tasks/{task_index}", response_model=PlanRead)
def delete_task(
    plan_id: int,
    day_index: int,
    task_index: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove one task from one day of a plan. Returns the updated plan."""
    plan = get_plan_or_404(plan_id, user, db)
    content = PlanContent.model_validate(plan.content)

    if not 0 <= day_index < len(content.days):
        raise HTTPException(status_code=404, detail="Day not found")
    tasks = content.days[day_index].tasks
    if not 0 <= task_index < len(tasks):
        raise HTTPException(status_code=404, detail="Task not found")

    del tasks[task_index]
    # Assign a new dict so SQLAlchemy notices the JSON column changed.
    plan.content = content.model_dump()
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = get_plan_or_404(plan_id, user, db)
    db.delete(plan)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
