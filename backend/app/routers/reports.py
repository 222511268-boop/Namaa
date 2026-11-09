"""Operational overview (US21), CSV exports and the printable site report (US22), AI overview summary (US27)."""

import csv
import io
import uuid
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ai_summary_users, any_user, overview_viewers
from app.models import (
    ACTIVE_SIGNAL_STATUSES,
    District,
    Observation,
    Role,
    Signal,
    SignalStatus,
    Site,
    SiteType,
    Task,
    TaskStatus,
    User,
    current_boundary,
)
from app.routers.sites import S2_ATTRIBUTION, _filtered, _latest_usable
from app.routers.sites import _detail as site_detail
from app.routers.tasks import task_out
from app.schemas import OverviewSummaryRequest
from app.services import ai, water
from app.services.heat import ATTRIBUTION as LANDSAT_ATTRIBUTION
from app.services.osm import OSM_ATTRIBUTION
from app.services.overview import default_filters, overview, site_conditions
from app.services.weather import ATTRIBUTION as WEATHER_ATTRIBUTION

router = APIRouter(tags=["reports"])

SOURCES = [
    "Park and district boundaries: (c) OpenStreetMap contributors, ODbL",
    "Vegetation observations: contains modified Copernicus Sentinel data, via Microsoft Planetary Computer",
    f"Surface temperature: {LANDSAT_ATTRIBUTION}, via Microsoft Planetary Computer",
    f"Water-demand estimates: {WEATHER_ATTRIBUTION}; plant factors are adjustable assumptions",
]


def _filters(db, district_id, start, end):
    if district_id is not None and db.get(District, district_id) is None:
        raise HTTPException(404, "District not found.")
    filters = default_filters(district_id, start, end)
    if filters.end < filters.start:
        raise HTTPException(422, "The end date must be on or after the start date.")
    return filters


@router.get("/api/overview")
def get_overview(
    district_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(overview_viewers),
):
    return overview(db, _filters(db, district_id, start, end))


# ---------------------------------------------------------------- AI overview summary (US27)


@router.get("/api/ai/status")
def ai_status(db: Session = Depends(get_db), user: User = Depends(any_user)):
    return ai.usage(db, user)


@router.post("/api/overview/summary")
def overview_summary(
    body: OverviewSummaryRequest, db: Session = Depends(get_db), user: User = Depends(ai_summary_users)
):
    f = _filters(db, body.district_id, body.start, body.end)
    ov = overview(db, f)
    facts = ai.overview_facts(ov)
    try:
        brief, reused = ai.generate(db, user, "overview_summary", f.key(), facts, ("overview", f.key()), body.force)
    except ai.AiError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return ai.brief_out(brief, reused=reused) | {"filters": ov["filters"]}


# ---------------------------------------------------------------- CSV exports (US22)


def _safe(v):
    """Neutralise spreadsheet formulas in text cells (CSV injection)."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return "" if v is None else v


def _csv(name: str, title: str, filters: dict, header: list[str], rows, sources: list[str]) -> StreamingResponse:
    buf = io.StringIO()
    buf.write("﻿")  # UTF-8 byte order mark so spreadsheet programs show Arabic names correctly
    w = csv.writer(buf)
    w.writerow([f"# Namaa export: {title}"])
    w.writerow([f"# Generated: {datetime.now(UTC).isoformat(timespec='seconds')}"])
    w.writerow(
        ["# Filters: " + "; ".join(f"{k}={v}" for k, v in filters.items() if v not in (None, "")) or "# Filters: none"]
    )
    for s in sources:
        w.writerow([f"# Source: {s}"])
    w.writerow(header)
    for r in rows:
        w.writerow([_safe(v) for v in r])
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="namaa-{name}-{stamp}.csv"'},
    )


def _period(start: date | None, end: date | None):
    if start and end and end < start:
        raise HTTPException(422, "The end date must be on or after the start date.")
    a = datetime.combine(start, time.min, tzinfo=UTC) if start else None
    b = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC) if end else None
    return a, b


@router.get("/api/exports/sites.csv")
def export_sites(
    q: str | None = Query(None, max_length=120),
    district_id: int | None = None,
    site_type: SiteType | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(any_user),
):
    sites = list(db.scalars(_filtered(q, district_id, site_type, include_inactive).order_by(Site.name)))
    latest = _latest_usable(db, [s.id for s in sites])
    cond = {sid: k for k, ids in site_conditions(db, district_id).items() for sid in ids}
    rows = []
    for s in sites:
        o = latest.get(s.id)
        rows.append(
            [
                s.id,
                s.name,
                s.name_ar,
                s.site_type.value,
                s.planting_category.value,
                (s.district.name_en or s.district.name_ar) if s.district else None,
                round(s.area_m2),
                round(s.irrigated_area_m2) if s.irrigated_area_m2 else None,
                s.status.value,
                cond.get(s.id, "inactive"),
                o.acquired_on if o else None,
                round(o.ndvi_mean, 3) if o and o.ndvi_mean is not None else None,
                "OpenStreetMap" if s.source.value == "osm" else "Drawn in Namaa",
                s.source_ref,
            ]
        )
    return _csv(
        "sites",
        "green spaces",
        {
            "search": q,
            "district_id": district_id,
            "site_type": site_type.value if site_type else None,
            "include_inactive": include_inactive,
        },
        [
            "id",
            "name",
            "name_ar",
            "site_type",
            "planting_category",
            "district",
            "area_m2",
            "irrigated_area_m2",
            "status",
            "condition",
            "latest_observation_on",
            "latest_ndvi",
            "boundary_source",
            "osm_ref",
        ],
        rows,
        SOURCES[:2],
    )


@router.get("/api/exports/signals.csv")
def export_signals(
    status_filter: str = Query("all", alias="status", pattern="^(active|open|under_inspection|dismissed|closed|all)$"),
    district_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(any_user),
):
    if user.role not in (Role.admin, Role.manager):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to export signals.")
    stmt = select(Signal).join(Site)
    if status_filter == "active":
        stmt = stmt.where(Signal.status.in_(ACTIVE_SIGNAL_STATUSES))
    elif status_filter != "all":
        stmt = stmt.where(Signal.status == SignalStatus(status_filter))
    if district_id is not None:
        stmt = stmt.where(Site.district_id == district_id)
    a, b = _period(start, end)
    if a:
        stmt = stmt.where(Signal.detected_at >= a)
    if b:
        stmt = stmt.where(Signal.detected_at < b)
    rows = []
    for s in db.scalars(stmt.order_by(Signal.detected_at.desc())):
        f = s.priority_factors or {}
        rows.append(
            [
                s.id,
                s.site.name,
                (s.site.district.name_en or s.site.district.name_ar) if s.site.district else None,
                s.status.value,
                s.outcome.value if s.outcome else None,
                s.outcome_method,
                s.detected_at.date(),
                s.first_obs_on,
                s.last_obs_on,
                round(s.latest_ndvi, 3),
                round(s.baseline_median, 3),
                round(s.deviation, 3),
                round(s.z_score, 2),
                s.priority_score,
                f.get("heat") if f.get("heat") is not None else "no heat data",
                s.closed_at.date() if s.closed_at else None,
            ]
        )
    return _csv(
        "signals",
        "signals",
        {"status": status_filter, "district_id": district_id, "detected_from": start, "detected_to": end},
        [
            "id",
            "site",
            "district",
            "status",
            "outcome",
            "outcome_method",
            "detected_on",
            "first_obs_on",
            "last_obs_on",
            "latest_ndvi",
            "baseline_median_ndvi",
            "ndvi_difference",
            "z_score",
            "priority_score",
            "priority_heat_points",
            "closed_on",
        ],
        rows,
        SOURCES[1:3],
    )


@router.get("/api/exports/tasks.csv")
def export_tasks(
    status_filter: str = Query("all", alias="status", pattern="^(open|assigned|in_progress|completed|cancelled|all)$"),
    district_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(any_user),
):
    if user.role == Role.viewer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to export tasks.")
    stmt = select(Task).join(Site)
    if user.role == Role.inspector:
        stmt = stmt.where(Task.assignee_id == user.id)  # inspectors export only their own tasks
    if status_filter == "open":
        stmt = stmt.where(Task.status.in_((TaskStatus.assigned, TaskStatus.in_progress)))
    elif status_filter != "all":
        stmt = stmt.where(Task.status == TaskStatus(status_filter))
    if district_id is not None:
        stmt = stmt.where(Site.district_id == district_id)
    a, b = _period(start, end)
    if a:
        stmt = stmt.where(Task.created_at >= a)
    if b:
        stmt = stmt.where(Task.created_at < b)
    rows = []
    for t in db.scalars(stmt.order_by(Task.due_date)):
        o = task_out(t)
        f = t.finding
        rows.append(
            [
                t.id,
                t.title,
                t.task_type.value,
                o["site_name"],
                o["district_name"],
                t.priority.value,
                t.status.value,
                t.due_date,
                "yes" if o["overdue"] else "no",
                o["assignee_name"],
                t.created_at.date(),
                t.completed_at.date() if t.completed_at else None,
                f.visit_date if f else None,
                f.condition.value if f and f.condition else None,
                len(f.photos) if f else 0,
            ]
        )
    return _csv(
        "tasks",
        "tasks",
        {
            "status": status_filter,
            "district_id": district_id,
            "created_from": start,
            "created_to": end,
            "scope": "own tasks" if user.role == Role.inspector else "all tasks",
        },
        [
            "id",
            "title",
            "type",
            "site",
            "district",
            "priority",
            "status",
            "due_date",
            "overdue",
            "assignee",
            "created_on",
            "completed_on",
            "visit_date",
            "observed_condition",
            "photos",
        ],
        rows,
        ["Field findings are user-entered by inspectors."],
    )


# ---------------------------------------------------------------- printable site report (US22)


@router.get("/api/sites/{site_id}/report")
def site_report(site_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(any_user)):
    """Everything needed for a printable site report; sections follow the reader's permissions."""
    from app.routers.insight import site_heat

    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Green space not found.")
    obs = list(
        db.scalars(
            select(Observation)
            .where(Observation.site_id == site.id, current_boundary(Observation), Observation.usable.is_(True))
            .order_by(Observation.acquired_on.desc())
            .limit(12)
        )
    )
    years = sorted({o.acquired_on.year for o in obs})
    cond = next((k for k, ids in site_conditions(db, None).items() if site.id in ids), "inactive")
    report = {
        "site": site_detail(db, site),
        "condition": cond,
        "recent_observations": [
            {"acquired_on": o.acquired_on, "ndvi": o.ndvi_mean, "ndmi": o.ndmi_mean, "valid_share": o.valid_share}
            for o in obs
        ],
        "water": water.site_water(db, site),
        "heat": site_heat(site.id, db, user),
        "generated_at": datetime.now(UTC),
        "generated_by_role": user.role.value,
        "attribution": [
            *([OSM_ATTRIBUTION] if site.source.value == "osm" else []),
            S2_ATTRIBUTION.format(years=", ".join(str(y) for y in years)).strip() if years else None,
            LANDSAT_ATTRIBUTION,
            WEATHER_ATTRIBUTION,
        ],
    }
    report["attribution"] = [a for a in report["attribution"] if a]
    if user.role in (Role.admin, Role.manager):
        from app.routers.signals import _summary as signal_summary

        report["signals"] = [
            signal_summary(s)
            for s in db.scalars(select(Signal).where(Signal.site_id == site.id).order_by(Signal.detected_at.desc()))
        ]
    if user.role != Role.viewer:
        tq = select(Task).where(Task.site_id == site.id).order_by(Task.created_at.desc())
        if user.role == Role.inspector:
            tq = tq.where(Task.assignee_id == user.id)
        report["tasks"] = [task_out(t) for t in db.scalars(tq)]
    return report
