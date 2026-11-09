import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import any_user, site_editors
from app.models import District, Observation, Site, SiteSource, SiteStatus, SiteType, User, current_boundary
from app.schemas import (
    ConditionHistory,
    ObservationOut,
    SiteCreate,
    SiteDetail,
    SiteStatusUpdate,
    SiteSummary,
    SiteUpdate,
)
from app.services import sites as svc
from app.services.audit import record
from app.services.geometry import GeometryError, validate_boundary
from app.services.osm import OSM_ATTRIBUTION

router = APIRouter(prefix="/api/sites", tags=["sites"])

S2_ATTRIBUTION = "Contains modified Copernicus Sentinel data {years}"


def _geometry_error(exc: GeometryError) -> HTTPException:
    return HTTPException(422, [{"loc": ["body", "geometry"], "msg": str(exc), "type": "value_error"}])


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filtered(q: str | None, district_id: int | None, site_type: SiteType | None, include_inactive: bool) -> Select:
    stmt = select(Site)
    if not include_inactive:
        stmt = stmt.where(Site.status == SiteStatus.active)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(or_(Site.name.ilike(pattern, escape="\\"), Site.name_ar.ilike(pattern, escape="\\")))
    if district_id is not None:
        stmt = stmt.where(Site.district_id == district_id)
    if site_type is not None:
        stmt = stmt.where(Site.site_type == site_type)
    return stmt


def _latest_usable(db: Session, site_ids: list[uuid.UUID]) -> dict[uuid.UUID, Observation]:
    if not site_ids:
        return {}
    rows = db.scalars(
        select(Observation)
        .where(Observation.site_id.in_(site_ids), current_boundary(Observation), Observation.usable.is_(True))
        .order_by(Observation.site_id, Observation.acquired_on.desc())
        .distinct(Observation.site_id)
    )
    return {o.site_id: o for o in rows}


def _summary(site: Site, latest: Observation | None) -> dict:
    d = site.district
    return {
        "id": site.id,
        "name": site.name,
        "name_ar": site.name_ar,
        "site_type": site.site_type,
        "planting_category": site.planting_category,
        "district_id": site.district_id,
        "district_name": (d.name_en or d.name_ar) if d else None,
        "area_m2": site.area_m2,
        "low_confidence": site.low_confidence,
        "needs_review": site.needs_review,
        "status": site.status,
        "source": site.source,
        "latest": (
            {"acquired_on": latest.acquired_on, "ndvi_mean": latest.ndvi_mean, "ndmi_mean": latest.ndmi_mean}
            if latest
            else None
        ),
    }


def _get_site(db: Session, site_id: uuid.UUID) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Green space not found.")
    return site


def _detail(db: Session, site: Site) -> dict:
    latest = _latest_usable(db, [site.id]).get(site.id)
    return {
        **_summary(site, latest),
        "source_ref": site.source_ref,
        "notes": site.notes,
        "irrigated_area_m2": site.irrigated_area_m2,
        "geometry": svc.site_geojson(site),
        "created_at": site.created_at,
        "updated_at": site.updated_at,
        "source_attribution": OSM_ATTRIBUTION if site.source == SiteSource.osm else None,
    }


def _check_irrigated_area(irrigated: float | None, area_m2: float) -> None:
    if irrigated is not None and irrigated > area_m2 * 1.001:
        raise HTTPException(
            422,
            [
                {
                    "loc": ["body", "irrigated_area_m2"],
                    "type": "value_error",
                    "msg": f"The irrigated area cannot be larger than the site ({round(area_m2):,} m²).",
                }
            ],
        )


@router.get("", response_model=list[SiteSummary])
def list_sites(
    q: str | None = Query(None, max_length=120),
    district_id: int | None = None,
    site_type: SiteType | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(any_user),
):
    sites = list(db.scalars(_filtered(q, district_id, site_type, include_inactive).order_by(Site.name)))
    latest = _latest_usable(db, [s.id for s in sites])
    return [_summary(s, latest.get(s.id)) for s in sites]


@router.get("/geojson")
def sites_geojson(
    q: str | None = Query(None, max_length=120),
    district_id: int | None = None,
    site_type: SiteType | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(any_user),
):
    stmt = _filtered(q, district_id, site_type, include_inactive).add_columns(ST_AsGeoJSON(Site.geom, 6))
    rows = db.execute(stmt).all()
    latest = _latest_usable(db, [r[0].id for r in rows])
    features = []
    for site, geojson in rows:
        obs = latest.get(site.id)
        features.append(
            {
                "type": "Feature",
                "id": str(site.id),
                "geometry": json.loads(geojson),
                "properties": {
                    "id": str(site.id),
                    "name": site.name,
                    "site_type": site.site_type.value,
                    "low_confidence": site.low_confidence,
                    "needs_review": site.needs_review,
                    "status": site.status.value,
                    "ndvi": round(obs.ndvi_mean, 3) if obs and obs.ndvi_mean is not None else None,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("/{site_id}", response_model=SiteDetail)
def get_site(site_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(any_user)):
    return _detail(db, _get_site(db, site_id))


@router.post("", response_model=SiteDetail, status_code=status.HTTP_201_CREATED)
def create_site(body: SiteCreate, db: Session = Depends(get_db), user: User = Depends(site_editors)):
    try:
        boundary = validate_boundary(body.geometry.model_dump())
    except GeometryError as exc:
        raise _geometry_error(exc) from exc
    _check_irrigated_area(body.irrigated_area_m2, boundary.area_m2)
    site = svc.create_site(db, body, boundary, user)
    record(
        db,
        user,
        "site.created",
        f"Created {site.name}",
        "site",
        site.id,
        {"site_type": site.site_type.value, "area_m2": site.area_m2},
    )
    return _detail(db, site)


@router.put("/{site_id}", response_model=SiteDetail)
def update_site(
    site_id: uuid.UUID, body: SiteUpdate, db: Session = Depends(get_db), user: User = Depends(site_editors)
):
    site = _get_site(db, site_id)
    boundary = None
    if body.geometry is not None:
        try:
            boundary = validate_boundary(body.geometry.model_dump())
        except GeometryError as exc:
            raise _geometry_error(exc) from exc
    _check_irrigated_area(body.irrigated_area_m2, boundary.area_m2 if boundary else site.area_m2)
    before = {
        "name": site.name,
        "site_type": site.site_type.value,
        "planting_category": site.planting_category.value,
        "status": site.status.value,
        "irrigated_area_m2": site.irrigated_area_m2,
    }
    site = svc.update_site(db, site, body, boundary, user)
    after = {
        "name": site.name,
        "site_type": site.site_type.value,
        "planting_category": site.planting_category.value,
        "status": site.status.value,
        "irrigated_area_m2": site.irrigated_area_m2,
    }
    changed = {k: {"from": before[k], "to": after[k]} for k in before if before[k] != after[k]}
    if boundary is not None:
        changed["boundary"] = "redrawn"
    record(db, user, "site.updated", f"Edited {site.name}", "site", site.id, changed)
    return _detail(db, site)


@router.patch("/{site_id}/status", response_model=SiteDetail)
def set_status(
    site_id: uuid.UUID, body: SiteStatusUpdate, db: Session = Depends(get_db), user: User = Depends(site_editors)
):
    site = _get_site(db, site_id)
    previous = site.status
    site.status = body.status
    site.updated_by = user.id
    record(
        db,
        user,
        "site.status_changed",
        f"Set {site.name} to {body.status.value}",
        "site",
        site.id,
        {"from": previous.value, "to": body.status.value},
    )
    db.refresh(site)
    return _detail(db, site)


@router.get("/{site_id}/observations", response_model=ConditionHistory)
def condition_history(site_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(any_user)):
    site = _get_site(db, site_id)
    obs = list(
        db.scalars(
            select(Observation)
            .where(Observation.site_id == site.id, current_boundary(Observation))
            .order_by(Observation.acquired_on)
        )
    )
    usable = [o for o in obs if o.usable]
    years = sorted({o.acquired_on.year for o in obs})
    s = get_settings()
    return ConditionHistory(
        site_id=site.id,
        observations=[ObservationOut.model_validate(o) for o in obs],
        usable_count=len(usable),
        unusable_count=len(obs) - len(usable),
        latest_usable_on=usable[-1].acquired_on if usable else None,
        attribution=S2_ATTRIBUTION.format(years=_year_span(years)) if years else None,
        thresholds={"min_valid_share": s.min_valid_share, "min_valid_pixels": s.min_valid_pixels},
    )


def _year_span(years: list[int]) -> str:
    return str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}"


districts_router = APIRouter(prefix="/api/districts", tags=["districts"])


@districts_router.get("")
def list_districts(db: Session = Depends(get_db), _: User = Depends(any_user)):
    counts = svc.district_counts(db)
    rows = db.scalars(select(District).order_by(func.coalesce(District.name_en, District.name_ar)))
    return [{"id": d.id, "name_en": d.name_en, "name_ar": d.name_ar, "site_count": counts.get(d.id, 0)} for d in rows]
