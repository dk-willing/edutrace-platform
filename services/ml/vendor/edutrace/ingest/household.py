"""DHS and MICS household surveys -> annual enrolment panel.

These are the two datasets that make a *Ghanaian* model possible in weeks.
Both are free, both cover Ghana with national samples, both record the
one-year school transition directly, and both are obtainable by registering
and stating a purpose.

    Ghana DHS 2022    https://dhsprogram.com  (per-project registration)
                      also microdata.statsghana.gov.gh/index.php/catalog/123
    Ghana MICS 2017/18 https://mics.unicef.org/surveys  (UNICEF MICS account)
                      GIS cluster release allows real distance-to-school

**Verify the recode against your download.**  DHS variable numbering shifts
between phases and MICS between rounds, so the maps below are defaults, not
truth.  Every DHS download ships a recode manual; open it, confirm the six
schooling variables, and correct ``DHS_DEFAULT`` if they differ.  A silently
wrong mapping here inverts the label and the pipeline will report a healthy
AUC on a model that has learned the opposite of reality.  ``--check`` prints
the crosstab you need to eyeball before trusting anything.

The DHS schooling block (Recode 6/7/8), which is what carries the outcome:

    HV121  attended school during the CURRENT school year   (0 no, 1/2 yes)
    HV122  educational level, current year   (0 pre, 1 primary, 2 secondary, 3 higher)
    HV123  educational grade, current year
    HV124  attended school during the PREVIOUS school year
    HV125  educational level, previous year
    HV126  educational grade, previous year

Note 121-123 are current and 124-126 previous.  It is commonly miscited the
other way round, which inverts the transition.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .base import (
    ColumnMap,
    QualityReport,
    finalise,
    restrict_to_jhs_age,
)

# --------------------------------------------------------------------------

DHS_DEFAULT = ColumnMap(
    columns={
        "hhid": "household_key",
        "hvidx": "member_index",
        "hv105": "age_years",
        "hv104": "sex_code",
        "hv025": "residence_code",
        "hv024": "region",
        "hv270": "wealth_quintile",
        "hv009": "household_size",
        "hv108": "years_of_education",
        "hv106": "education_level_code",
        "hv101": "relation_to_head_code",
        "hv121": "attended_current_raw",
        "hv122": "level_current_code",
        "hv123": "grade_current",
        "hv124": "attended_previous_raw",
        "hv125": "level_previous_code",
        "hv126": "grade_previous",
        "hv206": "has_electricity_raw",
        "hv201": "water_source_code",
        "hv111": "mother_alive_raw",
        "hv113": "father_alive_raw",
        "hv219": "head_sex_code",
        "hv007": "survey_year",
    },
    recode={
        "sex_code": {1: "M", 2: "F"},
        "residence_code": {1: 1, 2: 0},          # 1 urban -> urban=1
        "has_electricity_raw": {0: 0, 1: 1},
    },
    notes="DHS Recode 6/7/8 household member (PR) file. VERIFY against the "
          "recode manual shipped with your extract.",
)

#: MICS6 household questionnaire, education module.  Round-to-round variation
#: is larger than DHS, so this is a starting point that you WILL need to edit.
MICS_DEFAULT = ColumnMap(
    columns={
        "HH1": "cluster",
        "HH2": "household_key",
        "HL1": "member_index",
        "HL6": "age_years",
        "HL4": "sex_code",
        "HH6": "residence_code",
        "HH7": "region",
        "windex5": "wealth_quintile",
        "HH48": "household_size",
        "ED9": "attended_current_raw",
        "ED10A": "level_current_code",
        "ED10B": "grade_current",
        "ED14": "attended_previous_raw",
        "ED15A": "level_previous_code",
        "ED15B": "grade_previous",
        "HC8": "has_electricity_raw",
        "HL10": "mother_alive_raw",
        "HL12": "father_alive_raw",
    },
    recode={
        "sex_code": {1: "M", 2: "F"},
        "residence_code": {1: 1, 2: 0},
    },
    notes="MICS6 household + education module. Variable names differ by round; "
          "check your survey's codebook. ED numbering in particular moves.",
)

#: DHS/MICS level codes: 2 = secondary. Ghanaian JHS sits inside 'secondary'.
SECONDARY_LEVEL_CODES = {2, 3}


def _yes(series: pd.Series) -> pd.Series:
    """DHS/MICS encode attendance as 0 no, 1 yes, 2 yes-currently, 8/9 missing."""
    v = pd.to_numeric(series, errors="coerce")
    out = pd.Series(np.nan, index=series.index, dtype="float64")
    out[v == 0] = 0.0
    out[v.isin([1, 2])] = 1.0
    return out


def load(
    path: str | Path,
    survey: str = "dhs",
    colmap: ColumnMap | None = None,
    age_lo: int | None = None,
    age_hi: int | None = None,
    secondary_only: bool = True,
) -> tuple[pd.DataFrame, QualityReport]:
    """Read a DHS or MICS member-level extract into the enrolment panel.

    Accepts .dta (Stata, the DHS native format), .sav (SPSS, common for MICS),
    .csv or .parquet.
    """
    path = Path(path)
    if colmap is None:
        colmap = DHS_DEFAULT if survey.lower() == "dhs" else MICS_DEFAULT

    raw = _read_any(path)
    rows_in = len(raw)
    raw.columns = [str(c) for c in raw.columns]

    # Survey files are inconsistently cased; match case-insensitively.
    lower = {c.lower(): c for c in raw.columns}
    resolved = ColumnMap(
        columns={
            lower[src.lower()]: dst
            for src, dst in colmap.columns.items()
            if src.lower() in lower
        },
        recode=colmap.recode,
        notes=colmap.notes,
    )
    missing = [s for s in colmap.columns if s.lower() not in lower]
    df = resolved.apply(raw)

    # --- the transition -------------------------------------------------
    df["attended_current_year"] = _yes(df.get("attended_current_raw", pd.Series(dtype=float)))
    df["attended_previous_year"] = _yes(df.get("attended_previous_raw", pd.Series(dtype=float)))

    # --- household-level derivations, BEFORE the age filter -------------
    # These must be computed while siblings and the household head are still
    # in the frame; filtering to 12-17 year olds first would silently produce
    # all-NaN columns, which the support report would then flag as "unusable"
    # when the data was there all along.
    df = _household_derivations(df)

    # --- restrict to children who were in SECONDARY last year -----------
    # Otherwise the panel mixes primary leavers with JHS leavers, which have
    # different hazards and different policy levers.
    if secondary_only and "level_previous_code" in df.columns:
        lvl = pd.to_numeric(df["level_previous_code"], errors="coerce")
        df = df.loc[lvl.isin(SECONDARY_LEVEL_CODES) | lvl.isna()].copy()

    df = restrict_to_jhs_age(df, lo=age_lo, hi=age_hi)

    # --- derived ---------------------------------------------------------
    df["grade_ordinal"] = pd.to_numeric(df.get("grade_previous"), errors="coerce")
    df["urban"] = pd.to_numeric(df.get("residence_code"), errors="coerce")
    df["sex"] = df.get("sex_code")
    df["has_electricity"] = pd.to_numeric(
        df.get("has_electricity_raw"), errors="coerce"
    )
    if "water_source_code" in df.columns:
        w = pd.to_numeric(df["water_source_code"], errors="coerce")
        # DHS: codes under 30 are piped/tubewell/protected -> improved.
        df["has_improved_water"] = (w < 30).astype("float64").where(w.notna())
    df["orphan_status"] = _orphan(df)
    df["guardian_type_ord"] = _guardian(df)
    df["repeated_a_grade"] = _repeated(df)
    df["child_key"] = (
        df.get("household_key", pd.Series(range(len(df)))).astype(str)
        + "-"
        + df.get("member_index", pd.Series(range(len(df)))).astype(str)
    )
    df["academic_year"] = pd.to_numeric(df.get("survey_year"), errors="coerce")
    if df["academic_year"].isna().all():
        df["academic_year"] = 0

    panel, report = finalise(df, source=f"{survey.upper()} {path.name}", rows_in=rows_in)
    if missing:
        report.warnings_.append(
            f"{len(missing)} mapped columns absent from the file and dropped: "
            f"{', '.join(missing[:12])}{'...' if len(missing) > 12 else ''}. "
            f"Check your survey's codebook and supply --map."
        )
    return panel, report


def _household_derivations(df: pd.DataFrame) -> pd.DataFrame:
    """Features DHS/MICS hold implicitly, across members of a household.

    Household head's education and the number of siblings currently in school
    are both strong, well-attested predictors of continuation, and both are
    sitting in the file -- they just need a group-by. The Malawi household-panel
    study that reports AUC ~0.83 for school dropout has father's education as a
    top feature, so leaving this on the table would be a real loss.
    """
    d = df.copy()
    if "household_key" not in d.columns:
        return d

    g = d.groupby("household_key", sort=False)

    # Head's years of education: the member whose relation-to-head code is 1.
    if {"relation_to_head_code", "years_of_education"} <= set(d.columns):
        rel = pd.to_numeric(d["relation_to_head_code"], errors="coerce")
        edu = pd.to_numeric(d["years_of_education"], errors="coerce")
        head_edu = edu.where(rel == 1)
        d["head_education_years"] = g["household_key"].transform(
            lambda s: head_edu.loc[s.index].max()
        )

    # Siblings in school: other members of the household attending this year.
    if "attended_current_year" in d.columns:
        att = pd.to_numeric(d["attended_current_year"], errors="coerce").fillna(0)
        d["_att"] = att
        total = d.groupby("household_key", sort=False)["_att"].transform("sum")
        d["siblings_in_school"] = (total - att).clip(lower=0)
        d = d.drop(columns=["_att"])

    return d


def _read_any(path: Path) -> pd.DataFrame:
    s = path.suffix.lower()
    if s == ".dta":
        return pd.read_stata(path, convert_categoricals=False)
    if s == ".sav":
        try:
            import pyreadstat
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "reading SPSS .sav needs pyreadstat:  pip install pyreadstat"
            ) from exc
        return pyreadstat.read_sav(str(path), apply_value_formats=False)[0]
    if s in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def _orphan(df: pd.DataFrame) -> pd.Series:
    m = pd.to_numeric(df.get("mother_alive_raw"), errors="coerce")
    f = pd.to_numeric(df.get("father_alive_raw"), errors="coerce")
    if m.isna().all() and f.isna().all():
        return pd.Series(np.nan, index=df.index)
    # 0 = both alive, 1 = one deceased, 2 = both deceased.
    return ((m == 0).astype(int) + (f == 0).astype(int)).astype("float64")


def _guardian(df: pd.DataFrame) -> pd.Series:
    """Map DHS relationship-to-head into the contract's guardian ordinal."""
    rel = pd.to_numeric(df.get("relation_to_head_code"), errors="coerce")
    if rel.isna().all():
        return pd.Series(np.nan, index=df.index)
    out = pd.Series(np.nan, index=df.index, dtype="float64")
    out[rel.isin([1, 2, 3])] = 0.0        # head / spouse / own child
    out[rel.isin([4, 5])] = 1.0           # son-in-law, grandchild
    out[rel.isin([6, 7, 8, 9, 10])] = 2.0  # other relative
    out[rel.isin([11, 12, 13])] = 3.0     # unrelated / adopted / servant
    return out


def _repeated(df: pd.DataFrame) -> pd.Series:
    """Grade repetition: same grade this year as last, both attended."""
    gc = pd.to_numeric(df.get("grade_current"), errors="coerce")
    gp = pd.to_numeric(df.get("grade_previous"), errors="coerce")
    both = (df.get("attended_current_year") == 1) & (
        df.get("attended_previous_year") == 1
    )
    return (both & (gc == gp)).astype("float64").where(gc.notna() & gp.notna())


def crosstab(path: str | Path, survey: str = "dhs",
             colmap: ColumnMap | None = None) -> str:
    """Print the transition crosstab. Eyeball this BEFORE training anything.

    If the off-diagonal cell for 'attended last year, not this year' is
    implausibly large or is zero, the mapping is wrong. This one check catches
    the inverted-label error that otherwise produces a confident, backwards
    model.
    """
    colmap = colmap or (DHS_DEFAULT if survey.lower() == "dhs" else MICS_DEFAULT)
    raw = _read_any(Path(path))
    raw.columns = [str(c) for c in raw.columns]
    lower = {c.lower(): c for c in raw.columns}
    cur_src = next((lower[s.lower()] for s, d in colmap.columns.items()
                    if d == "attended_current_raw" and s.lower() in lower), None)
    prev_src = next((lower[s.lower()] for s, d in colmap.columns.items()
                     if d == "attended_previous_raw" and s.lower() in lower), None)
    if not cur_src or not prev_src:
        return (
            "Could not find the attendance variables in this file. Supply a "
            "--map JSON with the correct source column names."
        )
    ct = pd.crosstab(
        _yes(raw[prev_src]).fillna(-1).map({-1: "missing", 0.0: "no", 1.0: "yes"}),
        _yes(raw[cur_src]).fillna(-1).map({-1: "missing", 0.0: "no", 1.0: "yes"}),
        rownames=[f"attended PREVIOUS year ({prev_src})"],
        colnames=[f"attended CURRENT year ({cur_src})"],
    )
    return (
        str(ct)
        + "\n\nThe cell [previous=yes, current=no] is your positive class.\n"
        "If it is zero, or larger than the [yes, yes] cell, the mapping is "
        "wrong -- most likely current and previous are swapped."
    )


__all__ = ["DHS_DEFAULT", "MICS_DEFAULT", "load", "crosstab"]
