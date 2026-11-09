"""Review decisions, field tasks, findings, and the site activity timeline (US13-US16).

State models:
  Signal: open -> dismissed | closed (confirm) | under_inspection (send for inspection, creates a task)
          under_inspection -> open (inspection task cancelled) | closed (outcome after a completed inspection)
  Task:   assigned -> in_progress -> completed;  assigned | in_progress -> cancelled
"""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.localtime import local_today
from app.models import (
    DecisionType,
    FindingPhoto,
    Role,
    Signal,
    SignalDecision,
    SignalOutcome,
    SignalStatus,
    Site,
    SiteStatus,
    Task,
    TaskFinding,
    TaskStatus,
    TaskType,
    User,
)
from app.services.media import PhotoError, delete_photo_files, save_photo


class WorkflowError(Exception):
    """A request that conflicts with the current state (HTTP 409) or is invalid (HTTP 422)."""

    def __init__(self, message: str, status: int = 409, field: str | None = None):
        super().__init__(message)
        self.status = status
        self.field = field


def _now() -> datetime:
    return datetime.now(UTC)


def _decide(
    db: Session,
    signal: Signal,
    user: User | None,
    decision: DecisionType,
    reason: str | None = None,
    outcome: SignalOutcome | None = None,
) -> None:
    db.add(
        SignalDecision(
            signal_id=signal.id, decision=decision, reason=reason, outcome=outcome, user_id=user.id if user else None
        )
    )


def _require_status(signal: Signal, *allowed: SignalStatus) -> None:
    if signal.status not in allowed:
        raise WorkflowError(f"This signal is {signal.status.value.replace('_', ' ')}; that action is not available.")


# ---------------------------------------------------------------- signal decisions


def dismiss(db: Session, signal: Signal, user: User, reason: str) -> Signal:
    _require_status(signal, SignalStatus.open)
    if not reason or not reason.strip():
        raise WorkflowError("Give a reason for dismissing the signal.", status=422, field="reason")
    signal.status = SignalStatus.dismissed
    _decide(db, signal, user, DecisionType.dismiss, reason.strip())
    db.commit()
    return signal


def confirm(db: Session, signal: Signal, user: User, reason: str | None) -> Signal:
    _require_status(signal, SignalStatus.open)
    signal.status = SignalStatus.closed
    signal.outcome = SignalOutcome.confirmed
    signal.outcome_method = "desk_review"
    signal.closed_at = _now()
    _decide(db, signal, user, DecisionType.confirm, (reason or "").strip() or None, SignalOutcome.confirmed)
    db.commit()
    return signal


def send_for_inspection(db: Session, signal: Signal, user: User, task_data: dict) -> Task:
    _require_status(signal, SignalStatus.open)
    task = create_task(
        db,
        user,
        {**task_data, "site_id": signal.site_id, "signal_id": signal.id, "task_type": TaskType.inspection},
        commit=False,
    )
    signal.status = SignalStatus.under_inspection
    _decide(db, signal, user, DecisionType.send_for_inspection, task_data.get("instructions"))
    db.commit()
    return task


def record_outcome(db: Session, signal: Signal, user: User, outcome: SignalOutcome, note: str | None) -> Signal:
    _require_status(signal, SignalStatus.under_inspection)
    completed = db.scalar(
        select(Task.id)
        .where(Task.signal_id == signal.id, Task.task_type == TaskType.inspection, Task.status == TaskStatus.completed)
        .limit(1)
    )
    if completed is None:
        raise WorkflowError("Record the outcome after the inspection task has been completed.")
    signal.status = SignalStatus.closed
    signal.outcome = outcome
    signal.outcome_method = "field_inspection"
    signal.closed_at = _now()
    _decide(db, signal, user, DecisionType.record_outcome, (note or "").strip() or None, outcome)
    db.commit()
    return signal


# ---------------------------------------------------------------- tasks


def _active_inspector(db: Session, user_id) -> User:
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.role != Role.inspector:
        raise WorkflowError("Choose an active field inspector.", status=422, field="assignee_id")
    return user


def create_task(db: Session, user: User, data: dict, commit: bool = True) -> Task:
    site = db.get(Site, data["site_id"])
    if site is None or site.status != SiteStatus.active:
        raise WorkflowError("Tasks can only be created for active green spaces.", status=422, field="site_id")
    if data.get("signal_id"):
        signal = db.get(Signal, data["signal_id"])
        if signal is None or signal.site_id != site.id:
            raise WorkflowError("The signal does not belong to this site.", status=422, field="signal_id")
    _active_inspector(db, data["assignee_id"])
    task = Task(
        site_id=site.id,
        signal_id=data.get("signal_id"),
        task_type=data["task_type"],
        title=data["title"].strip(),
        instructions=(data.get("instructions") or "").strip() or None,
        priority=data["priority"],
        due_date=data["due_date"],
        assignee_id=data["assignee_id"],
        status=TaskStatus.assigned,
        created_by=user.id,
    )
    db.add(task)
    if commit:
        db.commit()
        db.refresh(task)
    else:
        db.flush()
    return task


def update_task(db: Session, task: Task, data: dict) -> Task:
    if task.status in (TaskStatus.completed, TaskStatus.cancelled):
        raise WorkflowError("Completed or cancelled tasks cannot be changed.")
    if "assignee_id" in data and data["assignee_id"] is not None:
        _active_inspector(db, data["assignee_id"])
    for key in ("title", "instructions", "priority", "due_date", "assignee_id"):
        if data.get(key) is not None:
            setattr(task, key, data[key])
    db.commit()
    db.refresh(task)
    return task


def _require_assignee(task: Task, user: User) -> None:
    if task.assignee_id != user.id:
        raise WorkflowError("Only the assigned inspector can update this task.", status=403)


def start_task(db: Session, task: Task, user: User) -> Task:
    _require_assignee(task, user)
    if task.status != TaskStatus.assigned:
        raise WorkflowError(f"The task is {task.status.value.replace('_', ' ')}; it cannot be started.")
    task.status = TaskStatus.in_progress
    task.started_at = _now()
    db.commit()
    return task


def cancel_task(db: Session, task: Task, user: User, reason: str | None) -> Task:
    if task.status in (TaskStatus.completed, TaskStatus.cancelled):
        raise WorkflowError(f"The task is already {task.status.value}.")
    task.status = TaskStatus.cancelled
    task.cancelled_at = _now()
    if task.signal_id and task.task_type == TaskType.inspection:
        signal = db.get(Signal, task.signal_id)
        others = db.scalar(
            select(Task.id)
            .where(
                Task.signal_id == task.signal_id,
                Task.id != task.id,
                Task.task_type == TaskType.inspection,
                Task.status.in_((TaskStatus.assigned, TaskStatus.in_progress, TaskStatus.completed)),
            )
            .limit(1)
        )
        if signal is not None and signal.status == SignalStatus.under_inspection and others is None:
            signal.status = SignalStatus.open
            _decide(db, signal, user, DecisionType.inspection_cancelled, (reason or "").strip() or None)
    db.commit()
    return task


def _finding(db: Session, task: Task, user: User) -> TaskFinding:
    if task.finding is None:
        task.finding = TaskFinding(task_id=task.id, recorded_by=user.id)
        db.add(task.finding)
        db.flush()
    return task.finding


def save_findings(db: Session, task: Task, user: User, data: dict) -> TaskFinding:
    _require_assignee(task, user)
    if task.status not in (TaskStatus.assigned, TaskStatus.in_progress):
        raise WorkflowError("Findings can only be recorded while the task is open.")
    visit: date | None = data.get("visit_date")
    if visit is not None and visit > local_today():
        raise WorkflowError("The visit date cannot be in the future.", status=422, field="visit_date")
    f = _finding(db, task, user)
    f.visit_date = visit
    f.condition = data.get("condition")
    f.notes = (data.get("notes") or "").strip() or None
    f.recorded_by = user.id
    if task.status == TaskStatus.assigned:  # recording findings implies the work has started
        task.status = TaskStatus.in_progress
        task.started_at = task.started_at or _now()
    db.commit()
    return f


def add_photo(db: Session, task: Task, user: User, data: bytes, filename: str | None) -> FindingPhoto:
    _require_assignee(task, user)
    if task.status not in (TaskStatus.assigned, TaskStatus.in_progress):
        raise WorkflowError("Photos can only be added while the task is open.")
    f = _finding(db, task, user)
    limit = get_settings().max_photos_per_finding
    if len(f.photos) >= limit:
        raise WorkflowError(f"A finding can have at most {limit} photos.", status=422, field="file")
    try:
        saved = save_photo(data, filename)
    except PhotoError as exc:
        raise WorkflowError(str(exc), status=422, field="file") from exc
    photo = FindingPhoto(
        finding_id=f.id,
        file_name=saved.file_name,
        thumb_name=saved.thumb_name,
        width=saved.width,
        height=saved.height,
        size_bytes=saved.size_bytes,
        uploaded_by=user.id,
    )
    db.add(photo)
    db.commit()
    db.refresh(f)
    return photo


def delete_photo(db: Session, task: Task, user: User, photo_id) -> None:
    _require_assignee(task, user)
    if task.status not in (TaskStatus.assigned, TaskStatus.in_progress):
        raise WorkflowError("Photos can only be removed while the task is open.")
    photo = db.get(FindingPhoto, photo_id)
    if photo is None or task.finding is None or photo.finding_id != task.finding.id:
        raise WorkflowError("Photo not found.", status=404)
    names = (photo.file_name, photo.thumb_name)
    db.delete(photo)
    db.commit()
    delete_photo_files(*names)


def complete_task(db: Session, task: Task, user: User) -> Task:
    _require_assignee(task, user)
    if task.status not in (TaskStatus.assigned, TaskStatus.in_progress):
        raise WorkflowError(f"The task is {task.status.value.replace('_', ' ')}; it cannot be completed.")
    f = task.finding
    missing = [
        name
        for name, value in (
            ("visit_date", f and f.visit_date),
            ("condition", f and f.condition),
            ("notes", f and f.notes),
        )
        if not value
    ]
    if missing:
        raise WorkflowError(
            "Record the visit date, observed condition and notes before completing the task.",
            status=422,
            field=missing[0],
        )
    task.status = TaskStatus.completed
    task.completed_at = _now()
    task.started_at = task.started_at or task.completed_at
    db.commit()
    return task


# ---------------------------------------------------------------- site timeline


def site_timeline(db: Session, site_id) -> list[dict]:
    """Signals, decisions, tasks, findings and outcomes for a site, oldest first (US16)."""
    events: list[dict] = []
    signals = list(db.scalars(select(Signal).where(Signal.site_id == site_id)))
    for s in signals:
        events.append(
            {
                "at": s.detected_at,
                "kind": "signal_detected",
                "signal_id": str(s.id),
                "text": f"Unusual decline detected (NDVI {s.latest_ndvi:.2f}, expected about {s.baseline_median:.2f})",
                "user": None,
            }
        )
    if signals:
        decisions = db.scalars(select(SignalDecision).where(SignalDecision.signal_id.in_([s.id for s in signals])))
        labels = {
            DecisionType.dismiss: "Signal dismissed",
            DecisionType.confirm: "Signal confirmed from the evidence",
            DecisionType.send_for_inspection: "Sent for field inspection",
            DecisionType.inspection_cancelled: "Inspection cancelled; signal reopened",
            DecisionType.record_outcome: "Outcome recorded",
            DecisionType.reopened: "Signal reopened by new observations",
        }
        for d in decisions:
            text = labels[d.decision]
            if d.outcome:
                text += f": {d.outcome.value.replace('_', ' ')}"
            events.append(
                {
                    "at": d.created_at,
                    "kind": f"decision_{d.decision.value}",
                    "signal_id": str(d.signal_id),
                    "text": text,
                    "detail": d.reason,
                    "user": d.user.full_name if d.user else None,
                }
            )
    for t in db.scalars(select(Task).where(Task.site_id == site_id)):
        base = {"task_id": str(t.id), "signal_id": str(t.signal_id) if t.signal_id else None}
        events.append(
            {
                **base,
                "at": t.created_at,
                "kind": "task_created",
                "text": f"{t.task_type.value.title()} task assigned to {t.assignee.full_name}: {t.title}",
                "user": t.creator.full_name if t.creator else None,
            }
        )
        if t.completed_at:
            f = t.finding
            detail = None
            if f is not None:
                detail = f"{f.condition.value.replace('_', ' ') if f.condition else ''} · {f.notes or ''}".strip(" ·")
            events.append(
                {
                    **base,
                    "at": t.completed_at,
                    "kind": "task_completed",
                    "text": f"Field findings recorded ({len(f.photos) if f else 0} photos)",
                    "detail": detail,
                    "user": t.assignee.full_name,
                }
            )
        if t.cancelled_at:
            events.append(
                {**base, "at": t.cancelled_at, "kind": "task_cancelled", "text": "Task cancelled", "user": None}
            )
    events.sort(key=lambda e: e["at"])
    return events
