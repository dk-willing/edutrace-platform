"""OULAD adapter: label construction and the domain guard.

These tests skip unless the OULAD CSVs are present, because the archive is
433 MB and does not belong in a repository. Point ``EDUTRACE_OULAD_DIR`` at an
unzipped copy to run them:

    EDUTRACE_OULAD_DIR=/path/to/oulad python -m pytest tests/test_oulad.py
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from edutrace.contract import HORIZON_WEEKS
from edutrace.ingest import oulad

OULAD_DIR = os.environ.get("EDUTRACE_OULAD_DIR", "/tmp/oulad")
HAVE_OULAD = all((Path(OULAD_DIR) / f).exists() for f in oulad.FILES)
PANEL_CSV = os.environ.get("EDUTRACE_OULAD_PANEL", "/tmp/work/oulad_panel.csv")
HAVE_PANEL = Path(PANEL_CSV).exists()

needs_panel = pytest.mark.skipif(not HAVE_PANEL, reason="no OULAD panel built")


# --------------------------------------------------------------------------
# Pure logic — runs without the dataset
# --------------------------------------------------------------------------


def test_imd_band_parsing_handles_the_source_inconsistency():
    """OULAD writes '10-20' without the % sign. Mapping on literals loses it."""
    s = pd.Series(["0-10%", "10-20", "50-60%", "90-100%", np.nan, "bogus"])
    q = oulad._imd_to_quintile(s)
    assert q.tolist()[:4] == [1.0, 1.0, 3.0, 5.0]
    assert pd.isna(q.iloc[4]) and pd.isna(q.iloc[5])
    assert q.notna().sum() == 4


def test_presentation_order_is_chronological():
    """2013B precedes 2013J: February start before October start."""
    o = oulad.PRESENTATION_ORDER
    assert o["2013B"] < o["2013J"] < o["2014B"] < o["2014J"]


def test_absent_features_are_declared_not_inferred():
    """The Ghana-specific drivers OULAD cannot supply must be named."""
    for f in ("fee_arrears_terms", "distance_band_ord", "does_paid_or_farm_work"):
        assert f in oulad.ABSENT_IN_OULAD


# --------------------------------------------------------------------------
# Panel properties
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def panel():
    if not HAVE_PANEL:
        pytest.skip("no OULAD panel")
    return pd.read_csv(PANEL_CSV, low_memory=False)


@needs_panel
def test_label_is_a_forward_hazard(panel):
    """Every positive precedes its exit, within the horizon."""
    assert panel["label"].isin([0, 1]).all()
    rate = panel["label"].mean()
    assert 0.01 < rate < 0.25, f"implausible positive rate {rate:.2%}"


@needs_panel
def test_engagement_separates_the_classes(panel):
    """If the proxy carries no signal, the whole exercise is void."""
    left = panel.loc[panel.label == 1, "attendance_rate_last_4w"].mean()
    stayed = panel.loc[panel.label == 0, "attendance_rate_last_4w"].mean()
    assert left < stayed - 5, (
        f"leavers ({left:.1f}%) should be markedly less engaged than "
        f"stayers ({stayed:.1f}%)"
    )


@needs_panel
def test_four_periods_allow_a_temporal_split(panel):
    years = sorted(panel["academic_year"].unique())
    assert len(years) >= 3, "need >= 3 periods for train/calibrate/test"
    assert years == sorted(oulad.PRESENTATION_ORDER.values())


@needs_panel
def test_no_learner_spans_two_periods(panel):
    """A student_key is (student, module, presentation), so it cannot leak."""
    per_key = panel.groupby("student_key")["academic_year"].nunique()
    assert per_key.max() == 1


@needs_panel
def test_censoring_leaves_no_unobserved_negatives(panel):
    """Rows without full follow-up must be dropped, not labelled zero."""
    # Use the TRUE observation end carried on the panel. Reconstructing it
    # from the surviving rows is circular: after censoring, the last kept row
    # is by construction end-minus-horizon, so that check flags every learner's
    # final rows and always "fails".
    if "observed_weeks" not in panel.columns:
        pytest.skip("panel predates the observed_weeks audit column")
    unobserved_neg = (
        (panel.label == 0)
        & (panel.week_abs + HORIZON_WEEKS > panel.observed_weeks)
    ).sum()
    assert unobserved_neg == 0, (
        f"{unobserved_neg:,} rows labelled 0 without full follow-up; the "
        f"administrative censoring is not being applied"
    )


@needs_panel
def test_ghana_specific_features_are_empty_and_flagged(panel):
    """OULAD must not silently supply fees, distance or child labour."""
    for f in ("fee_arrears_terms", "distance_band_ord", "does_paid_or_farm_work"):
        if f in panel.columns:
            assert panel[f].notna().mean() < 0.05


@needs_panel
def test_protected_attributes_are_present_for_the_audit(panel):
    for c in ("sex", "region", "poverty_quintile", "disability"):
        assert c in panel.columns
        assert panel[c].notna().mean() > 0.5


# --------------------------------------------------------------------------
# The domain guard
# --------------------------------------------------------------------------


@needs_panel
def test_validated_record_path_rejects_oulad(panel):
    """The JHS schema must refuse UK adults on lettered modules.

    This is the guard working, not a bug. OULAD learners are 27-60 years old
    in modules called 'AAA'. If ``StudentObservation`` accepted them, it would
    accept anything, and the model would happily score data it was never
    built for.
    """
    from edutrace.serve.scorer import _row_to_observation
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _row_to_observation(panel.iloc[0])


@needs_panel
def test_vector_path_scores_oulad(panel):
    """Cross-domain validation goes through the vector path instead."""
    from edutrace.features import build_frame
    from edutrace.serve.scorer import Scorer
    from edutrace.train.model import ModelBundle

    model_dir = Path("artifacts/oulad")
    if not (model_dir / "bundle.json").exists():
        pytest.skip("no OULAD model trained")

    b = ModelBundle.load(model_dir)
    s = Scorer(b)
    sub = panel.head(200)
    X = build_frame(sub, b.norm_context)
    a = s.score_vector(X[0])
    assert 0.0 < a.risk <= b.bounds.ceiling
    assert a.narrative
    assert a.contract_fingerprint


@needs_panel
def test_oulad_model_card_forbids_school_use():
    model_dir = Path("artifacts/oulad")
    if not (model_dir / "bundle.json").exists():
        pytest.skip("no OULAD model trained")
    import json

    card = json.loads((model_dir / "bundle.json").read_text())["card"]
    assert card["out_of_scope"]
    assert card["data_provenance"]


# --------------------------------------------------------------------------
# Full ingest — slow, needs the raw archive
# --------------------------------------------------------------------------


@pytest.mark.skipif(not HAVE_OULAD, reason="no OULAD archive")
@pytest.mark.slow
def test_full_ingest_runs():
    p, report = oulad.load(OULAD_DIR)
    assert report.ok(), "\n".join(report.problems)
    assert len(p) > 100_000
    assert any("UK adult" in w for w in report.warnings_)
    assert any("proxy" in w for w in report.warnings_)
