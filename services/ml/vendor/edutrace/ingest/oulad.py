"""OULAD -> weekly hazard panel.  Real people, real withdrawal, real dates.

The Open University Learning Analytics Dataset: 32,593 learners across 22
course presentations, 10.6M timestamped VLE interactions, CC-BY 4.0.

    https://analyse.kmi.open.ac.uk/open_dataset

**What this is for, and what it is not for.**

OULAD is UK adults studying at a distance. It is *not* Ghanaian junior high
school, and a model fitted to it must never score a JHS learner. What it does
give — and nothing else openly available does — is a real population with a
real, dated leaving event and a real weekly engagement time series. That makes
it the right instrument for validating the *methodology*: does the discrete-time
hazard label hold up, does the temporal split behave, does isotonic calibration
work at this base rate, do the capacity metrics and fairness gates mean anything
on real humans rather than on a simulator's output.

So the claim this data supports is "the pipeline was validated on 32,593 real
learners", and the claim it does not support is "the model predicts Ghanaian
dropout". The model card records the first and forbids the second.

**The engagement-as-attendance proxy, stated plainly.**

The weekly contract in ``edutrace.contract`` is written for school registers.
OULAD has no register; it has clicks. The mapping used here is:

    a learner is "present" in a week   <->  they clicked at least once
    attendance rate                    <->  share of weeks present
    consecutive absences (days)        <->  consecutive silent weeks x 5
    exam score                         <->  mean assessment score to date
    assessment completion              <->  submitted / due, to date
    repeated a grade                   <->  num_of_prev_attempts > 0

That is a proxy, not an equivalence: a learner can attend school without
clicking anything, and can click without learning. It is used because the two
signals play the same structural role — "is this person still showing up" — and
because it lets the identical pipeline run end to end on real data. Every
feature that has no OULAD counterpart (fees, distance, textbooks, guardian,
behaviour) stays NaN, and the ingest report says so loudly rather than letting
a model quietly learn to ignore the things that matter most in Ghana.

**Two label decisions that matter.**

*Withdrawals before day 0 are excluded, not labelled negative.*  2,678 learners
unregister before the presentation begins. They never started, so they cannot
stop — the same reason ``ingest.household`` excludes never-enrolled children.
Counting them as non-events would teach the model that the opening weeks are
uneventful; counting them as events would teach it to predict an outcome that
had already happened.

*Administrative censoring is applied.*  Rows whose 8-week horizon runs past the
end of the presentation, with no event, are dropped rather than labelled 0.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..contract import HORIZON_WEEKS, WEEKS_PER_TERM
from .base import QualityReport, assess

log = logging.getLogger(__name__)

FILES = (
    "studentInfo.csv",
    "studentRegistration.csv",
    "studentVle.csv",
    "studentAssessment.csv",
    "assessments.csv",
    "courses.csv",
)

#: Presentation code -> sortable period. 'B' starts in February, 'J' in October,
#: so within a year B precedes J. The temporal split uses this ordering, which
#: is what makes the forward-chaining test a genuine test.
PRESENTATION_ORDER = {"2013B": 20131, "2013J": 20132, "2014B": 20141, "2014J": 20142}

#: Assessment score below this counts as a failed assessment.
PASS_MARK = 40.0

#: Features the weekly contract declares that OULAD simply does not have.
#: Listed explicitly so the report can name them rather than leaving a reader
#: to infer their absence from a support table.
ABSENT_IN_OULAD = (
    "fee_status_ord", "fee_arrears_terms", "has_textbooks", "has_uniform",
    "siblings_in_school", "does_paid_or_farm_work", "distance_band_ord",
    "distance_x_rainy_term", "guardian_type_ord", "behaviour_incidents_term",
    "behaviour_severity_max", "health_absence_days_term", "bece_registered",
    "grade_ordinal", "age_for_grade_gap", "school_transfers_count",
)


@dataclass(slots=True)
class OuladSpec:
    #: Weeks per pseudo-term, so the contract's term/week fields stay meaningful.
    #: Presentations run 33-38 weeks, so three terms of 13 is a close fit.
    weeks_per_term: int = 13
    horizon_weeks: int = HORIZON_WEEKS
    #: Chunk size for the 10.6M-row VLE file. 3GB of RAM will not hold it whole.
    vle_chunksize: int = 2_000_000
    #: Drop learners who never registered activity AND withdrew before day 0.
    drop_pre_start_withdrawals: bool = True


# --------------------------------------------------------------------------


def _aggregate_vle(path: Path, spec: OuladSpec) -> pd.DataFrame:
    """Chunked reduction of 10.6M click rows to one row per learner-week."""
    parts: list[pd.DataFrame] = []
    reader = pd.read_csv(
        path,
        usecols=["code_module", "code_presentation", "id_student", "date", "sum_click"],
        dtype={"code_module": "category", "code_presentation": "category",
               "id_student": "int32", "date": "int16", "sum_click": "int32"},
        chunksize=spec.vle_chunksize,
    )
    for i, chunk in enumerate(reader):
        # Activity before day 0 is pre-course browsing, not attendance.
        chunk = chunk.loc[chunk["date"] >= 0].copy()
        if chunk.empty:
            continue
        chunk["week"] = (chunk["date"] // 7).astype("int16") + 1
        g = chunk.groupby(
            ["code_module", "code_presentation", "id_student", "week"],
            observed=True, sort=False,
        ).agg(clicks=("sum_click", "sum"), active_days=("date", "nunique"))
        parts.append(g.reset_index())
        log.info("vle chunk %d -> %d learner-weeks", i, len(g))

    out = pd.concat(parts, ignore_index=True)
    return out.groupby(
        ["code_module", "code_presentation", "id_student", "week"],
        observed=True, as_index=False,
    ).agg(clicks=("clicks", "sum"), active_days=("active_days", "sum"))


def _assessment_features(root: Path, spec: OuladSpec) -> pd.DataFrame:
    """Per learner-week cumulative assessment state."""
    sa = pd.read_csv(root / "studentAssessment.csv")
    asm = pd.read_csv(root / "assessments.csv")
    m = sa.merge(asm, on="id_assessment", how="left")
    m = m.loc[m["date_submitted"].notna()]
    m["week"] = (m["date_submitted"].clip(lower=0) // 7).astype(int) + 1
    m["score"] = pd.to_numeric(m["score"], errors="coerce")
    m["failed"] = (m["score"] < PASS_MARK).astype(float)

    per_week = m.groupby(
        ["code_module", "code_presentation", "id_student", "week"], as_index=False
    ).agg(
        submitted=("id_assessment", "count"),
        score_sum=("score", "sum"),
        score_n=("score", "count"),
        failed=("failed", "sum"),
    )

    # How many assessments were DUE by each week, per presentation.
    due = asm.loc[asm["date"].notna()].copy()
    due["week"] = (due["date"].clip(lower=0) // 7).astype(int) + 1
    due_per_week = due.groupby(
        ["code_module", "code_presentation", "week"], as_index=False
    ).agg(due=("id_assessment", "count"))
    return per_week, due_per_week


def _rolling(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling engagement features, computed exactly as ``features`` expects."""
    g = df.groupby("student_key", sort=False)

    df["_present"] = (df["clicks"] > 0).astype(float)
    df["_rate"] = df["_present"] * 100.0

    # Term-to-date and last-4-week engagement.
    gt = df.groupby(["student_key", "term"], sort=False)
    df["attendance_rate_term_to_date"] = (
        100.0 * gt["_present"].cumsum() / gt.cumcount().add(1)
    )
    df["attendance_rate_last_4w"] = g["_rate"].transform(
        lambda s: s.rolling(4, min_periods=1).mean()
    )

    # OLS slope over the trailing 4 weeks -- the same estimator as
    # edutrace.features.attendance_trend, so the panel and the serving path
    # cannot disagree about what "trend" means.
    xs = np.arange(4.0) - 1.5
    denom = float((xs * xs).sum())

    def slope(s: pd.Series) -> float:
        y = s.to_numpy(dtype=float)
        n = len(y)
        if n < 2:
            return np.nan
        x = np.arange(n, dtype=float)
        x -= x.mean()
        d = float((x * x).sum())
        return float((x * (y - y.mean())).sum() / d) if d else np.nan

    df["attendance_trend_4w"] = g["_rate"].transform(
        lambda s: s.rolling(4, min_periods=2).apply(slope, raw=False)
    )

    # Consecutive silent weeks, expressed in the contract's "school days" unit.
    def streak(present: pd.Series) -> pd.Series:
        out, run = [], 0.0
        for p in present.to_numpy():
            run = 0.0 if p > 0 else run + 5.0
            out.append(run)
        return pd.Series(out, index=present.index)

    df["consecutive_absences"] = g["_present"].transform(streak)
    df["longest_absence_streak_term"] = df.groupby(
        ["student_key", "term"], sort=False
    )["consecutive_absences"].cummax()

    # Prior-term engagement and prior "year" absences.
    term_rate = df.groupby(["student_key", "term"], as_index=False)["_present"].mean()
    term_rate["attendance_rate_prior_term"] = (
        term_rate.groupby("student_key")["_present"].shift(1) * 100.0
    )
    df = df.merge(
        term_rate[["student_key", "term", "attendance_rate_prior_term"]],
        on=["student_key", "term"], how="left",
    )
    df["absences_prior_year"] = np.nan  # single presentation: no prior year

    return df.drop(columns=["_present", "_rate"])


# --------------------------------------------------------------------------


def load(
    root: str | Path, spec: OuladSpec | None = None
) -> tuple[pd.DataFrame, QualityReport]:
    spec = spec or OuladSpec()
    root = Path(root)
    missing = [f for f in FILES if not (root / f).exists()]
    if missing:
        raise SystemExit(
            f"missing OULAD files in {root}: {', '.join(missing)}. Download the "
            f"full archive from https://analyse.kmi.open.ac.uk/open_dataset"
        )

    info = pd.read_csv(root / "studentInfo.csv")
    reg = pd.read_csv(root / "studentRegistration.csv")
    courses = pd.read_csv(root / "courses.csv")
    rows_in = len(info)

    base = info.merge(
        reg, on=["code_module", "code_presentation", "id_student"], how="left"
    ).merge(courses, on=["code_module", "code_presentation"], how="left")

    # --- exclusion: withdrew before the presentation began -----------------
    pre_start = base["date_unregistration"].notna() & (base["date_unregistration"] < 0)
    n_pre = int(pre_start.sum())
    if spec.drop_pre_start_withdrawals:
        base = base.loc[~pre_start].copy()

    base["student_key"] = (
        base["id_student"].astype(str) + "_" + base["code_module"]
        + "_" + base["code_presentation"]
    )
    base["weeks"] = (base["module_presentation_length"] // 7).astype(int)
    base["exit_week"] = np.where(
        base["date_unregistration"].notna() & (base["date_unregistration"] >= 0),
        np.ceil((base["date_unregistration"] + 1) / 7.0),
        np.nan,
    )
    # A recorded exit after the presentation ends is administrative, not a
    # withdrawal from teaching; treat as censored.
    base.loc[base["exit_week"] > base["weeks"], "exit_week"] = np.nan

    # --- the learner x week grid -------------------------------------------
    log.info("building panel grid for %d learners", len(base))
    grid = base.loc[base.index.repeat(base["weeks"])].copy()
    grid["week_abs"] = grid.groupby("student_key", sort=False).cumcount() + 1

    # --- engagement --------------------------------------------------------
    log.info("aggregating %s", root / "studentVle.csv")
    vle = _aggregate_vle(root / "studentVle.csv", spec)
    vle["student_key"] = (
        vle["id_student"].astype(str) + "_" + vle["code_module"].astype(str)
        + "_" + vle["code_presentation"].astype(str)
    )
    grid = grid.merge(
        vle[["student_key", "week", "clicks", "active_days"]],
        left_on=["student_key", "week_abs"], right_on=["student_key", "week"],
        how="left",
    ).drop(columns=["week"])
    grid["clicks"] = grid["clicks"].fillna(0.0)
    grid["active_days"] = grid["active_days"].fillna(0.0)

    # --- pseudo term / week, so the weekly contract stays meaningful -------
    grid["term_idx"] = np.minimum(
        2, (grid["week_abs"] - 1) // spec.weeks_per_term
    ).astype(int)
    grid["term"] = grid["term_idx"].map({0: "T1", 1: "T2", 2: "T3"})
    grid["week"] = np.clip(
        grid["week_abs"] - grid["term_idx"] * spec.weeks_per_term, 1, WEEKS_PER_TERM
    )

    grid = grid.sort_values(["student_key", "week_abs"]).reset_index(drop=True)
    grid = _rolling(grid)

    # --- assessments -------------------------------------------------------
    per_week, due_per_week = _assessment_features(root, spec)
    per_week["student_key"] = (
        per_week["id_student"].astype(str) + "_" + per_week["code_module"]
        + "_" + per_week["code_presentation"]
    )
    grid = grid.merge(
        per_week[["student_key", "week", "submitted", "score_sum", "score_n", "failed"]],
        left_on=["student_key", "week_abs"], right_on=["student_key", "week"],
        how="left", suffixes=("", "_a"),
    ).drop(columns=["week_a"], errors="ignore")
    for c in ("submitted", "score_sum", "score_n", "failed"):
        grid[c] = grid[c].fillna(0.0)

    ga = grid.groupby("student_key", sort=False)
    cum_sum = ga["score_sum"].cumsum()
    cum_n = ga["score_n"].cumsum()
    grid["avg_exam_score"] = np.where(cum_n > 0, cum_sum / cum_n.replace(0, np.nan), np.nan)
    grid["core_subject_failures"] = ga["failed"].cumsum()
    grid["cum_submitted"] = ga["submitted"].cumsum()

    due_per_week = due_per_week.sort_values(
        ["code_module", "code_presentation", "week"]
    )
    due_per_week["cum_due"] = due_per_week.groupby(
        ["code_module", "code_presentation"]
    )["due"].cumsum()
    grid = grid.merge(
        due_per_week[["code_module", "code_presentation", "week", "cum_due"]],
        left_on=["code_module", "code_presentation", "week_abs"],
        right_on=["code_module", "code_presentation", "week"],
        how="left", suffixes=("", "_d"),
    ).drop(columns=["week_d"], errors="ignore")
    grid["cum_due"] = grid.groupby("student_key", sort=False)["cum_due"].ffill().fillna(0.0)
    grid["assessment_completion_rate"] = np.where(
        grid["cum_due"] > 0,
        100.0 * grid["cum_submitted"] / grid["cum_due"].replace(0, np.nan),
        np.nan,
    ).clip(0, 100)

    # Previous term's mean score.
    tscore = grid.groupby(["student_key", "term"], as_index=False)["avg_exam_score"].last()
    tscore["avg_exam_score_prev_term"] = tscore.groupby("student_key")[
        "avg_exam_score"
    ].shift(1)
    grid = grid.merge(
        tscore[["student_key", "term", "avg_exam_score_prev_term"]],
        on=["student_key", "term"], how="left",
    )

    # --- contract fields ---------------------------------------------------
    grid["school_id"] = grid["code_module"]           # module == "school"
    # Exam percentiles are computed within (school_id, grade_level). Setting
    # grade_level to the module makes assessment scores comparable within a
    # course rather than across courses -- OULAD module marking differs far
    # more than cohorts do, exactly the reason the school contract percentiles
    # raw marks in the first place.
    grid["grade_level"] = grid["code_module"]
    grid["academic_year"] = grid["code_presentation"].map(PRESENTATION_ORDER)
    grid["repeated_a_grade"] = grid["num_of_prev_attempts"] > 0
    grid["weeks_elapsed_in_year"] = grid["week_abs"]
    grid["age_years"] = grid["age_band"].map({"0-35": 27.0, "35-55": 45.0, "55<=": 60.0})

    # Protected attributes: audit only, never model inputs.
    grid["sex"] = grid["gender"]
    grid["region"] = grid["region"]
    grid["poverty_quintile"] = _imd_to_quintile(grid["imd_band"])
    grid["disability"] = grid["disability"]

    for col in ABSENT_IN_OULAD:
        if col not in grid.columns:
            grid[col] = np.nan
    grid["bece_registered"] = np.nan

    # --- labels ------------------------------------------------------------
    w = grid["week_abs"].to_numpy(dtype=float)
    ew = grid["exit_week"].to_numpy(dtype=float)
    observed_to = np.where(np.isfinite(ew), ew, grid["weeks"].to_numpy(dtype=float))
    has_event = np.isfinite(ew)

    label = has_event & (ew > w) & (ew <= w + spec.horizon_weeks)
    fully_observed = (w + spec.horizon_weeks) <= observed_to
    keep = label | fully_observed

    grid["label"] = label.astype("int8")
    # Audit columns, not features: they are absent from FEATURE_ORDER so
    # build_frame ignores them, but they make the censoring independently
    # checkable after the fact. Without them, "was censoring applied?" can only
    # be answered from data the panel has already dropped.
    grid["exit_week"] = ew
    grid["observed_weeks"] = observed_to
    n_dropped = int((~keep).sum())
    panel = grid.loc[keep].reset_index(drop=True)

    report = assess(
        panel,
        source=f"OULAD ({root.name})",
        features=(
            "attendance_rate_term_to_date", "attendance_rate_last_4w",
            "attendance_trend_4w", "consecutive_absences",
            "longest_absence_streak_term", "attendance_rate_prior_term",
            "avg_exam_score", "assessment_completion_rate",
            "core_subject_failures", "repeated_a_grade", "age_years",
        ),
        label_col="label",
        rows_in=rows_in,
        min_rows=5000,
        min_positives=200,
        max_label_rate=0.25,
    )
    report.warnings_.append(
        "OULAD is UK adult distance learning. A model trained on it validates "
        "the METHODOLOGY and must never be used to score a school learner. The "
        "populations, the outcome and the drivers are all different."
    )
    report.warnings_.append(
        "'Attendance' here is a proxy: a learner counts as present in a week if "
        "they clicked at least once. Clicks are not attendance."
    )
    if n_pre:
        report.warnings_.append(
            f"{n_pre:,} learners who unregistered before day 0 were EXCLUDED. "
            f"They never started, so they cannot stop -- the same reason "
            f"never-enrolled children are excluded from the household panel."
        )
    report.warnings_.append(
        f"{n_dropped:,} rows dropped by administrative censoring (horizon runs "
        f"past the end of the presentation with no event)."
    )
    report.warnings_.append(
        f"features with no OULAD counterpart, left missing: "
        f"{', '.join(sorted(ABSENT_IN_OULAD))}"
    )
    return panel, report


def _imd_to_quintile(s: pd.Series) -> pd.Series:
    """Index of Multiple Deprivation band -> quintile, 1 = most deprived.

    OULAD writes these as '0-10%', '10-20' (note the missing %), up to
    '90-100%'. The inconsistency is in the source file and silently produces
    an all-NaN column if you map on the literal strings.
    """
    def band(v):
        if not isinstance(v, str):
            return np.nan
        head = v.replace("%", "").split("-")[0].strip()
        try:
            lo = float(head)
        except ValueError:
            return np.nan
        return float(min(5, int(lo // 20) + 1))

    return s.map(band)


__all__ = ["OuladSpec", "load", "PRESENTATION_ORDER", "ABSENT_IN_OULAD"]
