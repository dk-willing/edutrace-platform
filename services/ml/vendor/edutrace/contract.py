"""Canonical data contract for EduTrace.

This module is the single source of truth for:
  * the domain vocabulary (enums),
  * which columns exist on a raw observation,
  * which of those columns are allowed to reach the model,
  * which are held out as protected attributes for fairness auditing only.

Everything else in the codebase -- the simulator, the training pipeline, the
feature builder, the serving layer -- imports from here.  There is deliberately
no second place where a feature name is written down, because train/serve skew
in a tabular system is almost always a naming or ordering bug.

Design notes that differ from a naive spec
------------------------------------------
1.  ``sex`` is NOT a model input.  It is a protected attribute used only to
    audit error-rate parity.  Wisconsin's DEWS fed race and family income into
    the model and ended up with a false-alarm rate 42pp higher for Black
    students than White students.  The mechanisms that make sex predictive in
    Ghanaian JHS (pregnancy, care duties, menstrual-hygiene absence, distance
    risk) are captured as explicit, actionable features instead.

2.  The unit of observation is (student, term, week) -- a panel row, not a
    student.  The target is a *discrete-time hazard*: the probability that a
    currently-enrolled student stops attending within the next
    ``HORIZON_WEEKS``.  A flat "is this student a dropout" label leaks the
    future and cannot be acted on at week 3.

3.  Raw exam marks are converted to within-school-within-grade percentiles.
    A 62/100 means nothing across two schools with different marking cultures.

4.  Fee status is a 4-level taxonomy.  The original "fully / half / partially
    paid" had two overlapping levels and no way to express the capitation-grant
    exemption, which is the common case in Ghanaian public JHS.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


# --------------------------------------------------------------------------
# Horizon / cadence
# --------------------------------------------------------------------------

WEEKS_PER_TERM: Final[int] = 14
TERMS_PER_YEAR: Final[int] = 3
#: How far ahead the hazard model looks.  8 weeks is long enough that a school
#: can actually mount an intervention and short enough that the signal is real.
HORIZON_WEEKS: Final[int] = 8


# --------------------------------------------------------------------------
# Domain vocabulary
# --------------------------------------------------------------------------

class GradeLevel(str, Enum):
    JHS1 = "JHS1"
    JHS2 = "JHS2"
    JHS3 = "JHS3"


class Term(str, Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class FeeStatus(str, Enum):
    """Fee/levy standing for the current term.

    Ghanaian public JHS is nominally fee-free under the capitation grant, so
    ``EXEMPT`` (covered, nothing owed) is a distinct and common state from
    ``PAID_IN_FULL`` (levies settled by the household).  The operative cost
    pressure is PTA dues, exam/printing levies and uniform -- which is what
    ``PART_PAID`` and ``UNPAID`` capture.
    """

    EXEMPT = "EXEMPT"
    PAID_IN_FULL = "PAID_IN_FULL"
    PART_PAID = "PART_PAID"
    UNPAID = "UNPAID"


class DistanceBand(str, Enum):
    """Home-to-school travel, banded.

    Banded beats self-reported kilometres: guardians estimate distance badly,
    but they reliably know whether the walk is under fifteen minutes or over an
    hour.  Bands follow the UCI ``traveltime`` convention, which also makes a
    transfer-learning sanity check against that dataset possible.
    """

    UNDER_15_MIN = "UNDER_15_MIN"
    M15_TO_30 = "M15_TO_30"
    M30_TO_60 = "M30_TO_60"
    OVER_60_MIN = "OVER_60_MIN"


class GuardianType(str, Enum):
    BOTH_PARENTS = "BOTH_PARENTS"
    SINGLE_PARENT = "SINGLE_PARENT"
    RELATIVE = "RELATIVE"
    UNRELATED_OR_SELF = "UNRELATED_OR_SELF"


class BehaviourFlag(str, Enum):
    """Retained for backwards compatibility with existing school records.

    Prefer the structured teacher-rated items in ``edutrace.conversation``:
    a single subjective none/minor/serious flag is a well-documented bias
    vector, and it is the feature most likely to encode a teacher's opinion of
    a child rather than the child's behaviour.
    """

    NONE = "NONE"
    MINOR = "MINOR"
    SERIOUS = "SERIOUS"


class Sex(str, Enum):
    """Protected attribute.  Audit only -- never a model input."""

    F = "F"
    M = "M"


class RiskTier(str, Enum):
    LOW = "LOW"
    WATCH = "WATCH"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"


# --------------------------------------------------------------------------
# Column groups
# --------------------------------------------------------------------------

#: Identity + bookkeeping.  Never features.
IDENTITY_COLUMNS: Final[tuple[str, ...]] = (
    "student_key",      # pseudonymous, stable, hashed upstream of this system
    "school_id",
    "academic_year",
    "term",
    "week",
)

#: Personally identifying fields.  These live in the operational store behind
#: access control; they are physically absent from the modelling dataframe.
PII_COLUMNS: Final[tuple[str, ...]] = (
    "student_name",
    "guardian_name",
    "guardian_msisdn",
    "student_external_id",
)

#: Held out of X.  Used exclusively to compute per-group error rates.
PROTECTED_COLUMNS: Final[tuple[str, ...]] = (
    "sex",
    "region",
    "poverty_quintile",
)

#: Features the school can actually change.  Narrative explanations and
#: counterfactual recourse are restricted to this set -- telling a head teacher
#: that a child's risk is driven by "distance band = over 60 min" is true and
#: useless.
ACTIONABLE_FEATURES: Final[frozenset[str]] = frozenset({
    "attendance_rate_term_to_date",
    "attendance_rate_last_4w",
    "attendance_trend_4w",
    "consecutive_absences",
    "longest_absence_streak_term",
    "assessment_completion_rate",
    "exam_percentile_in_grade",
    "fee_arrears_terms",
    "fee_status_ord",
    "has_textbooks",
    "has_uniform",
    "behaviour_incidents_term",
    "bece_registered",
})


# --------------------------------------------------------------------------
# The feature vector
# --------------------------------------------------------------------------

#: Canonical, ordered feature list.  The XGBoost booster is trained on exactly
#: this order and the serving path rebuilds exactly this order.  Changing this
#: tuple invalidates every persisted model; ``ModelBundle`` stores a hash of it
#: and refuses to load a mismatched booster.
FEATURE_ORDER: Final[tuple[str, ...]] = (
    # --- attendance: the strongest and most actionable signal we have -------
    "attendance_rate_term_to_date",
    "attendance_rate_last_4w",
    "attendance_trend_4w",          # OLS slope of weekly attendance, last 4w
    "consecutive_absences",         # current unbroken run, in school days
    "longest_absence_streak_term",
    "absences_prior_year",
    "attendance_rate_prior_term",

    # --- achievement -------------------------------------------------------
    "exam_percentile_in_grade",     # within school x grade, not raw marks
    "exam_score_delta_prev_term",   # movement matters more than level
    "assessment_completion_rate",
    "core_subject_failures",        # count of core subjects below pass mark

    # --- progression -------------------------------------------------------
    "grade_ordinal",                # JHS1=1 .. JHS3=3
    "term_ordinal",
    "week",
    "weeks_elapsed_in_year",        # (term-1)*14 + week; the hazard clock
    "age_for_grade_gap",            # age - official age; over-age is huge in GH
    "repeated_a_grade",
    "school_transfers_count",

    # --- household economics ----------------------------------------------
    "fee_status_ord",               # EXEMPT=0, PAID=1, PART=2, UNPAID=3
    "fee_arrears_terms",
    "has_textbooks",
    "has_uniform",
    "siblings_in_school",
    "does_paid_or_farm_work",

    # --- access ------------------------------------------------------------
    "distance_band_ord",
    "distance_x_rainy_term",        # distance bites hardest in the rainy term
    "guardian_type_ord",

    # --- behaviour (weak, subjective; kept small on purpose) ---------------
    "behaviour_incidents_term",
    "behaviour_severity_max",

    # --- health / disruption ----------------------------------------------
    "health_absence_days_term",

    # --- terminal-year pressure -------------------------------------------
    "bece_registered",              # JHS3 only; 0 elsewhere
)

FEATURE_COUNT: Final[int] = len(FEATURE_ORDER)

#: Ordinal encodings.  Explicit rather than fitted, so they cannot drift
#: between a training run and a serving process.
FEE_STATUS_ORDINAL: Final[dict[str, int]] = {
    FeeStatus.EXEMPT.value: 0,
    FeeStatus.PAID_IN_FULL.value: 1,
    FeeStatus.PART_PAID.value: 2,
    FeeStatus.UNPAID.value: 3,
}

DISTANCE_ORDINAL: Final[dict[str, int]] = {
    DistanceBand.UNDER_15_MIN.value: 0,
    DistanceBand.M15_TO_30.value: 1,
    DistanceBand.M30_TO_60.value: 2,
    DistanceBand.OVER_60_MIN.value: 3,
}

GUARDIAN_ORDINAL: Final[dict[str, int]] = {
    GuardianType.BOTH_PARENTS.value: 0,
    GuardianType.SINGLE_PARENT.value: 1,
    GuardianType.RELATIVE.value: 2,
    GuardianType.UNRELATED_OR_SELF.value: 3,
}

BEHAVIOUR_ORDINAL: Final[dict[str, int]] = {
    BehaviourFlag.NONE.value: 0,
    BehaviourFlag.MINOR.value: 1,
    BehaviourFlag.SERIOUS.value: 2,
}

GRADE_ORDINAL: Final[dict[str, int]] = {
    GradeLevel.JHS1.value: 1,
    GradeLevel.JHS2.value: 2,
    GradeLevel.JHS3.value: 3,
}

TERM_ORDINAL: Final[dict[str, int]] = {
    Term.T1.value: 1,
    Term.T2.value: 2,
    Term.T3.value: 3,
}

#: Official starting age for each JHS grade in Ghana (JHS is ages 12-14).
OFFICIAL_AGE_FOR_GRADE: Final[dict[str, int]] = {
    GradeLevel.JHS1.value: 12,
    GradeLevel.JHS2.value: 13,
    GradeLevel.JHS3.value: 14,
}

#: Ghana's major rainy season runs roughly Apr-Jul, which overlaps Term 3 in
#: the southern zones.  Used to build the distance x weather interaction.
RAINY_TERMS: Final[frozenset[str]] = frozenset({Term.T3.value})


# --------------------------------------------------------------------------
# Human-readable labels, used by the narrative explainer and the UI
# --------------------------------------------------------------------------

FEATURE_LABELS: Final[dict[str, str]] = {
    "attendance_rate_term_to_date": "attendance so far this term",
    "attendance_rate_last_4w": "attendance over the last four weeks",
    "attendance_trend_4w": "the direction attendance is moving",
    "consecutive_absences": "days absent in a row right now",
    "longest_absence_streak_term": "the longest absence stretch this term",
    "absences_prior_year": "days absent last year",
    "attendance_rate_prior_term": "attendance last term",
    "exam_percentile_in_grade": "exam standing within the year group",
    "exam_score_delta_prev_term": "change in exam marks since last term",
    "assessment_completion_rate": "how much classwork is being handed in",
    "core_subject_failures": "core subjects currently below the pass mark",
    "grade_ordinal": "year group",
    "term_ordinal": "which term it is",
    "week": "how far into the term we are",
    "weeks_elapsed_in_year": "how far into the school year we are",
    "age_for_grade_gap": "being older than the year group",
    "repeated_a_grade": "having repeated a year",
    "school_transfers_count": "number of school changes",
    "fee_status_ord": "levy payment standing",
    "fee_arrears_terms": "terms of levies outstanding",
    "has_textbooks": "having the required textbooks",
    "has_uniform": "having a school uniform",
    "siblings_in_school": "siblings also in school",
    "does_paid_or_farm_work": "doing paid or farm work outside school",
    "distance_band_ord": "how far the journey to school is",
    "distance_x_rainy_term": "a long journey during the rainy term",
    "guardian_type_ord": "who the learner lives with",
    "behaviour_incidents_term": "recorded behaviour incidents",
    "behaviour_severity_max": "the most serious behaviour incident recorded",
    "health_absence_days_term": "days missed through illness",
    "bece_registered": "BECE registration status",
}


def contract_fingerprint() -> str:
    """Stable hash of the feature contract.

    Persisted alongside every trained booster.  Loading a model whose
    fingerprint does not match the running code raises rather than silently
    scoring a misaligned vector -- the classic way a tabular system starts
    producing confident nonsense in production.
    """
    import hashlib

    payload = "|".join(FEATURE_ORDER).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


__all__ = [
    "WEEKS_PER_TERM",
    "TERMS_PER_YEAR",
    "HORIZON_WEEKS",
    "GradeLevel",
    "Term",
    "FeeStatus",
    "DistanceBand",
    "GuardianType",
    "BehaviourFlag",
    "Sex",
    "RiskTier",
    "IDENTITY_COLUMNS",
    "PII_COLUMNS",
    "PROTECTED_COLUMNS",
    "ACTIONABLE_FEATURES",
    "FEATURE_ORDER",
    "FEATURE_COUNT",
    "FEE_STATUS_ORDINAL",
    "DISTANCE_ORDINAL",
    "GUARDIAN_ORDINAL",
    "BEHAVIOUR_ORDINAL",
    "GRADE_ORDINAL",
    "TERM_ORDINAL",
    "OFFICIAL_AGE_FOR_GRADE",
    "RAINY_TERMS",
    "FEATURE_LABELS",
    "contract_fingerprint",
]
