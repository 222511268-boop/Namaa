"""Opt-in live provider checks, separate from constructed acceptance fixtures (NAMAA_LIVE=1)."""

import os
from datetime import date

import pytest
from shapely.geometry import shape

from app.config import get_settings
from app.models import LstLayer, LstObservation, Role
from app.services.heat import LandsatSource, execute_lst_run, queue_lst_run
from app.services.weather import fetch
from tests.test_live_sentinel import LIVE_SITE

pytestmark = pytest.mark.skipif(os.environ.get("NAMAA_LIVE") != "1", reason="set NAMAA_LIVE=1 for live provider checks")


def test_live_weather_returns_dated_et0():
    rows = fetch([(46.775, 24.731)], date(2025, 6, 1), date(2025, 6, 5))[0]
    assert len(rows) == 5
    assert all(d.et0_mm is not None and 0 <= d.et0_mm < 30 and source == "open-meteo-archive" for d, source in rows)
    print("Live Open-Meteo ET0:", [(d.day.isoformat(), d.et0_mm, source) for d, source in rows])


def test_live_landsat_saves_surface_temperature_and_rendered_layer(as_role, db):
    settings = get_settings()
    source = LandsatSource(settings.stac_api_url, settings.landsat_collection, settings.landsat_max_cloud_cover)
    scene = next(
        s
        for s in source.search(shape(LIVE_SITE).bounds, "2025-06-01", "2025-06-20")
        if s.footprint.contains(shape(LIVE_SITE))
    )

    class SingleScene:
        def search(self, *_):
            return [scene]

        def signed_hrefs(self, selected):
            return source.signed_hrefs(selected)

    manager = as_role(Role.manager)
    site = manager.post(
        "/api/sites",
        json={"name": "Live Landsat Check", "site_type": "park", "planting_category": "mixed", "geometry": LIVE_SITE},
    ).json()
    run = queue_lst_run(db, date(2025, 6, 1), date(2025, 6, 20), None)
    execute_lst_run(db, run, SingleScene())
    assert run.status.value == "succeeded", run.error
    observation = db.query(LstObservation).filter_by(site_id=site["id"]).one()
    assert observation.usable and 10 < observation.site_c < 80
    layer = db.query(LstLayer).filter_by(scene_id=scene.id).one()
    response = manager.get(f"/api/media/heat/{layer.image}")
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    print(
        f"Live Landsat: {scene.id}, {observation.acquired_on}, site={observation.site_c} C, "
        f"surroundings={observation.surround_c} C, valid={observation.valid_share}, map={layer.image}"
    )
