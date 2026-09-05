"""Young Lives -> annual enrolment panel.

The best-fitting REAL longitudinal data reachable in days rather than months:
12,000 children in Ethiopia, India, Peru and Vietnam followed since 2001, with
a genuine enrolled -> left-school transition across ages 12-15, plus household
poverty, shocks, child work and prior grades.

    https://www.younglives.org.uk/using-our-data
    UK Data Service registration, End User Licence, free.
    Rounds 1-7 constructed files: SN 9543 (panel format, ~200 variables).

It is NOT Ghana. Use it to establish that the modelling approach recovers real
effect sizes on real children of the right age, and to sanity-check the
direction and rough magnitude of the household drivers. Then localise with
Ghana MICS/DHS, which are Ghanaian but shallower. Reporting a Young Lives model
as a Ghanaian dropout predictor would be a country substitution the evaluation
cannot detect.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .base import ColumnMap, QualityReport, finalise, restrict_to_jhs_age

#: Constructed-file names. Confirm against the SN 9543 data dictionary; Young
#: Lives renames variables between the round files and the constructed files.
YL_DEFAULT = ColumnMap(
    columns={
        "childid": "child_key",
        "round": "round",
        "yc": "cohort_code",
        "chsex": "sex_code",
        "agemon": "age_months",
        "enrol": "attended_current_raw",
        "grade": "grade_ordinal",
        "hhsize": "household_size",
        "wi": "wealth_index",
        "typesite": "residence_code",
        "dadedu": "father_education_years",
        "mumedu": "mother_education_years",
        "chlabour": "does_paid_or_farm_work",
        "dadlive": "father_alive_raw",
        "mumlive": "mother_alive_raw",
        "elecq": "has_electricity",
        "drwaterq": "has_improved_water",
        "region": "region",
    },
    recode={"sex_code": {1: "M", 2: "F"}, "residence_code": {1: 0, 2: 1}},
    notes="Young Lives constructed files, rounds 1-7 (SN 9543).",
)


def load(
    path: str | Path,
    colmap: ColumnMap | None = None,
    age_lo: int | None = None,
    age_hi: int | None = None,
) -> tuple[pd.DataFrame, QualityReport]:
    """Build the transition label by lagging enrolment WITHIN each child."""
    colmap = colmap or YL_DEFAULT
    path = Path(path)
    raw = (
        pd.read_stata(path, convert_categoricals=False)
        if path.suffix.lower() == ".dta"
        else pd.read_csv(path, low_memory=False)
    )
    rows_in = len(raw)
    raw.columns = [str(c).lower() for c in raw.columns]

    resolved = ColumnMap(
        columns={s.lower(): d for s, d in colmap.columns.items()
                 if s.lower() in raw.columns},
        recode=colmap.recode,
    )
    df = resolved.apply(raw)
    missing = [s for s in colmap.columns if s.lower() not in raw.columns]

    if "round" not in df.columns:
        raise SystemExit(
            "no 'round' column found. The panel label is built by lagging "
            "enrolment across rounds within each child, so the round index is "
            "required."
        )

    df["age_years"] = pd.to_numeric(df.get("age_months"), errors="coerce") / 12.0
    df["attended_current_year"] = pd.to_numeric(
        df.get("attended_current_raw"), errors="coerce"
    ).clip(0, 1)

    # The lag is the whole point: previous ROUND, within child.
    df = df.sort_values(["child_key", "round"])
    df["attended_previous_year"] = df.groupby("child_key")[
        "attended_current_year"
    ].shift(1)

    # Wealth index is continuous in Young Lives; cut to quintiles so the
    # feature means the same thing as it does in DHS/MICS.
    if "wealth_index" in df.columns:
        wi = pd.to_numeric(df["wealth_index"], errors="coerce")
        df["wealth_quintile"] = pd.qcut(wi, 5, labels=[1, 2, 3, 4, 5],
                                        duplicates="drop").astype("float64")

    df["urban"] = pd.to_numeric(df.get("residence_code"), errors="coerce")
    df["sex"] = df.get("sex_code")
    m = pd.to_numeric(df.get("mother_alive_raw"), errors="coerce")
    f = pd.to_numeric(df.get("father_alive_raw"), errors="coerce")
    df["orphan_status"] = ((m == 0).astype(int) + (f == 0).astype(int)).astype(
        "float64"
    ) if not (m.isna().all() and f.isna().all()) else np.nan
    df["academic_year"] = pd.to_numeric(df["round"], errors="coerce")

    df = restrict_to_jhs_age(df, lo=age_lo, hi=age_hi)
    # First round per child has no previous year and cannot be labelled.
    df = df.loc[df["attended_previous_year"].notna()]

    panel, report = finalise(df, source=f"Young Lives {path.name}", rows_in=rows_in)
    report.warnings_.append(
        "Young Lives is Ethiopia/India/Peru/Vietnam, NOT Ghana. Use it to "
        "validate the approach on real children of the right age; localise with "
        "Ghana MICS/DHS before claiming anything about Ghanaian learners."
    )
    report.warnings_.append(
        "'academic_year' holds the Young Lives ROUND index, so the temporal "
        "split splits by round -- which is the correct forward-chaining test here."
    )
    if missing:
        report.warnings_.append(
            f"columns absent from the file: {', '.join(missing[:12])}"
            f"{'...' if len(missing) > 12 else ''}"
        )
    return panel, report


__all__ = ["YL_DEFAULT", "load"]
