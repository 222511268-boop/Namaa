"""First administrator created from environment variables (plan §2; NFR06: no hard-coded credentials)."""

import pytest

from app.bootstrap import ensure_bootstrap_admin
from app.config import get_settings
from app.models import Role, User
from tests.conftest import login, make_user


@pytest.fixture
def bootstrap_env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "bootstrap_admin_email", "First.Admin@example.com")
    monkeypatch.setattr(s, "bootstrap_admin_password", "initial-admin-password")


def test_creates_admin_when_none_exists(db, bootstrap_env):
    user = ensure_bootstrap_admin(db)
    assert user.role == Role.admin and user.email == "first.admin@example.com"


def test_application_start_up_creates_admin_who_can_sign_in(db, bootstrap_env, client):
    # The `client` fixture starts the application, which runs the bootstrap step.
    assert db.query(User).filter_by(email="first.admin@example.com", role=Role.admin).count() == 1
    assert login(client, "first.admin@example.com", "initial-admin-password").status_code == 200


def test_does_nothing_when_admin_exists(db, bootstrap_env):
    make_user(db, Role.admin, email="existing@example.com")
    assert ensure_bootstrap_admin(db) is None
    assert db.query(User).count() == 1


def test_does_nothing_without_variables(db):
    assert ensure_bootstrap_admin(db) is None
    assert db.query(User).count() == 0


def test_rejects_short_password(db, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "bootstrap_admin_email", "a@example.com")
    monkeypatch.setattr(s, "bootstrap_admin_password", "short")
    with pytest.raises(RuntimeError, match="at least 10"):
        ensure_bootstrap_admin(db)
