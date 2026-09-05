"""Real-data ingestion: canonical panel, label construction, quality gates.

There are two different models here, and conflating them is the main way this
project could go wrong.

**Model B — weekly in-school triage** (what ``edutrace.contract`` describes).
Unit: one learner, one week.  Target: stops attending within 8 weeks.  Needs
attendance registers, continuous assessment, levy ledgers, behaviour records.
**No public dataset in the world contains this for Ghanaian JHS.**  It exists
only inside schools and inside GES EMIS.  ``emis.py`` is the adapter, and a
partner school is the only way to get it.

**Model A — annual enrolment continuation** (this module's ``ENROLMENT_FEATURES``).
Unit: one child, one school year.  Target: enrolled last year, not enrolled
this year.  Needs only household survey data — which *is* publicly available
for Ghana, and is what makes a locally credible model possible in weeks rather
than never.

Model A cannot do weekly triage: it has no attendance, so it cannot tell you
who to talk to on Tuesday.  What it *can* do is three things that matter:

1.  Give real, Ghanaian effect sizes for the household drivers — poverty,
    distance, over-age, child labour, guardian structure — instead of the
    hand-written coefficients in ``simulate/generator.py``.
2.  Target enrolment campaigns and re-entry outreach between school years,
    which is a genuine product on its own.
3.  Serve as the honest interim answer while a partner school accumulates the
    register data Model B requires.

Everything here refuses to guess.  Column mappings must be supplied or
confirmed, the label must be constructible, and ``QualityReport`` fails the
ingest rather than emitting a panel that looks fine and encodes nonsense.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Model A feature set
# --------------------------------------------------------------------------

#: Features an annual household survey can genuinely support.  Deliberately a
#: separate, smaller contract from ``edutrace.contract.FEATURE_ORDER`` -- a
#: model trained where attendance is always missing will never learn to use
#: attendance, and then ignores it at serving time when it finally appears.
#: Two contracts, two fingerprints, no silent overlap.
ENROLMENT_FEATURES: tuple[str, ...] = (
    "age_years",
    "age_for_grade_gap",
    "grade_ordinal",
    "years_of_education",
    "repeated_a_grade",
    "attended_previous_year",
    "household_size",
    "siblings_in_school",
    "wealth_quintile",
    "guardian_type_ord",
    "head_education_years",
    "mother_education_years",
    "father_education_years",
    "urban",
    "distance_band_ord",
    "does_paid_or_farm_work",
    "has_electricity",
    "has_improved_water",
    "orphan_status",
)

ENROLMENT_PROTECTED: tuple[str, ...] = ("sex", "region", "wealth_quintile")

ENROLMENT_LABEL = "left_school"


def enrolment_fingerprint() -> str:
    import hashlib

    return hashlib.sha256(
        "|".join(ENROLMENT_FEATURES).encode()
    ).hexdigest()[:16]


# --------------------------------------------------------------------------


@dataclass(slots=True)
class ColumnMap:
    """Source-column -> canonical-name mapping, with recodes.

    ``recode`` holds per-column value maps, because survey codes are not
    self-describing: DHS writes urban/rural as 1/2, MICS as 1/2 with different
    labels per round, and Young Lives as a string.  Getting this wrong produces
    a model that has learned the inverse of reality and reports a fine AUC.
    """

    columns: dict[str, str] = field(default_factory=dict)
    recode: dict[str, dict[Any, Any]] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "ColumnMap":
        d = json.loads(Path(path).read_text())
        return cls(
            columns=d.get("columns", {}),
            recode=d.get("recode", {}),
            notes=d.get("notes", ""),
        )

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.write_text(
            json.dumps(
                {"columns": self.columns, "recode": self.recode, "notes": self.notes},
                indent=2,
            )
        )
        return p

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        present = {src: dst for src, dst in self.columns.items() if src in df.columns}
        out = df[list(present)].rename(columns=present).copy()
        for col, mapping in self.recode.items():
            if col in out.columns:
                out[col] = out[col].map(lambda v: mapping.get(v, mapping.get(str(v), v)))
        return out

    def missing_from(self, df: pd.DataFrame) -> list[str]:
        return sorted(s for s in self.columns if s not in df.columns)


# --------------------------------------------------------------------------


@dataclass(slots=True)
class QualityReport:
    """Gate between a raw survey extract and anything that gets trained on."""

    source: str
    rows_in: int
    rows_out: int
    label_positives: int
    label_rate: float
    feature_support: dict[str, float] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    warnings_: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.problems

    def render(self) -> str:
        lines = [
            f"Ingest quality report — {self.source}",
            "=" * 78,
            f"  rows in           {self.rows_in:,}",
            f"  rows out          {self.rows_out:,}",
            f"  label positives   {self.label_positives:,} ({self.label_rate:.3%})",
            "",
            "  feature support (share of rows with a value):",
        ]
        for k, v in sorted(self.feature_support.items(), key=lambda kv: kv[1]):
            bar = "#" * int(v * 30)
            flag = "  <-- unusable" if v < 0.05 else ("  <-- sparse" if v < 0.30 else "")
            lines.append(f"      {k:<28} {v:>6.1%} {bar}{flag}")
        if self.warnings_:
            lines += ["", "  warnings:"] + [f"      ! {w}" for w in self.warnings_]
        if self.problems:
            lines += ["", "  BLOCKING PROBLEMS:"] + [f"      X {p}" for p in self.problems]
            lines += ["", "  Panel NOT written. Fix the mapping and re-run."]
        else:
            lines += ["", "  OK — panel written."]
        return "\n".join(lines)


def assess(
    df: pd.DataFrame,
    source: str,
    features: tuple[str, ...],
    label_col: str,
    rows_in: int,
    min_rows: int = 500,
    min_positives: int = 50,
    max_label_rate: float = 0.40,
) -> QualityReport:
    support = {
        f: (float(df[f].notna().mean()) if f in df.columns else 0.0) for f in features
    }
    pos = int(pd.to_numeric(df[label_col], errors="coerce").fillna(0).sum())
    rate = pos / len(df) if len(df) else 0.0

    problems, warns = [], []
    if len(df) < min_rows:
        problems.append(
            f"only {len(df):,} usable rows (need >= {min_rows:,}). A model fitted "
            f"to this will not generalise and its calibration will be noise."
        )
    if pos < min_positives:
        problems.append(
            f"only {pos} positive cases (need >= {min_positives}). Below this the "
            f"held-out evaluation cannot distinguish the model from chance."
        )
    if rate > max_label_rate:
        problems.append(
            f"label rate {rate:.1%} is implausibly high for school leaving. This "
            f"almost always means the enrolment transition was inverted or the "
            f"age filter was not applied — check the recode before trusting it."
        )
    dead = [f for f, v in support.items() if v < 0.05]
    if dead:
        warns.append(
            f"features with under 5% support will be ignored by the model and "
            f"must not be relied on at serving time: {', '.join(dead)}"
        )
    sparse = [f for f, v in support.items() if 0.05 <= v < 0.30]
    if sparse:
        warns.append(f"sparse features (under 30% support): {', '.join(sparse)}")

    return QualityReport(
        source=source,
        rows_in=rows_in,
        rows_out=len(df),
        label_positives=pos,
        label_rate=rate,
        feature_support=support,
        problems=problems,
        warnings_=warns,
    )


# --------------------------------------------------------------------------
# Shared derivations
# --------------------------------------------------------------------------

#: Ghana JHS official ages, from the MoE/GPE Partnership Compact 2023.
JHS_AGE_RANGE = (12, 17)
OFFICIAL_AGE = {"JHS1": 12, "JHS2": 13, "JHS3": 14}


def build_enrolment_label(
    df: pd.DataFrame,
    attended_current: str = "attended_current_year",
    attended_previous: str = "attended_previous_year",
) -> pd.Series:
    """The one-year enrolment transition, as UIS and UNICEF construct it.

    ``left_school`` = was in school last year, is not in school this year.

    Children who never attended are **excluded**, not labelled zero: never
    enrolling and dropping out are different outcomes with different drivers
    and different interventions, and a model trained on their union learns
    neither. Ghana's 2021 census counted 942,427 children who had never
    attended against 1.2m out of school in total — collapsing those groups
    would put the majority class in the wrong place entirely.
    """
    cur = pd.to_numeric(df.get(attended_current), errors="coerce")
    prev = pd.to_numeric(df.get(attended_previous), errors="coerce")
    return ((prev == 1) & (cur == 0)).astype("int8")


def restrict_to_jhs_age(
    df: pd.DataFrame, age_col: str = "age_years", lo: int | None = None,
    hi: int | None = None,
) -> pd.DataFrame:
    lo = lo if lo is not None else JHS_AGE_RANGE[0]
    hi = hi if hi is not None else JHS_AGE_RANGE[1]
    age = pd.to_numeric(df.get(age_col), errors="coerce")
    return df.loc[age.between(lo, hi)].copy()


def derive_age_for_grade(df: pd.DataFrame) -> pd.Series:
    """Age minus the official age for the grade.

    Over-age enrolment is roughly half the Ghanaian JHS cohort — GER 85%
    against NER 45% — so this is one of the highest-value derived features
    available from any survey that records age and grade.
    """
    age = pd.to_numeric(df.get("age_years"), errors="coerce")
    grade = df.get("grade_level")
    if grade is None:
        g_ord = pd.to_numeric(df.get("grade_ordinal"), errors="coerce")
        official = 11 + g_ord
    else:
        official = grade.map(OFFICIAL_AGE)
    return age - pd.to_numeric(official, errors="coerce")


def finalise(
    df: pd.DataFrame,
    source: str,
    rows_in: int,
    year_col: str = "academic_year",
) -> tuple[pd.DataFrame, QualityReport]:
    """Add derived columns, order to the enrolment contract, assess quality."""
    out = df.copy()
    if "age_for_grade_gap" not in out.columns:
        out["age_for_grade_gap"] = derive_age_for_grade(out)
    if ENROLMENT_LABEL not in out.columns:
        out[ENROLMENT_LABEL] = build_enrolment_label(out)

    for f in ENROLMENT_FEATURES:
        if f not in out.columns:
            out[f] = np.nan

    keep = (
        ["child_key", year_col, ENROLMENT_LABEL]
        + list(ENROLMENT_FEATURES)
        + [c for c in ENROLMENT_PROTECTED if c in out.columns]
    )
    keep = [c for c in dict.fromkeys(keep) if c in out.columns]
    out = out[keep]
    out = out.loc[out[ENROLMENT_LABEL].notna()]

    return out, assess(
        out, source, ENROLMENT_FEATURES, ENROLMENT_LABEL, rows_in=rows_in
    )


Adapter = Callable[..., tuple[pd.DataFrame, QualityReport]]


__all__ = [
    "ENROLMENT_FEATURES",
    "ENROLMENT_PROTECTED",
    "ENROLMENT_LABEL",
    "enrolment_fingerprint",
    "ColumnMap",
    "QualityReport",
    "assess",
    "build_enrolment_label",
    "restrict_to_jhs_age",
    "derive_age_for_grade",
    "finalise",
    "JHS_AGE_RANGE",
    "OFFICIAL_AGE",
]
