"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+psycopg://namaa:namaa@db:5432/namaa"

    # Sessions
    session_cookie_name: str = "namaa_session"
    session_ttl_hours: int = 12
    cookie_secure: bool = False  # set true behind HTTPS

    # First administrator, created at start-up only if no administrator exists.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "Namaa Administrator"

    # Pilot area (WGS84): min_lon, min_lat, max_lon, max_lat
    pilot_bbox: tuple[float, float, float, float] = (46.45, 24.45, 47.05, 25.05)
    min_monitoring_area_m2: float = 5000.0

    # OpenStreetMap
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    overpass_fallback_urls: list[str] = ["https://overpass.private.coffee/api/interpreter"]
    overpass_attempts_per_endpoint: int = 2
    overpass_retry_delay_s: float = 3.0
    overpass_timeout_s: float = 60.0  # 2 endpoints x 2 attempts stays under the 300 s web proxy limit
    http_user_agent: str = "Namaa/0.1 (academic project; Prince Sultan University)"

    # Satellite processing
    stac_api_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    stac_collection: str = "sentinel-2-l2a"
    scene_max_cloud_cover: float = 80.0
    min_valid_share: float = Field(0.70, ge=0, le=1)
    min_valid_pixels: int = 10
    worker_poll_seconds: float = 5.0
    satellite_auto_refresh: bool = True
    satellite_refresh_hours: float = Field(24.0, ge=1)
    satellite_refresh_days: int = Field(30, ge=1, le=366)

    # Analysis: seasonal baselines and the decline-detection rule
    baseline_min_obs: int = 8
    baseline_min_sd: float = 0.02
    detection_window: int = 3
    detection_z: float = -2.0
    detection_min_drop: float = 0.05

    # Account recovery
    reset_token_ttl_hours: int = 24
    public_base_url: str = "http://127.0.0.1:3000"

    # Uploaded photos and generated image chips
    media_dir: str = "/data/media"
    max_photo_bytes: int = 8 * 1024 * 1024
    max_photos_per_finding: int = 6

    # Calendar date for user-facing checks (visit and due dates, overdue tasks, report periods)
    local_timezone: str = "Asia/Riyadh"

    # File paths
    districts_file: str = "data/riyadh_districts.geojson"

    # Weather for water-demand estimates (Open-Meteo, no key required)
    weather_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    weather_timeout_s: float = 30.0
    weather_refresh_hours: float = 24.0  # the worker queues a weather run when stored data is older than this
    weather_history_days: int = 92
    weather_auto_refresh: bool = True

    # Landsat land surface temperature (US19-US20)
    landsat_collection: str = "landsat-c2-l2"
    landsat_max_cloud_cover: float = 30.0
    lst_surround_m: float = 300.0  # ring around the site used for the surrounding-area value
    lst_layer_range_c: tuple[float, float] = (15.0, 65.0)  # fixed colour scale of the heat map layer
    heat_max_age_days: int = 120  # older heat data is not used in priority scores

    # AI review assistant (US26-US27). The key stays on the server; leave it empty to disable AI features.
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_reasoning_effort: Literal["", "none", "low", "medium", "high", "xhigh", "max"] = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_s: float = 45.0
    ai_daily_limit_per_user: int = Field(30, ge=1, le=1000)


@lru_cache
def get_settings() -> Settings:
    return Settings()
