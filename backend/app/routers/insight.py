"""Water and heat insight (US17-US20): demand estimates, irrigation schedules, plant factors, surface temperature."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import any_user, site_editors
from app.models import (
    IrrigationSchedule,
    LstLayer,
    LstObservation,
    PlantFactor,
    PlantingCategory,
    Site,
    User,
    current_boundary,
)
from app.schemas import PlantFactorOut, PlantFactorUpdate, ScheduleBody, ScheduleOut
from app.services import heat as heat_svc
from app.services import water
from app.services.analysis import MIN_SITES_FOR_HEAT_RANK, heat_context
from app.services.audit import record

router = APIRouter(tags=["insight"])

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _site(db: Session, site_id: uuid.UUID) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Green space not found.")
    return site


def _field(field: str, msg: str) -> HTTPException:
    return HTTPException(422, [{"loc": ["body", field], "msg": msg, "type": "value_error"}])


# ---------------------------------------------------------------- water demand (US17) and schedules (US18)


@router.get("/api/sites/{site_id}/water")
def site_water(
    site_id: uuid.UUID,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(any_user),
):
    if start and end and end < start:
        raise HTTPException(422, "The end date must be on or after the start date.")
    if start and end and (end - start).days > 366:
        raise HTTPException(422, "Choose a period of at most one year.")
    try:
        return water.site_water(db, _site(db, site_id), start, end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/sites/{site_id}/schedules", response_model=list[ScheduleOut])
def list_schedules(site_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(any_user)):
    _site(db, site_id)
    return list(
        db.scalars(
            select(IrrigationSchedule)
            .where(IrrigationSchedule.site_id == site_id)
            .order_by(IrrigationSchedule.start_date.desc())
        )
    )


def _describe(body: ScheduleBody) -> str:
    days = ", ".join(WEEKDAYS[d - 1] for d in sorted(body.weekdays))
    until = body.end_date.isoformat() if body.end_date else "open-ended"
    return f"{round(body.litres_per_day):,} L on {days}, {body.start_date.isoformat()} to {until}"


@router.post("/api/sites/{site_id}/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    site_id: uuid.UUID, body: ScheduleBody, db: Session = Depends(get_db), user: User = Depends(site_editors)
):
    site = _site(db, site_id)
    data = body.model_dump()
    try:
        water.validate_schedule(db, site, data)
    except water.ScheduleError as exc:
        raise _field(exc.field or "start_date", str(exc)) from exc
    sch = IrrigationSchedule(site_id=site.id, created_by=user.id, **data)
    sch.weekdays = sorted(body.weekdays)
    db.add(sch)
    db.flush()
    record(
        db,
        user,
        "schedule.created",
        f"Added irrigation schedule for {site.name}: {_describe(body)}",
        "site",
        site.id,
        {"schedule_id": str(sch.id)},
        commit=False,
    )
    db.commit()
    db.refresh(sch)
    return sch


def _schedule(db: Session, schedule_id: uuid.UUID) -> IrrigationSchedule:
    sch = db.get(IrrigationSchedule, schedule_id)
    if sch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found.")
    return sch


@router.put("/api/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: uuid.UUID, body: ScheduleBody, db: Session = Depends(get_db), user: User = Depends(site_editors)
):
    sch = _schedule(db, schedule_id)
    site = _site(db, sch.site_id)
    data = body.model_dump()
    try:
        water.validate_schedule(db, site, data, schedule_id=sch.id)
    except water.ScheduleError as exc:
        raise _field(exc.field or "start_date", str(exc)) from exc
    for k, v in data.items():
        setattr(sch, k, v)
    sch.weekdays = sorted(body.weekdays)
    record(
        db,
        user,
        "schedule.updated",
        f"Edited irrigation schedule for {site.name}: {_describe(body)}",
        "site",
        site.id,
        {"schedule_id": str(sch.id)},
        commit=False,
    )
    db.commit()
    db.refresh(sch)
    return sch


@router.delete("/api/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(site_editors)):
    sch = _schedule(db, schedule_id)
    site = _site(db, sch.site_id)
    record(
        db,
        user,
        "schedule.deleted",
        f"Removed the irrigation schedule starting {sch.start_date.isoformat()} for {site.name}",
        "site",
        site.id,
        {"schedule_id": str(sch.id)},
        commit=False,
    )
    db.delete(sch)
    db.commit()


@router.get("/api/plant-factors", response_model=list[PlantFactorOut])
def plant_factors(db: Session = Depends(get_db), _: User = Depends(any_user)):
    return list(db.scalars(select(PlantFactor).order_by(PlantFactor.category)))


@router.put("/api/plant-factors/{category}", response_model=PlantFactorOut)
def update_plant_factor(
    category: PlantingCategory,
    body: PlantFactorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(site_editors),
):
    pf = db.get(PlantFactor, category)
    if pf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Planting category not found.")
    old = pf.factor
    pf.factor = round(body.factor, 3)
    pf.source_note = body.source_note.strip()
    pf.updated_by = user.id
    record(
        db,
        user,
        "plant_factor.updated",
        f"Changed the {category.value} plant factor from {old} to {pf.factor}",
        "plant_factor",
        category.value,
        {"from": old, "to": pf.factor},
        commit=False,
    )
    db.commit()
    db.refresh(pf)
    return pf


# ---------------------------------------------------------------- surface heat (US19-US20)


def _layer_out(layer: LstLayer) -> dict:
    return {
        "id": layer.id,
        "scene_id": layer.scene_id,
        "platform": layer.platform,
        "acquired_on": layer.acquired_on,
        "url": f"/api/media/heat/{layer.image}",
        "bounds": layer.bounds,
        "min_c": layer.min_c,
        "max_c": layer.max_c,
        "valid_share": layer.valid_share,
    }


@router.get("/api/heat/layers")
def heat_layers(limit: int = Query(12, ge=1, le=50), db: Session = Depends(get_db), _: User = Depends(any_user)):
    layers = list(db.scalars(select(LstLayer).order_by(LstLayer.acquired_on.desc()).limit(limit)))
    return {
        "layers": [_layer_out(x) for x in layers],
        "ramp": [{"c": c, "color": col} for c, col in heat_svc.RAMP],
        "unit": "°C",
        "resolution": heat_svc.SOURCE_RESOLUTION,
        "attribution": heat_svc.ATTRIBUTION,
    }


@router.get("/api/sites/{site_id}/heat")
def site_heat(site_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(any_user)):
    site = _site(db, site_id)
    rows = list(
        db.scalars(
            select(LstObservation)
            .where(LstObservation.site_id == site.id, current_boundary(LstObservation))
            .order_by(LstObservation.acquired_on.desc())
            .limit(12)
        )
    )
    usable = [r for r in rows if r.usable]
    latest = usable[0] if usable else None
    h = heat_context(db).get(site.id)
    return {
        "latest": (
            {
                "acquired_on": latest.acquired_on,
                "platform": latest.platform,
                "scene_id": latest.scene_id,
                "site_c": latest.site_c,
                "surround_c": latest.surround_c,
                "difference_c": round(latest.site_c - latest.surround_c, 1)
                if latest.site_c is not None and latest.surround_c is not None
                else None,
                "valid_share": latest.valid_share,
            }
            if latest
            else None
        ),
        "history": [
            {"acquired_on": r.acquired_on, "site_c": r.site_c, "surround_c": r.surround_c, "usable": r.usable}
            for r in rows
        ],
        "priority_heat": (
            {
                "surround_c": h.surround_c,
                "acquired_on": h.acquired_on,
                "percentile": round(100 * h.percentile),
                "sites_compared": h.sites_compared,
            }
            if h
            else None
        ),
        "surround_m": heat_svc.get_settings().lst_surround_m,
        "resolution": heat_svc.SOURCE_RESOLUTION,
        "attribution": heat_svc.ATTRIBUTION,
        "method": (
            "Site value: mean land surface temperature of clear pixels inside the boundary. Surrounding area: mean of "
            f"clear pixels within {int(heat_svc.get_settings().lst_surround_m)} m outside the boundary. Heat is used "
            f"in priority when at least {MIN_SITES_FOR_HEAT_RANK} sites were measured on the same date."
        ),
    }
