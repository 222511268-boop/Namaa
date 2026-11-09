"""Green-space registry operations: create, update, district assignment, and OpenStreetMap import."""

import json
from datetime import UTC, datetime

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import LineString, Point, shape
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    District,
    PlantingCategory,
    ProcessingRun,
    RunKind,
    RunStatus,
    Site,
    SiteBaseline,
    SiteSource,
    SiteStatus,
    SiteType,
    User,
)
from app.services import osm
from app.services.geometry import ValidBoundary, as_multipolygon, geodesic_area_m2, pilot_area


def assign_district(db: Session, geom_wkt: str) -> int | None:
    """District with the largest overlap with the site, or None when outside all districts."""
    return db.execute(
        text(
            "SELECT id FROM districts WHERE ST_Intersects(geom, ST_GeomFromText(:g, 4326)) "
            "ORDER BY ST_Area(ST_Intersection(geom, ST_GeomFromText(:g, 4326))) DESC LIMIT 1"
        ),
        {"g": geom_wkt},
    ).scalar()


def is_low_confidence(area_m2: float) -> bool:
    return area_m2 < get_settings().min_monitoring_area_m2


def apply_boundary(db: Session, site: Site, boundary: ValidBoundary) -> None:
    site.geom = from_shape(boundary.geom, srid=4326)
    site.area_m2 = round(boundary.area_m2, 1)
    site.low_confidence = is_low_confidence(boundary.area_m2)
    site.district_id = assign_district(db, boundary.wkt)


def create_site(db: Session, data, boundary: ValidBoundary, user: User) -> Site:
    site = Site(
        name=data.name,
        name_ar=data.name_ar,
        site_type=data.site_type,
        planting_category=data.planting_category,
        notes=data.notes,
        irrigated_area_m2=data.irrigated_area_m2,
        source=SiteSource.manual,
        status=SiteStatus.active,
        created_by=user.id,
        updated_by=user.id,
    )
    apply_boundary(db, site, boundary)
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


def update_site(db: Session, site: Site, data, boundary: ValidBoundary | None, user: User) -> Site:
    site.name = data.name
    site.name_ar = data.name_ar
    site.site_type = data.site_type
    site.planting_category = data.planting_category
    site.notes = data.notes
    site.irrigated_area_m2 = data.irrigated_area_m2
    if data.status is not None:
        site.status = data.status
    if boundary is not None:
        if not to_shape(site.geom).equals(boundary.geom):
            site.boundary_history = [
                *(site.boundary_history or []),
                {
                    "version": site.boundary_version,
                    "geometry": site_geojson(site),
                    "replaced_at": datetime.now(UTC).isoformat(),
                    "replaced_by": str(user.id),
                },
            ]
            site.boundary_version += 1
            db.execute(delete(SiteBaseline).where(SiteBaseline.site_id == site.id))
        apply_boundary(db, site, boundary)
    # A manager has now confirmed the name and planting category.
    site.needs_review = False
    site.updated_by = user.id
    db.commit()
    db.refresh(site)
    return site


def site_geojson(site: Site) -> dict:
    return json.loads(json.dumps(to_shape(site.geom).__geo_interface__))


# ---------------------------------------------------------------- OpenStreetMap import


class OsmImportError(RuntimeError):
    pass


def _feature_anchor(feature: osm.OsmFeature, raw_by_ref: dict) -> Point | None:
    if feature.geom is not None:
        return feature.geom.representative_point()
    pts = [(p["lon"], p["lat"]) for p in (raw_by_ref.get(feature.ref, {}).get("geometry") or []) if p]
    if len(pts) >= 2:
        return LineString(pts).interpolate(0.5, normalized=True)
    return Point(pts[0]) if pts else None


def import_district(db: Session, district: District, user: User) -> tuple[ProcessingRun, dict]:
    """Import OSM parks whose representative point lies inside the district.

    All new sites are created in one transaction; on any OpenStreetMap failure nothing is created.
    """
    district_shape = to_shape(district.geom)
    label = district.name_en or district.name_ar or f"District {district.id}"
    run = ProcessingRun(
        kind=RunKind.osm_import,
        status=RunStatus.running,
        params={"district_id": district.id, "district": label},
        requested_by=user.id,
        started_at=datetime.now(UTC),
    )
    db.add(run)
    db.commit()

    try:
        data = osm.run_query(osm.parks_query(district_shape.bounds))
    except osm.OverpassError as exc:
        run.status = RunStatus.failed
        run.error = str(exc)
        run.finished_at = datetime.now(UTC)
        db.commit()
        raise OsmImportError(str(exc)) from exc

    parsed = osm.parse_elements(data)
    raw_by_ref = {f"{e['type']}/{e['id']}": e for e in data.get("elements", []) if "id" in e}
    existing_refs = set(
        db.scalars(select(Site.source_ref).where(Site.source == SiteSource.osm, Site.source_ref.is_not(None)))
    )
    pilot = pilot_area()

    found, created, already, skipped = 0, [], 0, []
    for feat in parsed.features:
        anchor = _feature_anchor(feat, raw_by_ref)
        if anchor is None or not district_shape.contains(anchor):
            continue  # belongs to a neighbouring district
        found += 1
        if feat.ref in existing_refs:
            already += 1
            continue
        if feat.geom is None:
            skipped.append({"osm_ref": feat.ref, "name": feat.name, "reason": feat.problem or "Invalid geometry"})
            continue
        if not pilot.contains(feat.geom):
            skipped.append({"osm_ref": feat.ref, "name": feat.name, "reason": "Outside the pilot area"})
            continue
        mp = as_multipolygon(feat.geom)
        area = geodesic_area_m2(mp)
        if area <= 0:
            skipped.append({"osm_ref": feat.ref, "name": feat.name, "reason": "Zero area"})
            continue
        kind, osm_id = feat.ref.split("/")
        site = Site(
            name=(feat.name or f"Unnamed park (OSM {kind} {osm_id})")[:120],
            name_ar=(feat.name_ar or None) and feat.name_ar[:120],
            site_type=SiteType.garden if feat.tags.get("leisure") == "garden" else SiteType.park,
            planting_category=PlantingCategory.unknown,
            geom=from_shape(mp, srid=4326),
            area_m2=round(area, 1),
            low_confidence=is_low_confidence(area),
            needs_review=True,  # planting category is unknown until a manager reviews the site
            status=SiteStatus.active,
            source=SiteSource.osm,
            source_ref=feat.ref,
            district_id=district.id,
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(site)
        created.append(site)
        existing_refs.add(feat.ref)

    db.flush()
    run.status = RunStatus.succeeded
    run.finished_at = datetime.now(UTC)
    run.items_written = len(created)
    run.items_skipped = len(skipped) + already
    run.messages = skipped
    db.commit()

    return run, {
        "run_id": run.id,
        "district": label,
        "features_found": found,
        "created": len(created),
        "already_imported": already,
        "skipped": skipped,
        "created_site_ids": [s.id for s in created],
    }


# ---------------------------------------------------------------- districts


def load_districts_geojson(db: Session, path: str) -> int:
    """Insert or update districts from a GeoJSON FeatureCollection saved from OpenStreetMap."""
    with open(path, encoding="utf-8") as fh:
        fc = json.load(fh)
    count = 0
    for f in fc["features"]:
        props = f["properties"]
        geom = as_multipolygon(shape(f["geometry"]))
        osm_id = int(props["osm_id"])
        d = db.scalar(select(District).where(District.osm_id == osm_id)) or District(osm_id=osm_id)
        d.name_en = props.get("name_en")
        d.name_ar = props.get("name_ar")
        d.geom = from_shape(geom, srid=4326)
        db.add(d)
        count += 1
    db.commit()
    return count


def district_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Site.district_id, func.count()).where(Site.status == SiteStatus.active).group_by(Site.district_id)
    ).all()
    return {d: c for d, c in rows if d is not None}
