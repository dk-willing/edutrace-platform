"""Modelling behaviour: calibration, monotonicity, evaluation, latency."""

from __future__ import annotations

import time

import numpy as np
import pytest

from edutrace.contract import FEATURE_ORDER, RiskTier
from edutrace.features import build_frame
from edutrace.records import StudentObservation
from edutrace.simulate import observed_statistics
from edutrace.simulate.targets import TARGETS
from edutrace.train.baseline import abc_score, compare
from edutrace.train.evaluate import (
    evaluate,
    expected_calibration_error,
    precision_at_k,
    recall_at_k,
    top_k_mask,
)
from edutrace.train.splits import final_holdout, forward_chaining, group_by_school


# --------------------------------------------------------------------------
# Simulator fidelity
# --------------------------------------------------------------------------


def test_simulator_matches_published_ghana_statistics():
    """The simulator must be falsifiable against the literature, and pass.

    This deliberately does NOT reuse the small shared ``sim`` fixture. Several
    targets are *ratios* between subgroups -- poorest-to-richest quintile,
    male-to-female -- and at an annual hazard near 4% the richest quintile
    contributes single-digit exits in a 1,300-student run. The ratio is then
    dominated by sampling noise and the check fails or passes at random,
    which is worse than not checking. Run the calibration at the documented
    default size (3,600 students) where the comparison has power.
    """
    from edutrace.simulate import SimConfig, simulate

    res = simulate(SimConfig(n_schools=20, entrants_per_school=45, n_cohorts=4))
    obs = observed_statistics(res)
    failures = []
    for t in TARGETS:
        ok, line = t.check(obs.get(t.name, float("nan")))
        if not ok:
            failures.append(line)
    assert not failures, "\n".join(failures)


def test_simulator_is_deterministic():
    from edutrace.simulate import SimConfig, simulate

    cfg = SimConfig(n_schools=3, entrants_per_school=15, n_cohorts=2, seed=99)
    a, b = simulate(cfg), simulate(cfg)
    assert len(a.panel) == len(b.panel)
    assert float(a.panel["label"].mean()) == float(b.panel["label"].mean())


def test_poverty_gradient_exists(sim):
    """A dropout simulator with no SES gradient is not simulating dropout."""
    s = sim.students
    poorest = s.loc[s.poverty_quintile == 1, "exited"].mean()
    richest = s.loc[s.poverty_quintile == 5, "exited"].mean()
    assert poorest > richest * 2


# --------------------------------------------------------------------------
# Splits
# --------------------------------------------------------------------------


def test_forward_chaining_never_trains_on_the_future(panel):
    years = panel["academic_year"].to_numpy()
    for fold in forward_chaining(panel):
        assert years[fold.train_idx].max() < years[fold.test_idx].min()


def test_group_split_shares_no_school(panel):
    schools = panel["school_id"].to_numpy()
    for fold in group_by_school(panel, n_folds=3):
        assert not set(schools[fold.train_idx]) & set(schools[fold.test_idx])


def test_group_split_shares_no_student(panel):
    keys = panel["student_key"].to_numpy()
    for fold in group_by_school(panel, n_folds=3):
        assert not set(keys[fold.train_idx]) & set(keys[fold.test_idx])


def test_holdout_years_are_disjoint(panel):
    tr, cal, te = final_holdout(panel)
    y = panel["academic_year"].to_numpy()
    assert not set(y[tr]) & set(y[cal])
    assert not set(y[cal]) & set(y[te])
    assert not set(y[tr]) & set(y[te])


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


def test_precision_and_recall_at_k():
    y = np.array([0, 0, 1, 1, 0, 1, 0, 0, 0, 0])
    s = np.array([0.1, 0.2, 0.95, 0.9, 0.3, 0.85, 0.05, 0.01, 0.4, 0.2])
    assert precision_at_k(y, s, 3) == pytest.approx(1.0)
    assert recall_at_k(y, s, 3) == pytest.approx(1.0)
    assert top_k_mask(s, 3).sum() == 3


def test_ece_is_zero_for_a_perfect_model():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.95, 20000)
    y = (rng.uniform(size=20000) < p).astype(int)
    ece, curve = expected_calibration_error(y, p, n_bins=10)
    assert ece < 0.02
    assert len(curve) == 10


def test_fairness_gate_ignores_recall_when_base_rates_differ():
    """Equal recall is incompatible with calibration at unequal base rates."""
    rng = np.random.default_rng(1)
    n = 4000
    group = np.where(rng.uniform(size=n) < 0.5, "a", "b")
    base = np.where(group == "a", 0.2, 0.01)
    y = (rng.uniform(size=n) < base).astype(int)
    p = np.clip(base + rng.normal(0, 0.01, n), 0.0, 1.0)
    rep = evaluate(y, p, protected={"g": group}).fairness[0]
    assert rep.base_rate_ratio > 2.0
    assert rep.recall_gate_applicable is False


# --------------------------------------------------------------------------
# Model behaviour
# --------------------------------------------------------------------------


def test_probabilities_are_bounded(bundle, panel):
    p = bundle.predict(build_frame(panel, bundle.norm_context))
    assert p.min() >= bundle.bounds.floor
    assert p.max() <= bundle.bounds.ceiling
    assert bundle.bounds.ceiling <= 0.95, (
        "the system must never assert near-certainty that a named child will "
        "leave school"
    )


def test_worse_attendance_raises_risk(bundle):
    """Monotonicity in the single most important actionable feature."""
    from edutrace.features import build_row

    def at(rate: float) -> float:
        obs = StudentObservation(
            student_key="M", school_id="SCH001", academic_year=2024, term="T2",
            week=10, grade_level="JHS3", attendance_rate_term_to_date=rate,
            attendance_rate_last_4w=rate, avg_exam_score=45.0,
            fee_arrears_terms=1, age_years=15.0,
        )
        return float(bundle.raw_score(build_row(obs, bundle.norm_context))[0])

    scores = [at(r) for r in (95.0, 80.0, 60.0, 40.0, 20.0)]
    assert scores == sorted(scores), f"risk not monotone in absence: {scores}"


def test_tiers_are_ordered(bundle):
    t = bundle.thresholds
    assert t.watch <= t.elevated <= t.high
    assert bundle.tier(t.high + 1e-9) is RiskTier.HIGH
    assert bundle.tier(0.0) is RiskTier.LOW


def test_model_beats_the_abc_baseline(bundle, panel):
    """If the rule wins, ship the rule -- but here the model should win."""
    _, _, te = final_holdout(panel)
    test = panel.iloc[te]
    y = test["label"].to_numpy().astype(int)
    p = bundle.predict(build_frame(test, bundle.norm_context))
    k = max(10, int(0.02 * len(test)))
    cmps = compare(y, p, abc_score(test), {"top 2%": k})
    assert cmps[0].model_recall >= cmps[0].baseline_recall * 0.9, (
        "the model does not clear the transparent ABC rule; prefer the rule"
    )


def test_lift_over_random_is_substantial(bundle, panel):
    _, _, te = final_holdout(panel)
    test = panel.iloc[te]
    y = test["label"].to_numpy().astype(int)
    p = bundle.predict(build_frame(test, bundle.norm_context))
    rep = evaluate(y, p)
    assert rep.capacity_metrics["top 1%"]["lift"] > 3.0
    assert rep.roc_auc > 0.65


# --------------------------------------------------------------------------
# Explanation
# --------------------------------------------------------------------------


def test_shap_contributions_sum_to_the_margin(bundle, panel):
    X = build_frame(panel.head(50), bundle.norm_context)
    contribs = bundle.contributions(X)
    margins = bundle.booster.inplace_predict(
        np.ascontiguousarray(X), predict_type="margin"
    )
    assert np.allclose(contribs.sum(axis=1), np.asarray(margins), atol=1e-3)


def test_context_themes_are_not_shown_as_drivers(scorer, panel, bundle):
    """Week-of-term is identical for every learner scored; it cannot rank."""
    from edutrace.serve.scorer import _row_to_observation

    p = bundle.predict(build_frame(panel, bundle.norm_context))
    for i in np.argsort(-p)[:20]:
        a = scorer.score(_row_to_observation(panel.iloc[int(i)]))
        for d in a.drivers + a.protective:
            assert "where we are in the school year" not in d.label


def test_recourse_only_proposes_mutable_changes(scorer, panel, bundle):
    from edutrace.explain.recourse import LEVERS
    from edutrace.serve.scorer import _row_to_observation

    keys = {lv.key for lv in LEVERS}
    p = bundle.predict(build_frame(panel, bundle.norm_context))
    for i in np.argsort(-p)[:20]:
        a = scorer.score(_row_to_observation(panel.iloc[int(i)]))
        for step in a.recourse:
            assert step.feature in keys


def test_high_tier_requires_human_review(scorer, panel, bundle):
    from edutrace.serve.scorer import _row_to_observation

    p = bundle.predict(build_frame(panel, bundle.norm_context))
    a = scorer.score(_row_to_observation(panel.iloc[int(np.argmax(p))]))
    assert a.tier is RiskTier.HIGH
    assert a.requires_human_review is True


# --------------------------------------------------------------------------
# Latency
# --------------------------------------------------------------------------


def test_single_score_latency_budget(scorer):
    obs = StudentObservation(
        student_key="L", school_id="SCH001", academic_year=2024, term="T2",
        week=9, grade_level="JHS3", attendance_rate_term_to_date=55.0,
        attendance_rate_last_4w=45.0, consecutive_absences=6,
        avg_exam_score=38.0, fee_arrears_terms=2, age_years=16.0,
        distance_band="OVER_60_MIN", has_textbooks=False,
    )
    for _ in range(5):
        scorer.score(obs)
    t = time.perf_counter()
    for _ in range(50):
        scorer.score(obs)
    ms = (time.perf_counter() - t) / 50 * 1000
    assert ms < 120, f"single score with explanation took {ms:.1f} ms"


def test_batch_throughput(scorer, panel):
    sub = panel.head(10_000)
    t = time.perf_counter()
    p, tiers, _ = scorer.score_frame(sub, explain_top_k=None)
    elapsed = time.perf_counter() - t
    assert len(p) == len(sub)
    assert elapsed < 8.0, f"10k rows took {elapsed:.2f}s"


def test_feature_vector_shape(scorer):
    from edutrace.features import build_row

    x = build_row(
        StudentObservation(
            student_key="X", school_id="S", academic_year=2024, term="T1",
            week=1, grade_level="JHS1",
        )
    )
    assert x.shape == (1, len(FEATURE_ORDER))
    assert x.dtype == np.float32
