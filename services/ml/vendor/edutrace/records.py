"""Input records and API payloads.

Two layers, deliberately separated:

``StudentObservation``
    What a school actually records about one learner in one week.  This is the
    shape of a CSV row and the shape of the single-student API body.  It is
    permissive about what a school can supply -- most fields are optional,
    because no real school has all of them -- and strict about ranges.

``RiskAssessment``
    What comes back out.  A calibrated probability, a tier, ranked drivers, a
    recourse suggestion, and an explicit ``requires_human_review`` flag.

The PII fields are carried on a separate model (``StudentIdentity``) that is
never passed to the feature builder.  That separation is enforced by a test.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from .contract import (
    BehaviourFlag,
    DistanceBand,
    FeeStatus,
    GradeLevel,
    GuardianType,
    RiskTier,
    Sex,
    Term,
    WEEKS_PER_TERM,
)

Pct = Annotated[float, Field(ge=0.0, le=100.0)]


# --------------------------------------------------------------------------


class StudentIdentity(BaseModel):
    """Direct identifiers.  Kept out of the modelling path by construction."""

    model_config = ConfigDict(extra="forbid")

    student_name: str = Field(min_length=1, max_length=120)
    student_external_id: str | None = Field(default=None, max_length=64)
    guardian_name: str | None = Field(default=None, max_length=120)
    guardian_msisdn: str | None = Field(
        default=None,
        description="E.164, e.g. +233241234567. Validated by the messaging layer.",
        max_length=20,
    )

    def pseudonym(self, salt: str) -> str:
        """Stable pseudonymous key.

        The salt is per-tenant and lives in the secret store, so the same child
        at two different schools does not collide, and the mapping cannot be
        reversed from an exported modelling dataset.
        """
        basis = f"{salt}:{self.student_external_id or self.student_name}".encode()
        return hashlib.blake2b(basis, digest_size=16).hexdigest()


class StudentObservation(BaseModel):
    """One learner, one week.

    Everything optional has a documented default-handling rule in
    ``edutrace.features``; nothing is silently imputed with a mean, because a
    mean-imputed attendance rate is indistinguishable from a real one at
    serving time and that is how a school ends up trusting a fabricated score.
    Missing numerics are passed to XGBoost as NaN, which the booster handles
    natively by learning a default split direction.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    # --- keys -------------------------------------------------------------
    student_key: str = Field(min_length=1, max_length=64)
    school_id: str = Field(min_length=1, max_length=64)
    academic_year: int = Field(ge=2000, le=2100)
    term: Term
    week: int = Field(ge=1, le=WEEKS_PER_TERM)
    grade_level: GradeLevel

    # --- attendance -------------------------------------------------------
    attendance_rate_term_to_date: Pct | None = Field(
        default=None,
        description="Percent of school sessions attended this term up to and "
        "including this week.",
    )
    attendance_rate_last_4w: Pct | None = None
    attendance_rate_prior_term: Pct | None = None
    attendance_trend_4w: float | None = Field(
        default=None,
        ge=-100.0,
        le=100.0,
        description="Percentage points per week; negative means deteriorating. "
        "Derived from weekly_attendance_history when that is supplied; accepted "
        "directly when a school's export already carries it. Without this "
        "field the row-wise path could only ever emit NaN for a feature the "
        "vectorised path computes, which is train/serve skew.",
    )
    consecutive_absences: int | None = Field(default=None, ge=0, le=90)
    longest_absence_streak_term: int | None = Field(default=None, ge=0, le=90)
    absences_prior_year: int | None = Field(default=None, ge=0, le=200)
    weekly_attendance_history: list[Pct] | None = Field(
        default=None,
        max_length=WEEKS_PER_TERM,
        description="Oldest-first weekly attendance percentages for this term. "
        "If supplied, the 4-week rate and trend are derived from it rather "
        "than taken from the flat fields above.",
    )

    # --- achievement ------------------------------------------------------
    avg_exam_score: Pct | None = Field(
        default=None,
        description="Mean end-of-term score across subjects, out of 100. "
        "Converted to a within-school-within-grade percentile before use.",
    )
    avg_exam_score_prev_term: Pct | None = None
    assessment_completion_rate: Pct | None = None
    core_subject_failures: int | None = Field(default=None, ge=0, le=12)

    # --- progression ------------------------------------------------------
    age_years: float | None = Field(default=None, ge=8, le=25)
    repeated_a_grade: bool | None = None
    school_transfers_count: int | None = Field(default=None, ge=0, le=10)
    bece_registered: bool | None = None

    # --- household --------------------------------------------------------
    fee_status: FeeStatus | None = None
    fee_arrears_terms: int | None = Field(default=None, ge=0, le=9)
    has_textbooks: bool | None = None
    has_uniform: bool | None = None
    siblings_in_school: int | None = Field(default=None, ge=0, le=15)
    does_paid_or_farm_work: bool | None = None
    guardian_type: GuardianType | None = None

    # --- access -----------------------------------------------------------
    distance_band: DistanceBand | None = None

    # --- behaviour / health ----------------------------------------------
    behaviour_flag: BehaviourFlag | None = None
    behaviour_incidents_term: int | None = Field(default=None, ge=0, le=50)
    health_absence_days_term: int | None = Field(default=None, ge=0, le=90)

    # --- protected: audit only -------------------------------------------
    sex: Sex | None = Field(
        default=None,
        description="Never used as a model input. Retained so error-rate "
        "parity can be measured. Supplying it does not change the score.",
    )
    region: str | None = Field(default=None, max_length=64)
    poverty_quintile: int | None = Field(default=None, ge=1, le=5)

    @field_validator("weekly_attendance_history")
    @classmethod
    def _history_not_empty(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) == 0:
            raise ValueError("weekly_attendance_history must be omitted or non-empty")
        return v

    @field_validator(
        "consecutive_absences",
        "longest_absence_streak_term",
        "absences_prior_year",
        "core_subject_failures",
        "school_transfers_count",
        "fee_arrears_terms",
        "siblings_in_school",
        "behaviour_incidents_term",
        "health_absence_days_term",
        "poverty_quintile",
        "week",
        mode="before",
    )
    @classmethod
    def _round_count(cls, v):
        """Accept ``2.0`` where an integer count is expected.

        Every real school export writes counts as floats -- pandas turns any
        column with one missing value into float64, Excel writes "2.0", and a
        CSV round-trip does the rest. Rejecting the whole row over that is not
        a defensible product decision. Genuinely fractional input (2.4 terms
        owed) still fails, because that means the column is not what we think
        it is.
        """
        if v is None or isinstance(v, (bool, int, str)):
            return v
        try:
            f = float(v)
        except (TypeError, ValueError):
            return v
        if f != f:  # NaN
            return None
        return int(round(f)) if abs(f - round(f)) < 1e-6 else v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def observation_id(self) -> str:
        return f"{self.school_id}:{self.student_key}:{self.academic_year}:{self.term}:{self.week}"


# --------------------------------------------------------------------------


class Driver(BaseModel):
    """One ranked contributor to a score, in plain language."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    label: str
    direction: Literal["raises", "lowers"]
    magnitude: float = Field(description="Absolute SHAP value, in log-odds.")
    share: float = Field(ge=0.0, le=1.0, description="Share of total |SHAP|.")
    actionable: bool
    value: float | None = None


class RecourseStep(BaseModel):
    """A concrete, feasible change that would move the score below threshold."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    label: str
    current_value: float
    target_value: float
    projected_risk: float
    feasible: bool
    note: str


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    student_key: str
    school_id: str
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    risk: float = Field(
        ge=0.0,
        le=1.0,
        description="Calibrated probability of ceasing attendance within the "
        "horizon, conditional on being enrolled now.",
    )
    tier: RiskTier
    percentile_in_cohort: float | None = Field(default=None, ge=0.0, le=100.0)

    drivers: list[Driver] = Field(default_factory=list)
    protective: list[Driver] = Field(default_factory=list)
    recourse: list[RecourseStep] = Field(default_factory=list)
    narrative: str = ""

    model_version: str
    contract_fingerprint: str

    requires_human_review: bool = Field(
        default=True,
        description="Ghana's Data Protection Act 2012 s.41 lets a data subject "
        "object to a significant decision made solely by automatic means. No "
        "tier above WATCH may trigger contact with a guardian until a named "
        "member of staff has reviewed it.",
    )
    review_note: str = (
        "Advisory only. This is a statistical signal about a pattern, not a "
        "judgement about a child. A member of staff must confirm before any "
        "action is taken."
    )

    latency_ms: float | None = None


class BatchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows_in: int
    rows_scored: int
    rows_rejected: int
    errors: list[str] = Field(default_factory=list)
    flagged_count: int
    capacity_used: int
    tier_counts: dict[str, int] = Field(default_factory=dict)
    elapsed_ms: float
    model_version: str


__all__ = [
    "StudentIdentity",
    "StudentObservation",
    "Driver",
    "RecourseStep",
    "RiskAssessment",
    "BatchSummary",
]
