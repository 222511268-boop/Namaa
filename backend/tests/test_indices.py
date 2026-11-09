"""Vegetation index calculation (AC-07.2, AC-07.3): pure unit tests."""

import numpy as np
import pytest

from app.services.satellite import compute_site_stats, reflectance_offset


def arrays(b04=1500, b08=3500, b11=2500, scl=4, shape=(4, 4)):
    return (
        np.full(shape, b04, np.uint16),
        np.full(shape, b08, np.uint16),
        np.full(shape, b11, np.uint16),
        np.full(shape, scl, np.uint8),
    )


@pytest.mark.parametrize(
    "baseline, offset", [("05.11", -1000), ("04.00", -1000), ("03.01", 0), ("02.14", 0), ("", -1000)]
)
def test_reflectance_offset_by_processing_baseline(baseline, offset):
    assert reflectance_offset(baseline) == offset


def test_ndvi_ndmi_with_offset_match_hand_calculation():
    b04, b08, b11, scl = arrays()
    s = compute_site_stats(b04, b08, b11, scl, np.ones((4, 4), bool), offset=-1000)
    # red 0.05, nir 0.25, swir 0.15
    assert s.ndvi_mean == pytest.approx((0.25 - 0.05) / (0.25 + 0.05))
    assert s.ndmi_mean == pytest.approx((0.25 - 0.15) / (0.25 + 0.15))
    assert s.ndvi_std == pytest.approx(0.0) and s.valid_pixels == 16 and s.valid_share == 1.0


def test_offset_changes_result_so_it_must_be_applied():
    b04, b08, b11, scl = arrays()
    with_offset = compute_site_stats(b04, b08, b11, scl, np.ones((4, 4), bool), offset=-1000).ndvi_mean
    without = compute_site_stats(b04, b08, b11, scl, np.ones((4, 4), bool), offset=0).ndvi_mean
    assert with_offset == pytest.approx(0.6667, abs=1e-4) and without == pytest.approx(0.4, abs=1e-4)


@pytest.mark.parametrize("bad_class", [0, 1, 2, 3, 8, 9, 10, 11])
def test_invalid_scene_classes_are_masked(bad_class):
    b04, b08, b11, scl = arrays()
    scl[:2, :] = bad_class
    s = compute_site_stats(b04, b08, b11, scl, np.ones((4, 4), bool), offset=-1000)
    assert s.valid_pixels == 8 and s.total_pixels == 16 and s.valid_share == 0.5


@pytest.mark.parametrize("good_class", [4, 5, 6, 7])
def test_valid_scene_classes_kept(good_class):
    s = compute_site_stats(*arrays(scl=good_class), np.ones((4, 4), bool), offset=-1000)
    assert s.valid_pixels == 16


def test_only_pixels_inside_polygon_count():
    inside = np.zeros((4, 4), bool)
    inside[1:3, 1:3] = True
    b04, b08, b11, scl = arrays()
    b04[0, 0] = 9000  # outside the polygon: must not affect the mean
    s = compute_site_stats(b04, b08, b11, scl, inside, offset=-1000)
    assert s.total_pixels == 4 and s.valid_pixels == 4 and s.ndvi_mean == pytest.approx(2 / 3)


def test_nodata_pixels_excluded():
    b04, b08, b11, scl = arrays()
    b08[0, :] = 0
    s = compute_site_stats(b04, b08, b11, scl, np.ones((4, 4), bool), offset=-1000)
    assert s.valid_pixels == 12


def test_all_masked_returns_none_values():
    s = compute_site_stats(*arrays(scl=9), np.ones((4, 4), bool), offset=-1000)
    assert s.ndvi_mean is None and s.valid_pixels == 0 and s.valid_share == 0.0
    assert not s.usable(0.7, 10)


@pytest.mark.parametrize("valid, total, usable", [(10, 14, True), (10, 15, False), (9, 9, False), (70, 100, True)])
def test_usability_threshold(valid, total, usable):
    from app.services.satellite import SiteStats

    assert SiteStats(0.5, 0, 0.1, 0, valid, total).usable(0.70, 10) is usable


def test_mean_of_mixed_pixels():
    b04, b08, b11, scl = arrays()
    b08[:, :2] = 5500  # nir 0.45 on half of the pixels
    s = compute_site_stats(b04, b08, b11, scl, np.ones((4, 4), bool), offset=-1000)
    expected = np.mean([0.4 / 0.5, 0.2 / 0.3])
    assert s.ndvi_mean == pytest.approx(expected)
