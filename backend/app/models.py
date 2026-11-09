"""Database models.

Sprint 1: accounts, sessions, districts, sites, processing runs, observations.
Sprint 2: baselines, signals and decisions, tasks, findings and photos, password reset tokens.
Sprint 3: plant factors, weather, irrigation schedules, surface temperature, activity record, AI briefs.
"""

import enum
import uuid
from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _enum(cls, name):
    # Store enum values (lower-case strings) rather than member names.
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Role(enum.StrEnum):
    admin = "admin"
    manager = "manager"
    inspector = "inspector"
    viewer = "viewer"


class SiteType(enum.StrEnum):
    park = "park"
    garden = "garden"
    median = "median"
    plaza = "plaza"
    other = "other"


class PlantingCategory(enum.StrEnum):
    turf = "turf"
    shrubs = "shrubs"
    trees = "trees"
    native = "native"
    mixed = "mixed"
    unknown = "unknown"


class SiteStatus(enum.StrEnum):
    active = "active"
    inactive = "inactive"


class SiteSource(enum.StrEnum):
    osm = "osm"
    manual = "manual"


class RunKind(enum.StrEnum):
    sentinel2 = "sentinel2"
    osm_import = "osm_import"
    landsat_lst = "landsat_lst"
    weather = "weather"


class RunStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class SignalStatus(enum.StrEnum):
    open = "open"
    under_inspection = "under_inspection"
    dismissed = "dismissed"
    closed = "closed"


ACTIVE_SIGNAL_STATUSES = (SignalStatus.open, SignalStatus.under_inspection)


class SignalOutcome(enum.StrEnum):
    confirmed = "confirmed"
    not_confirmed = "not_confirmed"
    inconclusive = "inconclusive"


class DecisionType(enum.StrEnum):
    dismiss = "dismiss"
    confirm = "confirm"
    send_for_inspection = "send_for_inspection"
    inspection_cancelled = "inspection_cancelled"
    record_outcome = "record_outcome"
    reopened = "reopened"


class TaskType(enum.StrEnum):
    inspection = "inspection"
    maintenance = "maintenance"


class TaskPriority(enum.StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class TaskStatus(enum.StrEnum):
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class ObservedCondition(enum.StrEnum):
    healthy = "healthy"
    stressed = "stressed"
    damaged = "damaged"
    dead_or_missing = "dead_or_missing"
    not_vegetation = "not_vegetation"  # e.g. construction, paving, or replanting under way


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class District(Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name_en: Mapped[str | None] = mapped_column(String(120))
    name_ar: Mapped[str | None] = mapped_column(String(120))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False)


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("source", "source_ref", name="uq_sites_source_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str | None] = mapped_column(String(120))
    site_type: Mapped[SiteType] = mapped_column(_enum(SiteType, "site_type"))
    planting_category: Mapped[PlantingCategory] = mapped_column(_enum(PlantingCategory, "planting_category"))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"), index=True)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False)
    area_m2: Mapped[float] = mapped_column(Float)
    boundary_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    boundary_history: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    # Irrigated area for water-demand estimates (US17); None means the whole site area.
    irrigated_area_m2: Mapped[float | None] = mapped_column(Float)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[SiteStatus] = mapped_column(_enum(SiteStatus, "site_status"), default=SiteStatus.active)
    source: Mapped[SiteSource] = mapped_column(_enum(SiteSource, "site_source"))
    source_ref: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    district: Mapped[District | None] = relationship()


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[RunKind] = mapped_column(_enum(RunKind, "run_kind"))
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"), default=RunStatus.queued, index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    scenes_found: Mapped[int] = mapped_column(Integer, default=0)
    scenes_processed: Mapped[int] = mapped_column(Integer, default=0)
    items_written: Mapped[int] = mapped_column(Integer, default=0)
    items_skipped: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    messages: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    requester: Mapped[User | None] = relationship()


class Observation(Base):
    """Per-site Sentinel-2 summary for one acquisition date."""

    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("site_id", "acquired_on", "boundary_version", name="uq_observation_site_date"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_runs.id", ondelete="SET NULL"))
    scene_id: Mapped[str] = mapped_column(String(128))
    platform: Mapped[str] = mapped_column(String(32))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acquired_on: Mapped[date] = mapped_column(Date)
    processing_baseline: Mapped[str] = mapped_column(String(8))
    boundary_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    ndvi_mean: Mapped[float | None] = mapped_column(Float)
    ndvi_std: Mapped[float | None] = mapped_column(Float)
    ndmi_mean: Mapped[float | None] = mapped_column(Float)
    ndmi_std: Mapped[float | None] = mapped_column(Float)
    valid_pixels: Mapped[int] = mapped_column(Integer)
    total_pixels: Mapped[int] = mapped_column(Integer)
    valid_share: Mapped[float] = mapped_column(Float)
    usable: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- Sprint 2


class SiteBaseline(Base):
    """Expected NDVI range for one site and calendar month, from the site's earlier years."""

    __tablename__ = "site_baselines"

    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True)
    month: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_year: Mapped[int] = mapped_column(Integer)
    n_obs: Mapped[int] = mapped_column(Integer)
    median_ndvi: Mapped[float | None] = mapped_column(Float)
    robust_sd: Mapped[float | None] = mapped_column(Float)
    p10: Mapped[float | None] = mapped_column(Float)
    p90: Mapped[float | None] = mapped_column(Float)
    years: Mapped[str] = mapped_column(String(64))
    available: Mapped[bool] = mapped_column(Boolean)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Signal(Base):
    """A detected, unusually low vegetation condition that needs a human decision."""

    __tablename__ = "signals"
    __table_args__ = (
        # At most one active (open or under inspection) signal per site.
        Index(
            "uq_signals_one_active_per_site",
            "site_id",
            unique=True,
            postgresql_where=text("status IN ('open', 'under_inspection')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    status: Mapped[SignalStatus] = mapped_column(_enum(SignalStatus, "signal_status"), index=True)
    outcome: Mapped[SignalOutcome | None] = mapped_column(_enum(SignalOutcome, "signal_outcome"))
    outcome_method: Mapped[str | None] = mapped_column(String(32))  # "desk_review" | "field_inspection"
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_count: Mapped[int] = mapped_column(Integer, default=0)
    first_obs_on: Mapped[date] = mapped_column(Date)
    last_obs_on: Mapped[date] = mapped_column(Date)
    latest_ndvi: Mapped[float] = mapped_column(Float)
    baseline_median: Mapped[float] = mapped_column(Float)
    baseline_sd: Mapped[float] = mapped_column(Float)
    deviation: Mapped[float] = mapped_column(Float)
    z_score: Mapped[float] = mapped_column(Float)
    priority_score: Mapped[float] = mapped_column(Float)
    priority_factors: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    before_obs_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("observations.id", ondelete="SET NULL"))
    after_obs_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("observations.id", ondelete="SET NULL"))
    before_image: Mapped[str | None] = mapped_column(String(80))
    after_image: Mapped[str | None] = mapped_column(String(80))

    site: Mapped[Site] = relationship()


class SignalDecision(Base):
    __tablename__ = "signal_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), index=True)
    decision: Mapped[DecisionType] = mapped_column(_enum(DecisionType, "decision_type"))
    reason: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[SignalOutcome | None] = mapped_column(_enum(SignalOutcome, "signal_outcome"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship()


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id", ondelete="SET NULL"), index=True)
    task_type: Mapped[TaskType] = mapped_column(_enum(TaskType, "task_type"))
    title: Mapped[str] = mapped_column(String(160))
    instructions: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[TaskPriority] = mapped_column(_enum(TaskPriority, "task_priority"))
    due_date: Mapped[date] = mapped_column(Date)
    assignee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus, "task_status"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    site: Mapped[Site] = relationship()
    assignee: Mapped[User] = relationship(foreign_keys=[assignee_id])
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])
    finding: Mapped["TaskFinding | None"] = relationship(back_populates="task", uselist=False)


class TaskFinding(Base):
    __tablename__ = "task_findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), unique=True)
    visit_date: Mapped[date | None] = mapped_column(Date)
    condition: Mapped[ObservedCondition | None] = mapped_column(_enum(ObservedCondition, "observed_condition"))
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task: Mapped[Task] = relationship(back_populates="finding")
    photos: Mapped[list["FindingPhoto"]] = relationship(order_by="FindingPhoto.created_at")


class FindingPhoto(Base):
    __tablename__ = "finding_photos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_findings.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(80))
    thumb_name: Mapped[str] = mapped_column(String(80))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(foreign_keys=[user_id])


# ---------------------------------------------------------------- Sprint 3


class PlantFactor(Base):
    """Plant factor (fraction of reference evapotranspiration) per planting category; an adjustable assumption."""

    __tablename__ = "plant_factors"

    category: Mapped[PlantingCategory] = mapped_column(_enum(PlantingCategory, "planting_category"), primary_key=True)
    factor: Mapped[float] = mapped_column(Float)
    source_note: Mapped[str] = mapped_column(String(300))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WeatherDaily(Base):
    """Daily weather at a site's location (Open-Meteo)."""

    __tablename__ = "weather_daily"
    __table_args__ = (UniqueConstraint("site_id", "day", "boundary_version", name="uq_weather_site_day"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    boundary_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    et0_mm: Mapped[float | None] = mapped_column(Float)
    tmax_c: Mapped[float | None] = mapped_column(Float)
    tmin_c: Mapped[float | None] = mapped_column(Float)
    precip_mm: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))  # "forecast" | "archive"
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IrrigationSchedule(Base):
    """User-entered irrigation schedule for a site over a date range."""

    __tablename__ = "irrigation_schedules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    weekdays: Mapped[list] = mapped_column(JSON)  # ISO weekday numbers 1 (Monday) .. 7 (Sunday)
    litres_per_day: Mapped[float] = mapped_column(Float)  # total volume applied on each watering day
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LstObservation(Base):
    """Land surface temperature for a site and its surroundings on one Landsat acquisition date."""

    __tablename__ = "lst_observations"
    __table_args__ = (UniqueConstraint("site_id", "acquired_on", "boundary_version", name="uq_lst_site_date"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_runs.id", ondelete="SET NULL"))
    scene_id: Mapped[str] = mapped_column(String(128))
    platform: Mapped[str] = mapped_column(String(32))
    acquired_on: Mapped[date] = mapped_column(Date)
    boundary_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    site_c: Mapped[float | None] = mapped_column(Float)
    surround_c: Mapped[float | None] = mapped_column(Float)
    site_pixels: Mapped[int] = mapped_column(Integer)
    surround_pixels: Mapped[int] = mapped_column(Integer)
    valid_share: Mapped[float] = mapped_column(Float)
    usable: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LstLayer(Base):
    """Rendered surface temperature map of the pilot area from one Landsat scene."""

    __tablename__ = "lst_layers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scene_id: Mapped[str] = mapped_column(String(128), unique=True)
    platform: Mapped[str] = mapped_column(String(32))
    acquired_on: Mapped[date] = mapped_column(Date, index=True)
    image: Mapped[str] = mapped_column(String(80))
    bounds: Mapped[list] = mapped_column(JSON)  # [west, south, east, north] in WGS84
    min_c: Mapped[float] = mapped_column(Float)
    max_c: Mapped[float] = mapped_column(Float)
    valid_share: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    """Append-only record of key actions (US24). A database trigger rejects updates and deletes."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    user_name: Mapped[str | None] = mapped_column(String(120))
    user_role: Mapped[str | None] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(48), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(300))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class AiBrief(Base):
    """Validated AI-generated content (signal evidence brief or overview summary), cached by its input facts."""

    __tablename__ = "ai_briefs"
    __table_args__ = (Index("ix_ai_briefs_subject", "kind", "subject_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(24))  # "signal_brief" | "overview_summary"
    subject_key: Mapped[str] = mapped_column(String(200))
    facts_hash: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(80))
    facts: Mapped[list] = mapped_column(JSON)
    content: Mapped[dict] = mapped_column(JSON)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def current_boundary(model):
    """SQL predicate for spatial measurements of the site's current boundary revision."""
    return model.boundary_version == (
        select(Site.boundary_version).where(Site.id == model.site_id).correlate(model).scalar_subquery()
    )
