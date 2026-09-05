from __future__ import annotations

import numpy as np
import pytest

from edutrace.features import GradeNormContext, build_frame
from edutrace.simulate import SimConfig, simulate
from edutrace.train.model import (
    ModelBundle,
    ProbabilityBounds,
    Thresholds,
    fit_calibrator,
    make_card,
    train_booster,
)
from edutrace.train.splits import final_holdout


@pytest.fixture(scope="session")
def sim():
    """A small but structurally complete simulation."""
    return simulate(
        SimConfig(n_schools=10, entrants_per_school=32, n_cohorts=4, seed=11)
    )


@pytest.fixture(scope="session")
def panel(sim):
    return sim.panel


@pytest.fixture(scope="session")
def bundle(panel):
    y = panel["label"].to_numpy().astype(int)
    tr, cal, _ = final_holdout(panel)
    ctx = GradeNormContext.fit(panel.iloc[tr])
    X = build_frame(panel, ctx)

    booster = train_booster(
        X[tr], y[tr], num_boost_round=280, early_stopping_rounds=0
    )
    raw_cal = np.asarray(
        booster.inplace_predict(np.ascontiguousarray(X[cal])), dtype=float
    )
    calibrator = fit_calibrator(raw_cal, y[cal])
    p_cal = np.asarray(calibrator.predict(raw_cal))
    bounds = ProbabilityBounds.from_calibration(p_cal, y[cal])

    return ModelBundle(
        booster=booster,
        calibrator=calibrator,
        thresholds=Thresholds.from_scores(bounds.apply(p_cal)),
        norm_context=ctx,
        card=make_card(
            n_train_rows=len(tr),
            n_train_students=int(panel.iloc[tr]["student_key"].nunique()),
            train_years=[int(v) for v in sorted(set(panel.iloc[tr]["academic_year"]))],
            calibration_year=None,
            test_year=None,
            base_rate=float(y[tr].mean()),
            data_provenance="SIMULATED (pytest fixture)",
        ),
        bounds=bounds,
    )


@pytest.fixture(scope="session")
def scorer(bundle):
    from edutrace.serve.scorer import Scorer

    return Scorer(bundle)
