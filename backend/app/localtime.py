"""The pilot area's calendar date.

Users enter and read dates (visit dates, due dates, overdue flags, report periods) in local time, while the
containers run in UTC. Between local midnight and UTC midnight the two dates differ, so user-facing checks use the
date in the configured time zone (Asia/Riyadh by default) rather than the server clock's date.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def now_local() -> datetime:
    return datetime.now(ZoneInfo(get_settings().local_timezone))


def local_today() -> date:
    return now_local().date()
