"""TreeSHAP attribution, ranked and filtered for a human reader.

Exact Shapley values via XGBoost's native ``pred_contribs`` (the same C++
TreeSHAP the ``shap`` package calls, without the extra dependency).

Three guard rails, each for a documented reason.

*Only the ranking is shown, never the numbers.*  SHAP magnitudes are routinely
misread as effect sizes.  They are log-odds contributions from one model on one
row; the ordering is the part that survives contact with a non-specialist.

*Correlated features are collapsed.*  Attendance-term-to-date, attendance-last-
4-weeks and the absence streak are near-collinear, and TreeSHAP splits credit
between them arbitrarily.  Reporting them as three separate "drivers" makes one
signal look like three converging ones.  They are grouped into a single theme
before ranking.

*Nothing is described as a cause.*  Every phrase is comparative -- "resembles
learners who", "is associated with" -- because SHAP explains the model, not the
world, and a teacher who reads "unpaid levies caused this risk" will act on a
counterfactual the model never evaluated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..contract import ACTIONABLE_FEATURES, FEATURE_LABELS, FEATURE_ORDER
from ..records import Driver

#: Near-collinear features collapsed into one theme before ranking, so a single
#: underlying signal is not reported three times.
THEMES: dict[str, tuple[str, ...]] = {
    "attendance": (
        "attendance_rate_term_to_date",
        "attendance_rate_last_4w",
        "attendance_trend_4w",
        "consecutive_absences",
        "longest_absence_streak_term",
        "absences_prior_year",
        "attendance_rate_prior_term",
    ),
    "achievement": (
        "exam_percentile_in_grade",
        "exam_score_delta_prev_term",
        "assessment_completion_rate",
        "core_subject_failures",
    ),
    "household cost pressure": (
        "fee_status_ord",
        "fee_arrears_terms",
        "has_textbooks",
        "has_uniform",
    ),
    "work and care outside school": (
        "does_paid_or_farm_work",
        "siblings_in_school",
        "guardian_type_ord",
    ),
    "journey to school": ("distance_band_ord", "distance_x_rainy_term"),
    "progression": (
        "age_for_grade_gap",
        "repeated_a_grade",
        "school_transfers_count",
        "grade_ordinal",
    ),
    "behaviour record": ("behaviour_incidents_term", "behaviour_severity_max"),
    "health": ("health_absence_days_term",),
    "exam registration": ("bece_registered",),
    "point in the year": ("term_ordinal", "week", "weeks_elapsed_in_year"),
}

_FEATURE_TO_THEME = {f: theme for theme, feats in THEMES.items() for f in feats}

THEME_LABELS: dict[str, str] = {
    "attendance": "attendance and absence pattern",
    "achievement": "classwork and exam standing",
    "household cost pressure": "cost of staying in school",
    "work and care outside school": "work and responsibilities outside school",
    "journey to school": "the journey to school",
    "progression": "progression through the year groups",
    "behaviour record": "recorded behaviour",
    "health": "illness-related absence",
    "exam registration": "BECE registration",
    "point in the year": "where we are in the school year",
}

#: A theme is actionable if a school can plausibly change it this term.
ACTIONABLE_THEMES = frozenset(
    {
        "attendance",
        "achievement",
        "household cost pressure",
        "behaviour record",
        "exam registration",
    }
)

#: Themes suppressed from the displayed drivers.
#:
#: ``point in the year`` is term, week and weeks-elapsed.  Every learner scored
#: in the same run shares those values exactly, so the theme carries *zero*
#: information for ranking one learner against another -- yet it can dominate
#: SHAP, because the baseline hazard really does spike in JHS3 Term 3 and the
#: booster spends a lot of its budget encoding that.  Reporting it as this
#: child's top "driver" is worse than useless: a head teacher reads "the reason
#: is where we are in the school year" and correctly concludes the system has
#: nothing to say.  It belongs in the cohort-level view, not the learner card.
CONTEXT_THEMES = frozenset({"point in the year"})


@dataclass(slots=True)
class Attribution:
    base_value: float
    per_feature: dict[str, float]
    per_theme: dict[str, float]

    def top(self, n: int = 4, sign: int = +1) -> list[tuple[str, float]]:
        items = [
            (k, v)
            for k, v in self.per_theme.items()
            if np.sign(v) == sign and k not in CONTEXT_THEMES
        ]
        items.sort(key=lambda kv: -abs(kv[1]))
        return items[:n]


def attribute(contribs_row: np.ndarray) -> Attribution:
    """Turn one row of ``pred_contribs`` output into a themed attribution."""
    per_feature = {
        name: float(contribs_row[i]) for i, name in enumerate(FEATURE_ORDER)
    }
    per_theme: dict[str, float] = {}
    for feat, val in per_feature.items():
        theme = _FEATURE_TO_THEME.get(feat, feat)
        per_theme[theme] = per_theme.get(theme, 0.0) + val
    return Attribution(
        base_value=float(contribs_row[-1]),
        per_feature=per_feature,
        per_theme=per_theme,
    )


def drivers(
    attribution: Attribution,
    values: np.ndarray | None = None,
    max_raising: int = 3,
    max_lowering: int = 2,
    min_share: float = 0.03,
) -> tuple[list[Driver], list[Driver]]:
    """Ranked risk-raising and risk-lowering themes.

    ``min_share`` suppresses the long tail.  A theme contributing 1% of total
    attribution is noise to a reader, and listing it invites a teacher to act
    on it.
    """
    total = (
        sum(
            abs(v)
            for k, v in attribution.per_theme.items()
            if k not in CONTEXT_THEMES
        )
        or 1.0
    )

    def make(theme: str, val: float) -> Driver:
        # Report the largest single contributing feature's value, so the card
        # can show "attendance 61%" rather than an abstract theme name.
        members = THEMES.get(theme, (theme,))
        lead = max(
            members,
            key=lambda f: abs(attribution.per_feature.get(f, 0.0)),
            default=theme,
        )
        v = None
        if values is not None and lead in FEATURE_ORDER:
            raw = float(values[FEATURE_ORDER.index(lead)])
            v = None if not np.isfinite(raw) else raw
        return Driver(
            feature=lead,
            label=THEME_LABELS.get(theme, FEATURE_LABELS.get(lead, theme)),
            direction="raises" if val > 0 else "lowers",
            magnitude=abs(val),
            share=abs(val) / total,
            actionable=theme in ACTIONABLE_THEMES
            or lead in ACTIONABLE_FEATURES,
            value=v,
        )

    raising = [
        make(t, v)
        for t, v in attribution.top(max_raising * 2, sign=+1)
        if abs(v) / total >= min_share
    ][:max_raising]
    lowering = [
        make(t, v)
        for t, v in attribution.top(max_lowering * 2, sign=-1)
        if abs(v) / total >= min_share
    ][:max_lowering]
    return raising, lowering


__all__ = [
    "Attribution",
    "THEMES",
    "THEME_LABELS",
    "ACTIONABLE_THEMES",
    "attribute",
    "drivers",
]
