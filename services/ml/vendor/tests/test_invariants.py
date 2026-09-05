"""The invariants that must not silently break.

Each test here corresponds to a specific failure this system is designed to
avoid, and most of them correspond to a bug that actually occurred during
development.  A test that has never caught anything is decoration; these have.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from edutrace.contract import (
    ACTIONABLE_FEATURES,
    FEATURE_ORDER,
    PII_COLUMNS,
    PROTECTED_COLUMNS,
    contract_fingerprint,
)
from edutrace.features import build_frame, build_row
from edutrace.records import StudentObservation
from edutrace.serve.scorer import _row_to_observation


# --------------------------------------------------------------------------
# The big one
# --------------------------------------------------------------------------


def test_no_train_serve_skew(panel, bundle):
    """The vectorised and row-wise feature builders must agree exactly.

    This is the invariant the whole ``features`` module exists to hold. It has
    already failed once for real: the simulator emitted a two-point attendance
    slope while ``build_row`` computed a least-squares one. Nothing crashed;
    the model simply got a slightly wrong feature at serving time and ranked a
    genuinely high-risk profile about ten percentiles too low.
    """
    sub = panel.sample(300, random_state=3).reset_index(drop=True)
    Xf = build_frame(sub, bundle.norm_context)
    Xr = np.vstack(
        [
            build_row(_row_to_observation(sub.iloc[i]), bundle.norm_context)
            for i in range(len(sub))
        ]
    )
    assert Xf.shape == Xr.shape

    for j, name in enumerate(FEATURE_ORDER):
        a, b = Xf[:, j], Xr[:, j]
        nan_mismatch = int((np.isnan(a) != np.isnan(b)).sum())
        assert nan_mismatch == 0, f"{name}: {nan_mismatch} NaN-pattern mismatches"
        m = ~np.isnan(a) & ~np.isnan(b)
        if m.any():
            worst = float(np.max(np.abs(a[m] - b[m])))
            assert worst < 1e-3, f"{name}: max abs difference {worst}"


# --------------------------------------------------------------------------
# Protected attributes
# --------------------------------------------------------------------------


def test_protected_attributes_are_not_features():
    for col in PROTECTED_COLUMNS:
        assert col not in FEATURE_ORDER, (
            f"{col} is a protected attribute and must never be a model input. "
            f"Wisconsin's DEWS fed race and family income into the model and "
            f"produced a false-alarm rate 42 percentage points higher for "
            f"Black students."
        )


def test_pii_is_not_a_feature():
    for col in PII_COLUMNS:
        assert col not in FEATURE_ORDER


def test_sex_does_not_change_the_score(scorer):
    """Supplying sex must be inert. It is audited, never consumed."""
    base = dict(
        student_key="T1", school_id="SCH001", academic_year=2024, term="T2",
        week=8, grade_level="JHS2", attendance_rate_term_to_date=64.0,
        attendance_rate_last_4w=55.0, consecutive_absences=3,
        avg_exam_score=44.0, fee_status="UNPAID", fee_arrears_terms=2,
        age_years=15.0, distance_band="M30_TO_60",
    )
    f = scorer.score(StudentObservation(**base, sex="F"), explain=False)
    m = scorer.score(StudentObservation(**base, sex="M"), explain=False)
    n = scorer.score(StudentObservation(**base), explain=False)
    assert f.risk == m.risk == n.risk


def test_narrative_never_mentions_a_protected_attribute(scorer, panel, bundle):
    from edutrace.features import build_frame as bf

    sub = panel.sample(200, random_state=5).reset_index(drop=True)
    p = bundle.predict(bf(sub, bundle.norm_context))
    banned = ("male", "female", " girl", " boy", "poverty", "quintile", "region")
    for i in np.argsort(-p)[:25]:
        text = scorer.score(_row_to_observation(sub.iloc[int(i)])).narrative.lower()
        for word in banned:
            assert word not in text, f"narrative mentioned {word!r}: {text}"


# --------------------------------------------------------------------------
# Contract integrity
# --------------------------------------------------------------------------


def test_feature_order_is_unique():
    assert len(FEATURE_ORDER) == len(set(FEATURE_ORDER))


def test_actionable_features_exist():
    for f in ACTIONABLE_FEATURES:
        assert f in FEATURE_ORDER, f"{f} is marked actionable but is not a feature"


def test_bundle_refuses_mismatched_contract(bundle, tmp_path, monkeypatch):
    """Loading a model built against a different feature contract must raise."""
    from edutrace.train import model as model_mod

    d = bundle.save(tmp_path / "m")
    import json

    payload = json.loads((d / "bundle.json").read_text())
    payload["card"]["contract_fingerprint"] = "deadbeefdeadbeef"
    (d / "bundle.json").write_text(json.dumps(payload))

    with pytest.raises(RuntimeError, match="feature contract mismatch"):
        model_mod.ModelBundle.load(d)


def test_fingerprint_is_stable():
    assert contract_fingerprint() == contract_fingerprint()
    assert len(contract_fingerprint()) == 16


# --------------------------------------------------------------------------
# Label construction
# --------------------------------------------------------------------------


def test_labels_have_no_lookahead(sim):
    """Every positive row must precede the exit it predicts, within horizon."""
    from edutrace.contract import HORIZON_WEEKS

    panel = sim.panel
    exits = sim.students.set_index("student_key")["exit_week"].to_dict()
    pos = panel[panel["label"] == 1]
    ew = pos["student_key"].map(exits).to_numpy()
    w = pos["career_week"].to_numpy()
    assert (ew > w).all(), "a positive row is at or after the exit it predicts"
    assert (ew <= w + HORIZON_WEEKS).all(), "a positive row exceeds the horizon"


def test_censored_rows_are_dropped(sim):
    """Rows whose horizon runs past observation must not be labelled zero."""
    from edutrace.contract import HORIZON_WEEKS

    panel = sim.panel
    obs = sim.students.set_index("student_key")["weeks_observed"].to_dict()
    ow = panel["student_key"].map(obs).to_numpy()
    w = panel["career_week"].to_numpy()
    y = panel["label"].to_numpy()
    unobserved_negatives = ((y == 0) & (w + HORIZON_WEEKS > ow)).sum()
    assert unobserved_negatives == 0, (
        f"{unobserved_negatives} rows labelled 0 without full follow-up -- this "
        f"teaches the model that the end of every record is safe"
    )


def test_positive_rate_is_realistically_small(panel):
    rate = panel["label"].mean()
    assert 0.001 < rate < 0.05, (
        f"positive rate {rate:.4%} is implausible for an 8-week dropout hazard"
    )


# --------------------------------------------------------------------------
# Robust ingestion
# --------------------------------------------------------------------------


def test_integer_counts_accept_float_csv_values():
    """Real exports write '2.0'. Rejecting the row is not defensible."""
    obs = _row_to_observation(
        pd.Series(
            {
                "student_key": "X", "school_id": "S", "academic_year": 2024,
                "term": "T1", "week": 3.0, "grade_level": "JHS1",
                "fee_arrears_terms": 2.0, "consecutive_absences": 0.0,
                "siblings_in_school": np.nan,
            }
        )
    )
    assert obs.fee_arrears_terms == 2
    assert obs.siblings_in_school is None


def test_unknown_columns_are_ignored():
    obs = _row_to_observation(
        pd.Series(
            {
                "student_key": "X", "school_id": "S", "academic_year": 2024,
                "term": "T1", "week": 1, "grade_level": "JHS1",
                "some_column_the_school_added": "whatever",
            }
        )
    )
    assert obs.student_key == "X"


def test_missing_values_stay_nan_not_imputed():
    """Nothing is mean-imputed. NaN reaches XGBoost, which handles it."""
    x = build_row(
        StudentObservation(
            student_key="X", school_id="S", academic_year=2024,
            term="T1", week=1, grade_level="JHS1",
        )
    )
    ix = FEATURE_ORDER.index("attendance_rate_term_to_date")
    assert np.isnan(x[0, ix])
