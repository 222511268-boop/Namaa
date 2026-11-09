"""Operational overview (US21): counts of site conditions, signals, tasks, overdue tasks and signal outcomes.

Filters: district (optional) and period. Site conditions describe the current state of active sites. Signal
figures count signals detected in the period, task figures count tasks created in the period, and outcome figures
count signals closed in the period. Overdue tasks are tasks in the period that are still open after their due date.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, func, select, true
from sqlalchemy.orm import Session

from app.config import get_settings
from app.localtime import local_today
from app.models import (
    ACTIVE_SIGNAL_STATUSES,
    District,
    Observation,
    Signal,
    SignalOutcome,
    SignalStatus,
    Site,
    SiteBaseline,
    SiteStatus,
    Task,
    TaskStatus,
    current_boundary,
)

CONDITIONS = {
    "needs_attention": "Needs attention (active signal)",
    "within_range": "Within seasonal range",
    "below_range": "Below seasonal range (reviewed or not persistent)",
    "baseline_unavailable": "Baseline not yet available",
    "no_satellite_data": "No usable satellite data",
    "low_confidence": "Low confidence (small site)",
}
DEFINITIONS = {
    "conditions": "Current state of active green spaces in the district filter.",
    "signals": "Signals detected in the period, by current status.",
    "tasks": "Tasks created in the period, by current status.",
    "overdue": "Tasks created in the period that are still open after their due date.",
    "outcomes": "Signals closed in the period, by recorded outcome.",
    "confirmation_rate": (
        "Confirmed / (confirmed + not confirmed) field-inspection outcomes closed in the period; "
        "inconclusive and desk reviews excluded."
    ),
}


@dataclass
class Filters:
    district_id: int | None
    start: date
    end: date

    @property
    def start_dt(self) -> datetime:
        return datetime.combine(self.start, time.min, tzinfo=UTC)

    @property
    def end_dt(self) -> datetime:  # exclusive
        return datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=UTC)

    def key(self) -> str:
        return f"district={self.district_id or 'all'};start={self.start.isoformat()};end={self.end.isoformat()}"


def default_filters(district_id: int | None = None, start: date | None = None, end: date | None = None) -> Filters:
    end = end or local_today()
    return Filters(district_id, start or end - timedelta(days=89), end)


def site_conditions(db: Session, district_id: int | None) -> dict[str, list]:
    """Site ids per condition class (each active site appears in exactly one class)."""
    q = select(Site).where(Site.status == SiteStatus.active)
    if district_id is not None:
        q = q.where(Site.district_id == district_id)
    sites = list(db.scalars(q))
    ids = [s.id for s in sites]
    flagged = set(
        db.scalars(select(Signal.site_id).where(Signal.site_id.in_(ids), Signal.status.in_(ACTIVE_SIGNAL_STATUSES)))
    )
    observations = {
        o.site_id: o
        for o in db.scalars(
            select(Observation)
            .where(
                Observation.site_id.in_(ids),
                current_boundary(Observation),
                Observation.usable.is_(True),
                Observation.ndvi_mean.is_not(None),
            )
            .order_by(Observation.site_id, Observation.acquired_on.desc())
            .distinct(Observation.site_id)
        )
    }
    latest = {sid: o.acquired_on for sid, o in observations.items()}
    available = {
        (b.site_id, b.month): b
        for b in db.scalars(select(SiteBaseline).where(SiteBaseline.site_id.in_(ids), SiteBaseline.available))
    }
    settings = get_settings()
    out: dict[str, list] = {k: [] for k in CONDITIONS}
    for s in sites:
        if s.id in flagged:
            out["needs_attention"].append(s.id)
        elif s.low_confidence:
            out["low_confidence"].append(s.id)
        elif s.id not in latest:
            out["no_satellite_data"].append(s.id)
        elif (s.id, latest[s.id].month) not in available:
            out["baseline_unavailable"].append(s.id)
        else:
            o = observations[s.id]
            b = available[(s.id, latest[s.id].month)]
            drop = o.ndvi_mean - b.median_ndvi
            z = drop / max(b.robust_sd or 0, settings.baseline_min_sd)
            key = (
                "below_range" if drop <= -settings.detection_min_drop and z <= settings.detection_z else "within_range"
            )
            out[key].append(s.id)
    return out


def overview(db: Session, f: Filters) -> dict:
    in_district = (Site.district_id == f.district_id) if f.district_id is not None else true()
    sig_q = (
        select(Signal.status, func.count())
        .join(Site, Site.id == Signal.site_id)
        .where(in_district, Signal.detected_at >= f.start_dt, Signal.detected_at < f.end_dt)
        .group_by(Signal.status)
    )
    signals = {s.value: 0 for s in SignalStatus} | {k.value: v for k, v in db.execute(sig_q).all()}

    task_scope = and_(in_district, Task.created_at >= f.start_dt, Task.created_at < f.end_dt)
    task_q = (
        select(Task.status, func.count()).join(Site, Site.id == Task.site_id).where(task_scope).group_by(Task.status)
    )
    tasks = {s.value: 0 for s in TaskStatus} | {k.value: v for k, v in db.execute(task_q).all()}
    overdue = db.scalar(
        select(func.count())
        .select_from(Task)
        .join(Site, Site.id == Task.site_id)
        .where(
            task_scope,
            Task.status.in_((TaskStatus.assigned, TaskStatus.in_progress)),
            Task.due_date < local_today(),
        )
    )

    out_q = (
        select(Signal.outcome, Signal.outcome_method, func.count())
        .join(Site, Site.id == Signal.site_id)
        .where(
            in_district,
            Signal.status == SignalStatus.closed,
            Signal.closed_at >= f.start_dt,
            Signal.closed_at < f.end_dt,
        )
        .group_by(Signal.outcome, Signal.outcome_method)
    )
    outcomes = {o.value: 0 for o in SignalOutcome}
    by_method = {"field_inspection": 0, "desk_review": 0}
    field_confirmed = field_not_confirmed = 0
    for outcome, method, n in db.execute(out_q).all():
        if outcome is not None:
            outcomes[outcome.value] += n
        if method in by_method:
            by_method[method] += n
        if method == "field_inspection" and outcome == SignalOutcome.confirmed:
            field_confirmed += n
        elif method == "field_inspection" and outcome == SignalOutcome.not_confirmed:
            field_not_confirmed += n
    decided = field_confirmed + field_not_confirmed

    conditions = site_conditions(db, f.district_id)
    district = db.get(District, f.district_id) if f.district_id is not None else None
    return {
        "filters": {
            "district_id": f.district_id,
            "district_name": (district.name_en or district.name_ar) if district else None,
            "start": f.start,
            "end": f.end,
        },
        "generated_at": datetime.now(UTC),
        "sites_total": sum(len(v) for v in conditions.values()),
        "conditions": {k: len(v) for k, v in conditions.items()},
        "condition_labels": CONDITIONS,
        "signals": signals,
        "signals_total": sum(signals.values()),
        "tasks": tasks,
        "tasks_total": sum(tasks.values()),
        "overdue_tasks": overdue,
        "outcomes": outcomes,
        "outcomes_by_method": by_method,
        "confirmation_rate_pct": round(100 * field_confirmed / decided, 1) if decided else None,
        "definitions": DEFINITIONS,
    }
