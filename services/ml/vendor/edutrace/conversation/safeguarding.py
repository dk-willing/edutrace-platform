"""Safeguarding escalation.  Metadata only, never content.

If a learner discloses abuse, self-harm, exploitation or pregnancy during a
support conversation, three things must happen and one must not.

Must happen:

1.  The conversation **stops**.  The teacher is a first responder and a
    connector, not a counsellor, and continuing to ask is probing for trauma
    detail -- the thing WHO Psychological First Aid explicitly tells
    non-specialists not to do.
2.  The escalation ladder is displayed with named, local contacts:
    class teacher -> head teacher -> school Guidance & Counselling coordinator
    -> District G&C coordinator (Ghana Education Service maintains coordinators
    across districts and regions) -> Department of Social Welfare / DOVVSU.
    Ghana's Children's Act 1998 (Act 560) creates a broad duty: any person with
    information about a child in need of care and protection reports it, and a
    complaint may be made without parental consent.
3.  A record is written that an escalation was raised, of what category, by
    whom, to whom, and when.

Must NOT happen: the **content** is not stored.  Not in the case file, not in
the audit log, and above all not in the feature store or any training set.
Under Act 843 s.37, health data and data concerning a child under parental
control are special personal data.  A narrative disclosure about abuse sitting
in a row that a model later trains on is the worst outcome this system could
produce, and it happens by default unless something prevents it.  So the record
type here has no free-text field at all -- the guard is structural, not a
policy note.

Pregnancy is handled as a *continuation* case, not an exit case.  Ghana's 2018
Guidelines for Prevention of Pregnancy Among School Girls and Facilitation of
Re-Entry into School After Childbirth provide that a pregnant learner remains
in school unless her condition prevents it, with maternity leave and a right to
return.  The system's job is to make the re-entry pathway visible, never to
close the case.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Category(str, Enum):
    """Deliberately coarse.  Precision here would be a content field."""

    IMMEDIATE_SAFETY = "IMMEDIATE_SAFETY"
    HARM_TO_SELF = "HARM_TO_SELF"
    ABUSE_OR_NEGLECT = "ABUSE_OR_NEGLECT"
    EXPLOITATION_OR_CHILD_LABOUR = "EXPLOITATION_OR_CHILD_LABOUR"
    PREGNANCY_OR_PARENTING = "PREGNANCY_OR_PARENTING"
    HEALTH_NEEDS_REFERRAL = "HEALTH_NEEDS_REFERRAL"
    OTHER_WELFARE_CONCERN = "OTHER_WELFARE_CONCERN"


class Referral(str, Enum):
    HEAD_TEACHER = "HEAD_TEACHER"
    SCHOOL_GC_COORDINATOR = "SCHOOL_GC_COORDINATOR"
    DISTRICT_GC_COORDINATOR = "DISTRICT_GC_COORDINATOR"
    SOCIAL_WELFARE = "DEPT_SOCIAL_WELFARE"
    DOVVSU = "POLICE_DOVVSU"
    HEALTH_SERVICE = "GHANA_HEALTH_SERVICE"


#: Minimum referral set per category.  The app renders these as a checklist the
#: teacher must complete, not as advice they may take.
REQUIRED_REFERRALS: dict[Category, tuple[Referral, ...]] = {
    Category.IMMEDIATE_SAFETY: (
        Referral.HEAD_TEACHER, Referral.SOCIAL_WELFARE, Referral.DOVVSU,
    ),
    Category.HARM_TO_SELF: (
        Referral.HEAD_TEACHER, Referral.SCHOOL_GC_COORDINATOR,
        Referral.HEALTH_SERVICE,
    ),
    Category.ABUSE_OR_NEGLECT: (
        Referral.HEAD_TEACHER, Referral.SOCIAL_WELFARE, Referral.DOVVSU,
    ),
    Category.EXPLOITATION_OR_CHILD_LABOUR: (
        Referral.HEAD_TEACHER, Referral.SOCIAL_WELFARE,
    ),
    Category.PREGNANCY_OR_PARENTING: (
        Referral.HEAD_TEACHER, Referral.SCHOOL_GC_COORDINATOR,
        Referral.HEALTH_SERVICE,
    ),
    Category.HEALTH_NEEDS_REFERRAL: (
        Referral.SCHOOL_GC_COORDINATOR, Referral.HEALTH_SERVICE,
    ),
    Category.OTHER_WELFARE_CONCERN: (
        Referral.HEAD_TEACHER, Referral.SCHOOL_GC_COORDINATOR,
    ),
}

GUIDANCE: dict[Category, str] = {
    Category.IMMEDIATE_SAFETY:
        "Do not send the learner home. Stay with them, get the head teacher "
        "now, and contact Social Welfare and DOVVSU today.",
    Category.HARM_TO_SELF:
        "Stay with the learner. Do not leave them alone and do not promise "
        "secrecy. Get the head teacher and the G&C coordinator now.",
    Category.ABUSE_OR_NEGLECT:
        "Stop the conversation. Do not question the learner further, do not "
        "contact the family, and do not investigate -- that is Social "
        "Welfare's role, and questioning can compromise their process. Report "
        "today under Act 560.",
    Category.EXPLOITATION_OR_CHILD_LABOUR:
        "Report to the head teacher and Social Welfare. Keep the learner "
        "enrolled while the referral proceeds.",
    Category.PREGNANCY_OR_PARENTING:
        "The learner stays enrolled. Under the 2018 Re-Entry Guidelines she "
        "has a right to continue and to return after childbirth, with "
        "maternity leave. Arrange health referral and a continuation plan; do "
        "not treat this as an exit.",
    Category.HEALTH_NEEDS_REFERRAL:
        "Refer to the school nurse or nearest CHPS compound. Inform the "
        "guardian with the learner's knowledge.",
    Category.OTHER_WELFARE_CONCERN:
        "Raise with the head teacher and agree who follows up and by when.",
}


class EscalationRecord(BaseModel):
    """What is stored.  Note the absence of any free-text field.

    ``model_config`` forbids extra keys, so a future contributor cannot add a
    ``details`` field to this model from a call site. The only way to store
    disclosure content is to deliberately edit this class, which is a code
    review someone will see.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    student_key: str
    school_id: str
    category: Category
    raised_by: str
    raised_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    referred_to: list[Referral] = Field(default_factory=list)
    conversation_stopped: bool = True
    learner_informed: bool = Field(
        default=True,
        description="Whether the learner was told, before the disclosure, that "
        "safety concerns must be passed on. They should always have been.",
    )
    follow_up_due: str | None = None

    def missing_referrals(self) -> list[Referral]:
        required = set(REQUIRED_REFERRALS.get(self.category, ()))
        return sorted(required - set(self.referred_to), key=lambda r: r.value)

    def complete(self) -> bool:
        return not self.missing_referrals()

    def guidance(self) -> str:
        return GUIDANCE[self.category]


def escalate(
    student_key: str,
    school_id: str,
    category: Category,
    raised_by: str,
    audit=None,
) -> EscalationRecord:
    rec = EscalationRecord(
        student_key=student_key,
        school_id=school_id,
        category=category,
        raised_by=raised_by,
    )
    if audit is not None:
        # Category, who, when. Nothing about what was said.
        audit.append(
            "safeguarding.escalation_raised",
            student_key=student_key,
            school_id=school_id,
            category=category.value,
            raised_by=raised_by,
            required_referrals=[r.value for r in REQUIRED_REFERRALS[category]],
        )
    return rec


__all__ = [
    "Category",
    "Referral",
    "REQUIRED_REFERRALS",
    "GUIDANCE",
    "EscalationRecord",
    "escalate",
]
