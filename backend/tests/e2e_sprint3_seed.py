"""CONSTRUCTED Sprint 3 browser fixtures. Allowed only in the isolated E2E stack."""

import json
from datetime import date, timedelta

from geoalchemy2.shape import from_shape
from PIL import Image
from shapely.geometry import MultiPolygon, box

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    LstLayer,
    LstObservation,
    PlantingCategory,
    Signal,
    Site,
    SiteSource,
    SiteStatus,
    SiteType,
    WeatherDaily,
)
from app.services.analysis import analyse_sites
from app.services.geometry import geodesic_area_m2
from app.services.media import media_path
from tests.analysis_helpers import add_observations, history, latest


def main():
    assert get_settings().openai_base_url == "http://ai-mock:8080/v1", (
        "E2E fixtures require the isolated test configuration"
    )
    with SessionLocal() as db:
        geom = MultiPolygon([box(46.64, 24.64, 46.643, 24.643)])
        site = db.query(Site).filter_by(name="E2E Sprint 3 Park (constructed)").one_or_none()
        if site is None:
            site = Site(
                name="E2E Sprint 3 Park (constructed)",
                site_type=SiteType.park,
                planting_category=PlantingCategory.turf,
                geom=from_shape(geom, srid=4326),
                area_m2=geodesic_area_m2(geom),
                low_confidence=False,
                needs_review=False,
                source=SiteSource.manual,
                status=SiteStatus.active,
            )
            db.add(site)
            db.commit()
            add_observations(
                db,
                site.id,
                history(0.35, 0.03, 0.01, [2025])
                + latest([("2026-05-05", 0.2), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]),
            )
            for n in range(30):
                db.add(
                    WeatherDaily(
                        site_id=site.id,
                        day=date.today() - timedelta(days=n + 1),
                        et0_mm=5,
                        precip_mm=0,
                        source="e2e-constructed",
                    )
                )
            day = date.today() - timedelta(days=2)
            db.add(
                LstObservation(
                    site_id=site.id,
                    scene_id="E2E-CONSTRUCTED-HEAT",
                    platform="landsat-9",
                    acquired_on=day,
                    site_c=38,
                    surround_c=42,
                    site_pixels=20,
                    surround_pixels=50,
                    valid_share=1,
                    usable=True,
                )
            )
            Image.new("RGBA", (32, 32), (245, 158, 11, 255)).save(media_path("heat", "e2e-constructed.png"))
            db.add(
                LstLayer(
                    scene_id="E2E-CONSTRUCTED-HEAT",
                    platform="landsat-9",
                    acquired_on=day,
                    image="e2e-constructed.png",
                    bounds=[46.63, 24.63, 46.65, 24.65],
                    min_c=38,
                    max_c=42,
                    valid_share=1,
                )
            )
            db.commit()
        analyse_sites(db, [site.id])
        sig = db.query(Signal).filter_by(site_id=site.id).one()
        print(json.dumps({"site": str(site.id), "signal": str(sig.id)}))


if __name__ == "__main__":
    main()
