"""US07 Process satellite observations: AC-07.1 to AC-07.6, using constructed GeoTIFF scenes."""

from datetime import date, datetime, timedelta

import pytest
from shapely.geometry import box, shape

from app.models import Observation, Role, RunStatus
from app.services.processing import claim_next_run, execute_run, requeue_interrupted_runs
from tests.conftest import square
from tests.satellite_fakes import FakeSource, SceneValues, reference_stats, write_scene

SITE = square(46.705, 24.705, 0.001)


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


@pytest.fixture
def site(manager):
    r = manager.post(
        "/api/sites", json={"name": "Pipeline Park", "site_type": "park", "planting_category": "turf", "geometry": SITE}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _queue(manager, **extra):
    r = manager.post("/api/processing-runs", json={"start_date": "2025-06-01", "end_date": "2025-06-30", **extra})
    assert r.status_code == 202, r.text
    return r.json()


def _run(db, source):
    run = claim_next_run(db)
    assert run is not None
    return execute_run(db, run, source)


def test_ac_07_1_run_is_queued_then_processed_with_visible_status(manager, site, db, tmp_path):
    queued = _queue(manager)
    assert queued["status"] == "queued" and queued["requested_by_name"] == "Test Manager"
    claimed = claim_next_run(db)
    assert claimed.status == RunStatus.running and claim_next_run(db) is None  # not claimed twice
    execute_run(db, claimed, FakeSource([write_scene(tmp_path, "S2B_TEST_1")]))
    done = manager.get(f"/api/processing-runs/{queued['id']}").json()
    assert done["status"] == "succeeded" and done["scenes_found"] == 1 and done["items_written"] == 1
    assert done["started_at"] and done["finished_at"]


def test_ac_07_2_values_match_independent_reference(manager, site, db, tmp_path):
    v = SceneValues(b04=1320, b08=3010, b11=2440)
    scene = write_scene(tmp_path, "S2B_REF", v=v)
    _queue(manager)
    _run(db, FakeSource([scene]))
    obs = db.query(Observation).one()
    ref = reference_stats(scene, shape(SITE), v, offset=-1000)
    assert obs.total_pixels == ref["inside"] and obs.valid_pixels == ref["valid"]
    assert obs.ndvi_mean == pytest.approx(ref["ndvi"], abs=1e-9)
    assert obs.ndmi_mean == pytest.approx(ref["ndmi"], abs=1e-9)
    assert obs.scene_id == "S2B_REF" and obs.processing_baseline == "05.11" and obs.usable
    assert obs.acquired_on == date(2025, 6, 1)


def test_ac_07_2_old_baseline_uses_no_offset(manager, site, db, tmp_path):
    v = SceneValues()
    scene = write_scene(tmp_path, "S2A_OLD", v=v, baseline="02.14")
    _queue(manager)
    _run(db, FakeSource([scene]))
    assert db.query(Observation).one().ndvi_mean == pytest.approx(reference_stats(scene, shape(SITE), v, 0)["ndvi"])


def test_ac_07_3_cloudy_observation_stored_as_unusable(manager, site, db, tmp_path):
    v = SceneValues(cloud_rows=106)  # cloud covers roughly the northern half of the site
    scene = write_scene(tmp_path, "S2B_CLOUD", v=v)
    _queue(manager)
    _run(db, FakeSource([scene]))
    obs = db.query(Observation).one()
    ref = reference_stats(scene, shape(SITE), v, -1000)
    assert obs.valid_pixels == ref["valid"] and 0 < obs.valid_share < 0.7
    assert obs.usable is False
    history = manager.get(f"/api/sites/{site['id']}/observations").json()
    assert history["usable_count"] == 0 and history["unusable_count"] == 1 and history["latest_usable_on"] is None


def test_ac_07_4_rerun_creates_no_duplicates(manager, site, db, tmp_path):
    scenes = [write_scene(tmp_path, f"S2B_{d}", when=datetime(2025, 6, d, 7, 26)) for d in (1, 6, 11)]
    _queue(manager)
    first = _run(db, FakeSource(scenes))
    _queue(manager)
    second = _run(db, FakeSource(scenes))
    assert first.items_written == 3 and second.items_written == 0 and second.items_skipped == 3
    assert db.query(Observation).count() == 3


def test_overlapping_tiles_same_day_keep_better_observation(manager, site, db, tmp_path):
    cloudy = write_scene(tmp_path / "a", "S2B_T38RPN", v=SceneValues(cloud_rows=106))
    clear = write_scene(tmp_path / "b", "S2B_T38RQN")
    _queue(manager)
    _run(db, FakeSource([cloudy, clear]))
    obs = db.query(Observation).one()
    assert obs.scene_id == "S2B_T38RQN" and obs.usable


@pytest.mark.parametrize("later_failure", [False, True])
def test_saved_measurements_are_replaced_only_after_complete_success(manager, site, db, tmp_path, later_failure):
    old = write_scene(tmp_path / "old", "S2_SAVED", v=SceneValues(cloud_rows=106))
    _queue(manager)
    _run(db, FakeSource([old]))
    saved = db.query(Observation).one()
    before = {column.name: getattr(saved, column.name) for column in Observation.__table__.columns}

    better = write_scene(tmp_path / "better", "S2_BETTER", v=SceneValues(b04=2000, b08=6000))
    poorer = write_scene(tmp_path / "poorer", "S2_POORER", v=SceneValues(cloud_rows=100))
    new = write_scene(tmp_path / "new", "S2_NEW", when=datetime(2025, 6, 6))
    scenes = [better, poorer, new]
    if later_failure:
        broken = write_scene(tmp_path / "broken", "S2_BROKEN", when=datetime(2025, 6, 11))
        broken.hrefs["B08"] = str(tmp_path / "missing.tif")
        scenes.append(broken)
    _queue(manager)
    result = _run(db, FakeSource(scenes))
    db.expire_all()
    saved = db.get(Observation, before["id"])
    assert db.query(Observation).count() == 2  # New completed dates survive a later scene failure.
    if later_failure:
        assert result.status == RunStatus.failed and result.items_written == 1
        assert {column.name: getattr(saved, column.name) for column in Observation.__table__.columns} == before
        _queue(manager)
        result = _run(db, FakeSource([better, poorer, new]))
        assert result.status == RunStatus.succeeded and result.items_written == 1
    else:
        assert result.status == RunStatus.succeeded and result.items_written == 2
    db.expire_all()
    assert db.get(Observation, before["id"]).scene_id == better.id
    _queue(manager)
    repeated = _run(db, FakeSource([better, poorer, new]))
    assert repeated.status == RunStatus.succeeded and repeated.items_written == 0
    assert db.query(Observation).count() == 2


def test_ac_07_5_catalogue_outage_fails_run_and_keeps_existing_data(manager, site, db, tmp_path):
    _queue(manager)
    _run(db, FakeSource([write_scene(tmp_path, "S2B_GOOD")]))
    before = [(o.id, o.ndvi_mean, o.scene_id) for o in db.query(Observation).all()]
    q = _queue(manager)
    _run(db, FakeSource([], fail_search=True))
    run = manager.get(f"/api/processing-runs/{q['id']}").json()
    assert run["status"] == "failed" and "simulated outage" in run["error"]
    db.expire_all()
    assert [(o.id, o.ndvi_mean, o.scene_id) for o in db.query(Observation).all()] == before


def test_ac_07_5_unreadable_asset_fails_run_but_keeps_completed_scenes(manager, site, db, tmp_path):
    _queue(manager)
    _run(db, FakeSource([write_scene(tmp_path, "S2B_EARLIER", when=datetime(2025, 5, 1))]))
    earlier = db.query(Observation).one()
    earlier_values = (earlier.id, earlier.ndvi_mean)

    good = write_scene(tmp_path, "S2B_JUNE01", when=datetime(2025, 6, 1))
    broken = write_scene(tmp_path, "S2B_JUNE06", when=datetime(2025, 6, 6))
    broken.hrefs["B08"] = str(tmp_path / "missing.tif")
    q = _queue(manager)
    _run(db, FakeSource([good, broken]))
    run = manager.get(f"/api/processing-runs/{q['id']}").json()
    assert run["status"] == "failed" and "1 of 2 scenes" in run["error"]
    assert any("S2B_JUNE06" in m for m in run["messages"])
    db.expire_all()
    days = {o.acquired_on for o in db.query(Observation).all()}
    assert days == {date(2025, 5, 1), date(2025, 6, 1)}
    kept = db.get(Observation, earlier_values[0])
    assert (kept.id, kept.ndvi_mean) == earlier_values


def test_ac_07_6_inactive_sites_and_sites_outside_footprint_skipped(manager, site, db, tmp_path):
    other = manager.post(
        "/api/sites",
        json={"name": "Inactive", "site_type": "park", "planting_category": "turf", "geometry": square(46.708, 24.708)},
    ).json()
    manager.patch(f"/api/sites/{other['id']}/status", json={"status": "inactive"})
    partial_footprint = box(46.7055, 24.69, 46.73, 24.72)  # cuts through Pipeline Park
    scenes = [
        write_scene(tmp_path / "full", "S2B_FULL"),
        write_scene(tmp_path / "part", "S2B_PART", when=datetime(2025, 6, 6), footprint=partial_footprint),
    ]
    _queue(manager)
    _run(db, FakeSource(scenes))
    obs = db.query(Observation).all()
    assert [(o.scene_id, str(o.site_id)) for o in obs] == [("S2B_FULL", site["id"])]


def test_run_restricted_to_selected_sites(manager, site, db, tmp_path):
    other = manager.post(
        "/api/sites",
        json={"name": "Other", "site_type": "park", "planting_category": "turf", "geometry": square(46.708, 24.708)},
    ).json()
    _queue(manager, site_ids=[other["id"]])
    _run(db, FakeSource([write_scene(tmp_path, "S2B_SEL")]))
    assert {str(o.site_id) for o in db.query(Observation).all()} == {other["id"]}


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"start_date": "2025-06-30", "end_date": "2025-06-01"}, "on or after"),
        ({"start_date": "2025-06-01", "end_date": (date.today() + timedelta(days=2)).isoformat()}, "future"),
        ({"start_date": "2020-01-01", "end_date": "2025-01-01"}, "three years"),
        (
            {
                "start_date": "2025-06-01",
                "end_date": "2025-06-30",
                "site_ids": ["00000000-0000-0000-0000-000000000000"],
            },
            "do not exist",
        ),
    ],
)
def test_run_request_validation(manager, site, payload, message):
    r = manager.post("/api/processing-runs", json=payload)
    assert r.status_code == 422 and message in str(r.json())


def test_run_rejected_when_no_active_sites(manager):
    r = manager.post("/api/processing-runs", json={"start_date": "2025-06-01", "end_date": "2025-06-30"})
    assert r.status_code == 422 and "no active sites" in str(r.json())


def test_condition_history_and_attribution(manager, site, db, tmp_path):
    scenes = [write_scene(tmp_path / str(d), f"S2B_{d}", when=datetime(2024 + d % 2, 6, d, 7)) for d in (1, 2)]
    _queue(manager, start_date="2024-06-01")
    _run(db, FakeSource(scenes))
    h = manager.get(f"/api/sites/{site['id']}/observations").json()
    assert h["usable_count"] == 2 and h["attribution"] == "Contains modified Copernicus Sentinel data 2024–2025"
    assert [o["acquired_on"] for o in h["observations"]] == sorted(o["acquired_on"] for o in h["observations"])
    assert h["thresholds"] == {"min_valid_share": 0.7, "min_valid_pixels": 10}
    listed = manager.get("/api/sites").json()[0]
    assert listed["latest"]["acquired_on"] == h["latest_usable_on"]


def test_interrupted_run_is_requeued_and_completes(manager, site, db, tmp_path):
    q = _queue(manager)
    stale = claim_next_run(db)  # worker took the run, then stopped before finishing
    stale.scenes_found, stale.scenes_processed, stale.items_written = 5, 3, 7  # partial progress
    db.commit()
    assert manager.get(f"/api/processing-runs/{q['id']}").json()["status"] == "running"
    assert requeue_interrupted_runs(db) == 1
    run = _run(db, FakeSource([write_scene(tmp_path, "S2B_RESUMED")]))
    assert run.status == RunStatus.succeeded
    assert any("interrupted" in m for m in run.messages)
    assert (run.scenes_found, run.scenes_processed, run.items_written) == (1, 1, 1)  # counters describe this attempt


def test_rerun_skips_already_stored_scene_without_reading(manager, site, db, tmp_path):
    scene = write_scene(tmp_path, "S2B_ONCE")
    _queue(manager)
    _run(db, FakeSource([scene]))
    scene.hrefs = {k: str(tmp_path / "deleted.tif") for k in scene.hrefs}  # would fail if it were read again
    _queue(manager)
    again = _run(db, FakeSource([scene]))
    assert again.status == RunStatus.succeeded and again.items_skipped == 1 and again.items_written == 0
