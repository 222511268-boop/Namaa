"""OpenStreetMap import, processing runs and data freshness, and the role-based workspace summary."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import any_user, processing_operators, site_editors
from app.localtime import local_today
from app.models import (
    District,
    LstLayer,
    LstObservation,
    Observation,
    ProcessingRun,
    Role,
    RunKind,
    RunStatus,
    Signal,
    SignalStatus,
    Site,
    SiteStatus,
    Task,
    TaskStatus,
    User,
    WeatherDaily,
    current_boundary,
)
from app.schemas import ImportRequest, ImportResult, ProcessingRunCreate, ProcessingRunOut
from app.services import processing
from app.services.audit import record
from app.services.sites import OsmImportError, import_district

router = APIRouter(tags=["operations"])


@router.post("/api/imports/osm", response_model=ImportResult)
def import_osm(body: ImportRequest, db: Session = Depends(get_db), user: User = Depends(site_editors)):
    district = db.get(District, body.district_id)
    if district is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "District not found.")
    try:
        _, result = import_district(db, district, user)
    except OsmImportError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    record(
        db,
        user,
        "site.imported",
        f"Imported {result['created']} green spaces from {result['district']}",
        "district",
        district.id,
        {
            "created": result["created"],
            "already_imported": result["already_imported"],
            "skipped": len(result["skipped"]),
        },
    )
    return result


def _run_out(run: ProcessingRun) -> ProcessingRunOut:
    out = ProcessingRunOut.model_validate(run)
    out.requested_by_name = run.requester.full_name if run.requester else None
    return out


@router.get("/api/processing-runs", response_model=list[ProcessingRunOut])
def list_runs(db: Session = Depends(get_db), _: User = Depends(processing_operators)):
    runs = db.scalars(select(ProcessingRun).order_by(ProcessingRun.created_at.desc()).limit(50))
    return [_run_out(r) for r in runs]


RUN_LABELS = {
    RunKind.sentinel2: "Sentinel-2 vegetation",
    RunKind.landsat_lst: "Landsat surface temperature",
    RunKind.weather: "Weather (Open-Meteo)",
    RunKind.osm_import: "OpenStreetMap import",
}


def _queued(db: Session, user: User, run: ProcessingRun, rerun_of=None) -> ProcessingRunOut:
    p = run.params or {}
    period = f" for {p['start_date']} to {p['end_date']}" if p.get("start_date") else ""
    record(
        db,
        user,
        "run.queued",
        f"{'Re-ran' if rerun_of else 'Started'} {RUN_LABELS[run.kind]} processing{period}",
        "processing_run",
        run.id,
        {"kind": run.kind.value, **({"rerun_of": str(rerun_of)} if rerun_of else {})},
    )
    return _run_out(run)


@router.post("/api/processing-runs", response_model=ProcessingRunOut, status_code=status.HTTP_202_ACCEPTED)
def create_run(body: ProcessingRunCreate, db: Session = Depends(get_db), user: User = Depends(processing_operators)):
    kind = RunKind(body.kind)
    if kind == RunKind.landsat_lst:
        # Surface temperature covers the whole pilot area; site values are added for every active site.
        return _queued(db, user, processing.queue_run(db, body.start_date, body.end_date, None, user.id, kind))
    if body.site_ids:
        found = db.scalar(
            select(func.count()).select_from(Site).where(Site.id.in_(body.site_ids), Site.status == SiteStatus.active)
        )
        if found != len(set(body.site_ids)):
            raise HTTPException(
                422,
                [
                    {
                        "loc": ["body", "site_ids"],
                        "msg": "Some selected sites do not exist or are inactive.",
                        "type": "value_error",
                    }
                ],
            )
    elif not db.scalar(select(func.count()).select_from(Site).where(Site.status == SiteStatus.active)):
        raise HTTPException(
            422,
            [{"loc": ["body", "site_ids"], "msg": "There are no active sites to process.", "type": "value_error"}],
        )
    return _queued(db, user, processing.queue_run(db, body.start_date, body.end_date, body.site_ids, user.id, kind))


@router.post(
    "/api/processing-runs/{run_id}/rerun", response_model=ProcessingRunOut, status_code=status.HTTP_202_ACCEPTED
)
def rerun(run_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(processing_operators)):
    """Queue a new run with the same type and settings (US23). Stored results are kept; processing is idempotent."""
    old = db.get(ProcessingRun, run_id)
    if old is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Processing run not found.")
    if old.kind == RunKind.osm_import:
        raise HTTPException(status.HTTP_409_CONFLICT, "Re-run an import from the Import page.")
    if db.scalar(
        select(func.count())
        .select_from(ProcessingRun)
        .where(ProcessingRun.kind == old.kind, ProcessingRun.status.in_((RunStatus.queued, RunStatus.running)))
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "A run of this type is already queued or running.")
    run = ProcessingRun(kind=old.kind, status=RunStatus.queued, params=dict(old.params or {}), requested_by=user.id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return _queued(db, user, run, rerun_of=old.id)


def _last_run(db: Session, kind: RunKind):
    run = db.scalar(select(ProcessingRun).where(ProcessingRun.kind == kind).order_by(ProcessingRun.created_at.desc()))
    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status.value,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "error": run.error,
    }


@router.get("/api/data-freshness")
def data_freshness(db: Session = Depends(get_db), _: User = Depends(processing_operators)):
    """Date of the latest data from each source and the last run that updated it (US23)."""
    return [
        {
            "source": "sentinel2",
            "label": "Sentinel-2 vegetation (NDVI, NDMI)",
            "provider": "ESA Copernicus via Microsoft Planetary Computer",
            "latest_data_on": db.scalar(
                select(func.max(Observation.acquired_on)).where(Observation.usable, current_boundary(Observation))
            ),
            "last_run": _last_run(db, RunKind.sentinel2),
        },
        {
            "source": "landsat_lst",
            "label": "Landsat land surface temperature",
            "provider": "USGS Landsat 8/9 via Microsoft Planetary Computer",
            "latest_data_on": max(
                [
                    d
                    for d in (
                        db.scalar(
                            select(func.max(LstObservation.acquired_on)).where(
                                LstObservation.usable, current_boundary(LstObservation)
                            )
                        ),
                        db.scalar(select(func.max(LstLayer.acquired_on))),
                    )
                    if d is not None
                ],
                default=None,
            ),
            "last_run": _last_run(db, RunKind.landsat_lst),
        },
        {
            "source": "weather",
            "label": "Weather and reference evapotranspiration",
            "provider": "Open-Meteo (CC BY 4.0)",
            "latest_data_on": db.scalar(select(func.max(WeatherDaily.day)).where(current_boundary(WeatherDaily))),
            "last_run": _last_run(db, RunKind.weather),
        },
        {
            "source": "osm_import",
            "label": "Park boundaries",
            "provider": "OpenStreetMap contributors (ODbL)",
            "latest_data_on": (lambda r: r.finished_at.date() if r and r.finished_at else None)(
                db.scalar(
                    select(ProcessingRun)
                    .where(ProcessingRun.kind == RunKind.osm_import, ProcessingRun.status == RunStatus.succeeded)
                    .order_by(ProcessingRun.created_at.desc())
                )
            ),
            "last_run": _last_run(db, RunKind.osm_import),
        },
    ]


@router.get("/api/processing-runs/{run_id}", response_model=ProcessingRunOut)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(processing_operators)):
    run = db.get(ProcessingRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Processing run not found.")
    return _run_out(run)


@router.get("/api/summary")
def workspace_summary(db: Session = Depends(get_db), user: User = Depends(any_user)):
    active = Site.status == SiteStatus.active
    count = lambda *conds: db.scalar(select(func.count()).select_from(Site).where(active, *conds))  # noqa: E731
    summary = {
        "role": user.role.value,
        "sites": {
            "active": count(),
            "needs_review": count(Site.needs_review.is_(True)),
            "low_confidence": count(Site.low_confidence.is_(True)),
            "with_observations": db.scalar(
                select(func.count(func.distinct(Observation.site_id)))
                .join(Site)
                .where(active, Observation.usable, current_boundary(Observation))
            ),
            "total_area_m2": round(db.scalar(select(func.coalesce(func.sum(Site.area_m2), 0)).where(active)), 1),
        },
        "latest_observation_on": db.scalar(
            select(func.max(Observation.acquired_on)).where(Observation.usable, current_boundary(Observation))
        ),
    }
    if user.role in (Role.admin, Role.manager):
        summary["signals"] = {
            "open": db.scalar(select(func.count()).select_from(Signal).where(Signal.status == SignalStatus.open)),
            "under_inspection": db.scalar(
                select(func.count()).select_from(Signal).where(Signal.status == SignalStatus.under_inspection)
            ),
        }
        summary["tasks"] = _task_counts(db, None)
    if user.role == Role.inspector:
        summary["tasks"] = _task_counts(db, user.id)
    if user.role in (Role.admin, Role.manager):
        last = db.scalar(
            select(ProcessingRun)
            .where(ProcessingRun.kind == RunKind.sentinel2)
            .order_by(ProcessingRun.created_at.desc())
        )
        summary["latest_run"] = _run_out(last).model_dump(mode="json") if last else None
    return summary


def _task_counts(db: Session, assignee_id) -> dict:
    open_q = (
        select(func.count()).select_from(Task).where(Task.status.in_((TaskStatus.assigned, TaskStatus.in_progress)))
    )
    if assignee_id is not None:
        open_q = open_q.where(Task.assignee_id == assignee_id)
    return {
        "open": db.scalar(open_q),
        "overdue": db.scalar(open_q.where(Task.due_date < local_today())),
    }
