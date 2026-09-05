"""Guardian and staff message templates.

Guardian messages state an **attendance fact** and extend an **invitation**.
They never contain a risk score, a tier, a ranking, or the word "dropout".
Three reasons, in increasing order of importance:

1.  It is what worked.  Bergman & Chan's parent text-message trial -- course
    failures down 27%, class attendance up 12% -- sent specific, factual
    information about missed work and absences, not risk assessments.  Rogers &
    Feller's absence nudges, which cut chronic absenteeism 10-15% across
    100,000+ families, worked by correcting parents' *underestimate of how much
    school their child had missed*.  The fact is the active ingredient.
2.  A percentage is not decodable.  The Ghana parental-nudge trial found
    simple-English SMS was null on average and negative for the 65% of
    caregivers with no formal schooling.  A probability will not survive that.
3.  Telling a family their child is a predicted dropout is a labelling harm
    with no offsetting benefit.  Nothing in the message should be something a
    guardian could repeat to the child as an accusation.

Templates are short by design: under 160 GSM-7 septets keeps every message to
one segment.  ``check_all`` verifies that at import-review time rather than at
2am on the first real send.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contract import RiskTier
from .encoding import Segmentation, prepare


@dataclass(frozen=True, slots=True)
class Template:
    key: str
    audience: str
    body: str
    max_segments: int = 1

    def render(self, **kw) -> tuple[str, Segmentation]:
        return prepare(self.body.format(**kw))


GUARDIAN_ATTENDANCE = Template(
    key="guardian.attendance",
    audience="guardian",
    body=(
        "{school}: {first_name} has missed {missed} of the last {total} school "
        "days. Please call {phone} or come by, we want to help. "
        "Reply STOP to opt out."
    ),
)

GUARDIAN_LEVIES = Template(
    key="guardian.levies",
    audience="guardian",
    body=(
        "{school}: we would like to talk about {first_name}'s school costs. "
        "Support may be available. Please call {phone}. Reply STOP to opt out."
    ),
)

GUARDIAN_BECE = Template(
    key="guardian.bece",
    audience="guardian",
    body=(
        "{school}: {first_name} is not yet registered for the BECE. "
        "Registration closes soon. Please call {phone} this week. "
        "Reply STOP to opt out."
    ),
)

GUARDIAN_INVITE = Template(
    key="guardian.invite",
    audience="guardian",
    body=(
        "{school}: we would like a short meeting about {first_name}'s "
        "schooling. Please call {phone} to arrange a time. "
        "Reply STOP to opt out."
    ),
)

STAFF_CALL_TASK = Template(
    key="staff.call_task",
    audience="staff",
    body=(
        "EduTrace: {count} learner(s) at {school} need a call this week. "
        "Open the review list before Friday."
    ),
)

ALL_TEMPLATES = (
    GUARDIAN_ATTENDANCE,
    GUARDIAN_LEVIES,
    GUARDIAN_BECE,
    GUARDIAN_INVITE,
    STAFF_CALL_TASK,
)


#: Which template a driver implies.  Ordered: the most specific, most
#: actionable fact wins, because specificity is what the RCT evidence says
#: carries the effect.
DRIVER_TO_TEMPLATE = {
    "exam registration": GUARDIAN_BECE,
    "attendance and absence pattern": GUARDIAN_ATTENDANCE,
    "cost of staying in school": GUARDIAN_LEVIES,
}


def select(tier: RiskTier, driver_labels: list[str]) -> Template:
    """Pick the template matching the strongest actionable driver."""
    for label in driver_labels:
        t = DRIVER_TO_TEMPLATE.get(label)
        if t is not None:
            return t
    return GUARDIAN_INVITE


_SAMPLE = {
    "school": "Adjeikojo M/A JHS",
    "first_name": "Ama",
    "missed": 6,
    "total": 10,
    "phone": "0302123456",
    "count": 7,
}


def check_all() -> list[str]:
    """Verify every template fits one segment with realistic substitutions."""
    problems = []
    for t in ALL_TEMPLATES:
        text, seg = t.render(**_SAMPLE)
        if seg.segments > t.max_segments:
            problems.append(
                f"{t.key}: {seg.segments} segments ({seg.units} {seg.encoding} "
                f"units) exceeds max {t.max_segments} -- {text!r}"
            )
    return problems


__all__ = [
    "Template",
    "ALL_TEMPLATES",
    "GUARDIAN_ATTENDANCE",
    "GUARDIAN_LEVIES",
    "GUARDIAN_BECE",
    "GUARDIAN_INVITE",
    "STAFF_CALL_TASK",
    "select",
    "check_all",
]
