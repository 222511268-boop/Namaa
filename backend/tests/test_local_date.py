"""User-facing date checks use the pilot's local date (Asia/Riyadh), not the server's UTC date.

Regression: between local midnight and 03:00 in Riyadh the UTC date is still the previous day. A visit dated
"today" in the browser was rejected as being in the future, so inspectors could not complete tasks.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app import localtime
from app.models import Role
from tests.test_tasks import manager, site, task  # noqa: F401  (pytest fixtures)

# 02:30 on 9 November in Riyadh is 23:30 on 8 November in UTC.
RIYADH_NIGHT = datetime(2026, 11, 9, 2, 30, tzinfo=ZoneInfo("Asia/Riyadh"))


@pytest.fixture
def riyadh_night(monkeypatch):
    assert RIYADH_NIGHT.astimezone(UTC).date() == date(2026, 11, 8)
    monkeypatch.setattr(localtime, "now_local", lambda: RIYADH_NIGHT)


def test_local_today_follows_the_configured_time_zone():
    assert localtime.local_today() == datetime.now(ZoneInfo("Asia/Riyadh")).date()


def test_visit_dated_local_today_is_accepted_after_local_midnight(task, as_role, riyadh_night):  # noqa: F811
    insp = as_role(Role.inspector)
    body = {"condition": "stressed", "notes": "Dry patches."}
    ok = insp.put(f"/api/tasks/{task['id']}/findings", json=body | {"visit_date": "2026-11-09"})
    assert ok.status_code == 200, ok.text
    future = insp.put(f"/api/tasks/{task['id']}/findings", json=body | {"visit_date": "2026-11-10"})
    assert future.status_code == 422 and "future" in future.text


def test_due_date_and_overdue_use_local_date(task, manager, db, riyadh_night):  # noqa: F811
    # "Today" in Riyadh is a valid due date; the UTC date (one day earlier) is in the past locally.
    assert manager.patch(f"/api/tasks/{task['id']}", json={"due_date": "2026-11-09"}).status_code == 200
    assert manager.get(f"/api/tasks/{task['id']}").json()["overdue"] is False
    r = manager.patch(f"/api/tasks/{task['id']}", json={"due_date": "2026-11-08"})
    assert r.status_code == 422 and "past" in r.text


def test_overview_default_period_ends_on_local_today(as_role, riyadh_night):
    ov = as_role(Role.manager).get("/api/overview").json()
    assert ov["filters"]["end"] == "2026-11-09"
    assert ov["filters"]["start"] == (date(2026, 11, 9) - timedelta(days=89)).isoformat()
