"""The human-review gate, and the bounded override.

Two things are enforced here, and both are load-bearing.

**No contact without review.**  Ghana's Data Protection Act 2012 s.41 lets a
data subject require by written notice that a significant decision about them
not be taken solely by automatic means.  A dropout flag that triggers a message
to a guardian is exactly such a decision.  So a named member of staff must open
the assessment and record a decision before any outbound notification can be
sent, and the audit log records who and when.  The gate is a legal control that
happens to also be good practice, not a UX preference that happens to be legal.

**Overrides are bounded and reason-coded.**  Teachers know things the data does
not -- a bereavement, a pregnancy, a family that has already moved.  The
risk-assessment literature calls this structured professional judgement, and it
also documents the failure mode: unbounded clinical overrides frequently
*degrade* predictive accuracy and encode bias rather than information.  So an
override may move the tier by one step, must carry a reason from a fixed list,
and is logged so that override accuracy can be audited against realised
outcomes -- by sex, by region, by school, annually.  A staff member whose
dismissals are systematically wrong for one group is a finding, not an
accusation, and the system should be able to produce it.

The questionnaire score from a support conversation is deliberately *not*
blended into the model score.  Two channels stay separate: the actuarial
estimate says who to look at; the conversation says what to do.  Feeding
teacher perception back into the risk number creates a loop in which the
model's ground truth becomes the teacher's opinion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..contract import RiskTier

_TIER_ORDER = [RiskTier.LOW, RiskTier.WATCH, RiskTier.ELEVATED, RiskTier.HIGH]


class ReviewDecision(str, Enum):
    CONFIRM = "CONFIRM"          # the flag matches what staff see
    DISMISS = "DISMISS"          # staff have information the data lacks
    ESCALATE = "ESCALATE"        # staff judge the risk higher than modelled
    DEFER = "DEFER"              # not enough information yet


class OverrideReason(str, Enum):
    """Fixed list.  Free text would defeat the point of auditing overrides."""

    ALREADY_TRANSFERRED = "ALREADY_TRANSFERRED"
    ABSENCE_EXPLAINED_ILLNESS = "ABSENCE_EXPLAINED_ILLNESS"
    ABSENCE_EXPLAINED_BEREAVEMENT = "ABSENCE_EXPLAINED_BEREAVEMENT"
    ABSENCE_EXPLAINED_TRAVEL = "ABSENCE_EXPLAINED_TRAVEL"
    SUPPORT_ALREADY_IN_PLACE = "SUPPORT_ALREADY_IN_PLACE"
    LEVIES_WAIVED = "LEVIES_WAIVED"
    DATA_ENTRY_ERROR = "DATA_ENTRY_ERROR"
    STAFF_CONCERN_NOT_IN_DATA = "STAFF_CONCERN_NOT_IN_DATA"
    HOUSEHOLD_CIRCUMSTANCES_CHANGED = "HOUSEHOLD_CIRCUMSTANCES_CHANGED"
    OTHER_RECORDED_OFFLINE = "OTHER_RECORDED_OFFLINE"


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    reviewer_id: str = Field(min_length=1, max_length=64)
    reviewer_role: Literal[
        "class_teacher", "head_teacher", "guidance_coordinator", "district_officer"
    ]
    decision: ReviewDecision
    reason: OverrideReason | None = None
    #: Optional one-step tier adjustment. Two steps is not an override, it is a
    #: different model, and should be raised as a data-quality issue instead.
    adjust_tier_by: int = Field(default=0, ge=-1, le=1)
    note: str = Field(
        default="",
        max_length=500,
        description="Operational note only. Never record disclosures about "
        "abuse, self-harm, pregnancy, or health here -- those follow the "
        "safeguarding escalation path, which stores metadata, not content.",
    )


class ReviewOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    student_key: str
    model_tier: RiskTier
    final_tier: RiskTier
    overridden: bool
    decision: ReviewDecision
    reason: OverrideReason | None
    reviewer_id: str
    reviewer_role: str
    reviewed_at: datetime
    notification_unlocked: bool


class ReviewError(ValueError):
    pass


def apply_review(
    request: ReviewRequest, model_tier: RiskTier, student_key: str
) -> ReviewOutcome:
    if request.adjust_tier_by != 0 and request.reason is None:
        raise ReviewError(
            "A tier adjustment requires a reason code. Unreasoned overrides "
            "cannot be audited, and the override literature is clear that "
            "unaudited overrides tend to encode bias rather than information."
        )
    if request.decision is ReviewDecision.DISMISS and request.reason is None:
        raise ReviewError("Dismissing a flag requires a reason code.")

    idx = _TIER_ORDER.index(model_tier)
    final = _TIER_ORDER[
        max(0, min(len(_TIER_ORDER) - 1, idx + request.adjust_tier_by))
    ]
    if request.decision is ReviewDecision.DISMISS:
        final = RiskTier.LOW

    return ReviewOutcome(
        observation_id=request.observation_id,
        student_key=student_key,
        model_tier=model_tier,
        final_tier=final,
        overridden=final is not model_tier,
        decision=request.decision,
        reason=request.reason,
        reviewer_id=request.reviewer_id,
        reviewer_role=request.reviewer_role,
        reviewed_at=datetime.now(timezone.utc),
        # Only a confirmed or escalated flag unlocks contact with a guardian.
        notification_unlocked=request.decision
        in (ReviewDecision.CONFIRM, ReviewDecision.ESCALATE),
    )


__all__ = [
    "ReviewDecision",
    "OverrideReason",
    "ReviewRequest",
    "ReviewOutcome",
    "ReviewError",
    "apply_review",
]
