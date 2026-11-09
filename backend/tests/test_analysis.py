"""US09 baselines, US10 detection rule, US11 priority: unit tests on constructed data."""

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from app.models import SiteType
from app.services.analysis import Obs, compute_baselines, detect, evaluate, priority
from tests.analysis_helpers import case_series, history

CASES = json.loads((Path(__file__).parent / "fixtures" / "detection_reference_cases.json").read_text(encoding="utf-8"))


def obs(day: str, v: float) -> Obs:
    return Obs(day, date.fromisoformat(day), v)


def test_ac_09_1_baseline_matches_hand_calculation():
    # March window = Feb, Mar, Apr of earlier years; one value outside the window must be ignored.
    values = [0.30, 0.32, 0.34, 0.36, 0.38, 0.40, 0.42, 0.44, 0.90]
    days = [
        "2025-02-03",
        "2025-02-20",
        "2025-03-01",
        "2025-03-15",
        "2025-03-28",
        "2025-04-02",
        "2025-04-18",
        "2024-03-10",
        "2025-06-01",
    ]
    series = [obs(d, v) for d, v in zip(days, values, strict=True)]
    b = compute_baselines(series, 2026, min_obs=8, min_sd=0.02)[3]
    window = np.array(values[:8])
    med = float(np.median(window))
    mad = float(np.median(np.abs(window - med)))
    assert b.available and b.n_obs == 8 and b.years == (2024, 2025)
    assert b.median == pytest.approx(med) and b.robust_sd == pytest.approx(1.4826 * mad)


def test_ac_09_1_window_wraps_around_the_year():
    series = [obs(f"2025-12-{d:02d}", 0.3) for d in range(1, 31, 5)] + [obs(f"2025-02-{d:02d}", 0.3) for d in (3, 9)]
    b = compute_baselines(series, 2026, min_obs=8, min_sd=0.02)
    assert b[1].n_obs == 8 and b[1].available  # December + February feed January


def test_ac_09_1_only_earlier_years_are_used():
    series = [obs(f"2026-03-{d:02d}", 0.3) for d in range(1, 29, 2)]
    assert not compute_baselines(series, 2026, 8, 0.02)[3].available


def test_ac_09_3_insufficient_history_marked_unavailable():
    series = [obs(f"2025-03-{d:02d}", 0.3) for d in range(1, 8)]  # 7 observations
    b = compute_baselines(series, 2026, min_obs=8, min_sd=0.02)[3]
    assert not b.available and b.n_obs == 7 and b.median is None
    assert evaluate(obs("2026-03-10", 0.1), b).z is None


def test_robust_sd_floor_applies_to_perfectly_stable_sites():
    series = [obs(f"2025-03-{d:02d}", 0.4) for d in range(1, 21)]
    assert compute_baselines(series, 2026, 8, 0.02)[3].robust_sd == 0.02


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_ac_10_5_reference_cases(case):
    series = case_series(case)
    baselines = compute_baselines(series, 2026, min_obs=8, min_sd=0.02)
    result = detect(series, baselines, k=3, z_threshold=-2.0, min_drop=0.05)
    assert result.triggered is case["expected"], f"{case['name']}: {case['why']} -> {result.reason}"


def test_ac_10_1_rule_needs_all_three_conditions():
    series = history(0.35, 0.0, 0.01, [2025])
    b = compute_baselines(series, 2026, 8, 0.02)
    sd, med = b[5].robust_sd, b[5].median
    just_meets = med + min(-2.0 * sd, -0.05) - 0.001  # both conditions: the stricter threshold
    hit = series + [obs("2026-05-01", just_meets), obs("2026-05-06", just_meets), obs("2026-05-11", just_meets)]
    miss = series + [obs("2026-05-01", just_meets), obs("2026-05-06", just_meets), obs("2026-05-11", med)]
    assert detect(hit, b, 3, -2.0, 0.05).triggered
    assert not detect(miss, b, 3, -2.0, 0.05).triggered


def test_ac_11_1_priority_matches_hand_calculation():
    score, f = priority(
        mean_z=-3.0, first=date(2026, 5, 1), last=date(2026, 5, 16), area_m2=50_000, site_type=SiteType.park
    )
    severity = 50 * min(3 / 4, 1)  # 37.5
    persistence = 20 * min(15 / 30, 1)  # 10
    size = 20 * min(max(math.log10(50_000 / 5000) / math.log10(50), 0), 1)  # ~11.77
    site_type = 10 * 1.0
    expected = {"severity": severity, "persistence": persistence, "size": round(size, 1), "site_type": site_type}
    # Sprint 3 (US20): without heat data the score is unchanged and the factors mark heat as unavailable.
    assert f == expected | {"heat": None}
    assert score == pytest.approx(round(sum(expected.values()), 1))


@pytest.mark.parametrize(
    "area, kind, expected_size, expected_type",
    [
        (5000, SiteType.median, 0.0, 5.0),
        (250_000, SiteType.plaza, 20.0, 7.0),
        (10_000_000, SiteType.garden, 20.0, 10.0),
    ],
)
def test_priority_bounds(area, kind, expected_size, expected_type):
    _, f = priority(-10, date(2026, 1, 1), date(2026, 6, 1), area, kind)
    assert f["severity"] == 50.0 and f["persistence"] == 20.0
    assert f["size"] == expected_size and f["site_type"] == expected_type


def test_persistence_measures_the_whole_below_range_run():
    series = history(0.35, 0.0, 0.01, [2025])
    series += [obs(f"2026-04-{d:02d}", 0.35) for d in (1, 6, 11)]  # normal
    series += [obs(f"2026-04-{d:02d}", 0.18) for d in (16, 21, 26)] + [
        obs(f"2026-05-{d:02d}", 0.18) for d in (1, 6, 11)
    ]
    det = detect(series, compute_baselines(series, 2026, 8, 0.02), 3, -2.0, 0.05)
    assert det.triggered and det.run_length == 6 and det.run_start == date(2026, 4, 16)
    assert [e.obs.day for e in det.window] == [date(2026, 5, 1), date(2026, 5, 6), date(2026, 5, 11)]


def test_run_does_not_extend_into_the_baseline_years():
    series = history(0.35, 0.0, 0.01, [2025]) + [obs(f"2026-01-{d:02d}", 0.10) for d in (5, 10, 15)]
    det = detect(series, compute_baselines(series, 2026, 8, 0.02), 3, -2.0, 0.05)
    assert det.triggered and det.run_start == date(2026, 1, 5) and det.run_length == 3
