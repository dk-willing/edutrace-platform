"""The safety net, and the real-data ingestion path."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from edutrace.contract import RiskTier
from edutrace.features import build_frame
from edutrace.ingest import base as ib
from edutrace.ingest import household
from edutrace.ingest.fixtures import make_dhs_like
from edutrace.triage import Floors, coverage, triage


# --------------------------------------------------------------------------
# Triage: the floor must be rare, and must not hurt
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def week(panel):
    """A single week of one term -- how the system is actually run."""
    latest = panel.academic_year.max()
    w = panel[
        (panel.academic_year == latest) & (panel.term == "T2") & (panel.week == 9)
    ].reset_index(drop=True)
    if len(w) < 50:  # pragma: no cover
        pytest.skip("fixture cohort too small for a weekly slice")
    return w


def test_floor_rules_stay_within_the_trip_budget(week):
    """A rule firing on a third of learners is a feature, not a floor."""
    problems = Floors().validate(week)
    assert problems == [], "\n".join(problems)


def test_loose_floor_is_rejected_by_validation(week):
    """The floor that broke the first version must now fail loudly."""
    loose = Floors(collapsed_attendance_pct=80.0, consecutive_absence_days=1)
    problems = loose.validate(week)
    assert problems, "a floor at 80% attendance should blow the trip budget"
    assert "not a floor" in problems[0]
    with pytest.raises(ValueError):
        loose.validate(week, raise_on_fail=True)


def test_floor_never_lowers_a_tier(week, bundle):
    p = bundle.predict(build_frame(week, bundle.norm_context))
    mt = np.array([bundle.tier(v).value for v in p], dtype=object)
    r = triage(week, p, mt, capacity=20)
    rank = {"LOW": 0, "WATCH": 1, "ELEVATED": 2, "HIGH": 3}
    assert all(rank[a] >= rank[b] for a, b in zip(r.tier, r.model_tier))


def test_floor_escalation_carries_a_human_reason(week, bundle):
    p = bundle.predict(build_frame(week, bundle.norm_context))
    mt = np.array([bundle.tier(v).value for v in p], dtype=object)
    r = triage(week, p, mt, capacity=20)
    for i in np.flatnonzero(r.raised_by_floor):
        assert r.floor_reasons[i], "escalated with no explanation"
        for reason in r.floor_reasons[i]:
            assert reason.endswith(".")
            # A floor reason must stand alone, without invoking the model.
            assert "model" not in reason.lower()
            assert "%" not in reason or "attendance" in reason.lower()


def test_worklist_respects_capacity(week, bundle):
    p = bundle.predict(build_frame(week, bundle.norm_context))
    mt = np.array([bundle.tier(v).value for v in p], dtype=object)
    for cap in (5, 20, 50):
        r = triage(week, p, mt, capacity=cap)
        assert len(r.worklist) <= cap


def test_worklist_is_deduplicated_by_learner(panel, bundle):
    """Capacity counts children, not learner-weeks."""
    latest = panel.academic_year.max()
    many = panel[panel.academic_year == latest].reset_index(drop=True)
    p = bundle.predict(build_frame(many, bundle.norm_context))
    mt = np.array([bundle.tier(v).value for v in p], dtype=object)
    r = triage(many, p, mt, capacity=40)
    keys = many.student_key.to_numpy()[r.worklist]
    assert len(set(keys)) == len(keys), "same learner appears twice in one worklist"


def test_floor_does_not_reduce_recall(week, bundle):
    """The regression that broke version one: floor flooding cut recall.

    With a validated floor and a reserved capacity share, the combined system
    must never catch fewer learners than the model would alone.
    """
    y = week.label.to_numpy().astype(int)
    if y.sum() == 0:  # pragma: no cover
        pytest.skip("no positives in this slice")
    p = bundle.predict(build_frame(week, bundle.norm_context))
    mt = np.array([bundle.tier(v).value for v in p], dtype=object)
    cap = 20
    r = triage(week, p, mt, capacity=cap)
    cov = coverage(week, y, p, r)
    assert cov.caught_total >= cov.model_only_caught


def test_coverage_states_its_own_miss_rate(week, bundle):
    y = week.label.to_numpy().astype(int)
    p = bundle.predict(build_frame(week, bundle.norm_context))
    mt = np.array([bundle.tier(v).value for v in p], dtype=object)
    cov = coverage(week, y, p, triage(week, p, mt, capacity=20))
    text = cov.render()
    assert "MISSED" in text
    assert "recall" in text
    assert cov.caught_total + cov.missed == cov.positives
    # And it must publish the price of chasing perfect recall.
    assert any(abs(t - 1.0) < 1e-9 for t, _, _ in cov.recall_curve)


def test_perfect_recall_requires_flagging_most_of_the_cohort(week, bundle):
    """The claim in the docstrings, asserted rather than asserted-in-prose."""
    y = week.label.to_numpy().astype(int)
    if y.sum() < 3:  # pragma: no cover
        pytest.skip("too few positives to characterise the curve")
    p = bundle.predict(build_frame(week, bundle.norm_context))
    mt = np.array([bundle.tier(v).value for v in p], dtype=object)
    cov = coverage(week, y, p, triage(week, p, mt, capacity=20))
    full = [c for c in cov.recall_curve if abs(c[0] - 1.0) < 1e-9][0]
    _, need, precision = full
    assert need > 0.4 * cov.n_rows, (
        "100% recall should require flagging a large share of the cohort; if "
        "it does not, the label or the split is leaking"
    )
    assert precision < 0.10


def test_nan_never_trips_a_floor():
    df = pd.DataFrame({
        "student_key": ["a"], "grade_level": ["JHS1"], "term": ["T1"],
        "attendance_rate_term_to_date": [np.nan],
        "attendance_rate_last_4w": [np.nan],
        "consecutive_absences": [np.nan],
        "bece_registered": [np.nan],
    })
    assert not any(m.any() for m in Floors().evaluate(df).values())


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dhs_raw():
    return make_dhs_like(n_households=1500, seed=3)


@pytest.fixture(scope="module")
def dhs_panel(dhs_raw, tmp_path_factory):
    p = tmp_path_factory.mktemp("ingest") / "dhs.csv"
    dhs_raw.to_csv(p, index=False)
    return household.load(p, survey="dhs")


def test_dhs_adapter_produces_the_enrolment_contract(dhs_panel):
    panel, report = dhs_panel
    for f in ib.ENROLMENT_FEATURES:
        assert f in panel.columns
    assert ib.ENROLMENT_LABEL in panel.columns
    assert report.rows_out > 0


def test_transition_label_is_not_inverted(dhs_panel):
    """The single most dangerous ingestion error."""
    panel, _ = dhs_panel
    y = panel[ib.ENROLMENT_LABEL]
    assert 0.0 < y.mean() < 0.40, (
        f"label rate {y.mean():.1%} — current/previous almost certainly swapped"
    )
    # Every positive must have been enrolled the previous year.
    assert (panel.loc[y == 1, "attended_previous_year"] == 1).all()


def test_never_enrolled_children_are_excluded(dhs_raw, tmp_path):
    """Never attending and dropping out are different outcomes."""
    raw = dhs_raw.copy()
    raw.loc[raw.index[:200], ["hv121", "hv124"]] = 0  # never enrolled
    p = tmp_path / "d.csv"
    raw.to_csv(p, index=False)
    panel, _ = household.load(p, survey="dhs")
    # A never-enrolled child has attended_previous_year == 0 and must not be
    # counted as a school leaver.
    assert (panel.loc[panel[ib.ENROLMENT_LABEL] == 1, "attended_previous_year"]
            == 1).all()


def test_age_filter_restricts_to_jhs_band(dhs_panel):
    panel, _ = dhs_panel
    age = pd.to_numeric(panel["age_years"], errors="coerce")
    assert age.min() >= ib.JHS_AGE_RANGE[0]
    assert age.max() <= ib.JHS_AGE_RANGE[1]


def test_household_derivations_populate(dhs_panel):
    """Head education and siblings-in-school come from the group-by, not the row."""
    panel, report = dhs_panel
    assert report.feature_support["head_education_years"] > 0.5
    assert report.feature_support["siblings_in_school"] > 0.5


def test_quality_report_blocks_a_thin_panel(tmp_path):
    tiny = make_dhs_like(n_households=40, seed=1)
    p = tmp_path / "tiny.csv"
    tiny.to_csv(p, index=False)
    _, report = household.load(p, survey="dhs")
    assert not report.ok()
    assert any("rows" in x or "positive" in x for x in report.problems)


def test_quality_report_flags_unsupported_features(dhs_panel):
    """DHS has no distance-to-school or child-labour module in the PR file."""
    _, report = dhs_panel
    assert report.feature_support["distance_band_ord"] < 0.05
    assert any("under 5% support" in w for w in report.warnings_)


def test_enrolment_contract_is_separate_from_the_weekly_one():
    """Two model families must not share a fingerprint."""
    from edutrace.contract import contract_fingerprint

    assert ib.enrolment_fingerprint() != contract_fingerprint()
    assert "attendance_rate_last_4w" not in ib.ENROLMENT_FEATURES


def test_crosstab_detects_a_swapped_mapping(dhs_raw, tmp_path):
    p = tmp_path / "d.csv"
    dhs_raw.to_csv(p, index=False)
    text = household.crosstab(p, "dhs")
    assert "attended PREVIOUS year" in text
    assert "positive class" in text
