"""Test fixtures. Tests run against the dedicated `namaa_test` PostGIS database.

Run inside Docker:
  docker compose run --rm -e DATABASE_URL=postgresql+psycopg://USER:PASS@db:5432/namaa_test backend pytest
(see scripts/test-backend.sh)
"""

import os
import uuid

import pytest

if not os.environ.get("DATABASE_URL", "").rstrip("/").endswith("_test"):
    raise RuntimeError("Tests must run against a database whose name ends with '_test'.")

# Tests create their own users; the start-up administrator is tested separately in test_bootstrap.py.
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = ""
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = ""
os.environ["MEDIA_DIR"] = "/tmp/namaa-test-media"

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from geoalchemy2.shape import from_shape  # noqa: E402
from shapely.geometry import MultiPolygon, box  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import District, Role, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.water import DEFAULT_NOTE, DEFAULT_PLANT_FACTORS  # noqa: E402

PASSWORD = "correct-horse-battery"
TABLES = (
    "ai_briefs, audit_events, lst_layers, lst_observations, irrigation_schedules, weather_daily, "
    "finding_photos, task_findings, tasks, signal_decisions, signals, site_baselines, password_reset_tokens, "
    "observations, processing_runs, sites, sessions, users, districts"
)

# A real-sized test district inside the pilot area (central Riyadh), about 2 km x 2 km.
DISTRICT_BOX = box(46.70, 24.70, 46.72, 24.72)


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        # Plant factors are seeded by the migration; TRUNCATE ... CASCADE empties them (they reference users).
        conn.execute(text("TRUNCATE plant_factors"))
        for category, factor in DEFAULT_PLANT_FACTORS.items():
            conn.execute(
                text(
                    "INSERT INTO plant_factors (category, factor, source_note) "
                    "VALUES (CAST(:c AS planting_category), :f, :n)"
                ),
                {"f": factor, "c": category.value, "n": DEFAULT_NOTE},
            )
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_user(db, role: Role, email: str | None = None, active: bool = True) -> User:
    user = User(
        email=email or f"{role.value}-{uuid.uuid4().hex[:6]}@example.com",
        full_name=f"Test {role.value.title()}",
        role=role,
        password_hash=hash_password(PASSWORD),
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def users(db) -> dict[Role, User]:
    return {r: make_user(db, r, email=f"{r.value}@example.com") for r in Role}


@pytest.fixture
def district(db) -> District:
    d = District(
        osm_id=990001,
        name_en="Test District",
        name_ar="حي الاختبار",
        geom=from_shape(MultiPolygon([DISTRICT_BOX]), srid=4326),
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def as_role(users):
    """Return a fresh signed-in TestClient for a role."""
    clients = []

    def _make(role: Role) -> TestClient:
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        r = login(c, users[role].email)
        assert r.status_code == 200, r.text
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


def square(lon: float, lat: float, size_deg: float = 0.001) -> dict:
    """GeoJSON polygon; 0.001 degrees is roughly 100 m x 111 m in Riyadh (about 1.1 ha)."""
    return {
        "type": "Polygon",
        "coordinates": [
            [[lon, lat], [lon + size_deg, lat], [lon + size_deg, lat + size_deg], [lon, lat + size_deg], [lon, lat]]
        ],
    }
