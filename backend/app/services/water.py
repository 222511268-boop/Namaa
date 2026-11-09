"""Water-demand estimates and irrigation schedule comparison (US17-US18).

Landscape coefficient method:  demand (litres/day) = ET0 (mm/day) x plant factor x irrigated area (m2),
because 1 mm of water over 1 m2 is 1 litre. Rainfall is not deducted (it is negligible in most Riyadh months and
is shown separately). Plant factors come from guidance outside Saudi Arabia and are adjustable assumptions.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.localtime import local_today
from app.models import (
    IrrigationSchedule,
    PlantFactor,
    PlantingCategory,
    ProcessingRun,
    RunKind,
    RunStatus,
    Site,
    WeatherDaily,
    current_boundary,
)
from app.services.weather import ATTRIBUTION

FORMULA = "Demand (litres/day) = ET0 (mm/day) × plant factor × irrigated area (m²)"
DEFAULT_PERIOD_DAYS = 30
# Upper bound for a schedule's daily volume: 100 mm of water over the irrigated area on one watering day.
MAX_MM_PER_WATERING_DAY = 100

# Starting values, as seeded by migration 0003 (WUCOLS IV); managers can adjust them.
DEFAULT_PLANT_FACTORS = {
    PlantingCategory.turf: 0.6,
    PlantingCategory.shrubs: 0.5,
    PlantingCategory.trees: 0.5,
    PlantingCategory.native: 0.2,
    PlantingCategory.mixed: 0.5,
    PlantingCategory.unknown: 0.5,
}
DEFAULT_NOTE = "WUCOLS IV landscape coefficient guidance. Guidance from outside KSA; adjustable assumption."


class ScheduleError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


def daily_demand_l(et0_mm: float, plant_factor: float, area_m2: float) -> float:
    return et0_mm * plant_factor * area_m2


def irrigated_area(site: Site) -> tuple[float, str]:
    if site.irrigated_area_m2:
        return site.irrigated_area_m2, "user-entered"
    return site.area_m2, "whole site area (no irrigated area entered)"


def scheduled_litres(schedules: list[IrrigationSchedule], day: date) -> float | None:
    """Volume the schedules apply on a day; None when no schedule covers the day."""
    covering = [s for s in schedules if s.start_date <= day and (s.end_date is None or day <= s.end_date)]
    if not covering:
        return None
    return sum(s.litres_per_day for s in covering if day.isoweekday() in s.weekdays)


@dataclass
class Period:
    start: date
    end: date


def default_period(db: Session, site_id) -> Period:
    last = db.scalar(
        select(func.max(WeatherDaily.day)).where(WeatherDaily.site_id == site_id, current_boundary(WeatherDaily))
    )
    end = last or local_today() - timedelta(days=1)
    return Period(end - timedelta(days=DEFAULT_PERIOD_DAYS - 1), end)


def latest_weather_run(db: Session) -> ProcessingRun | None:
    return db.scalar(
        select(ProcessingRun)
        .where(ProcessingRun.kind == RunKind.weather, ProcessingRun.status.in_((RunStatus.succeeded, RunStatus.failed)))
        .order_by(ProcessingRun.created_at.desc())
    )


def site_water(db: Session, site: Site, start: date | None = None, end: date | None = None) -> dict:
    """Estimated demand for each day of the period, and the schedule comparison when a schedule exists."""
    period = default_period(db, site.id)
    if end is not None and start is None:
        period.start = end - timedelta(days=DEFAULT_PERIOD_DAYS - 1)
    if start is not None:
        period.start = start
    if end is not None:
        period.end = end
    if period.end < period.start or (period.end - period.start).days > 366:
        raise ValueError("Choose a valid period of at most one year.")
    factor = db.get(PlantFactor, site.planting_category)
    kp = factor.factor if factor else DEFAULT_PLANT_FACTORS[site.planting_category]
    area, area_source = irrigated_area(site)
    weather = list(
        db.scalars(
            select(WeatherDaily)
            .where(
                WeatherDaily.site_id == site.id,
                current_boundary(WeatherDaily),
                WeatherDaily.day >= period.start,
                WeatherDaily.day <= period.end,
            )
            .order_by(WeatherDaily.day)
        )
    )
    schedules = list(
        db.scalars(
            select(IrrigationSchedule)
            .where(IrrigationSchedule.site_id == site.id)
            .order_by(IrrigationSchedule.start_date)
        )
    )
    daily = []
    demand_total = et0_total = precip_total = 0.0
    scheduled_total = 0.0
    scheduled_days = 0
    for w in weather:
        demand = daily_demand_l(w.et0_mm, kp, area) if w.et0_mm is not None else None
        planned = scheduled_litres(schedules, w.day)
        daily.append(
            {
                "day": w.day,
                "et0_mm": w.et0_mm,
                "tmax_c": w.tmax_c,
                "precip_mm": w.precip_mm,
                "demand_l": round(demand) if demand is not None else None,
                "scheduled_l": round(planned) if planned is not None else None,
            }
        )
        if demand is not None:
            demand_total += demand
            et0_total += w.et0_mm
            precip_total += w.precip_mm or 0.0
            if planned is not None:
                scheduled_total += planned
                scheduled_days += 1

    comparison = None
    if schedules:
        # Compare only over days that have both an estimate and a schedule.
        demand_on_scheduled = sum(
            d["demand_l"] for d in daily if d["scheduled_l"] is not None and d["demand_l"] is not None
        )
        diff = scheduled_total - demand_on_scheduled
        comparison = {
            "days_compared": scheduled_days,
            "scheduled_m3": round(scheduled_total / 1000, 1),
            "demand_m3": round(demand_on_scheduled / 1000, 1),
            "difference_m3": round(diff / 1000, 1),
            "difference_pct": round(100 * diff / demand_on_scheduled, 1) if demand_on_scheduled else None,
            "label": "Schedule values are user-entered.",
        }

    latest = db.scalar(
        select(func.max(WeatherDaily.day)).where(WeatherDaily.site_id == site.id, current_boundary(WeatherDaily))
    )
    fetched = db.scalar(
        select(func.max(WeatherDaily.fetched_at)).where(WeatherDaily.site_id == site.id, current_boundary(WeatherDaily))
    )
    run = latest_weather_run(db)
    notice = None
    if run is not None and run.status == RunStatus.failed:
        notice = "The weather service could not be reached on the last update" + (
            f"; showing stored values up to {latest.isoformat()}." if latest else "; no weather values are stored yet."
        )
    elif latest is None:
        notice = "No weather values are stored yet for this site. They are fetched automatically once a day."
    days_with_data = sum(1 for d in daily if d["demand_l"] is not None)
    if not days_with_data:
        missing = (
            "No reference evapotranspiration (ET0) is stored for the selected period; a demand estimate is unavailable."
        )
        notice = f"{notice} {missing}" if notice else missing
    c = to_shape(site.geom).representative_point()
    return {
        "label": "Estimate",
        "formula": FORMULA,
        "inputs": {
            "plant_category": site.planting_category.value,
            "plant_factor": kp,
            "plant_factor_note": factor.source_note if factor else "Default assumption.",
            "irrigated_area_m2": round(area, 1),
            "irrigated_area_source": area_source,
            "location": [round(c.x, 4), round(c.y, 4)],
            "rainfall": "Not deducted; shown for reference.",
        },
        "source": ATTRIBUTION,
        "period": {
            "start": period.start,
            "end": period.end,
            "days": (period.end - period.start).days + 1,
            "days_with_data": days_with_data,
        },
        "totals": {
            "demand_m3": round(demand_total / 1000, 1),
            "et0_mm": round(et0_total, 1),
            "precip_mm": round(precip_total, 1),
            "mean_daily_demand_m3": round(demand_total / 1000 / days_with_data, 2) if days_with_data else None,
        },
        "daily": daily,
        "has_schedule": bool(schedules),
        "comparison": comparison,
        "latest_weather_on": latest,
        "weather_fetched_at": fetched,
        "notice": notice,
    }


# ---------------------------------------------------------------- schedules


def validate_schedule(db: Session, site: Site, data: dict, schedule_id=None) -> None:
    start, end = data["start_date"], data.get("end_date")
    if end is not None and end < start:
        raise ScheduleError("The end date must be on or after the start date.", "end_date")
    weekdays = data["weekdays"]
    if not weekdays:
        raise ScheduleError("Choose at least one watering day.", "weekdays")
    if len(set(weekdays)) != len(weekdays) or any(d < 1 or d > 7 for d in weekdays):
        raise ScheduleError("Watering days must be distinct days of the week.", "weekdays")
    area, _ = irrigated_area(site)
    limit = area * MAX_MM_PER_WATERING_DAY
    if data["litres_per_day"] > limit:
        raise ScheduleError(
            f"That is more than {MAX_MM_PER_WATERING_DAY} mm over the irrigated area ({round(limit):,} litres). "
            "Check the volume and the unit (litres per watering day).",
            "litres_per_day",
        )
    for other in db.scalars(select(IrrigationSchedule).where(IrrigationSchedule.site_id == site.id)):
        if other.id == schedule_id:
            continue
        o_end = other.end_date or date.max
        n_end = end or date.max
        if start <= o_end and other.start_date <= n_end:
            raise ScheduleError(
                f"This period overlaps the schedule starting {other.start_date.isoformat()}. "
                "End that schedule first or choose other dates.",
                "start_date",
            )
