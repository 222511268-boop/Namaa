"""Sprint 2 boundary cases: values exactly at, and just outside, each documented limit.

Thresholds are probed with numbers that binary floating point represents exactly (0.5, 0.4375, 0.03125 ...),
so an inclusive comparison is tested at the true boundary rather than one rounding step away from it.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import update

from app.config import get_settings
from app.models import PasswordResetToken, Role
from app.services.analysis import Obs, compute_baselines, detect
from tests.test_accounts import link, token_of  # noqa: F401  (pytest fixture and helper)
from tests.test_tasks import jpeg, manager, site, task  # noqa: F401  (pytest fixtures and helper)

STEP = 2**-10  # smallest move used to step just outside a boundary


def stable_history(level: float) -> list[Obs]:
    """Twenty identical May observations in 2025: median = level, robust SD = the configured floor."""
    return [Obs(f"h{d}", date(2025, 5, d), level) for d in range(1, 21)]


def latest_three(value: float) -> list[Obs]:
    return [Obs(f"n{d}", date(2026, 5, d), value) for d in (1, 6, 11)]


def run(value: float, min_sd: float, min_drop: float) -> bool:
    series = stable_history(0.5) + latest_three(value)
    baselines = compute_baselines(series, 2026, min_obs=8, min_sd=min_sd)
    return detect(series, baselines, k=3, z_threshold=-2.0, min_drop=min_drop).triggered


def test_z_exactly_minus_two_triggers_and_just_above_does_not():
    # median 0.5, robust SD 0.03125: 0.4375 gives z = -2.0 exactly (drop 0.0625 also meets 0.05).
    assert run(0.4375, min_sd=0.03125, min_drop=0.05)
    assert not run(0.4375 + STEP, min_sd=0.03125, min_drop=0.05)  # z = -1.96875


def test_drop_exactly_at_minimum_triggers_and_just_smaller_does_not():
    # robust SD 0.015625 keeps z far below -2, so only the drop condition decides.
    assert run(0.4375, min_sd=0.015625, min_drop=0.0625)  # deviation = -0.0625 exactly
    assert not run(0.4375 + STEP, min_sd=0.015625, min_drop=0.0625)  # deviation = -0.0615...


def test_baseline_available_at_eight_observations_not_seven():
    eight = [Obs(f"e{d}", date(2025, 5, d), 0.4) for d in range(1, 9)]
    assert compute_baselines(eight, 2026, min_obs=8, min_sd=0.02)[5].available
    assert not compute_baselines(eight[:7], 2026, min_obs=8, min_sd=0.02)[5].available


def test_sixth_photo_accepted_seventh_rejected(task, as_role):  # noqa: F811
    assert get_settings().max_photos_per_finding == 6
    insp = as_role(Role.inspector)
    for i in range(6):
        r = insp.post(f"/api/tasks/{task['id']}/photos", files={"file": (f"p{i}.jpg", jpeg(), "image/jpeg")})
        assert r.status_code == 201, r.text
    r = insp.post(f"/api/tasks/{task['id']}/photos", files={"file": ("p7.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 422 and "at most 6" in r.json()["detail"][0]["msg"]


def test_photo_at_size_limit_accepted_one_byte_over_rejected(task, as_role, monkeypatch):  # noqa: F811
    assert get_settings().max_photo_bytes == 8 * 1024 * 1024
    data = jpeg()
    insp = as_role(Role.inspector)
    monkeypatch.setattr(get_settings(), "max_photo_bytes", len(data))
    r = insp.post(f"/api/tasks/{task['id']}/photos", files={"file": ("ok.jpg", data, "image/jpeg")})
    assert r.status_code == 201
    monkeypatch.setattr(get_settings(), "max_photo_bytes", len(data) - 1)
    r = insp.post(f"/api/tasks/{task['id']}/photos", files={"file": ("big.jpg", data, "image/jpeg")})
    assert r.status_code == 422 and "larger than" in r.json()["detail"][0]["msg"]


def test_reset_link_valid_one_minute_before_expiry(link, client, db):  # noqa: F811
    db.execute(update(PasswordResetToken).values(expires_at=datetime.now(UTC) + timedelta(minutes=1)))
    db.commit()
    assert client.post("/api/auth/reset-password/check", json={"token": token_of(link["url"])}).status_code == 200


def test_reset_link_lifetime_is_24_hours(link, db):  # noqa: F811
    t = db.query(PasswordResetToken).one()
    hours = (t.expires_at - t.created_at).total_seconds() / 3600
    assert 23.99 < hours < 24.01
