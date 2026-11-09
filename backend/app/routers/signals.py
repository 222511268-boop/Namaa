"""Attention queue, signal evidence and review decisions (US11-US13, US16); baselines and timeline (US09, US16)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import any_user, signal_viewers, site_editors
from app.models import (
    ACTIVE_SIGNAL_STATUSES,
    Observation,
    Signal,
    SignalDecision,
    SignalStatus,
    Site,
    SiteBaseline,
    Task,
    User,
)
from app.routers.tasks import task_out, workflow_http
from app.schemas import (
    BaselineOut,
    BriefRequest,
    DismissBody,
    OutcomeBody,
    ReasonBody,
    SignalDetail,
    SignalSummary,
    TaskFields,
    TaskOut,
)
from app.services import ai, workflow
from app.services.audit import record
from app.services.workflow import WorkflowError

router = APIRouter(tags=["signals"])


def _summary(sig: Signal) -> dict:
    site = sig.site
    d = site.district
    return {
        "id": sig.id,
        "site_id": site.id,
        "site_name": site.name,
        "site_name_ar": site.name_ar,
        "district_id": site.district_id,
        "district_name": (d.name_en or d.name_ar) if d else None,
        "site_type": site.site_type.value,
        "area_m2": site.area_m2,
        "status": sig.status,
        "outcome": sig.outcome,
        "detected_at": sig.detected_at,
        "first_obs_on": sig.first_obs_on,
        "last_obs_on": sig.last_obs_on,
        "latest_ndvi": sig.latest_ndvi,
        "baseline_median": sig.baseline_median,
        "deviation": sig.deviation,
        "z_score": sig.z_score,
        "priority_score": sig.priority_score,
        "priority_factors": sig.priority_factors,
        "reopened_count": sig.reopened_count,
    }


def _image(db: Session, obs_id, name: str | None) -> dict | None:
    if obs_id is None:
        return None
    obs = db.get(Observation, obs_id)
    if obs is None:
        return None
    return {
        "date": obs.acquired_on.isoformat(),
        "scene_id": obs.scene_id,
        "ndvi": obs.ndvi_mean,
        "url": f"/api/media/chips/{name}" if name else None,
    }


def _get_signal(db: Session, signal_id: uuid.UUID) -> Signal:
    sig = db.get(Signal, signal_id)
    if sig is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Signal not found.")
    return sig


def _detail(db: Session, sig: Signal) -> dict:
    decisions = db.scalars(
        select(SignalDecision).where(SignalDecision.signal_id == sig.id).order_by(SignalDecision.created_at)
    )
    tasks = db.scalars(select(Task).where(Task.signal_id == sig.id).order_by(Task.created_at))
    years = sorted({o["date"][:4] for o in (sig.evidence or {}).get("observations", [])})
    return {
        **_summary(sig),
        "outcome_method": sig.outcome_method,
        "closed_at": sig.closed_at,
        "baseline_sd": sig.baseline_sd,
        "evidence": sig.evidence,
        "boundary_changed": (sig.evidence or {}).get("boundary_version", 1) != sig.site.boundary_version,
        "before_image": _image(db, sig.before_obs_id, sig.before_image),
        "after_image": _image(db, sig.after_obs_id, sig.after_image),
        "decisions": [
            {
                "decision": d.decision.value,
                "reason": d.reason,
                "outcome": d.outcome,
                "user_name": d.user.full_name if d.user else None,
                "created_at": d.created_at,
            }
            for d in decisions
        ],
        "tasks": [task_out(t) for t in tasks],
        "attribution": f"Contains modified Copernicus Sentinel data {', '.join(years) or ''}".strip(),
    }


@router.get("/api/signals", response_model=list[SignalSummary])
def list_signals(
    status_filter: str = Query(
        "active", alias="status", pattern="^(active|open|under_inspection|dismissed|closed|all)$"
    ),
    district_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(signal_viewers),
):
    q = select(Signal).join(Site)
    if status_filter == "active":
        q = q.where(Signal.status.in_(ACTIVE_SIGNAL_STATUSES))
    elif status_filter != "all":
        q = q.where(Signal.status == SignalStatus(status_filter))
    if district_id is not None:
        q = q.where(Site.district_id == district_id)
    q = q.order_by(Signal.priority_score.desc(), Signal.detected_at)
    return [_summary(s) for s in db.scalars(q)]


@router.get("/api/signals/{signal_id}", response_model=SignalDetail)
def get_signal(signal_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(signal_viewers)):
    return _detail(db, _get_signal(db, signal_id))


@router.post("/api/signals/{signal_id}/dismiss", response_model=SignalDetail)
def dismiss(signal_id: uuid.UUID, body: DismissBody, db: Session = Depends(get_db), user: User = Depends(site_editors)):
    try:
        sig = workflow.dismiss(db, _get_signal(db, signal_id), user, body.reason)
    except WorkflowError as exc:
        raise workflow_http(exc) from exc
    record(
        db,
        user,
        "signal.dismissed",
        f"Dismissed the signal for {sig.site.name}",
        "signal",
        sig.id,
        {"reason": body.reason.strip()},
    )
    return _detail(db, sig)


@router.post("/api/signals/{signal_id}/confirm", response_model=SignalDetail)
def confirm(signal_id: uuid.UUID, body: ReasonBody, db: Session = Depends(get_db), user: User = Depends(site_editors)):
    try:
        sig = workflow.confirm(db, _get_signal(db, signal_id), user, body.reason)
    except WorkflowError as exc:
        raise workflow_http(exc) from exc
    record(db, user, "signal.confirmed", f"Confirmed the signal for {sig.site.name} by desk review", "signal", sig.id)
    return _detail(db, sig)


@router.post("/api/signals/{signal_id}/inspection", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def send_for_inspection(
    signal_id: uuid.UUID, body: TaskFields, db: Session = Depends(get_db), user: User = Depends(site_editors)
):
    try:
        task = workflow.send_for_inspection(db, _get_signal(db, signal_id), user, body.model_dump())
    except WorkflowError as exc:
        raise workflow_http(exc) from exc
    record(
        db,
        user,
        "signal.sent_for_inspection",
        f"Sent the signal for {task.site.name} for inspection",
        "signal",
        signal_id,
        {"task_id": str(task.id), "assignee": task.assignee.full_name, "due_date": task.due_date.isoformat()},
    )
    db.refresh(task)
    return task_out(task)


@router.post("/api/signals/{signal_id}/outcome", response_model=SignalDetail)
def record_outcome(
    signal_id: uuid.UUID, body: OutcomeBody, db: Session = Depends(get_db), user: User = Depends(site_editors)
):
    try:
        sig = workflow.record_outcome(db, _get_signal(db, signal_id), user, body.outcome, body.note)
    except WorkflowError as exc:
        raise workflow_http(exc) from exc
    record(
        db,
        user,
        "signal.outcome_recorded",
        f"Recorded outcome '{body.outcome.value.replace('_', ' ')}' for {sig.site.name}",
        "signal",
        sig.id,
        {"outcome": body.outcome.value},
    )
    return _detail(db, sig)


@router.get("/api/sites/{site_id}/baselines", response_model=list[BaselineOut])
def site_baselines(site_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(any_user)):
    if db.get(Site, site_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Green space not found.")
    return list(db.scalars(select(SiteBaseline).where(SiteBaseline.site_id == site_id).order_by(SiteBaseline.month)))


@router.get("/api/sites/{site_id}/timeline")
def site_timeline(site_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(any_user)):
    if db.get(Site, site_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Green space not found.")
    active = db.scalar(select(Signal.id).where(Signal.site_id == site_id, Signal.status.in_(ACTIVE_SIGNAL_STATUSES)))
    return {"active_signal_id": active, "events": workflow.site_timeline(db, site_id)}


# ---------------------------------------------------------------- AI evidence brief (US26)


@router.get("/api/signals/{signal_id}/brief")
def get_brief(signal_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(signal_viewers)):
    """The latest stored brief, marked outdated when the signal's evidence has changed since it was generated."""
    sig = _get_signal(db, signal_id)
    brief = ai.cached(db, "signal_brief", str(sig.id))
    if brief is None:
        return None
    current = ai.facts_hash(ai.signal_facts(db, sig), brief.prompt_version, brief.model)
    return ai.brief_out(brief, current) | {"checklist_text": ai.checklist_text(brief.content)}


@router.post("/api/signals/{signal_id}/brief")
def create_brief(
    signal_id: uuid.UUID, body: BriefRequest, db: Session = Depends(get_db), user: User = Depends(site_editors)
):
    """Generate (or reuse) the AI evidence brief. Managers only; failures never block the review workflow."""
    sig = _get_signal(db, signal_id)
    facts = ai.signal_facts(db, sig)
    try:
        brief, reused = ai.generate(db, user, "signal_brief", str(sig.id), facts, ("signal", str(sig.id)), body.force)
    except ai.AiError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return ai.brief_out(brief, reused=reused) | {"checklist_text": ai.checklist_text(brief.content)}
