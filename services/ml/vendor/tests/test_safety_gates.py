"""Gates that protect learners.  These are the tests that must never be relaxed."""

from __future__ import annotations

import pytest

from edutrace.contract import RiskTier
from edutrace.conversation.safeguarding import Category, EscalationRecord, escalate
from edutrace.messaging import templates as tmpl
from edutrace.messaging.dispatcher import (
    Channel,
    Dispatcher,
    DispatcherSettings,
    MessageRejected,
)
from edutrace.messaging.encoding import plan, prepare
from edutrace.messaging.providers import ConsoleProvider
from edutrace.serve.audit import AuditLog, AuditViolation
from edutrace.serve.review import (
    OverrideReason,
    ReviewDecision,
    ReviewError,
    ReviewRequest,
    apply_review,
)


@pytest.fixture
def dispatcher():
    return Dispatcher(ConsoleProvider(echo=False), DispatcherSettings())


# --------------------------------------------------------------------------
# No contact without a human review
# --------------------------------------------------------------------------


def test_no_notification_without_review(dispatcher):
    p = dispatcher.plan(
        tier=RiskTier.HIGH, student_key="S1", school_id="SCH1", term="T1",
        guardian_msisdn="0244000000", text="School: Ama has missed 6 days.",
        review_completed=False,
    )
    assert p.channel is Channel.NONE
    assert "s.41" in (p.suppressed_reason or "")


def test_high_tier_creates_a_call_task(dispatcher):
    """SMS alone is a null result. The call is the intervention."""
    p = dispatcher.plan(
        tier=RiskTier.HIGH, student_key="S1", school_id="SCH1", term="T1",
        guardian_msisdn="0244000000", text="School: Ama has missed 6 days.",
        review_completed=True, assign_call_to="teacher.mensah",
    )
    assert p.channel is Channel.SMS_PLUS_CALL
    assert p.call_task is not None
    assert p.call_task.assigned_to == "teacher.mensah"


def test_elevated_tier_is_sms_only(dispatcher):
    p = dispatcher.plan(
        tier=RiskTier.ELEVATED, student_key="S1", school_id="SCH1", term="T1",
        guardian_msisdn="0244000000", text="School: Ama has missed 4 days.",
        review_completed=True,
    )
    assert p.channel is Channel.SMS
    assert p.call_task is None


def test_watch_tier_sends_nothing(dispatcher):
    p = dispatcher.plan(
        tier=RiskTier.WATCH, student_key="S1", school_id="SCH1", term="T1",
        guardian_msisdn="0244000000", text="anything", review_completed=True,
    )
    assert p.channel is Channel.NONE


def test_opt_out_is_honoured(dispatcher):
    dispatcher.opt_out("233244000000")
    p = dispatcher.plan(
        tier=RiskTier.HIGH, student_key="S1", school_id="SCH1", term="T1",
        guardian_msisdn="233244000000", text="School: Ama has missed 6 days.",
        review_completed=True,
    )
    assert p.channel is Channel.NONE
    assert "opted out" in (p.suppressed_reason or "")


def test_per_term_message_cap(dispatcher):
    args = dict(
        tier=RiskTier.ELEVATED, student_key="S9", school_id="SCH1", term="T2",
        guardian_msisdn="0244111111", text="School: Ama has missed 4 days.",
        review_completed=True,
    )
    for _ in range(dispatcher.settings.max_messages_per_learner_per_term):
        p = dispatcher.plan(**args)
        dispatcher.dispatch(p, "0244111111", "S9", "T2")
    p = dispatcher.plan(**args)
    assert p.channel is Channel.NONE
    assert "cap" in (p.suppressed_reason or "")


# --------------------------------------------------------------------------
# What a guardian may be told
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "Ama is at risk of dropping out.",
        "Ama has a 73% risk of leaving school.",
        "Ama has been flagged as high risk.",
        "Our system predicts Ama will drop out.",
        "Ama is ranked 4th for dropout risk.",
    ],
)
def test_guardian_messages_reject_risk_language(bad):
    with pytest.raises(MessageRejected):
        Dispatcher.validate_text(bad)


def test_factual_attendance_message_is_allowed():
    Dispatcher.validate_text(
        "Adjeikojo M/A JHS: Ama has missed 6 of the last 10 school days. "
        "Please call 0302123456."
    )


def test_all_templates_fit_one_segment():
    assert tmpl.check_all() == []


def test_templates_pass_the_content_filter():
    sample = dict(
        school="Adjeikojo M/A JHS", first_name="Ama", missed=6, total=10,
        phone="0302123456", count=3,
    )
    for t in tmpl.ALL_TEMPLATES:
        Dispatcher.validate_text(t.body.format(**sample))


# --------------------------------------------------------------------------
# Encoding
# --------------------------------------------------------------------------


def test_ghanaian_orthography_forces_ucs2_and_transliteration_fixes_it():
    twi = (
        "Mema wo akye. Yɛhunuu sɛ Kwame ammɛ sukuu nnansa yi. "
        "Yɛsrɛ wo frɛ sukuu no so, na yɛpɛ sɛ yɛboa."
    )
    assert plan(twi).encoding == "UCS-2"
    wire, seg = prepare(twi)
    assert seg.encoding == "GSM-7"
    assert seg.segments < plan(twi).segments or seg.segments == 1
    assert "ɛ" not in wire


def test_ascii_message_stays_gsm7():
    assert plan("Ama has missed 6 of the last 10 school days.").encoding == "GSM-7"


# --------------------------------------------------------------------------
# Review and override
# --------------------------------------------------------------------------


def test_override_requires_a_reason_code():
    with pytest.raises(ReviewError):
        apply_review(
            ReviewRequest(
                observation_id="o1", reviewer_id="r1",
                reviewer_role="class_teacher",
                decision=ReviewDecision.CONFIRM, adjust_tier_by=-1,
            ),
            RiskTier.HIGH, "S1",
        )


def test_dismiss_requires_a_reason_code():
    with pytest.raises(ReviewError):
        apply_review(
            ReviewRequest(
                observation_id="o1", reviewer_id="r1",
                reviewer_role="head_teacher", decision=ReviewDecision.DISMISS,
            ),
            RiskTier.HIGH, "S1",
        )


def test_override_is_bounded_to_one_step():
    """Two steps is not an override, it is a different model."""
    with pytest.raises(Exception):
        ReviewRequest(
            observation_id="o1", reviewer_id="r1", reviewer_role="head_teacher",
            decision=ReviewDecision.CONFIRM, adjust_tier_by=-2,
        )


def test_dismissal_blocks_notification():
    out = apply_review(
        ReviewRequest(
            observation_id="o1", reviewer_id="r1", reviewer_role="class_teacher",
            decision=ReviewDecision.DISMISS,
            reason=OverrideReason.ABSENCE_EXPLAINED_BEREAVEMENT,
        ),
        RiskTier.HIGH, "S1",
    )
    assert out.final_tier is RiskTier.LOW
    assert out.notification_unlocked is False
    assert out.overridden is True


def test_confirm_unlocks_notification():
    out = apply_review(
        ReviewRequest(
            observation_id="o1", reviewer_id="r1", reviewer_role="head_teacher",
            decision=ReviewDecision.CONFIRM,
        ),
        RiskTier.ELEVATED, "S1",
    )
    assert out.notification_unlocked is True
    assert out.overridden is False


# --------------------------------------------------------------------------
# Safeguarding: metadata only
# --------------------------------------------------------------------------


def test_escalation_record_has_no_content_field():
    with pytest.raises(Exception):
        EscalationRecord(
            student_key="S1", school_id="SCH1",
            category=Category.ABUSE_OR_NEGLECT, raised_by="t1",
            disclosure_text="the child said ...",
        )


def test_escalation_lists_required_referrals():
    rec = escalate("S1", "SCH1", Category.ABUSE_OR_NEGLECT, "t1")
    assert not rec.complete()
    assert "DEPT_SOCIAL_WELFARE" in [r.value for r in rec.missing_referrals()]
    assert "Act 560" in rec.guidance()


def test_pregnancy_is_a_continuation_not_an_exit():
    rec = escalate("S1", "SCH1", Category.PREGNANCY_OR_PARENTING, "t1")
    g = rec.guidance().lower()
    assert "stays enrolled" in g
    assert "not treat this as an exit" in g


def test_audit_log_refuses_disclosure_content(tmp_path):
    a = AuditLog(tmp_path / "audit.jsonl", fsync=False)
    a.append("score.single", student_key="S1", tier="HIGH")
    with pytest.raises(AuditViolation):
        a.append("safeguarding", student_key="S1", disclosure_text="...")
    with pytest.raises(AuditViolation):
        a.append("score.single", student_key="S1", guardian_msisdn="0244000000")
    assert a.count() == 1


def test_needs_profile_does_not_carry_a_score():
    from edutrace.conversation.protocol import Domain, Finding, NeedsProfile

    p = NeedsProfile(
        student_key="S1", school_id="SCH1", conducted_by="t1",
        findings=[Finding(prompt_id="cost", domain=Domain.COST, present=True)],
    )
    assert not hasattr(p, "score")
    assert p.not_a_diagnosis is True
    assert any("levy" in a.lower() or "capitation" in a.lower()
               for a in p.suggested_actions())
