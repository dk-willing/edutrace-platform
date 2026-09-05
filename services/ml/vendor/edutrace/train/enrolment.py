"""Train the ANNUAL enrolment-continuation model (Model A).

    python -m edutrace.train.enrolment --panel data/ghana_dhs.csv --out artifacts/enrolment

Different question from the weekly triage model, and the difference matters:

    weekly triage  "which learners should the counsellor see on Tuesday?"
                   needs registers; only a partner school has them
    enrolment      "which children are at risk of not returning next year?"
                   needs a household survey; Ghana MICS/DHS have them, free

The enrolment model is the one you can train on real Ghanaian data now.  It
targets enrolment campaigns, re-entry outreach and resource allocation between
school years.  It cannot do weekly triage, and this module refuses to pretend
otherwise: the artifact it writes carries its own contract fingerprint, and
``edutrace.serve`` will not load it as a weekly model.

The same discipline applies as everywhere else: split by survey round or year
rather than at random, calibrate on a held-out slice, report precision and
recall at a stated outreach capacity, and gate on fairness.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from ..ingest.base import (
    ENROLMENT_FEATURES,
    ENROLMENT_LABEL,
    ENROLMENT_PROTECTED,
    enrolment_fingerprint,
)
from .evaluate import evaluate
from .model import DEFAULT_PARAMS, ProbabilityBounds, Thresholds

log = logging.getLogger("edutrace.train.enrolment")

#: Direction is known for most household drivers. Same reasoning as the weekly
#: model: without constraints the booster learns locally non-monotone responses
#: in thin regions, which makes explanations indefensible.
MONOTONE_ENROLMENT = {
    "age_for_grade_gap": +1,
    "repeated_a_grade": +1,
    "attended_previous_year": -1,
    "wealth_quintile": -1,
    "years_of_education": -1,
    "head_education_years": -1,
    "mother_education_years": -1,
    "father_education_years": -1,
    "urban": -1,
    "distance_band_ord": +1,
    "does_paid_or_farm_work": +1,
    "has_electricity": -1,
    "has_improved_water": -1,
    "orphan_status": +1,
    "siblings_in_school": -1,
}


def build_matrix(df: pd.DataFrame) -> np.ndarray:
    X = np.full((len(df), len(ENROLMENT_FEATURES)), np.nan, dtype=np.float32)
    for j, f in enumerate(ENROLMENT_FEATURES):
        if f in df.columns:
            X[:, j] = pd.to_numeric(df[f], errors="coerce").to_numpy(dtype=float)
    return X


def _split(df: pd.DataFrame, year_col: str = "academic_year"):
    """Temporal split where possible; otherwise grouped by child.

    A single-round survey has no time dimension, so we fall back to a *child*
    split -- never a row split, which would put the same child on both sides.
    """
    years = sorted(pd.unique(pd.to_numeric(df[year_col], errors="coerce").dropna()))
    idx = np.arange(len(df))
    if len(years) >= 3:
        yv = pd.to_numeric(df[year_col], errors="coerce").to_numpy()
        return (
            idx[np.isin(yv, years[:-2])],
            idx[yv == years[-2]],
            idx[yv == years[-1]],
            f"temporal: train {years[:-2]} | calibrate {years[-2]} | test {years[-1]}",
        )

    keys = df["child_key"].astype(str).to_numpy() if "child_key" in df.columns else (
        idx.astype(str)
    )
    uniq = np.array(sorted(set(keys)))
    rng = np.random.default_rng(17)
    rng.shuffle(uniq)
    n = len(uniq)
    tr_k = set(uniq[: int(0.6 * n)])
    ca_k = set(uniq[int(0.6 * n) : int(0.8 * n)])
    te_k = set(uniq[int(0.8 * n) :])
    return (
        idx[[k in tr_k for k in keys]],
        idx[[k in ca_k for k in keys]],
        idx[[k in te_k for k in keys]],
        "grouped by child (only one survey round available -- NOT a temporal "
        "test, so it will overstate performance under drift)",
    )


def main(argv: list[str] | None = None) -> int:
    import xgboost as xgb

    ap = argparse.ArgumentParser(description="Train the annual enrolment model.")
    ap.add_argument("--panel", required=True, help="CSV from edutrace.ingest.cli")
    ap.add_argument("--out", default="artifacts/enrolment")
    ap.add_argument("--rounds", type=int, default=500)
    ap.add_argument("--capacity-pct", type=float, default=5.0,
                    help="Outreach capacity as %% of the cohort.")
    ap.add_argument("--allow-unfair", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    t0 = time.perf_counter()
    print("=" * 78)
    print("EduTrace :: annual enrolment-continuation model (Model A)")
    print("=" * 78)

    df = pd.read_csv(args.panel)
    if ENROLMENT_LABEL not in df.columns:
        raise SystemExit(
            f"panel has no '{ENROLMENT_LABEL}' column. Build it with "
            f"`python -m edutrace.ingest.cli convert ...`, which constructs the "
            f"enrolment transition correctly and refuses when it cannot."
        )

    y = pd.to_numeric(df[ENROLMENT_LABEL], errors="coerce").fillna(0).astype(int).to_numpy()
    X = build_matrix(df)
    support = {f: float(np.isfinite(X[:, j]).mean())
               for j, f in enumerate(ENROLMENT_FEATURES)}

    print(f"\npanel: {len(df):,} child-years, {int(y.sum()):,} left school "
          f"({y.mean():.3%})")
    print(f"contract: enrolment/{enrolment_fingerprint()} "
          f"({len(ENROLMENT_FEATURES)} features)")
    unusable = [f for f, v in support.items() if v < 0.05]
    if unusable:
        print(f"\n  ! {len(unusable)} features have under 5% support and will be "
              f"ignored:\n    {', '.join(unusable)}")

    tr, cal, te, how = _split(df)
    print(f"\nsplit ({how})")
    print(f"  train {len(tr):,} | calibrate {len(cal):,} | test {len(te):,}")
    if min(len(tr), len(cal), len(te)) < 200:
        raise SystemExit("splits too small to evaluate honestly; need more data")

    params = {
        **DEFAULT_PARAMS,
        "monotone_constraints": "("
        + ",".join(str(MONOTONE_ENROLMENT.get(f, 0)) for f in ENROLMENT_FEATURES)
        + ")",
    }
    pos, neg = float(y[tr].sum()), float(len(tr) - y[tr].sum())
    params["scale_pos_weight"] = float(np.sqrt(neg / max(pos, 1.0)))

    dtrain = xgb.DMatrix(X[tr], label=y[tr], feature_names=list(ENROLMENT_FEATURES))
    dvalid = xgb.DMatrix(X[cal], label=y[cal], feature_names=list(ENROLMENT_FEATURES))
    booster = xgb.train(
        params, dtrain, num_boost_round=args.rounds,
        evals=[(dtrain, "train"), (dvalid, "valid")],
        early_stopping_rounds=40, verbose_eval=False,
    )
    print(f"\ntrees: {booster.num_boosted_rounds()}")

    raw_cal = np.asarray(booster.inplace_predict(np.ascontiguousarray(X[cal])), float)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(raw_cal, y[cal])
    p_cal = np.asarray(iso.predict(raw_cal))
    bounds = ProbabilityBounds.from_calibration(p_cal, y[cal])
    thresholds = Thresholds.from_scores(bounds.apply(p_cal))

    raw_te = np.asarray(booster.inplace_predict(np.ascontiguousarray(X[te])), float)
    p_te = bounds.apply(np.asarray(iso.predict(raw_te)))

    test = df.iloc[te]
    n_te = len(te)
    caps = {f"top {q:g}%": max(1, int(q / 100 * n_te)) for q in (1, 2, 5, 10)}
    protected = {
        c: test[c].astype(str).to_numpy()
        for c in ENROLMENT_PROTECTED if c in test.columns
    }

    print("\n" + "=" * 78)
    print("HELD-OUT EVALUATION")
    print("=" * 78)
    rep = evaluate(y[te], p_te, capacities=caps, protected=protected,
                   note=f"Real data: {args.panel}")
    print(rep.render())

    gate = rep.fairness_passes()
    if not gate and not args.allow_unfair:
        print("\n  !! FAIRNESS GATE FAILED — artifact not written.")
        for f in rep.fairness:
            if not f.passes():
                print(f"     - {f.attribute}: FPR spread {f.fpr_spread:.4f}, "
                      f"worst calibration gap {f.worst_calibration_gap:.4f}")
        print("  Re-run with --allow-unfair to record the failure on the card.")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out / "booster.json"))
    (out / "bundle.json").write_text(json.dumps({
        "profile": "enrolment",
        "contract_fingerprint": enrolment_fingerprint(),
        "feature_order": list(ENROLMENT_FEATURES),
        "feature_support": support,
        "thresholds": asdict(thresholds),
        "bounds": asdict(bounds),
        "calibrator": {"x": iso.X_thresholds_.tolist(),
                       "y": iso.y_thresholds_.tolist()},
        "data_provenance": f"REAL data from {args.panel}",
        "split": how,
        "metrics": {"roc_auc": rep.roc_auc, "pr_auc": rep.pr_auc,
                    "brier": rep.brier, "ece": rep.ece,
                    "capacity": rep.capacity_metrics,
                    "fairness_gate_passed": gate},
        "intended_use": (
            "Between-year enrolment targeting: which children are at risk of "
            "not returning next school year. Directs enrolment campaigns and "
            "re-entry outreach."
        ),
        "out_of_scope": [
            "Weekly in-school triage -- this model has no attendance data and "
            "cannot tell you who to speak to this week.",
            "Any decision about a named child without human review.",
            "Ranking schools, teachers or districts.",
        ],
    }, indent=2))
    (out / "eval_report.txt").write_text(rep.render())
    print(f"\nwrote {out}")
    print(f"elapsed {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
