"""School registers / GES EMIS -> weekly hazard panel.

This is the only path that produces the model actually specified: weekly,
in-school, actionable on a Tuesday.  No public dataset contains it, because
attendance registers do not leave schools.  What a partner school can give you
is usually one of two shapes, and both are handled here:

    DAILY   one row per learner per day, present/absent
    WEEKLY  one row per learner per week, sessions attended out of sessions held

Everything else -- rolling rates, streaks, trends, the 8-week label, the
censoring -- is derived here so it is derived *identically* to the simulator
and to ``edutrace.features``.  Deriving it in a spreadsheet first is how
train/serve skew gets in.

The exit definition, which the school must agree in writing before you start
-------------------------------------------------------------------------------
"Stopped attending" is a decision, not a fact.  A learner absent for three
weeks who returns is not a dropout.  A learner who transfers is not a dropout
either, and counting them as one teaches the model that transfers are
failures.  The default here:

    A learner EXITS at the last date they attended, if they then record no
    attendance for ``exit_gap_weeks`` consecutive weeks AND do not return
    before the end of the observation window AND are not marked transferred.

Transfers are **excluded from the panel entirely**, not labelled zero: their
outcome is unobserved, and treating unobserved as negative is the same error
as labelling administratively censored rows zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..contract import HORIZON_WEEKS, WEEKS_PER_TERM
from ..features import attendance_trend
from .base import QualityReport, assess

REQUIRED_ANY = [
    ("student_key", "a stable pseudonymous learner id"),
    ("school_id", "which school"),
    ("academic_year", "e.g. 2025"),
    ("term", "T1 / T2 / T3"),
]


@dataclass(slots=True)
class EmisSpec:
    """How this school's export is shaped."""

    granularity: str = "weekly"        # "weekly" or "daily"
    sessions_per_week: int = 5
    exit_gap_weeks: int = 4
    transfer_col: str | None = "transferred_out"
    present_col: str = "sessions_present"
    held_col: str = "sessions_held"
    date_col: str = "date"
    present_flag_col: str = "present"


def load(
    path: str | Path,
    spec: EmisSpec | None = None,
    horizon_weeks: int = HORIZON_WEEKS,
) -> tuple[pd.DataFrame, QualityReport]:
    spec = spec or EmisSpec()
    raw = pd.read_csv(path, low_memory=False)
    rows_in = len(raw)

    missing = [c for c, _ in REQUIRED_ANY if c not in raw.columns]
    if missing:
        raise SystemExit(
            "school export is missing required columns: "
            + ", ".join(f"{c} ({why})" for c, why in REQUIRED_ANY if c in missing)
        )

    df = raw.copy()
    if spec.granularity == "daily":
        df = _daily_to_weekly(df, spec)

    df = df.sort_values(["student_key", "academic_year", "term", "week"])

    if spec.transfer_col and spec.transfer_col in df.columns:
        moved = df.groupby("student_key")[spec.transfer_col].transform(
            lambda s: pd.to_numeric(s, errors="coerce").fillna(0).max() > 0
        )
        n_moved = int(df.loc[moved, "student_key"].nunique())
        df = df.loc[~moved].copy()
    else:
        n_moved = 0

    df = _derive_rolling(df, spec)
    df, n_exits = _attach_exit_labels(df, spec, horizon_weeks)

    report = assess(
        df,
        source=f"EMIS {Path(path).name}",
        features=(
            "attendance_rate_term_to_date",
            "attendance_rate_last_4w",
            "attendance_trend_4w",
            "consecutive_absences",
            "avg_exam_score",
            "fee_arrears_terms",
            "core_subject_failures",
        ),
        label_col="label",
        rows_in=rows_in,
        min_rows=2000,
        min_positives=40,
        max_label_rate=0.15,
    )
    if n_moved:
        report.warnings_.append(
            f"{n_moved} learners marked transferred were EXCLUDED, not labelled "
            f"zero. Their outcome is unobserved; counting a transfer as a "
            f"non-event teaches the model that leaving quietly is safe."
        )
    report.warnings_.append(
        f"exit defined as {spec.exit_gap_weeks} consecutive weeks of no "
        f"attendance with no return before the end of the window. Agree this "
        f"definition with the school in writing before training -- it decides "
        f"what the model means."
    )
    if n_exits:
        report.warnings_.append(f"{n_exits} learner exits identified.")
    return df, report


# --------------------------------------------------------------------------


def _daily_to_weekly(df: pd.DataFrame, spec: EmisSpec) -> pd.DataFrame:
    if spec.date_col not in df.columns:
        raise SystemExit(
            f"daily granularity needs a '{spec.date_col}' column to group into weeks"
        )
    d = df.copy()
    d[spec.date_col] = pd.to_datetime(d[spec.date_col], errors="coerce")
    d = d.loc[d[spec.date_col].notna()]
    if "week" not in d.columns:
        # Week within term, from the earliest date recorded for that term.
        base = d.groupby(["academic_year", "term"])[spec.date_col].transform("min")
        d["week"] = ((d[spec.date_col] - base).dt.days // 7 + 1).clip(1, WEEKS_PER_TERM)

    present = pd.to_numeric(d.get(spec.present_flag_col), errors="coerce").fillna(0)
    d["_present"] = present
    keys = ["student_key", "school_id", "academic_year", "term", "week"]
    agg = d.groupby(keys, as_index=False).agg(
        sessions_present=("_present", "sum"), sessions_held=("_present", "size")
    )
    # Carry any per-learner static columns through.
    statics = [
        c for c in df.columns
        if c not in keys + [spec.date_col, spec.present_flag_col, "_present"]
    ]
    if statics:
        first = d.groupby(keys, as_index=False)[statics].first()
        agg = agg.merge(first, on=keys, how="left")
    return agg


def _derive_rolling(df: pd.DataFrame, spec: EmisSpec) -> pd.DataFrame:
    d = df.copy()
    present = pd.to_numeric(d.get(spec.present_col), errors="coerce")
    held = pd.to_numeric(d.get(spec.held_col), errors="coerce")
    if held.isna().all():
        held = pd.Series(spec.sessions_per_week, index=d.index, dtype=float)
    d["_present"], d["_held"] = present, held
    d["_rate"] = 100.0 * present / held.replace(0, np.nan)

    g = d.groupby(["student_key", "academic_year", "term"], sort=False)
    d["attendance_rate_term_to_date"] = (
        100.0 * g["_present"].cumsum() / g["_held"].cumsum().replace(0, np.nan)
    )
    d["attendance_rate_last_4w"] = g["_rate"].transform(
        lambda s: s.rolling(4, min_periods=1).mean()
    )
    # Same OLS slope as edutrace.features.attendance_trend, so the training
    # panel and the serving path cannot disagree.
    d["attendance_trend_4w"] = g["_rate"].transform(
        lambda s: s.rolling(4, min_periods=2).apply(
            lambda w: attendance_trend(list(w), 4), raw=False
        )
    )

    absent = (held - present).fillna(0)
    d["_absent"] = absent
    d["consecutive_absences"] = g["_absent"].transform(_streak)
    d["longest_absence_streak_term"] = g.apply(
        lambda x: _streak(x["_absent"]).cummax(), include_groups=False
    ).reset_index(level=[0, 1, 2], drop=True)

    prior_year = d.groupby(["student_key", "academic_year"], sort=False)[
        "_absent"
    ].transform("sum")
    d["absences_prior_year"] = (
        d.groupby("student_key", sort=False)["academic_year"].transform("min")
        .ne(d["academic_year"])
        .astype(float)
        * prior_year
    ).replace(0, np.nan)

    return d.drop(columns=["_present", "_held", "_rate", "_absent"], errors="ignore")


def _streak(absent: pd.Series) -> pd.Series:
    """Running count of consecutive absent sessions, reset by any attendance."""
    out, run = [], 0.0
    for a in absent.fillna(0).to_numpy():
        run = run + a if a > 0 else 0.0
        out.append(run)
    return pd.Series(out, index=absent.index)


def _attach_exit_labels(
    df: pd.DataFrame, spec: EmisSpec, horizon: int
) -> tuple[pd.DataFrame, int]:
    """Find each learner's exit week and build the forward-hazard label.

    Identical construction to ``simulate.generator._attach_labels``: rows whose
    horizon runs past the end of observation with no event are DROPPED, not
    labelled zero. Keeping them teaches the model that the last eight weeks of
    every record are safe, which is false and is the classic quiet leak.
    """
    d = df.copy()
    d["_abs_week"] = (
        d["term"].map({"T1": 0, "T2": 1, "T3": 2}).fillna(0) * WEEKS_PER_TERM
        + pd.to_numeric(d["week"], errors="coerce")
        + (d["academic_year"] - d["academic_year"].min()) * WEEKS_PER_TERM * 3
    )

    last_seen = d.groupby("student_key")["_abs_week"].max()
    window_end = float(d["_abs_week"].max())
    exits = last_seen[(window_end - last_seen) >= spec.exit_gap_weeks]

    exit_week = d["student_key"].map(exits)
    observed_to = d["student_key"].map(
        lambda k: exits.get(k, window_end)
    ).astype(float)

    w = d["_abs_week"].to_numpy(dtype=float)
    ew = exit_week.to_numpy(dtype=float)
    has_event = ~np.isnan(ew)

    label = has_event & (ew > w) & (ew <= w + horizon)
    fully_observed = (w + horizon) <= observed_to.to_numpy(dtype=float)
    keep = label | fully_observed

    d["label"] = label.astype("int8")
    d = d.loc[keep].drop(columns=["_abs_week"]).reset_index(drop=True)
    return d, int(len(exits))


__all__ = ["EmisSpec", "load"]
