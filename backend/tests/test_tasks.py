"""US14 tasks and US15 field findings and photos."""

import io
from datetime import date, timedelta

import pytest
from PIL import Image

from app.localtime import local_today
from app.models import Role
from app.services.media import media_path
from tests.conftest import make_user, square


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


@pytest.fixture
def site(manager):
    return manager.post(
        "/api/sites",
        json={
            "name": "Task Park",
            "site_type": "park",
            "planting_category": "turf",
            "geometry": square(46.705, 24.705, 0.002),
        },
    ).json()


def body(site_id, assignee_id, **kw):
    return {
        "site_id": site_id,
        "task_type": "maintenance",
        "title": "Repair irrigation valve",
        "priority": "medium",
        "due_date": (date.today() + timedelta(days=7)).isoformat(),
        "assignee_id": str(assignee_id),
        **kw,
    }


def jpeg(size=(640, 480), exif=True) -> bytes:
    img = Image.new("RGB", size, (40, 120, 60))
    buf = io.BytesIO()
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "TestCam"  # Make
        ex[0x8825] = {2: (24.0, 42.0, 0.0)}  # GPS info: latitude
        img.save(buf, "JPEG", exif=ex)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def task(manager, site, users):
    r = manager.post("/api/tasks", json=body(site["id"], users[Role.inspector].id))
    assert r.status_code == 201, r.text
    return r.json()


def test_ac_14_1_task_records_fields(task, site, users):
    assert task["site_id"] == site["id"] and task["task_type"] == "maintenance" and task["priority"] == "medium"
    assert task["assignee_name"] == "Test Inspector" and task["status"] == "assigned" and task["overdue"] is False
    assert task["created_by_name"] == "Test Manager" and task["signal_id"] is None


@pytest.mark.parametrize("who", ["viewer", "manager", "inactive", "unknown"])
def test_ac_14_1_assignee_must_be_active_inspector(manager, site, users, db, who):
    target = {
        "viewer": users[Role.viewer].id,
        "manager": users[Role.manager].id,
        "inactive": make_user(db, Role.inspector, active=False).id,
        "unknown": "00000000-0000-0000-0000-000000000000",
    }[who]
    r = manager.post("/api/tasks", json=body(site["id"], target))
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][-1] == "assignee_id"


def test_task_validation(manager, site, users):
    r = manager.post("/api/tasks", json=body(site["id"], users[Role.inspector].id, due_date="2020-01-01", title="x"))
    fields = {e["loc"][-1] for e in r.json()["detail"]}
    assert r.status_code == 422 and {"due_date", "title"} <= fields


def test_ac_14_2_inspectors_see_only_their_tasks(task, as_role, db):
    mine = as_role(Role.inspector).get("/api/tasks").json()
    assert [t["id"] for t in mine] == [task["id"]]
    other = make_user(db, Role.inspector, email="other.inspector@example.com")
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import login

    with TestClient(app) as c:
        login(c, other.email)
        assert c.get("/api/tasks").json() == []
        assert c.get(f"/api/tasks/{task['id']}").status_code == 404
        assert c.post(f"/api/tasks/{task['id']}/start").status_code == 404


def test_ac_14_3_workflow_and_invalid_transitions(task, as_role, manager):
    insp = as_role(Role.inspector)
    assert insp.post(f"/api/tasks/{task['id']}/complete").status_code == 422  # findings missing
    assert insp.post(f"/api/tasks/{task['id']}/start").json()["status"] == "in_progress"
    assert insp.post(f"/api/tasks/{task['id']}/start").status_code == 409
    insp.put(
        f"/api/tasks/{task['id']}/findings",
        json={"visit_date": date.today().isoformat(), "condition": "healthy", "notes": "Valve replaced"},
    )
    done = insp.post(f"/api/tasks/{task['id']}/complete").json()
    assert done["status"] == "completed" and done["completed_at"]
    assert manager.post(f"/api/tasks/{task['id']}/cancel", json={}).status_code == 409
    assert manager.patch(f"/api/tasks/{task['id']}", json={"priority": "low"}).status_code == 409


def test_ac_15_1_only_assignee_updates(task, as_role):
    for role in (Role.manager, Role.viewer, Role.admin):
        c = as_role(role)
        assert c.post(f"/api/tasks/{task['id']}/start").status_code == 403
        assert c.put(f"/api/tasks/{task['id']}/findings", json={"notes": "x"}).status_code == 403


def test_ac_15_2_findings_validation(task, as_role):
    insp = as_role(Role.inspector)
    # The server checks against the local (Riyadh) date.
    future = (local_today() + timedelta(days=1)).isoformat()
    r = insp.put(f"/api/tasks/{task['id']}/findings", json={"visit_date": future, "condition": "healthy", "notes": "x"})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][-1] == "visit_date"
    r = insp.put(f"/api/tasks/{task['id']}/findings", json={"condition": "unknown-condition"})
    assert r.status_code == 422
    findings = {"visit_date": local_today().isoformat(), "condition": "damaged"}
    insp.put(f"/api/tasks/{task['id']}/findings", json=findings)
    r = insp.post(f"/api/tasks/{task['id']}/complete")
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][-1] == "notes"


def test_ac_15_3_photo_is_reencoded_without_exif(task, as_role):
    insp = as_role(Role.inspector)
    r = insp.post(f"/api/tasks/{task['id']}/photos", files={"file": ("site.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 201, r.text
    photo = r.json()["finding"]["photos"][0]
    stored = Image.open(media_path("photos", photo["url"].rsplit("/", 1)[1]))
    assert stored.format == "JPEG" and stored.size == (640, 480)
    assert len(stored.getexif()) == 0  # camera and GPS metadata removed
    thumb = insp.get(photo["thumb_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize(
    "name, data, ctype, message",
    [
        ("notes.txt", b"not an image at all", "text/plain", "not a readable image"),
        ("fake.jpg", b"GIF89a" + b"\x00" * 100, "image/jpeg", "not a"),  # content checked, not the extension
        ("empty.png", b"", "image/png", "is empty"),
    ],
)
def test_ac_15_3_invalid_files_rejected(task, as_role, name, data, ctype, message):
    r = as_role(Role.inspector).post(f"/api/tasks/{task['id']}/photos", files={"file": (name, data, ctype)})
    assert r.status_code == 422 and message in r.json()["detail"][0]["msg"]


def test_ac_15_3_size_and_count_limits(task, as_role, monkeypatch):
    from app.config import get_settings

    insp = as_role(Role.inspector)
    monkeypatch.setattr(get_settings(), "max_photo_bytes", 2000)
    r = insp.post(f"/api/tasks/{task['id']}/photos", files={"file": ("big.jpg", jpeg((1200, 900)), "image/jpeg")})
    assert r.status_code == 422 and "larger than" in r.json()["detail"][0]["msg"]
    monkeypatch.setattr(get_settings(), "max_photo_bytes", 8 * 1024 * 1024)
    monkeypatch.setattr(get_settings(), "max_photos_per_finding", 2)
    for _ in range(2):
        assert (
            insp.post(f"/api/tasks/{task['id']}/photos", files={"file": ("a.jpg", jpeg(), "image/jpeg")}).status_code
            == 201
        )
    r = insp.post(f"/api/tasks/{task['id']}/photos", files={"file": ("c.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 422 and "at most 2" in r.json()["detail"][0]["msg"]


def test_photo_delete_removes_files(task, as_role):
    insp = as_role(Role.inspector)
    p = insp.post(f"/api/tasks/{task['id']}/photos", files={"file": ("a.jpg", jpeg(), "image/jpeg")}).json()
    photo = p["finding"]["photos"][0]
    path = media_path("photos", photo["url"].rsplit("/", 1)[1])
    assert path.exists()
    r = insp.delete(f"/api/tasks/{task['id']}/photos/{photo['id']}")
    assert r.status_code == 200 and r.json()["finding"]["photos"] == [] and not path.exists()


def test_ac_15_4_findings_visible_on_task_and_site(task, as_role, manager, site):
    insp = as_role(Role.inspector)
    insp.put(
        f"/api/tasks/{task['id']}/findings",
        json={"visit_date": date.today().isoformat(), "condition": "stressed", "notes": "Yellowing turf"},
    )
    insp.post(f"/api/tasks/{task['id']}/photos", files={"file": ("a.jpg", jpeg(), "image/jpeg")})
    insp.post(f"/api/tasks/{task['id']}/complete")
    t = manager.get(f"/api/tasks/{task['id']}").json()
    assert t["finding"]["condition"] == "stressed" and len(t["finding"]["photos"]) == 1
    assert manager.get(f"/api/sites/{site['id']}/tasks").json()[0]["finding"]["notes"] == "Yellowing turf"
    events = manager.get(f"/api/sites/{site['id']}/timeline").json()["events"]
    assert events[-1]["kind"] == "task_completed" and "1 photos" in events[-1]["text"]


def test_reassign_and_overdue_flag(task, manager, db):
    from sqlalchemy import update

    from app.models import Task

    other = make_user(db, Role.inspector, email="second.inspector@example.com")
    r = manager.patch(f"/api/tasks/{task['id']}", json={"assignee_id": str(other.id), "priority": "high"})
    assert r.status_code == 200
    assert r.json()["assignee_id"] == str(other.id) and r.json()["priority"] == "high"
    db.execute(update(Task).values(due_date=date.today() - timedelta(days=1)))
    db.commit()
    assert manager.get(f"/api/tasks/{task['id']}").json()["overdue"] is True


def test_inspectors_list_for_assignment(manager, users, as_role):
    names = [u["full_name"] for u in manager.get("/api/inspectors").json()]
    assert names == ["Test Inspector"]
    assert as_role(Role.viewer).get("/api/inspectors").status_code == 403
