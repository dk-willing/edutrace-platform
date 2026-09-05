"""Survey-shaped fixtures for exercising the adapters.

These generate files with the **real variable names and real code values** of a
DHS household-member recode, so the ingestion path can be tested end to end
before a real extract arrives.  They test the *adapter*, not the model.

    python -m edutrace.ingest.fixtures --out /tmp/fake_dhs.csv

A model trained on this output is meaningless and the ingest report will say so
in its provenance.  The point is that when the real GHPR8AFL.DTA lands, the
mapping, the transition logic, the age filter and the quality gates have
already been exercised, so the only new variable is the data.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd


def make_dhs_like(n_households: int = 4000, seed: int = 5) -> pd.DataFrame:
    """A DHS PR-file-shaped frame: real column names, real code values."""
    rng = np.random.default_rng(seed)
    rows = []
    for h in range(n_households):
        urban = 1 if rng.random() < 0.42 else 2          # hv025
        region = int(rng.integers(1, 17))                 # hv024
        wealth = int(np.clip(rng.normal(3.4 if urban == 1 else 2.4, 1.2), 1, 5))
        hhsize = int(np.clip(rng.poisson(5.2), 1, 20))
        elec = 1 if rng.random() < (0.85 if urban == 1 else 0.45) else 0
        water = int(rng.choice([11, 12, 13, 21, 31, 32, 41, 42, 51, 61]))
        head_edu = int(np.clip(rng.normal(7 - (5 - wealth), 4), 0, 18))

        # A real PR file holds EVERY household member, not just children.
        # The head's row is what carries head education (hv101 == 1), which the
        # adapter derives across the household.
        rows.append({
            "hhid": f"H{h:06d}", "hvidx": 0,
            "hv007": 2023, "hv024": region, "hv025": urban, "hv009": hhsize,
            "hv270": wealth, "hv206": elec, "hv201": water,
            "hv219": int(rng.integers(1, 3)),
            "hv105": int(np.clip(rng.normal(44, 10), 20, 85)),
            "hv104": int(rng.integers(1, 3)), "hv101": 1, "hv106": 1,
            "hv108": head_edu,
            "hv121": 0, "hv122": 0, "hv123": 0,
            "hv124": 0, "hv125": 0, "hv126": 0,
            "hv111": 1, "hv113": 1,
        })

        for m in range(int(np.clip(rng.poisson(1.6), 0, 5))):
            age = int(rng.integers(10, 19))
            sex = int(rng.integers(1, 3))
            # Over-age is common: GER 85 vs NER 45.
            over = max(0, int(rng.normal(1.4 - 0.25 * wealth, 1.2)))
            grade_prev = int(np.clip(age - 11 - over, 1, 3))

            # Latent hazard: poverty, over-age, rural, orphanhood, child work.
            work = 1 if rng.random() < 0.30 - 0.04 * wealth + 0.10 * (sex == 1) else 0
            eta = (
                -2.6
                - 0.34 * wealth
                + 0.22 * over
                + 0.30 * (urban == 2)
                + 0.55 * work
                - 0.045 * head_edu
                + 0.45 * (grade_prev == 3)
                + rng.normal(0, 0.5)
            )
            left = rng.random() < 1 / (1 + np.exp(-eta))

            attended_prev = 1
            attended_cur = 0 if left else 1
            grade_cur = grade_prev if rng.random() < 0.12 else grade_prev + 1

            rows.append({
                "hhid": f"H{h:06d}",
                "hvidx": m + 1,
                "hv007": int(rng.choice([2022, 2023, 2024])),
                "hv024": region,
                "hv025": urban,
                "hv009": hhsize,
                "hv270": wealth,
                "hv206": elec,
                "hv201": water,
                "hv219": int(rng.integers(1, 3)),
                "hv105": age,
                "hv104": sex,
                "hv101": int(rng.choice([3, 3, 3, 6, 7, 11], p=[.5, .2, .1, .1, .05, .05])),
                "hv106": 2,
                "hv108": int(np.clip(6 + grade_prev, 0, 18)),
                # The schooling block: 121-123 CURRENT, 124-126 PREVIOUS.
                "hv121": attended_cur,
                "hv122": 2 if attended_cur else 0,
                "hv123": grade_cur if attended_cur else 0,
                "hv124": attended_prev,
                "hv125": 2,
                "hv126": grade_prev,
                "hv111": 0 if rng.random() < 0.94 else 1,
                "hv113": 0 if rng.random() < 0.90 else 1,
            })
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write a DHS-shaped fixture file.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--households", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args(argv)
    df = make_dhs_like(args.households, args.seed)
    df.to_csv(args.out, index=False)
    print(f"wrote {args.out}: {len(df):,} member records, "
          f"{df.hv124.eq(1).sum():,} attended last year, "
          f"{((df.hv124 == 1) & (df.hv121 == 0)).sum():,} left school")
    print("\nThis is a SHAPE fixture for testing the adapter. It is not data "
          "about anyone, and a model trained on it means nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
