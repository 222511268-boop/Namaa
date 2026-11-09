"""Live checks against real Sentinel-2 data on the Planetary Computer (AC-07.2 real scene, AC-07.7).

Skipped unless NAMAA_LIVE=1, because they need internet access and take a few minutes.
The reference calculation reads the full-resolution assets independently (whole-array reads, explicit
pixel-centre test with shapely) and compares the result with the production pipeline.
"""

import os
from datetime import date

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform

from app.config import get_settings
from app.models import Observation, Role
from app.services.processing import claim_next_run, execute_run
from app.services.satellite import PlanetaryComputerSource

pytestmark = pytest.mark.skipif(os.environ.get("NAMAA_LIVE") != "1", reason="set NAMAA_LIVE=1 for live data checks")

# Al Roudah Gardens, Al Rawdah District, Riyadh (OSM way 53062891, bounding box 46.77252-46.77732 E,
# 24.72920-24.73343 N). A rectangle in the centre of the park (about 2.2 ha) is used for this check.
LIVE_SITE = {
    "type": "Polygon",
    "coordinates": [
        [[46.7740, 24.7305], [46.7760, 24.7305], [46.7760, 24.7315], [46.7740, 24.7315], [46.7740, 24.7305]]
    ],
}


def _source():
    s = get_settings()
    return PlanetaryComputerSource(s.stac_api_url, s.stac_collection, s.scene_max_cloud_cover)


def test_ac_07_7_live_run_stores_real_observations(as_role, db):
    manager = as_role(Role.manager)
    site = manager.post(
        "/api/sites",
        json={"name": "Live Check Park", "site_type": "park", "planting_category": "mixed", "geometry": LIVE_SITE},
    ).json()
    manager.post("/api/processing-runs", json={"start_date": "2025-06-01", "end_date": "2025-06-30"})
    run = execute_run(db, claim_next_run(db), _source())
    assert run.status.value == "succeeded", run.error
    obs = db.query(Observation).filter_by(site_id=site["id"]).all()
    assert len(obs) >= 4, "June in Riyadh should give several clear acquisitions"
    assert all(o.scene_id.startswith("S2") and o.acquired_on.month == 6 for o in obs)
    usable = [o for o in obs if o.usable]
    assert usable and all(-1 <= o.ndvi_mean <= 1 for o in usable)
    print("\nLIVE observations:")
    for o in sorted(obs, key=lambda o: o.acquired_on):
        print(
            f"  {o.acquired_on} {o.scene_id[:60]} ndvi={o.ndvi_mean} ndmi={o.ndmi_mean} "
            f"valid={o.valid_pixels}/{o.total_pixels} usable={o.usable}"
        )


def test_ac_07_2_live_scene_matches_independent_reference(as_role, db):
    src = _source()
    geom = shape(LIVE_SITE)
    scene = next(s for s in src.search(geom.bounds, "2025-06-01", "2025-06-30") if s.footprint.contains(geom))
    hrefs = src.signed_hrefs(scene)

    from app.services.satellite import SceneReader

    with SceneReader(hrefs, scene) as reader:
        stats = reader.site_stats(geom)

    # Independent reference: read B04/B08 windows via a different code path and test pixel centres directly.
    to_utm = Transformer.from_crs(4326, scene.epsg, always_xy=True)
    poly = transform(to_utm.transform, geom)
    minx, miny, maxx, maxy = poly.bounds
    with rasterio.open(hrefs["B04"]) as b4, rasterio.open(hrefs["B08"]) as b8, rasterio.open(hrefs["SCL"]) as scl:
        win = b4.window(minx - 20, miny - 20, maxx + 20, maxy + 20).round_offsets().round_lengths()
        red, nir = b4.read(1, window=win).astype(float), b8.read(1, window=win).astype(float)
        t = b4.window_transform(win)
        scl_arr, st = scl.read(1), scl.transform
    vals, inside = [], 0
    for r in range(red.shape[0]):
        for c in range(red.shape[1]):
            x, y = t.c + (c + 0.5) * t.a, t.f + (r + 0.5) * t.e
            if not poly.contains(Point(x, y)):
                continue
            inside += 1
            sr, sc = int((y - st.f) / st.e), int((x - st.c) / st.a)
            if scl_arr[sr, sc] not in (4, 5, 6, 7) or red[r, c] == 0 or nir[r, c] == 0:
                continue
            rr, nn = (red[r, c] - 1000) / 1e4, (nir[r, c] - 1000) / 1e4
            if rr + nn > 0:
                vals.append((nn - rr) / (nn + rr))
    print(
        f"\nLIVE reference {scene.id}: pipeline ndvi={stats.ndvi_mean:.5f} "
        f"({stats.valid_pixels}/{stats.total_pixels} px), "
        f"reference ndvi={np.mean(vals):.5f} ({len(vals)}/{inside} px)"
    )
    assert stats.total_pixels == inside
    # B11 no-data and swir>0 checks are only in the pipeline; allow a tiny pixel-count difference.
    assert abs(stats.valid_pixels - len(vals)) <= 2
    assert stats.ndvi_mean == pytest.approx(float(np.mean(vals)), abs=0.005)
    assert scene.acquired_at.date() >= date(2025, 6, 1)
