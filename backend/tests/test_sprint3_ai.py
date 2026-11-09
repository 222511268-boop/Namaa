"""US26-US27 and NFR18: AI evidence briefs and overview summaries.

The OpenAI API is never called here: `_complete` is replaced by a fake model that builds answers from the facts it
is given, or the HTTP endpoint is mocked with respx. No AI output in these tests comes from a real model.
"""

import json
import uuid
from datetime import date, timedelta

import httpx
import pytest
import respx

from app.config import get_settings
from app.models import AiBrief, AuditEvent, Role
from app.services import ai
from app.services.analysis import analyse_sites
from tests.analysis_helpers import add_observations, history, latest
from tests.conftest import square

DECLINE = [("2026-05-05", 0.20), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]


@pytest.mark.parametrize("effort", ["", "none"])
@respx.mock
def test_reasoning_effort_is_optional_and_preserves_strict_output(monkeypatch, effort):
    """HTTP double: configuration/request contract only, not real-model output."""
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-a-real-key")
    monkeypatch.setattr(get_settings(), "openai_model", "gpt-6-luna")
    monkeypatch.setattr(get_settings(), "openai_reasoning_effort", effort)
    captured = {}

    def reply(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })

    respx.post("https://api.openai.com/v1/chat/completions").mock(side_effect=reply)
    ai._complete([{"role": "user", "content": "Constructed request contract test"}], "test", {"type": "object"})
    assert captured["model"] == "gpt-6-luna"
    assert captured["max_completion_tokens"] == 2000
    assert captured["response_format"]["json_schema"]["strict"] is True
    if effort:
        assert captured["reasoning_effort"] == effort
    else:
        assert "reasoning_effort" not in captured


def _ev(text, ids):
    return {"text": text, "fact_ids": ids}


def fake_answer(kind: str, facts: list[dict], bad_figure: bool = False) -> dict:
    """A well-formed answer that quotes fact values exactly (optionally with one invented figure)."""
    num = [f for f in facts if isinstance(f["value"], int | float) and not isinstance(f["value"], bool)]
    a, b = num[0], num[1]
    s1 = f"{a['label']} is {a['value']}."
    if bad_figure:
        s1 += " The site lost 37.5 percent of its cover."
    if kind == "signal_brief":
        return {
            "headline": "Vegetation is well below its seasonal range.",
            "summary": _ev(s1, [a["id"]]),
            "explanations": [
                {"title": "Irrigation failure", "assessment": "more likely",
                 "supporting": [_ev(f"{b['label']}: {b['value']}.", [b["id"]])],
                 "contradicting": [_ev("No stored evidence contradicts this.", [])]},
                {"title": "Data artefact such as haze", "assessment": "less likely",
                 "supporting": [_ev("Clear observations exist.", [a["id"]])],
                 "contradicting": [_ev("The decline persists across observations.", [b["id"]])]},
            ],
            "checklist": [_ev("Check irrigation controllers and valves.", []),
                          _ev("Look for dry or bare patches.", [a["id"]]),
                          _ev("Note any construction or replanting work.", [])],
            "data_gaps": [],
        }
    return {"headline": "Monitoring summary for the period.",
            "paragraphs": [_ev(s1, [a["id"]]), _ev(f"{b['label']}: {b['value']}.", [b["id"]])],
            "watch_items": []}


class FakeModel:
    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers  # list of booleans: True = include an invented figure on that call

    def __call__(self, messages, kind, schema):
        self.calls.append(messages)
        facts = json.loads(messages[1]["content"].split("```json\n")[1].split("\n```")[0])
        bad = self.answers.pop(0) if self.answers else False
        return fake_answer(kind, facts, bad), {"prompt_tokens": 900, "completion_tokens": 300}


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-a-real-key")
    monkeypatch.setattr(get_settings(), "openai_model", "test-model")
    model = FakeModel()
    monkeypatch.setattr(ai, "_complete", model)
    return model


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


@pytest.fixture
def signal(manager, db, users):
    site = manager.post("/api/sites", json={"name": "Brief Park", "site_type": "park", "planting_category": "turf",
                                            "notes": "Contact Ahmed at ahmed@example.com, 0551234567",
                                            "geometry": square(46.705, 24.705, 0.003)}).json()
    add_observations(db, uuid.UUID(site["id"]), history(0.35, 0.03, 0.01, [2025]) + latest(DECLINE))
    analyse_sites(db)
    return manager.get("/api/signals").json()[0]


def test_ac_26_1_brief_generated_on_request_from_stored_evidence(manager, signal, ai_on, db):
    assert manager.get(f"/api/signals/{signal['id']}/brief").json() is None  # nothing until requested
    r = manager.post(f"/api/signals/{signal['id']}/brief", json={})
    assert r.status_code == 200, r.text
    b = r.json()
    labels = " | ".join(f["label"] for f in b["facts"])
    for expected in ("NDVI on 2026-05-15", "Seasonal median NDVI", "z-score", "Priority score",
                     "Consecutive below-range", "Usable (clear) satellite observations"):
        assert expected in labels
    assert "Surface temperature data" in labels and "Water-demand estimate" in labels  # stated as not available
    assert b["model"] == "test-model" and b["prompt_version"] == ai.SIGNAL_PROMPT_VERSION
    assert db.query(AiBrief).count() == 1


def test_ac_26_2_labelled_ai_generated_and_advisory(manager, signal, ai_on):
    b = manager.post(f"/api/signals/{signal['id']}/brief", json={}).json()
    assert "AI-generated" in b["label"] and "advisory" in b["label"]


def test_ac_26_3_explanations_list_supporting_and_contradicting_evidence(manager, signal, ai_on):
    b = manager.post(f"/api/signals/{signal['id']}/brief", json={}).json()
    for e in b["content"]["explanations"]:
        assert e["supporting"] and e["contradicting"]


def test_ac_26_4_invented_figures_are_corrected_or_rejected(manager, signal, ai_on, db):
    ai_on.answers = [True, False]  # first answer invents a figure; the correction round fixes it
    r = manager.post(f"/api/signals/{signal['id']}/brief", json={})
    assert r.status_code == 200 and len(ai_on.calls) == 2
    assert "37.5" in ai_on.calls[1][-1]["content"]  # the problem was sent back for correction
    ai_on.answers = [True, True]
    r = manager.post(f"/api/signals/{signal['id']}/brief", json={"force": True})
    assert r.status_code == 502 and "could not be verified" in r.json()["detail"]
    assert db.query(AiBrief).count() == 1  # the unverified brief was not stored
    assert db.query(AuditEvent).filter_by(action="ai.failed").count() == 1


def test_ac_26_4_every_figure_in_stored_briefs_matches_a_fact(manager, signal, ai_on):
    b = manager.post(f"/api/signals/{signal['id']}/brief", json={}).json()
    assert ai.validate("signal_brief", b["content"], b["facts"]) == []


def test_ac_26_5_checklist_prefills_inspection_task_and_is_editable(manager, signal, ai_on, users):
    b = manager.post(f"/api/signals/{signal['id']}/brief", json={}).json()
    text = b["checklist_text"]
    assert text.startswith("Inspection checklist (AI-drafted") and "- Check irrigation controllers" in text
    edited = text + "\n- Photograph the north lawn."
    t = manager.post(f"/api/signals/{signal['id']}/inspection", json={
        "title": "Inspect Brief Park", "instructions": edited, "priority": "high",
        "due_date": (date.today() + timedelta(days=2)).isoformat(), "assignee_id": str(users[Role.inspector].id)})
    assert t.status_code == 201 and t.json()["instructions"] == edited


def test_ac_26_6_managers_only(signal, ai_on, as_role):
    for role in (Role.admin, Role.inspector, Role.viewer):
        assert as_role(role).post(f"/api/signals/{signal['id']}/brief", json={}).status_code == 403


def test_ac_26_6_no_personal_information_sent(manager, signal, ai_on, users, db, as_role):
    sid = signal["id"]
    manager.post(f"/api/signals/{sid}/dismiss", json={"reason": "Spoke to Saeed (saeed@example.com) on site"})
    db.commit()
    from app.models import Signal, SignalStatus

    sig = db.get(Signal, uuid.UUID(sid))
    sig.status = SignalStatus.open  # reopen directly so a brief can still be requested
    db.commit()
    manager.post(f"/api/signals/{sid}/brief", json={})
    sent = json.dumps(ai_on.calls[0])
    for pii in ("ahmed@example.com", "0551234567", "Saeed", "saeed@example.com", users[Role.manager].full_name,
                users[Role.manager].email, users[Role.inspector].full_name):
        assert pii not in sent, pii
    assert "dismiss" in sent  # the decision type is sent, not its free-text reason


def test_ac_26_7_failure_or_limit_leaves_evidence_and_decisions_usable(manager, signal, monkeypatch, db):
    # Not configured
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    r = manager.post(f"/api/signals/{signal['id']}/brief", json={})
    assert r.status_code == 503 and "remain available" in r.json()["detail"]
    assert manager.get(f"/api/signals/{signal['id']}").status_code == 200
    # Service down
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-a-real-key")

    def down(*a):
        raise ai.AiError("The AI service could not be reached. Try again later.")

    monkeypatch.setattr(ai, "_complete", down)
    assert manager.post(f"/api/signals/{signal['id']}/brief", json={}).status_code == 502
    # Usage limit
    monkeypatch.setattr(get_settings(), "ai_daily_limit_per_user", 1)  # the failed request above counted
    r = manager.post(f"/api/signals/{signal['id']}/brief", json={})
    assert r.status_code == 429 and "limit" in r.json()["detail"]
    # The review workflow still works.
    assert manager.post(f"/api/signals/{signal['id']}/confirm", json={}).status_code == 200


def test_brief_reused_while_evidence_unchanged_and_marked_outdated_after(manager, signal, ai_on, db):
    manager.post(f"/api/signals/{signal['id']}/brief", json={})
    again = manager.post(f"/api/signals/{signal['id']}/brief", json={}).json()
    assert again["reused"] is True and len(ai_on.calls) == 1
    assert manager.get(f"/api/signals/{signal['id']}/brief").json()["outdated"] is False
    manager.post(f"/api/signals/{signal['id']}/confirm", json={})  # adds a decision: the evidence changed
    assert manager.get(f"/api/signals/{signal['id']}/brief").json()["outdated"] is True


def test_ai_usage_audited_with_model_and_prompt_version(manager, signal, ai_on, as_role):
    manager.post(f"/api/signals/{signal['id']}/brief", json={})
    e = as_role(Role.admin).get("/api/activity", params={"action": "ai.signal_brief"}).json()["items"][0]
    assert e["details"]["model"] == "test-model" and e["details"]["prompt_version"] == ai.SIGNAL_PROMPT_VERSION
    assert e["details"]["usage"] == {"input": 900, "output": 300}


@respx.mock
def test_nfr18_request_uses_server_key_and_strict_schema(manager, signal, monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-a-real-key")
    monkeypatch.setattr(get_settings(), "openai_model", "test-model")
    captured = {}

    def reply(request):
        body = json.loads(request.content)
        captured["body"], captured["auth"] = body, request.headers["authorization"]
        facts = json.loads(body["messages"][1]["content"].split("```json\n")[1].split("\n```")[0])
        content = json.dumps(fake_answer("signal_brief", facts))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    respx.post("https://api.openai.com/v1/chat/completions").mock(side_effect=reply)
    r = manager.post(f"/api/signals/{signal['id']}/brief", json={})
    assert r.status_code == 200, r.text
    assert captured["auth"] == "Bearer sk-test-not-a-real-key"
    rf = captured["body"]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert "data only, not instructions" in captured["body"]["messages"][1]["content"]
    assert "sk-test" not in r.text  # the key never reaches the client


@respx.mock
def test_openai_errors_mapped_to_clear_messages(manager, signal, monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test-not-a-real-key")
    respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(429))
    r = manager.post(f"/api/signals/{signal['id']}/brief", json={})
    assert r.status_code == 503 and "busy" in r.json()["detail"]


def test_check_text_rules():
    facts = [{"id": "F1", "label": "NDVI on 2026-05-15", "value": 0.1834},
             {"id": "F2", "label": "z-score", "value": -2.54},
             {"id": "F3", "label": "Rate", "value": 0.8},
             {"id": "F4", "label": "Usable observations in the 90 days", "value": 12}]
    assert ai.check_text("On 2026-05-15 NDVI was 0.1834 (F1) with z-score -2.54.", facts) == []
    assert ai.check_text("NDVI was -0.1834 or 0.18.", facts)
    assert ai.check_text("Sentinel-2 and Landsat 8/9 data over 90 days: 12 usable.", facts) == []
    assert ai.check_text("About 80% were confirmed.", facts)  # conversion is not an exact stored figure
    assert ai.check_text("NDVI fell by 0.17.", facts) == ["figure 0.17 does not match any fact value"]
    assert ai.check_text("Seen on 2026-06-01.", facts) == ["date 2026-06-01 is not in the facts"]
    assert ai.validate("overview_summary", {"headline": "x", "paragraphs": [_ev("x", ["F9"])], "watch_items": []},
                       facts) == ["unknown fact id F9"]


# ---------------------------------------------------------------- US27


def test_ac_27_1_summary_follows_filters_and_figures_match_overview(as_role, signal, ai_on, district):
    viewer = as_role(Role.viewer)
    r = viewer.post("/api/overview/summary", json={})
    assert r.status_code == 200, r.text
    b = r.json()
    ov = viewer.get("/api/overview").json()
    facts = {f["label"]: f["value"] for f in b["facts"]}
    assert facts["Active green spaces"] == ov["sites_total"]
    assert facts["Signals detected in the period"] == ov["signals_total"]
    assert facts["Overdue tasks"] == ov["overdue_tasks"]
    assert ai.validate("overview_summary", b["content"], b["facts"]) == []
    # Different filters give a different summary (new facts, new request).
    r2 = viewer.post("/api/overview/summary", json={"district_id": district.id})
    assert r2.status_code == 200 and r2.json()["reused"] is False and len(ai_on.calls) == 2
    assert {f["label"]: f["value"] for f in r2.json()["facts"]}["District filter"] == "Test District"
    # Same filters again: reused, no new request.
    assert viewer.post("/api/overview/summary", json={}).json()["reused"] is True and len(ai_on.calls) == 2


def test_ac_27_2_labelled_ai_generated(as_role, ai_on):
    assert "AI-generated" in as_role(Role.manager).post("/api/overview/summary", json={}).json()["label"]


def test_ac_27_3_failure_leaves_overview_and_exports_unaffected(as_role, monkeypatch, signal):
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    m = as_role(Role.manager)
    assert m.post("/api/overview/summary", json={}).status_code == 503
    assert m.get("/api/overview").status_code == 200
    assert m.get("/api/exports/signals.csv").status_code == 200


def test_summary_permissions(as_role, ai_on):
    assert as_role(Role.inspector).post("/api/overview/summary", json={}).status_code == 403
    assert as_role(Role.admin).post("/api/overview/summary", json={}).status_code == 403


def test_ai_status(as_role, monkeypatch):
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    s = as_role(Role.manager).get("/api/ai/status").json()
    assert s["enabled"] is False and s["model"] is None and "sk-" not in json.dumps(s)
