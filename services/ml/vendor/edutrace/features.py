"""Feature construction.  One implementation, used by training and by serving.

The single most common failure in a deployed tabular model is train/serve skew:
the notebook computed ``attendance_last_4w`` one way, the API computes it
another, and the model quietly degrades in a way no dashboard catches.  The
defence here is that both paths call the same functions in this module, and the
row-wise path is tested to produce bit-identical output to the vectorised path.

Two entry points:

``build_frame(df)``
    Vectorised.  Takes a raw pandas frame of observations, returns an
    ``(n, FEATURE_COUNT)`` float32 matrix in ``FEATURE_ORDER``.  Used for
    training and for CSV batch scoring.

``build_row(obs, ctx)``
    Row-wise, no pandas.  Takes one ``StudentObservation`` and returns a
    ``(1, FEATURE_COUNT)`` float32 array.  Used on the single-student hot path,
    where constructing a DataFrame would dominate the latency budget.

Missingness policy
------------------
Missing numerics become ``NaN`` and are handed to XGBoost, which learns a
default split direction per node.  Nothing is mean-imputed.  A mean-imputed
attendance rate is indistinguishable from a measured one downstream, and that
is precisely how a school comes to trust a number the system invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import (
    BEHAVIOUR_ORDINAL,
    DISTANCE_ORDINAL,
    FEATURE_COUNT,
    FEATURE_ORDER,
    FEE_STATUS_ORDINAL,
    GRADE_ORDINAL,
    GUARDIAN_ORDINAL,
    OFFICIAL_AGE_FOR_GRADE,
    RAINY_TERMS,
    TERM_ORDINAL,
    WEEKS_PER_TERM,
)
from .records import StudentObservation

NAN = float("nan")
_INDEX = {name: i for i, name in enumerate(FEATURE_ORDER)}


# --------------------------------------------------------------------------
# Percentile context
# --------------------------------------------------------------------------


@dataclass(slots=True)
class GradeNormContext:
    """Empirical exam-score distribution per (school, grade).

    Raw marks are not comparable across schools -- a 62 at one JHS is a
    different animal from a 62 at another, because marking cultures differ more
    than pupils do.  The model therefore consumes a *within-school-within-grade
    percentile*.

    Fitted on training data, persisted with the model bundle, and applied
    unchanged at serving time.  A school not seen during training falls back to
    the grade-level pooled distribution, and a grade not seen falls back to the
    global one, so a brand-new tenant still scores rather than erroring.
    """

    by_school_grade: dict[tuple[str, str], np.ndarray] = field(default_factory=dict)
    by_grade: dict[str, np.ndarray] = field(default_factory=dict)
    globally: np.ndarray | None = None

    _QUANTILES = np.linspace(0.0, 1.0, 101)

    @classmethod
    def fit(cls, df: pd.DataFrame, min_support: int = 30) -> "GradeNormContext":
        ctx = cls()
        scores = pd.to_numeric(df.get("avg_exam_score"), errors="coerce")
        ok = scores.notna()
        if not ok.any():
            return ctx

        ctx.globally = np.quantile(scores[ok].to_numpy(), cls._QUANTILES)

        work = df.loc[ok, ["school_id", "grade_level"]].copy()
        work["score"] = scores[ok].to_numpy()

        for grade, g in work.groupby("grade_level", observed=True):
            if len(g) >= min_support:
                ctx.by_grade[str(grade)] = np.quantile(
                    g["score"].to_numpy(), cls._QUANTILES
                )

        for (school, grade), g in work.groupby(
            ["school_id", "grade_level"], observed=True
        ):
            if len(g) >= min_support:
                ctx.by_school_grade[(str(school), str(grade))] = np.quantile(
                    g["score"].to_numpy(), cls._QUANTILES
                )
        return ctx

    def _curve(self, school_id: str, grade: str) -> np.ndarray | None:
        # Explicit `is not None` rather than `or`-chaining: these are numpy
        # arrays, and `arr or fallback` raises on any array of length > 1.
        curve = self.by_school_grade.get((school_id, grade))
        if curve is not None:
            return curve
        curve = self.by_grade.get(grade)
        if curve is not None:
            return curve
        return self.globally

    def percentile(self, score: float | None, school_id: str, grade: str) -> float:
        if score is None or not np.isfinite(score):
            return NAN
        curve = self._curve(school_id, grade)
        if curve is None:
            # No fitted context at all: fall back to the raw mark, which is a
            # defensible identity mapping on a 0-100 scale.
            return float(score)
        return float(np.searchsorted(curve, score, side="right"))

    def percentile_vec(
        self, scores: np.ndarray, school_ids: np.ndarray, grades: np.ndarray
    ) -> np.ndarray:
        out = np.full(len(scores), NAN, dtype=np.float64)
        # Group by curve identity so each unique curve is applied once.
        keys = [
            (s, g) if (s, g) in self.by_school_grade else (None, g)
            for s, g in zip(school_ids, grades)
        ]
        unique: dict[tuple[str | None, str], list[int]] = {}
        for i, k in enumerate(keys):
            unique.setdefault(k, []).append(i)
        for (school, grade), idx in unique.items():
            if school is not None:
                curve = self.by_school_grade.get((school, grade))
            else:
                curve = self.by_grade.get(grade)
                if curve is None:
                    curve = self.globally
            sub = scores[idx]
            if curve is None:
                out[idx] = sub
            else:
                out[idx] = np.searchsorted(curve, sub, side="right")
        out[~np.isfinite(scores)] = NAN
        return out

    def to_dict(self) -> dict:
        return {
            "by_school_grade": {
                f"{k[0]}\x1f{k[1]}": v.tolist() for k, v in self.by_school_grade.items()
            },
            "by_grade": {k: v.tolist() for k, v in self.by_grade.items()},
            "globally": None if self.globally is None else self.globally.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GradeNormContext":
        ctx = cls()
        for k, v in d.get("by_school_grade", {}).items():
            school, grade = k.split("\x1f", 1)
            ctx.by_school_grade[(school, grade)] = np.asarray(v, dtype=np.float64)
        ctx.by_grade = {
            k: np.asarray(v, dtype=np.float64) for k, v in d.get("by_grade", {}).items()
        }
        g = d.get("globally")
        ctx.globally = None if g is None else np.asarray(g, dtype=np.float64)
        return ctx


# --------------------------------------------------------------------------
# Derived quantities shared by both paths
# --------------------------------------------------------------------------


def attendance_trend(history: list[float] | None, window: int = 4) -> float:
    """OLS slope of weekly attendance over the trailing ``window`` weeks.

    Level and direction carry different information.  A learner steady at 78%
    is a different case from one who fell 95% -> 78% over a month, and the
    second is the one worth a phone call this week.  Returned in percentage
    points per week; negative means deteriorating.
    """
    if not history:
        return NAN
    y = np.asarray(history[-window:], dtype=np.float64)
    y = y[np.isfinite(y)]
    if y.size < 2:
        return NAN
    x = np.arange(y.size, dtype=np.float64)
    x -= x.mean()
    denom = float((x * x).sum())
    if denom == 0.0:
        return NAN
    return float((x * (y - y.mean())).sum() / denom)


def _mean_tail(history: list[float] | None, window: int = 4) -> float:
    if not history:
        return NAN
    y = np.asarray(history[-window:], dtype=np.float64)
    y = y[np.isfinite(y)]
    return float(y.mean()) if y.size else NAN


def _ord(mapping: dict[str, int], value) -> float:
    if value is None:
        return NAN
    key = value.value if hasattr(value, "value") else str(value)
    v = mapping.get(key)
    return NAN if v is None else float(v)


def _bool(value) -> float:
    return NAN if value is None else float(bool(value))


def _num(value) -> float:
    if value is None:
        return NAN
    try:
        f = float(value)
    except (TypeError, ValueError):
        return NAN
    return f if np.isfinite(f) else NAN


def weeks_elapsed(term, week: int) -> float:
    t = _ord(TERM_ORDINAL, term)
    if not np.isfinite(t):
        return NAN
    return float((t - 1) * WEEKS_PER_TERM + week)


# --------------------------------------------------------------------------
# Row-wise path (serving hot path -- no pandas)
# --------------------------------------------------------------------------


def build_row(
    obs: StudentObservation, ctx: GradeNormContext | None = None
) -> np.ndarray:
    """Build a single feature vector.  ~10us, no DataFrame allocation."""
    v = np.full(FEATURE_COUNT, NAN, dtype=np.float32)
    ix = _INDEX
    hist = obs.weekly_attendance_history

    # --- attendance -------------------------------------------------------
    att_ttd = _num(obs.attendance_rate_term_to_date)
    if not np.isfinite(att_ttd) and hist:
        clean = [h for h in hist if h is not None]
        att_ttd = float(np.mean(clean)) if clean else NAN
    v[ix["attendance_rate_term_to_date"]] = att_ttd

    att_4w = _num(obs.attendance_rate_last_4w)
    if not np.isfinite(att_4w):
        att_4w = _mean_tail(hist, 4)
    v[ix["attendance_rate_last_4w"]] = att_4w

    # History wins when present (it is the richer signal); otherwise take the
    # school's own precomputed slope. Falling back to NaN here while the
    # vectorised path reads a real column is precisely the skew that
    # tests/test_invariants.py::test_no_train_serve_skew exists to catch.
    trend = attendance_trend(hist, 4)
    if not np.isfinite(trend):
        trend = _num(obs.attendance_trend_4w)
    v[ix["attendance_trend_4w"]] = trend
    v[ix["consecutive_absences"]] = _num(obs.consecutive_absences)
    v[ix["longest_absence_streak_term"]] = _num(obs.longest_absence_streak_term)
    v[ix["absences_prior_year"]] = _num(obs.absences_prior_year)
    v[ix["attendance_rate_prior_term"]] = _num(obs.attendance_rate_prior_term)

    # --- achievement ------------------------------------------------------
    grade = obs.grade_level if isinstance(obs.grade_level, str) else obs.grade_level.value
    score = _num(obs.avg_exam_score)
    v[ix["exam_percentile_in_grade"]] = (
        ctx.percentile(score if np.isfinite(score) else None, obs.school_id, grade)
        if ctx is not None
        else score
    )
    prev = _num(obs.avg_exam_score_prev_term)
    v[ix["exam_score_delta_prev_term"]] = (
        score - prev if np.isfinite(score) and np.isfinite(prev) else NAN
    )
    v[ix["assessment_completion_rate"]] = _num(obs.assessment_completion_rate)
    v[ix["core_subject_failures"]] = _num(obs.core_subject_failures)

    # --- progression ------------------------------------------------------
    v[ix["grade_ordinal"]] = _ord(GRADE_ORDINAL, obs.grade_level)
    v[ix["term_ordinal"]] = _ord(TERM_ORDINAL, obs.term)
    v[ix["week"]] = float(obs.week)
    v[ix["weeks_elapsed_in_year"]] = weeks_elapsed(obs.term, obs.week)

    age = _num(obs.age_years)
    official = OFFICIAL_AGE_FOR_GRADE.get(grade)
    v[ix["age_for_grade_gap"]] = (
        age - official if np.isfinite(age) and official is not None else NAN
    )
    v[ix["repeated_a_grade"]] = _bool(obs.repeated_a_grade)
    v[ix["school_transfers_count"]] = _num(obs.school_transfers_count)

    # --- household --------------------------------------------------------
    v[ix["fee_status_ord"]] = _ord(FEE_STATUS_ORDINAL, obs.fee_status)
    v[ix["fee_arrears_terms"]] = _num(obs.fee_arrears_terms)
    v[ix["has_textbooks"]] = _bool(obs.has_textbooks)
    v[ix["has_uniform"]] = _bool(obs.has_uniform)
    v[ix["siblings_in_school"]] = _num(obs.siblings_in_school)
    v[ix["does_paid_or_farm_work"]] = _bool(obs.does_paid_or_farm_work)

    # --- access -----------------------------------------------------------
    dist = _ord(DISTANCE_ORDINAL, obs.distance_band)
    v[ix["distance_band_ord"]] = dist
    term_val = obs.term if isinstance(obs.term, str) else obs.term.value
    v[ix["distance_x_rainy_term"]] = (
        dist * (1.0 if term_val in RAINY_TERMS else 0.0) if np.isfinite(dist) else NAN
    )
    v[ix["guardian_type_ord"]] = _ord(GUARDIAN_ORDINAL, obs.guardian_type)

    # --- behaviour --------------------------------------------------------
    v[ix["behaviour_incidents_term"]] = _num(obs.behaviour_incidents_term)
    v[ix["behaviour_severity_max"]] = _ord(BEHAVIOUR_ORDINAL, obs.behaviour_flag)

    # --- health -----------------------------------------------------------
    v[ix["health_absence_days_term"]] = _num(obs.health_absence_days_term)

    # --- terminal year ----------------------------------------------------
    if grade == "JHS3":
        v[ix["bece_registered"]] = _bool(obs.bece_registered)
    else:
        v[ix["bece_registered"]] = 0.0

    return v.reshape(1, FEATURE_COUNT)


# --------------------------------------------------------------------------
# Vectorised path (training, CSV batch)
# --------------------------------------------------------------------------


def _col(df: pd.DataFrame, name: str) -> np.ndarray:
    if name not in df.columns:
        return np.full(len(df), NAN, dtype=np.float64)
    return pd.to_numeric(df[name], errors="coerce").to_numpy(dtype=np.float64)


def _map_col(df: pd.DataFrame, name: str, mapping: dict[str, int]) -> np.ndarray:
    if name not in df.columns:
        return np.full(len(df), NAN, dtype=np.float64)
    return df[name].map(mapping).astype("float64").to_numpy()


def _bool_col(df: pd.DataFrame, name: str) -> np.ndarray:
    if name not in df.columns:
        return np.full(len(df), NAN, dtype=np.float64)
    s = df[name]
    if s.dtype == object:
        s = s.map(
            {
                True: 1.0,
                False: 0.0,
                "True": 1.0,
                "False": 0.0,
                "true": 1.0,
                "false": 0.0,
                1: 1.0,
                0: 0.0,
                "1": 1.0,
                "0": 0.0,
                "Y": 1.0,
                "N": 0.0,
                "yes": 1.0,
                "no": 0.0,
            }
        )
    return pd.to_numeric(s, errors="coerce").astype("float64").to_numpy()


def build_frame(df: pd.DataFrame, ctx: GradeNormContext | None = None) -> np.ndarray:
    """Vectorised feature build.  ~10k rows in well under a second."""
    n = len(df)
    X = np.full((n, FEATURE_COUNT), NAN, dtype=np.float32)
    ix = _INDEX

    # attendance
    att_ttd = _col(df, "attendance_rate_term_to_date")
    X[:, ix["attendance_rate_term_to_date"]] = att_ttd
    X[:, ix["attendance_rate_last_4w"]] = _col(df, "attendance_rate_last_4w")
    X[:, ix["attendance_trend_4w"]] = _col(df, "attendance_trend_4w")
    X[:, ix["consecutive_absences"]] = _col(df, "consecutive_absences")
    X[:, ix["longest_absence_streak_term"]] = _col(df, "longest_absence_streak_term")
    X[:, ix["absences_prior_year"]] = _col(df, "absences_prior_year")
    X[:, ix["attendance_rate_prior_term"]] = _col(df, "attendance_rate_prior_term")

    # achievement
    score = _col(df, "avg_exam_score")
    if ctx is not None:
        schools = df.get("school_id", pd.Series([""] * n)).astype(str).to_numpy()
        grades = df.get("grade_level", pd.Series([""] * n)).astype(str).to_numpy()
        X[:, ix["exam_percentile_in_grade"]] = ctx.percentile_vec(score, schools, grades)
    else:
        X[:, ix["exam_percentile_in_grade"]] = score
    X[:, ix["exam_score_delta_prev_term"]] = score - _col(df, "avg_exam_score_prev_term")
    X[:, ix["assessment_completion_rate"]] = _col(df, "assessment_completion_rate")
    X[:, ix["core_subject_failures"]] = _col(df, "core_subject_failures")

    # progression
    grade_ord = _map_col(df, "grade_level", GRADE_ORDINAL)
    term_ord = _map_col(df, "term", TERM_ORDINAL)
    week = _col(df, "week")
    X[:, ix["grade_ordinal"]] = grade_ord
    X[:, ix["term_ordinal"]] = term_ord
    X[:, ix["week"]] = week
    X[:, ix["weeks_elapsed_in_year"]] = (term_ord - 1.0) * WEEKS_PER_TERM + week

    official = (
        df.get("grade_level", pd.Series([None] * n))
        .map(OFFICIAL_AGE_FOR_GRADE)
        .astype("float64")
        .to_numpy()
    )
    X[:, ix["age_for_grade_gap"]] = _col(df, "age_years") - official
    X[:, ix["repeated_a_grade"]] = _bool_col(df, "repeated_a_grade")
    X[:, ix["school_transfers_count"]] = _col(df, "school_transfers_count")

    # household
    X[:, ix["fee_status_ord"]] = _map_col(df, "fee_status", FEE_STATUS_ORDINAL)
    X[:, ix["fee_arrears_terms"]] = _col(df, "fee_arrears_terms")
    X[:, ix["has_textbooks"]] = _bool_col(df, "has_textbooks")
    X[:, ix["has_uniform"]] = _bool_col(df, "has_uniform")
    X[:, ix["siblings_in_school"]] = _col(df, "siblings_in_school")
    X[:, ix["does_paid_or_farm_work"]] = _bool_col(df, "does_paid_or_farm_work")

    # access
    dist = _map_col(df, "distance_band", DISTANCE_ORDINAL)
    X[:, ix["distance_band_ord"]] = dist
    rainy = (
        df.get("term", pd.Series([None] * n))
        .isin(RAINY_TERMS)
        .astype("float64")
        .to_numpy()
    )
    X[:, ix["distance_x_rainy_term"]] = dist * rainy
    X[:, ix["guardian_type_ord"]] = _map_col(df, "guardian_type", GUARDIAN_ORDINAL)

    # behaviour / health
    X[:, ix["behaviour_incidents_term"]] = _col(df, "behaviour_incidents_term")
    X[:, ix["behaviour_severity_max"]] = _map_col(
        df, "behaviour_flag", BEHAVIOUR_ORDINAL
    )
    X[:, ix["health_absence_days_term"]] = _col(df, "health_absence_days_term")

    # terminal year
    bece = _bool_col(df, "bece_registered")
    is_jhs3 = (grade_ord == 3.0)
    X[:, ix["bece_registered"]] = np.where(is_jhs3, bece, 0.0)

    return X


__all__ = [
    "GradeNormContext",
    "attendance_trend",
    "build_row",
    "build_frame",
    "weeks_elapsed",
]
