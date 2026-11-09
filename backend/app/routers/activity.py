"""Activity record (US24): read-only and filterable, administrators only. There are no write endpoints."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import admin_only
from app.models import AuditEvent, User
from app.services.audit import ACTIONS

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("")
def list_activity(
    action: str | None = Query(None, max_length=48),
    category: str | None = Query(None, pattern="^(auth|user|site|schedule|plant_factor|signal|task|run|ai)$"),
    user_id: UUID | None = None,
    entity_type: str | None = Query(None, max_length=32),
    entity_id: str | None = Query(None, max_length=64),
    start: date | None = None,
    end: date | None = None,
    q: str | None = Query(None, max_length=120),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    if start and end and end < start:
        raise HTTPException(422, "The end date must be on or after the start date.")
    stmt = select(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if category:
        stmt = stmt.where(AuditEvent.action.startswith(f"{category}."))
    if user_id:
        stmt = stmt.where(AuditEvent.user_id == user_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if start:
        stmt = stmt.where(AuditEvent.at >= datetime.combine(start, time.min, tzinfo=UTC))
    if end:
        stmt = stmt.where(AuditEvent.at < datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC))
    if q and q.strip():
        pattern = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            or_(AuditEvent.summary.ilike(pattern, escape="\\"), AuditEvent.user_name.ilike(pattern, escape="\\"))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditEvent.at.desc(), AuditEvent.id.desc()).limit(limit).offset(offset))
    return {
        "total": total,
        "items": [
            {
                "id": e.id,
                "at": e.at,
                "user_id": e.user_id,
                "user_name": e.user_name,
                "user_role": e.user_role,
                "action": e.action,
                "action_label": ACTIONS.get(e.action, e.action),
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "summary": e.summary,
                "details": e.details,
            }
            for e in rows
        ],
    }


@router.get("/actions")
def actions(_: User = Depends(admin_only)):
    return [{"action": k, "label": v} for k, v in ACTIONS.items()]
