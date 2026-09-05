"""End-to-end HTTP flow: score -> review -> notify, and the gate in between."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from edutrace.contract import RiskTier


@pytest.fixture
def client(bundle, tmp_path, monkeypatch):
    from edutrace.messaging import Dispatcher
    from edutrace.messaging.providers import ConsoleProvider
    from edutrace.serve import app as app_mod
    from edutrace.serve.audit import AuditLog
    from edutrace.serve.scorer import Scorer

    app_mod.RT.bundle = bundle
    app_mod.RT.scorer = Scorer(bundle)
    app_mod.RT.audit = AuditLog(tmp_path / "audit.jsonl", fsync=False)
    app_mod.RT.dispatcher = Dispatcher(
        ConsoleProvider(echo=False), audit=app_mod.RT.audit
    )
    app_mod.RT.store = app_mod.Store()
    with TestClient(app_mod.app) as c:
        # TestClient runs lifespan, which reloads from disk; put ours back.
        app_mod.RT.bundle = bundle
        app_mod.RT.scorer = Scorer(bundle)
        app_mod.RT.audit = AuditLog(tmp_path / "audit.jsonl", fsync=False)
        app_mod.RT.dispatcher = Dispatcher(
            ConsoleProvider(echo=False), audit=app_mod.RT.audit
        )
        app_mod.RT.store = app_mod.Store()
        yield c


HIGH_RISK = dict(
    student_key="S-API-1", school_id="SCH001", academic_year=2024, term="T3",
    week=6, grade_level="JHS3", attendance_rate_term_to_date=22.0,
    attendance_rate_last_4w=15.0, attendance_trend_4w=-9.0,
    consecutive_absences=12, longest_absence_streak_term=14,
    absences_prior_year=52, attendance_rate_prior_term=48.0,
    avg_exam_score=27.0, avg_exam_score_prev_term=41.0,
    assessment_completion_rate=18.0, core_subject_failures=4,
    age_years=17.0, repeated_a_grade=True, bece_registered=False,
    fee_status="UNPAID", fee_arrears_terms=3, has_textbooks=False,
    has_uniform=False, siblings_in_school=4, does_paid_or_farm_work=True,
    guardian_type="RELATIVE", distance_band="OVER_60_MIN",
    behaviour_flag="MINOR", behaviour_incidents_term=2,
    health_absence_days_term=4, sex="M", region="Savannah", poverty_quintile=1,
)

LOW_RISK = dict(
    student_key="S-API-2", school_id="SCH001", academic_year=2024, term="T1",
    week=4, grade_level="JHS1", attendance_rate_term_to_date=98.0,
    attendance_rate_last_4w=99.0, attendance_trend_4w=0.5,
    consecutive_absences=0, avg_exam_score=78.0,
    assessment_completion_rate=96.0, core_subject_failures=0, age_years=12.0,
    fee_status="PAID_IN_FULL", fee_arrears_terms=0, has_textbooks=True,
    has_uniform=True, distance_band="UNDER_15_MIN",
)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["model_loaded"] is True


def test_model_card_states_provenance_and_scope(client):
    card = client.get("/model-card").json()
    assert "SIMULATED" in card["data_provenance"].upper()
    assert card["out_of_scope"], "a model card without out-of-scope uses is decoration"
    assert any("review" in s.lower() for s in card["out_of_scope"])
    assert card["known_limitations"]


def test_score_returns_an_explanation(client):
    r = client.post("/v1/score", json=HIGH_RISK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert 0.0 < body["risk"] <= 0.95
    assert body["tier"] in {t.value for t in RiskTier}
    assert body["narrative"]
    assert body["contract_fingerprint"]
    assert body["latency_ms"] is not None


def test_low_risk_learner_needs_no_review(client):
    body = client.post("/v1/score", json=LOW_RISK).json()
    assert body["tier"] == RiskTier.LOW.value
    assert body["requires_human_review"] is False


def test_notify_is_blocked_until_reviewed(client):
    obs = client.post("/v1/score", json=HIGH_RISK).json()
    r = client.post(
        "/v1/notify",
        json={
            "observation_id": obs["observation_id"],
            "guardian_msisdn": "0244000111",
            "first_name": "Kofi",
            "school_name": "Adjeikojo M/A JHS",
            "school_phone": "0302123456",
            "term": "T3",
            "missed_days": 8,
            "of_last_days": 10,
        },
    ).json()
    assert r["channel"] == "NONE"
    assert "s.41" in r["suppressed_reason"]


def test_full_flow_score_review_notify(client):
    obs = client.post("/v1/score", json=HIGH_RISK).json()
    assert obs["requires_human_review"] is True

    rev = client.post(
        "/v1/review",
        json={
            "observation_id": obs["observation_id"],
            "reviewer_id": "head.owusu",
            "reviewer_role": "head_teacher",
            "decision": "CONFIRM",
        },
    )
    assert rev.status_code == 200, rev.text
    assert rev.json()["notification_unlocked"] is True

    note = client.post(
        "/v1/notify",
        json={
            "observation_id": obs["observation_id"],
            "guardian_msisdn": "0244000111",
            "first_name": "Kofi",
            "school_name": "Adjeikojo M/A JHS",
            "school_phone": "0302123456",
            "term": "T3",
            "missed_days": 8,
            "of_last_days": 10,
            "assign_call_to": "teacher.mensah",
        },
    ).json()
    assert note["channel"] in {"SMS", "SMS_PLUS_CALL"}
    assert note["accepted"] is True
    assert note["segments"] == 1
    assert note["encoding"] == "GSM-7"
    text = note["text"].lower()
    for banned in ("dropout", "drop out", "risk", "%"):
        assert banned not in text


def test_dismissed_flag_cannot_notify(client):
    obs = client.post("/v1/score", json=HIGH_RISK).json()
    client.post(
        "/v1/review",
        json={
            "observation_id": obs["observation_id"],
            "reviewer_id": "t1", "reviewer_role": "class_teacher",
            "decision": "DISMISS", "reason": "ALREADY_TRANSFERRED",
        },
    )
    note = client.post(
        "/v1/notify",
        json={
            "observation_id": obs["observation_id"],
            "guardian_msisdn": "0244000111", "first_name": "Kofi",
            "school_name": "X JHS", "school_phone": "0302123456", "term": "T3",
        },
    ).json()
    assert note["channel"] == "NONE"


def test_review_of_unknown_observation_404s(client):
    r = client.post(
        "/v1/review",
        json={
            "observation_id": "does-not-exist", "reviewer_id": "t1",
            "reviewer_role": "class_teacher", "decision": "CONFIRM",
        },
    )
    assert r.status_code == 404


def test_unreasoned_override_is_rejected(client):
    obs = client.post("/v1/score", json=HIGH_RISK).json()
    r = client.post(
        "/v1/review",
        json={
            "observation_id": obs["observation_id"], "reviewer_id": "t1",
            "reviewer_role": "class_teacher", "decision": "CONFIRM",
            "adjust_tier_by": -1,
        },
    )
    assert r.status_code == 422
    assert "reason code" in r.json()["detail"]


def test_batch_scoring_respects_capacity(client, panel):
    csv = panel.head(3000).to_csv(index=False)
    r = client.post(
        "/v1/score/batch?capacity=25",
        files={"file": ("cohort.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["rows_scored"] == 3000
    assert len(body["worklist"]) <= 25
    assert "capacity" in body["guidance"]
    risks = [a["risk"] for a in body["worklist"]]
    assert risks == sorted(risks, reverse=True)


def test_conversation_guide_is_not_a_psychometric(client):
    g = client.get("/v1/conversation/guide").json()
    assert g["not_a_psychometric_assessment"] is True
    assert g["prompts"]
    for p in g["prompts"]:
        assert p["ask"].endswith("?") or p["ask"].endswith(".")
        assert p["actions"]
    assert "safety" in g["confidentiality_script"].lower()


def test_safeguarding_escalation_stores_no_content(client):
    r = client.post(
        "/v1/safeguarding/escalate",
        json={
            "student_key": "S-API-1", "school_id": "SCH001",
            "category": "ABUSE_OR_NEGLECT", "raised_by": "teacher.mensah",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["conversation_stopped"] is True
    assert "DEPT_SOCIAL_WELFARE" in body["required_referrals"]

    # And the extra-field guard: no free-text may be submitted at all.
    r2 = client.post(
        "/v1/safeguarding/escalate",
        json={
            "student_key": "S-API-1", "school_id": "SCH001",
            "category": "ABUSE_OR_NEGLECT", "raised_by": "t1",
            "detail": "the learner said ...",
        },
    )
    assert r2.status_code == 422


def test_needs_profile_does_not_affect_risk(client):
    r = client.post(
        "/v1/conversation/profile",
        json={
            "profile": {
                "student_key": "S-API-1", "school_id": "SCH001",
                "conducted_by": "teacher.mensah",
                "findings": [
                    {"prompt_id": "cost", "domain": "COST", "present": True}
                ],
                "agreed_actions": ["Levy waiver referral"],
            }
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["affects_risk_score"] is False
    assert r.json()["suggested_actions"]


def test_audit_log_records_the_chain(client, tmp_path):
    from edutrace.serve import app as app_mod

    obs = client.post("/v1/score", json=HIGH_RISK).json()
    client.post(
        "/v1/review",
        json={
            "observation_id": obs["observation_id"], "reviewer_id": "head.owusu",
            "reviewer_role": "head_teacher", "decision": "CONFIRM",
        },
    )
    events = [e["event"] for e in app_mod.RT.audit.read()]
    assert "score.single" in events
    assert "review.recorded" in events
    for rec in app_mod.RT.audit.read():
        assert "guardian_msisdn" not in rec
        assert "student_name" not in rec
