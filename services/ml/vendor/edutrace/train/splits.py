"""Splitting strategy.

A random ``train_test_split`` on this panel would be a lie, twice over.

*Cluster leakage.*  The same child contributes ~120 highly autocorrelated rows.
Random splitting puts week 7 in train and week 8 in test, so the model is asked
to predict a row it has essentially already seen.  Reported AUC goes up; real
performance does not.

*Temporal leakage.*  Dropout drivers move.  This simulator embeds an economic
shock in one academic year precisely so that a split which ignores time looks
great and a split which respects it does not.  Deployed models are always asked
about a year they were not trained on.

So two schemes, both of which this module provides:

``forward_chaining``
    Train on academic years <= t, evaluate on t+1.  This is the number to quote.

``group_by_school``
    Hold out entire schools.  Because the simulator assigns region per school,
    this is also a region holdout -- the "will it work at a school we have never
    seen" question, which is the one a buyer actually asks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class Fold:
    name: str
    train_idx: np.ndarray
    test_idx: np.ndarray
    description: str

    def sizes(self) -> str:
        return f"train={len(self.train_idx):,} test={len(self.test_idx):,}"


def forward_chaining(
    df: pd.DataFrame,
    year_col: str = "academic_year",
    min_train_years: int = 1,
) -> list[Fold]:
    """Expanding-window folds over academic years."""
    years = sorted(pd.unique(df[year_col]))
    if len(years) < min_train_years + 1:
        raise ValueError(
            f"need at least {min_train_years + 1} distinct years, found {len(years)}"
        )
    idx = np.arange(len(df))
    yv = df[year_col].to_numpy()
    folds: list[Fold] = []
    for i in range(min_train_years, len(years)):
        train_years = years[:i]
        test_year = years[i]
        folds.append(
            Fold(
                name=f"fc_{test_year}",
                train_idx=idx[np.isin(yv, train_years)],
                test_idx=idx[yv == test_year],
                description=f"train {train_years[0]}-{train_years[-1]} -> test {test_year}",
            )
        )
    return folds


def group_by_school(
    df: pd.DataFrame,
    n_folds: int = 4,
    group_col: str = "school_id",
    seed: int = 7,
) -> list[Fold]:
    """Hold out whole schools.  Tests transfer to an unseen institution."""
    groups = np.array(sorted(pd.unique(df[group_col])))
    rng = np.random.default_rng(seed)
    rng.shuffle(groups)
    chunks = np.array_split(groups, n_folds)
    idx = np.arange(len(df))
    gv = df[group_col].to_numpy()
    folds: list[Fold] = []
    for k, held in enumerate(chunks):
        mask = np.isin(gv, held)
        folds.append(
            Fold(
                name=f"school_fold_{k}",
                train_idx=idx[~mask],
                test_idx=idx[mask],
                description=f"holdout schools: {', '.join(map(str, held[:4]))}"
                + ("..." if len(held) > 4 else ""),
            )
        )
    return folds


def final_holdout(
    df: pd.DataFrame, year_col: str = "academic_year"
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Train / calibration / test, split strictly by time.

    The calibration slice is a *separate* year from both training and test.
    Fitting the isotonic calibrator on training predictions would inherit the
    booster's in-sample optimism and produce a calibrator that is itself
    miscalibrated -- a subtle error that shows up only as a probability curve
    that hugs the diagonal in development and drifts in production.
    """
    years = sorted(pd.unique(df[year_col]))
    if len(years) < 3:
        raise ValueError("need >= 3 academic years for train/calib/test")
    train_years, calib_year, test_year = years[:-2], years[-2], years[-1]
    yv = df[year_col].to_numpy()
    idx = np.arange(len(df))
    return (
        idx[np.isin(yv, train_years)],
        idx[yv == calib_year],
        idx[yv == test_year],
    )


__all__ = ["Fold", "forward_chaining", "group_by_school", "final_holdout"]
