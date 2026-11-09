"""Seed CONSTRUCTED data for the end-to-end workflow tests (never run against real deployments).

Creates two clearly named test sites with a constructed 2025 NDVI history and a 2026 decline, then runs the real
analysis so the attention queue contains two signals. Prints the created ids as JSON.

Usage (inside the E2E backend container): python -m tests.e2e_seed
"""

import json

from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, box

from app.db import SessionLocal
from app.models import PlantingCategory, Signal, Site, SiteSource, SiteStatus, SiteType
from app.services.analysis import analyse_sites
from app.services.geometry import geodesic_area_m2
from tests.analysis_helpers import add_observations, history, latest

SITES = [
    (
        "E2E Decline Park A (constructed data)",
        (46.60, 24.60, 46.603, 24.603),
        [("2026-05-05", 0.20), ("2026-05-10", 0.19), ("2026-05-15", 0.18)],
    ),
    (
        "E2E Decline Park B (constructed data)",
        (46.61, 24.60, 46.612, 24.602),
        [("2026-05-05", 0.24), ("2026-05-10", 0.23), ("2026-05-15", 0.22)],
    ),
]


def main() -> None:
    out = []
    with SessionLocal() as db:
        for name, bounds, points in SITES:
            existing = db.query(Site).filter_by(name=name).one_or_none()
            if existing is None:
                geom = MultiPolygon([box(*bounds)])
                existing = Site(
                    name=name,
                    site_type=SiteType.park,
                    planting_category=PlantingCategory.turf,
                    geom=from_shape(geom, srid=4326),
                    area_m2=round(geodesic_area_m2(geom), 1),
                    low_confidence=False,
                    needs_review=False,
                    status=SiteStatus.active,
                    source=SiteSource.manual,
                    notes="Constructed test data for end-to-end tests.",
                )
                db.add(existing)
                db.commit()
                add_observations(db, existing.id, history(0.35, 0.03, 0.01, [2025]) + latest(points))
            out.append(existing.id)
        analyse_sites(db, out)
        signals = {str(s.site_id): str(s.id) for s in db.query(Signal).filter(Signal.site_id.in_(out))}
    print(json.dumps({"sites": [str(i) for i in out], "signals": signals}))


if __name__ == "__main__":
    main()
