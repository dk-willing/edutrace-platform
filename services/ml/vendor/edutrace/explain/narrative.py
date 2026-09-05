"""Plain-language explanation, generated from attribution + recourse.

Deterministic templates, no language model.  Three reasons: a teacher-facing
safety-critical string must be reproducible and reviewable; an LLM adds latency
to a hot path measured in milliseconds; and a generated sentence can assert a
causal claim the model never evaluated.

House style, enforced by tests:

* Comparative, never causal.  "resembles learners who", not "because of".
* No number a reader could mistake for certainty about this child.  The
  probability is stated once, as a rate over similar learners.
* Ends on an action, never on a label.
* Never names a protected attribute -- they are not model inputs, so they
  cannot appear as drivers, and the narrative asserts nothing about them.
* Never addresses or describes the learner.  The reader is a teacher.
"""

from __future__ import annotations

from ..contract import RiskTier
from ..records import Driver, RecourseStep

_TIER_OPENING = {
    RiskTier.HIGH: (
        "This learner's record is among the most concerning in the year group "
        "this week."
    ),
    RiskTier.ELEVATED: (
        "This learner's record stands out from the year group this week."
    ),
    RiskTier.WATCH: (
        "This learner is worth keeping an eye on, though nothing here is urgent."
    ),
    RiskTier.LOW: (
        "Nothing in this learner's record stands out this week."
    ),
}

_TIER_CLOSING = {
    RiskTier.HIGH: (
        "Please review before the end of the week and decide whether a "
        "conversation is warranted."
    ),
    RiskTier.ELEVATED: (
        "Worth a short check-in when you next have the chance."
    ),
    RiskTier.WATCH: (
        "No action needed yet -- this is context for your next class review."
    ),
    RiskTier.LOW: "",
}


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _rate_phrase(p: float) -> str:
    """State the probability as a frequency over similar learners.

    "About 1 in 8 learners with a similar record left within eight weeks" is
    understood correctly far more often than "12.4% risk", which reads as a
    property of this child rather than of a reference class.
    """
    if p <= 0:
        return "very few learners with a similar record"
    denom = max(2, round(1.0 / max(p, 1e-6)))
    if denom > 200:
        return "a very small share of learners with a similar record"
    return f"about 1 in {denom} learners with a similar record"


def compose(
    tier: RiskTier,
    risk: float,
    raising: list[Driver],
    lowering: list[Driver],
    recourse: list[RecourseStep],
    horizon_weeks: int = 8,
) -> str:
    parts: list[str] = [_TIER_OPENING[tier]]

    if raising:
        drivers_txt = _join([d.label for d in raising])
        parts.append(
            f"What the model is weighing most heavily: {drivers_txt}. "
            f"Over past cohorts, {_rate_phrase(risk)} stopped attending within "
            f"{horizon_weeks} weeks."
        )
    elif tier is not RiskTier.LOW:
        parts.append(
            "No single factor dominates -- the estimate reflects the overall "
            "pattern rather than one standout problem."
        )

    if lowering:
        parts.append(
            f"Working in the learner's favour: {_join([d.label for d in lowering])}."
        )

    if recourse:
        step = recourse[0]
        if step.feasible:
            parts.append(
                f"Most tractable change: {step.note} On that alone the "
                f"model's estimate would drop to about {step.projected_risk:.0%} "
                f"and move the learner down a tier."
            )
        else:
            parts.append(step.note)

    closing = _TIER_CLOSING[tier]
    if closing:
        parts.append(closing)

    if tier in (RiskTier.HIGH, RiskTier.ELEVATED):
        parts.append(
            "This is a pattern in the data, not a judgement about the learner, "
            "and it should not be shared with them."
        )
    return " ".join(p for p in parts if p)


__all__ = ["compose"]
