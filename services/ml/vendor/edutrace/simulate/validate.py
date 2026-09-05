"""Falsify the simulator against published Ghanaian statistics.

A synthetic dataset that nobody checks is a random number generator with
paperwork.  This module computes the same quantities that ``targets.py``
records from the literature and reports pass/fail per target.

Run it after any change to ``generator.py``:

    python -m edutrace.simulate.validate
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from .generator import JHS_WEEKS, WEEKS_PER_YEAR, SimConfig, SimResult, simulate
from .targets import TARGETS


def observed_statistics(res: SimResult) -> dict[str, float]:
    s = res.students
    p = res.panel
    out: dict[str, float] = {}

    # Annualised exit rate: total exits / total student-years at risk.
    student_years = s["weeks_observed"].sum() / WEEKS_PER_YEAR
    out["dropout_annual_rate"] = float(s["exited"].sum() / max(student_years, 1e-9))

    def rate(mask: pd.Series) -> float:
        sub = s.loc[mask]
        if sub.empty:
            return float("nan")
        yrs = sub["weeks_observed"].sum() / WEEKS_PER_YEAR
        return float(sub["exited"].sum() / max(yrs, 1e-9))

    poorest = rate(s["poverty_quintile"] == 1)
    richest = rate(s["poverty_quintile"] == 5)
    out["dropout_ratio_poorest_to_richest"] = (
        float(poorest / richest) if richest > 0 else float("inf")
    )

    male = rate(s["sex"] == "M")
    female = rate(s["sex"] == "F")
    out["dropout_ratio_male_to_female"] = float(male / female) if female > 0 else float("inf")

    out["share_over_age"] = float((s["over_age_years"] > 0).mean())
    out["repetition_rate"] = float(s["repeated_a_grade"].mean())
    out["share_within_short_walk"] = float((s["distance_ord"] <= 1).mean())

    exits = s.loc[s["exited"]]
    if len(exits):
        jhs3 = (exits["exit_week"] >= 2 * WEEKS_PER_YEAR).mean()
        out["jhs3_share_of_all_exits"] = float(jhs3)
        fem = exits.loc[exits["sex"] == "F"]
        out["female_exits_attributable_to_pregnancy"] = (
            float((fem["exit_reason"] == "pregnancy").mean()) if len(fem) else float("nan")
        )
    else:
        out["jhs3_share_of_all_exits"] = float("nan")
        out["female_exits_attributable_to_pregnancy"] = float("nan")

    out["_panel_rows"] = float(len(p))
    out["_positive_rate"] = float(p["label"].mean())
    out["_students"] = float(len(s))
    return out


def report(res: SimResult) -> tuple[bool, str]:
    obs = observed_statistics(res)
    lines = [
        "Simulator calibration report",
        "=" * 78,
        f"  students          {int(obs['_students']):>10,}",
        f"  panel rows        {int(obs['_panel_rows']):>10,}",
        f"  positive rate     {obs['_positive_rate']:>10.4%}   "
        f"(P(exit within {JHS_WEEKS and 8} weeks | enrolled))",
        "-" * 78,
    ]
    all_ok = True
    for t in TARGETS:
        ok, line = t.check(obs.get(t.name, float("nan")))
        all_ok &= ok
        lines.append("  " + line)
    lines.append("=" * 78)
    lines.append("  RESULT: " + ("all targets within tolerance" if all_ok else "OUT OF TOLERANCE"))
    return all_ok, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Validate the EduTrace simulator.")
    ap.add_argument("--schools", type=int, default=20)
    ap.add_argument("--entrants", type=int, default=45)
    ap.add_argument("--cohorts", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260829)
    args = ap.parse_args(argv)

    res = simulate(
        SimConfig(
            n_schools=args.schools,
            entrants_per_school=args.entrants,
            n_cohorts=args.cohorts,
            seed=args.seed,
        )
    )
    ok, text = report(res)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
