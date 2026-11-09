"""Request and response schemas."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.localtime import local_today
from app.models import (
    ObservedCondition,
    PlantingCategory,
    Role,
    RunKind,
    RunStatus,
    SignalOutcome,
    SignalStatus,
    SiteSource,
    SiteStatus,
    SiteType,
    TaskPriority,
    TaskStatus,
    TaskType,
)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    role: Role
    password: str = Field(min_length=10, max_length=256)

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must have at least 2 characters.")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


# GeoJSON geometry as submitted by the map editor.
class GeoJSONGeometry(BaseModel):
    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]


class SiteBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    name_ar: str | None = Field(default=None, max_length=120)
    site_type: SiteType
    planting_category: PlantingCategory
    notes: str | None = Field(default=None, max_length=2000)
    irrigated_area_m2: float | None = Field(default=None, gt=0, le=10_000_000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required.")
        return v

    @field_validator("name_ar", "notes")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v is not None else None

    @field_validator("planting_category")
    @classmethod
    def category_known(cls, v: PlantingCategory) -> PlantingCategory:
        if v == PlantingCategory.unknown:
            raise ValueError("Choose a planting category.")
        return v


class SiteCreate(SiteBase):
    geometry: GeoJSONGeometry


class SiteUpdate(SiteBase):
    geometry: GeoJSONGeometry | None = None
    status: SiteStatus | None = None


class SiteStatusUpdate(BaseModel):
    status: SiteStatus


class LatestObservation(BaseModel):
    acquired_on: date
    ndvi_mean: float | None
    ndmi_mean: float | None


class SiteSummary(BaseModel):
    id: uuid.UUID
    name: str
    name_ar: str | None
    site_type: SiteType
    planting_category: PlantingCategory
    district_id: int | None
    district_name: str | None
    area_m2: float
    low_confidence: bool
    needs_review: bool
    status: SiteStatus
    source: SiteSource
    latest: LatestObservation | None = None


class SiteDetail(SiteSummary):
    irrigated_area_m2: float | None
    source_ref: str | None
    notes: str | None
    geometry: dict
    created_at: datetime
    updated_at: datetime
    source_attribution: str | None


class ImportRequest(BaseModel):
    district_id: int


class SkippedFeature(BaseModel):
    osm_ref: str
    name: str | None
    reason: str


class ImportResult(BaseModel):
    run_id: uuid.UUID
    district: str
    features_found: int
    created: int
    already_imported: int
    skipped: list[SkippedFeature]
    created_site_ids: list[uuid.UUID]


class ProcessingRunCreate(BaseModel):
    kind: Literal["sentinel2", "landsat_lst", "weather"] = "sentinel2"
    start_date: date
    end_date: date
    site_ids: list[uuid.UUID] | None = None

    @field_validator("end_date")
    @classmethod
    def range_ok(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("End date must be on or after the start date.")
        if v > date.today():
            raise ValueError("End date cannot be in the future.")
        if start and (v - start).days > 3 * 366:
            raise ValueError("Choose a range of at most three years.")
        return v


class ProcessingRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: RunKind
    status: RunStatus
    params: dict
    requested_by_name: str | None = None
    scenes_found: int
    scenes_processed: int
    items_written: int
    items_skipped: int
    error: str | None
    messages: list
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    acquired_on: date
    acquired_at: datetime
    scene_id: str
    platform: str
    ndvi_mean: float | None
    ndvi_std: float | None
    ndmi_mean: float | None
    ndmi_std: float | None
    valid_pixels: int
    total_pixels: int
    valid_share: float
    usable: bool


class ConditionHistory(BaseModel):
    site_id: uuid.UUID
    observations: list[ObservationOut]
    usable_count: int
    unusable_count: int
    latest_usable_on: date | None
    attribution: str | None
    thresholds: dict


# ---------------------------------------------------------------- Sprint 2


class ReasonBody(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class DismissBody(BaseModel):
    reason: str = Field(max_length=2000)


class OutcomeBody(BaseModel):
    outcome: SignalOutcome
    note: str | None = Field(default=None, max_length=2000)


class TaskFields(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    instructions: str | None = Field(default=None, max_length=4000)
    priority: TaskPriority
    due_date: date
    assignee_id: uuid.UUID

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Give the task a title of at least 3 characters.")
        return v

    @field_validator("due_date")
    @classmethod
    def not_past(cls, v: date) -> date:
        if v < local_today():
            raise ValueError("The due date cannot be in the past.")
        return v


class TaskCreate(TaskFields):
    site_id: uuid.UUID
    signal_id: uuid.UUID | None = None
    task_type: TaskType


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    instructions: str | None = Field(default=None, max_length=4000)
    priority: TaskPriority | None = None
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None

    @field_validator("due_date")
    @classmethod
    def not_past(cls, v: date | None) -> date | None:
        if v is not None and v < local_today():
            raise ValueError("The due date cannot be in the past.")
        return v


class FindingsBody(BaseModel):
    visit_date: date | None = None
    condition: ObservedCondition | None = None
    notes: str | None = Field(default=None, max_length=4000)


class PhotoOut(BaseModel):
    id: uuid.UUID
    url: str
    thumb_url: str
    width: int
    height: int


class FindingOut(BaseModel):
    visit_date: date | None
    condition: ObservedCondition | None
    notes: str | None
    recorded_at: datetime | None
    photos: list[PhotoOut]


class TaskOut(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    site_name: str
    site_name_ar: str | None
    district_name: str | None
    signal_id: uuid.UUID | None
    task_type: TaskType
    title: str
    instructions: str | None
    priority: TaskPriority
    due_date: date
    overdue: bool
    assignee_id: uuid.UUID
    assignee_name: str
    status: TaskStatus
    created_by_name: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    finding: FindingOut | None


class DecisionOut(BaseModel):
    decision: str
    reason: str | None
    outcome: SignalOutcome | None
    user_name: str | None
    created_at: datetime


class SignalSummary(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    site_name: str
    site_name_ar: str | None
    district_id: int | None
    district_name: str | None
    site_type: str
    area_m2: float
    status: SignalStatus
    outcome: SignalOutcome | None
    detected_at: datetime
    first_obs_on: date
    last_obs_on: date
    latest_ndvi: float
    baseline_median: float
    deviation: float
    z_score: float
    priority_score: float
    priority_factors: dict
    reopened_count: int


class SignalDetail(SignalSummary):
    boundary_changed: bool = False
    outcome_method: str | None
    closed_at: datetime | None
    baseline_sd: float
    evidence: dict
    before_image: dict | None
    after_image: dict | None
    decisions: list[DecisionOut]
    tasks: list[TaskOut]
    attribution: str


class BaselineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: int
    target_year: int
    n_obs: int
    median_ndvi: float | None
    robust_sd: float | None
    p10: float | None
    p90: float | None
    years: str
    available: bool


class ChangePasswordBody(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class ResetPasswordBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=10, max_length=256)


class ResetCheckBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetLinkOut(BaseModel):
    url: str
    expires_at: datetime


# ---------------------------------------------------------------- Sprint 3


class ScheduleBody(BaseModel):
    start_date: date
    end_date: date | None = None
    weekdays: list[int] = Field(min_length=1, max_length=7)
    litres_per_day: float = Field(gt=0, le=100_000_000)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("start_date")
    @classmethod
    def plausible_start(cls, v: date) -> date:
        if v.year < 2015:
            raise ValueError("Choose a start date from 2015 onwards.")
        return v

    @field_validator("notes")
    @classmethod
    def blank_notes(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v is not None else None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    start_date: date
    end_date: date | None
    weekdays: list[int]
    litres_per_day: float
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PlantFactorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: PlantingCategory
    factor: float
    source_note: str
    updated_at: datetime


class PlantFactorUpdate(BaseModel):
    factor: float = Field(ge=0.05, le=1.2)
    source_note: str = Field(min_length=3, max_length=300)


class BriefRequest(BaseModel):
    force: bool = False


class OverviewSummaryRequest(BaseModel):
    district_id: int | None = None
    start: date | None = None
    end: date | None = None
    force: bool = False
