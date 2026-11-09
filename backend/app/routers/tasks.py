"""Inspection and maintenance tasks, field findings and photos (US14, US15)."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import site_editors, task_viewers
from app.localtime import local_today
from app.models import Role, Site, Task, TaskStatus, User
from app.schemas import FindingsBody, ReasonBody, TaskCreate, TaskOut, TaskUpdate
from app.services import workflow
from app.services.audit import record
from app.services.workflow import WorkflowError

router = APIRouter(tags=["tasks"])


def task_out(t: Task) -> dict:
    f = t.finding
    d = t.site.district
    return {
        "id": t.id,
        "site_id": t.site_id,
        "site_name": t.site.name,
        "site_name_ar": t.site.name_ar,
        "district_name": (d.name_en or d.name_ar) if d else None,
        "signal_id": t.signal_id,
        "task_type": t.task_type,
        "title": t.title,
        "instructions": t.instructions,
        "priority": t.priority,
        "due_date": t.due_date,
        "overdue": t.status in (TaskStatus.assigned, TaskStatus.in_progress) and t.due_date < local_today(),
        "assignee_id": t.assignee_id,
        "assignee_name": t.assignee.full_name,
        "status": t.status,
        "created_by_name": t.creator.full_name if t.creator else None,
        "created_at": t.created_at,
        "started_at": t.started_at,
        "completed_at": t.completed_at,
        "cancelled_at": t.cancelled_at,
        "finding": None
        if f is None
        else {
            "visit_date": f.visit_date,
            "condition": f.condition,
            "notes": f.notes,
            "recorded_at": f.recorded_at,
            "photos": [
                {
                    "id": p.id,
                    "url": f"/api/media/photos/{p.file_name}",
                    "thumb_url": f"/api/media/photos/{p.thumb_name}",
                    "width": p.width,
                    "height": p.height,
                }
                for p in f.photos
            ],
        },
    }


def workflow_http(exc: WorkflowError) -> HTTPException:
    if exc.field:
        return HTTPException(exc.status, [{"loc": ["body", exc.field], "msg": str(exc), "type": "value_error"}])
    return HTTPException(exc.status, str(exc))


_http = workflow_http


def _get_task(db: Session, task_id: uuid.UUID, user: User) -> Task:
    task = db.get(Task, task_id)
    # Inspectors only see their own tasks; another inspector's task is reported as not found.
    if task is None or (user.role == Role.inspector and task.assignee_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found.")
    return task


@router.get("/api/tasks", response_model=list[TaskOut])
def list_tasks(
    status_filter: str = Query("open", alias="status", pattern="^(open|assigned|in_progress|completed|cancelled|all)$"),
    site_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(task_viewers),
):
    q = select(Task)
    if user.role == Role.inspector:
        q = q.where(Task.assignee_id == user.id)
    if status_filter == "open":
        q = q.where(Task.status.in_((TaskStatus.assigned, TaskStatus.in_progress)))
    elif status_filter != "all":
        q = q.where(Task.status == TaskStatus(status_filter))
    if site_id is not None:
        q = q.where(Task.site_id == site_id)
    q = q.order_by(Task.due_date, Task.created_at)
    return [task_out(t) for t in db.scalars(q)]


@router.post("/api/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, db: Session = Depends(get_db), user: User = Depends(site_editors)):
    try:
        task = workflow.create_task(db, user, body.model_dump())
    except WorkflowError as exc:
        raise _http(exc) from exc
    record(
        db,
        user,
        "task.created",
        f"Created {task.task_type.value} task '{task.title}' at {task.site.name}",
        "task",
        task.id,
        {"assignee": task.assignee.full_name, "due_date": task.due_date.isoformat()},
    )
    return task_out(task)


@router.get("/api/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(task_viewers)):
    return task_out(_get_task(db, task_id, user))


@router.patch("/api/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: uuid.UUID, body: TaskUpdate, db: Session = Depends(get_db), user: User = Depends(site_editors)
):
    try:
        task = workflow.update_task(db, _get_task(db, task_id, user), body.model_dump(exclude_unset=True))
    except WorkflowError as exc:
        raise _http(exc) from exc
    record(
        db,
        user,
        "task.updated",
        f"Edited task '{task.title}'",
        "task",
        task.id,
        {"fields": sorted(body.model_dump(exclude_unset=True))},
    )
    return task_out(task)


@router.post("/api/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(
    task_id: uuid.UUID, body: ReasonBody, db: Session = Depends(get_db), user: User = Depends(site_editors)
):
    try:
        task = workflow.cancel_task(db, _get_task(db, task_id, user), user, body.reason)
    except WorkflowError as exc:
        raise _http(exc) from exc
    record(
        db,
        user,
        "task.cancelled",
        f"Cancelled task '{task.title}'",
        "task",
        task.id,
        {"reason": (body.reason or "").strip() or None},
    )
    return task_out(task)


def _inspector_action(fn, task_id, db, user, *args):
    if user.role != Role.inspector:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the assigned field inspector can do this.")
    try:
        return fn(db, _get_task(db, task_id, user), user, *args)
    except WorkflowError as exc:
        raise _http(exc) from exc


@router.post("/api/tasks/{task_id}/start", response_model=TaskOut)
def start_task(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(task_viewers)):
    task = _inspector_action(workflow.start_task, task_id, db, user)
    record(db, user, "task.started", f"Started task '{task.title}'", "task", task.id)
    return task_out(task)


@router.put("/api/tasks/{task_id}/findings", response_model=TaskOut)
def save_findings(
    task_id: uuid.UUID, body: FindingsBody, db: Session = Depends(get_db), user: User = Depends(task_viewers)
):
    _inspector_action(workflow.save_findings, task_id, db, user, body.model_dump())
    task = _get_task(db, task_id, user)
    record(
        db,
        user,
        "task.findings_saved",
        f"Saved findings for task '{task.title}'",
        "task",
        task.id,
        {"condition": body.condition.value if body.condition else None},
    )
    return task_out(task)


@router.post("/api/tasks/{task_id}/photos", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def upload_photo(
    task_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(task_viewers)
):
    limit = get_settings().max_photo_bytes
    data = await file.read(limit + 1)  # read at most one byte over the limit
    _inspector_action(workflow.add_photo, task_id, db, user, data, file.filename)
    return task_out(_get_task(db, task_id, user))


@router.delete("/api/tasks/{task_id}/photos/{photo_id}", response_model=TaskOut)
def delete_photo(
    task_id: uuid.UUID, photo_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(task_viewers)
):
    _inspector_action(workflow.delete_photo, task_id, db, user, photo_id)
    return task_out(_get_task(db, task_id, user))


@router.post("/api/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(task_viewers)):
    task = _inspector_action(workflow.complete_task, task_id, db, user)
    record(db, user, "task.completed", f"Completed task '{task.title}'", "task", task.id)
    return task_out(task)


@router.get("/api/inspectors")
def list_inspectors(db: Session = Depends(get_db), _: User = Depends(site_editors)):
    """Active inspectors, for task assignment."""
    rows = db.scalars(
        select(User).where(User.role == Role.inspector, User.is_active.is_(True)).order_by(User.full_name)
    )
    return [{"id": u.id, "full_name": u.full_name, "email": u.email} for u in rows]


@router.get("/api/sites/{site_id}/tasks", response_model=list[TaskOut])
def site_tasks(site_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(task_viewers)):
    if db.get(Site, site_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Green space not found.")
    q = select(Task).where(Task.site_id == site_id).order_by(Task.created_at.desc())
    if user.role == Role.inspector:
        q = q.where(Task.assignee_id == user.id)
    return [task_out(t) for t in db.scalars(q)]
