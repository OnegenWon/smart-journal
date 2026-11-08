"""CRUD endpoints for journal entries."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Entry
from app.schemas import EntryCreate, EntryRead, EntryUpdate

router = APIRouter(prefix="/api/entries", tags=["entries"])


def get_entry_or_404(entry_id: int, db: Session) -> Entry:
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
    return entry


@router.get("", response_model=list[EntryRead])
def list_entries(
    q: str | None = Query(default=None, max_length=100, description="Search titles and bodies"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(Entry)
    if q:
        pattern = f"%{q}%"  # sent as a bound parameter by SQLAlchemy, so no SQL injection
        stmt = stmt.where(or_(Entry.title.ilike(pattern), Entry.body.ilike(pattern)))
    stmt = stmt.order_by(Entry.created_at.desc(), Entry.id.desc()).limit(limit)
    return db.scalars(stmt).all()


@router.get("/{entry_id}", response_model=EntryRead)
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    return get_entry_or_404(entry_id, db)


@router.post("", response_model=EntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(payload: EntryCreate, db: Session = Depends(get_db)):
    entry = Entry(**payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=EntryRead)
def update_entry(entry_id: int, payload: EntryUpdate, db: Session = Depends(get_db)):
    entry = get_entry_or_404(entry_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = get_entry_or_404(entry_id, db)
    db.delete(entry)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
