"""CRUD endpoints for journal entries. Every query is scoped to the logged-in user."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Entry, User
from app.schemas import EntryCreate, EntryRead, EntryUpdate

router = APIRouter(prefix="/api/entries", tags=["entries"])


def get_entry_or_404(entry_id: int, user: User, db: Session) -> Entry:
    entry = db.get(Entry, entry_id)
    # Someone else's entry gets the same 404 as a missing one, so ids can't be probed.
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
    return entry


@router.get("", response_model=list[EntryRead])
def list_entries(
    q: str | None = Query(default=None, max_length=100, description="Search titles and bodies"),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Entry).where(Entry.user_id == user.id)
    if q:
        pattern = f"%{q}%"  # sent as a bound parameter by SQLAlchemy, so no SQL injection
        stmt = stmt.where(or_(Entry.title.ilike(pattern), Entry.body.ilike(pattern)))
    stmt = stmt.order_by(Entry.created_at.desc(), Entry.id.desc()).limit(limit)
    return db.scalars(stmt).all()


@router.get("/{entry_id}", response_model=EntryRead)
def get_entry(entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_entry_or_404(entry_id, user, db)


@router.post("", response_model=EntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(payload: EntryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = Entry(user_id=user.id, **payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=EntryRead)
def update_entry(
    entry_id: int,
    payload: EntryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = get_entry_or_404(entry_id, user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = get_entry_or_404(entry_id, user, db)
    db.delete(entry)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
