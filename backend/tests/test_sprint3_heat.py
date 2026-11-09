"""US19-US20: Landsat land surface temperature layer, site values, and heat in priority.

Landsat scenes here are small CONSTRUCTED GeoTIFFs with known values, not real data.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from shapely.geometry import box, shape
from shapely.ops import transform as shp_transform

from app.config import get_settings
from app.models import LstLayer, LstObservation, ProcessingRun, Role, RunKind, RunStatus, Signal, SiteType
from app.services.analysis import Heat, analyse_sites, heat_context, percentile_rank, priority
from app.services.heat import (
    LstReader,
    clear_mask,
    colourise,
    dn_to_celsius,
    execute_lst_run,
)
from app.services.media import media_path
from app.services.processing import analyse_after_run
from app.services.satellite import Scene
from tests.analysis_helpers import add_observations, history, latest
from tests.conftest import square

EPSG = 32638
_to_utm = Transformer.from_crs(4326, EPSG, always_xy=True)
_to_wgs = Transformer.from_crs(EPSG, 4326, always_xy=True)


def dn_for(celsius: float) -> int:
    return round((celsius + 273.15 - 149.0) / 0.00341802)


def write_landsat(folder: Path, scene_id: str, site_geoms, site_c=35.0, other_c=45.0, cloud_rows=0,
                  when=datetime(2026, 6, 10, 7, 20, tzinfo=UTC), origin=(46.700, 24.715), size_px=100) -> Scene:
    """30 m thermal and QA rasters: `site_c` inside the given polygons, `other_c` elsewhere; the top `cloud_rows`
    rows are flagged as cloud (QA bit 3) with a cold value that must be excluded."""
    folder.mkdir(parents=True, exist_ok=True)
    x0, y0 = _to_utm.transform(*origin)
    x0, y0 = round(x0 / 30) * 30, round(y0 / 30) * 30
    tr = from_origin(x0, y0, 30, 30)
    st = np.full((size_px, size_px), dn_for(other_c), dtype="uint16")
    qa = np.full((size_px, size_px), 0b1000000, dtype="uint16")  # bit 6: clear
    if site_geoms:
        utm = [shp_transform(_to_utm.transform, g) for g in site_geoms]
        inside = geometry_mask(utm, out_shape=st.shape, transform=tr, invert=True)
        st[inside] = dn_for(site_c)
    if cloud_rows:
        st[:cloud_rows, :] = dn_for(5.0)
        qa[:cloud_rows, :] = 0b1000  # cloud
    hrefs = {}
    for name, arr in (("lwir11", st), ("qa_pixel", qa)):
        p = folder / f"{scene_id}_{name}.tif"
        with rasterio.open(p, "w", driver="GTiff", height=size_px, width=size_px, count=1, dtype="uint16",
                           crs=f"EPSG:{EPSG}", transform=tr) as dst:
            dst.write(arr, 1)
        hrefs[name] = str(p)
    xmax, ymin = x0 + size_px * 30, y0 - size_px * 30
    (lon0, lat1), (lon1, lat0) = _to_wgs.transform(x0, y0), _to_wgs.transform(xmax, ymin)
    return Scene(id=scene_id, acquired_at=when, platform="landsat-9", processing_baseline="", epsg=EPSG,
                 footprint=box(lon0, lat0, lon1, lat1), hrefs=hrefs)


class FakeLandsat:
    def __init__(self, scenes):
        self.scenes = scenes

    def search(self, bbox, start, end):
        return self.scenes

    def signed_hrefs(self, scene):
        return scene.hrefs


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


@pytest.fixture
def small_pilot(monkeypatch):
    # Pilot area reduced to the constructed scene so the map layer has meaningful coverage.
    monkeypatch.setattr(get_settings(), "pilot_bbox", (46.700, 24.690, 46.725, 24.712))
    monkeypatch.setattr(get_settings(), "media_dir", "/tmp/namaa-test-media")


def _site(manager, name, lon, size=0.003):
    r = manager.post("/api/sites", json={"name": name, "site_type": "park", "planting_category": "turf",
                                         "geometry": square(lon, 24.700, size)})
    assert r.status_code == 201, r.text
    return r.json()


def test_dn_conversion_and_quality_mask():
    assert dn_to_celsius(np.array([dn_for(35.0)]))[0] == pytest.approx(35.0, abs=0.01)
    st = np.array([0, 100, 100, 100, 100, 100], dtype="uint16")
    qa = np.array([0, 0b1, 0b100, 0b1000, 0b10000, 0b1000000], dtype="uint16")
    assert clear_mask(st, qa).tolist() == [False, False, False, False, False, True]


def test_colour_scale_fixed_and_transparent_where_invalid():
    rgba = colourise(np.array([[10.0, 15.0, 65.0, 80.0]]), np.array([[True, True, True, False]]))
    assert rgba[0, 0, :3].tolist() == rgba[0, 1, :3].tolist() == [0xFE, 0xF3, 0xC7]  # clipped to 15 °C
    assert rgba[0, 2, :3].tolist() == [0x6B, 0x0F, 0x1A]
    assert rgba[0, 3, 3] == 0 and rgba[0, 0, 3] == 255


def test_ac_19_2_site_and_surrounding_values(tmp_path):
    geom = shape(square(46.705, 24.700, 0.003))
    scene = write_landsat(tmp_path, "LC09_T1", [geom], site_c=35.0, other_c=45.0, cloud_rows=5)
    with LstReader(scene.hrefs, scene) as r:
        stats = r.site_stats(geom)
    assert stats.site_c == pytest.approx(35.0, abs=0.01)
    assert stats.surround_c == pytest.approx(45.0, abs=0.01)  # cloudy rows (5 °C) excluded
    assert stats.site_pixels > 50 and stats.surround_pixels > stats.site_pixels
    assert stats.usable


def test_ac_19_1_run_stores_site_values_and_map_layer(manager, db, tmp_path, small_pilot, as_role):
    a = _site(manager, "Heat Park A", 46.705)
    scene = write_landsat(tmp_path, "LC09_L2SP_165043_20260610", [shape(square(46.705, 24.700, 0.003))])
    run = ProcessingRun(kind=RunKind.landsat_lst, status=RunStatus.running,
                        params={"start_date": "2026-06-01", "end_date": "2026-06-30"})
    db.add(run)
    db.commit()
    execute_lst_run(db, run, FakeLandsat([scene]))
    assert run.status == RunStatus.succeeded, (run.error, run.messages)
    obs = db.query(LstObservation).one()
    assert obs.site_c == pytest.approx(35.0, abs=0.01) and obs.surround_c == pytest.approx(45.0, abs=0.01)
    assert obs.acquired_on == date(2026, 6, 10) and obs.usable

    layer = db.query(LstLayer).one()
    assert layer.acquired_on == date(2026, 6, 10)
    w, s, e, n = layer.bounds
    assert (w, s, e, n) == get_settings().pilot_bbox
    img = Image.open(media_path("heat", layer.image))
    assert img.mode == "RGBA" and img.size == (round((e - w) / 0.0005), round((n - s) / 0.0005))
    assert layer.min_c == pytest.approx(35.0, abs=0.1) and layer.max_c == pytest.approx(45.0, abs=0.1)

    viewer = as_role(Role.viewer)
    layers = viewer.get("/api/heat/layers").json()
    assert layers["unit"] == "°C" and layers["layers"][0]["acquired_on"] == "2026-06-10"
    assert [x["c"] for x in layers["ramp"]][0] == 15.0 and "100 m" in layers["resolution"]
    assert "U.S. Geological Survey" in layers["attribution"]
    png = viewer.get(layers["layers"][0]["url"])
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"

    h = viewer.get(f"/api/sites/{a['id']}/heat").json()
    assert h["latest"]["site_c"] == pytest.approx(35.0, abs=0.01)
    assert h["latest"]["surround_c"] == pytest.approx(45.0, abs=0.01)
    assert h["latest"]["difference_c"] == pytest.approx(-10.0, abs=0.05)
    assert "100 m" in h["resolution"] and h["surround_m"] == 300


def test_lst_run_failure_keeps_stored_values(db, manager, tmp_path, small_pilot):
    class Down:
        def search(self, *a):
            from app.services.satellite import SceneSourceError

            raise SceneSourceError("The Landsat catalogue could not be searched: simulated outage")

    run = ProcessingRun(kind=RunKind.landsat_lst, status=RunStatus.running,
                        params={"start_date": "2026-06-01", "end_date": "2026-06-30"})
    db.add(run)
    db.commit()
    execute_lst_run(db, run, Down())
    assert run.status == RunStatus.failed and "simulated outage" in run.error


# ---------------------------------------------------------------- US20


def test_ac_20_1_priority_with_documented_heat_factor():
    first, last = date(2026, 5, 1), date(2026, 5, 31)
    base, f0 = priority(-4.0, first, last, 250000, SiteType.park)
    assert f0["heat"] is None and base == pytest.approx(100.0)  # all four factors at maximum
    hot, f1 = priority(-4.0, first, last, 250000, SiteType.park, Heat(47.0, date(2026, 6, 10), 1.0, 5))
    assert f1["heat"] == 10.0 and f1["severity"] == 45.0 and hot == pytest.approx(100.0)
    cool, f2 = priority(-4.0, first, last, 250000, SiteType.park, Heat(40.0, date(2026, 6, 10), 0.0, 5))
    assert f2["heat"] == 0.0 and cool == pytest.approx(90.0)
    assert f1["heat_c"] == 47.0 and f1["heat_date"] == "2026-06-10" and f1["heat_percentile"] == 100
    # contributions add up to the score
    assert sum(v for k, v in f1.items() if k in ("severity", "persistence", "size", "site_type", "heat")) == hot


def test_percentile_rank():
    vals = [40.0, 42.0, 44.0, 46.0]
    assert percentile_rank(40.0, vals) == 0.125 and percentile_rank(46.0, vals) == 0.875


def _lst(db, site_id, day, surround, usable=True):
    db.add(LstObservation(site_id=uuid.UUID(site_id), scene_id="CONSTRUCTED", platform="landsat-9", acquired_on=day,
                          site_c=surround - 3, surround_c=surround, site_pixels=40, surround_pixels=200,
                          valid_share=1.0, usable=usable))


def test_ac_20_2_signal_reasons_show_heat_and_sites_without_heat_are_marked(manager, db):
    day = date.today() - timedelta(days=10)
    sites = [_site(manager, f"Rank Park {i}", 46.60 + i * 0.01) for i in range(4)]
    for i, s in enumerate(sites[:3]):
        _lst(db, s["id"], day, 40.0 + 2 * i)  # 40, 42, 44 °C
    db.commit()
    decline = [("2026-05-05", 0.20), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]
    for s in (sites[2], sites[3]):
        add_observations(db, uuid.UUID(s["id"]), history(0.35, 0.03, 0.01, [2025]) + latest(decline))
    analyse_sites(db)
    sigs = {str(x.site_id): x for x in db.query(Signal).all()}
    hot = sigs[sites[2]["id"]].priority_factors
    assert hot["heat"] == pytest.approx(10 * (2.5 / 3), abs=0.05) and hot["heat_sites_compared"] == 3
    assert sigs[sites[3]["id"]].priority_factors["heat"] is None  # no heat data: marked, scored without it
    queue = manager.get("/api/signals").json()
    assert {q["site_name"]: q["priority_factors"]["heat"] is None for q in queue} == {
        "Rank Park 2": False, "Rank Park 3": True}


def test_heat_ignored_when_too_old_or_too_few_sites(manager, db):
    s = [_site(manager, f"Old Park {i}", 46.60 + i * 0.01) for i in range(3)]
    old = date.today() - timedelta(days=get_settings().heat_max_age_days + 5)
    for i, x in enumerate(s):
        _lst(db, x["id"], old, 40.0 + i)
    _lst(db, s[0]["id"], date.today() - timedelta(days=3), 41.0)  # newer, but only one site on that date
    db.commit()
    assert heat_context(db) == {}


def test_rescore_after_heat_run(manager, db):
    sites = [_site(manager, f"Rescore Park {i}", 46.60 + i * 0.01) for i in range(3)]
    decline = [("2026-05-05", 0.20), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]
    add_observations(db, uuid.UUID(sites[0]["id"]), history(0.35, 0.03, 0.01, [2025]) + latest(decline))
    analyse_sites(db)
    sig = db.query(Signal).one()
    assert sig.priority_factors["heat"] is None
    for i, s in enumerate(sites):
        _lst(db, s["id"], date.today() - timedelta(days=5), 50.0 - i)  # site 0 hottest
    run = ProcessingRun(kind=RunKind.landsat_lst, status=RunStatus.succeeded, items_written=3, params={})
    db.add(run)
    db.commit()
    analyse_after_run(db, run, None)
    db.refresh(sig)
    assert sig.priority_factors["heat"] == pytest.approx(10 * (2.5 / 3), abs=0.05)
    assert any("re-scored" in m for m in run.messages)
