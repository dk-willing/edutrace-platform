"""Training entrypoint.

    python -m edutrace.train.run --out artifacts/model

Sequence:

1.  Load the panel (simulated by default; ``--panel`` takes a real CSV).
2.  Split strictly by academic year into train / calibration / test.
3.  Report the forward-chaining curve, so drift is visible rather than averaged
    away.
4.  Fit the booster on the natural class distribution.
5.  Fit an isotonic calibrator on the calibration *year*.
6.  Set tier thresholds from the calibration-year score distribution.
7.  Evaluate on the held-out final year: capacity metrics, calibration, and a
    fairness audit by sex, poverty quintile and region.
8.  Compare against the ABC rule at every capacity.
9.  Refuse to write the artifact if the fairness gate fails, unless
    ``--allow-unfair`` is passed explicitly and the reason is recorded on the
    model card.

Step 9 is the one that matters.  DEWS ran for a decade after its own equity
analysis concluded "Is DEWS Fair? ... no"; nothing in the pipeline could stop
it.  Here, something can.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..contract import HORIZON_WEEKS, contract_fingerprint
from ..features import GradeNormContext, build_frame
from ..simulate import SimConfig, simulate
from . import baseline
from .evaluate import evaluate
from .model import (
    ModelBundle,
    ProbabilityBounds,
    Thresholds,
    fit_calibrator,
    make_card,
    train_booster,
)
from .splits import final_holdout, forward_chaining, group_by_school

log = logging.getLogger("edutrace.train")


def load_panel(args) -> tuple[pd.DataFrame, str]:
    if args.panel:
        df = pd.read_csv(args.panel)
        if "label" not in df.columns:
            raise SystemExit(
                "--panel CSV must contain a 'label' column built as a "
                f"{HORIZON_WEEKS}-week forward hazard with administrative "
                "censoring applied. See edutrace/simulate/generator.py::_attach_labels."
            )
        side = Path(str(args.panel) + ".provenance.txt")
        if side.exists():
            return df, "REAL DATA. " + side.read_text().strip()
        return df, (
            f"real panel from {args.panel} (no provenance sidecar found -- "
            f"prefer generating panels with edutrace.ingest.cli, which records "
            f"source, counts and caveats automatically)"
        )

    cfg = SimConfig(
        n_schools=args.schools,
        entrants_per_school=args.entrants,
        n_cohorts=args.cohorts,
        seed=args.seed,
    )
    res = simulate(cfg)
    return res.panel, (
        "SIMULATED by edutrace.simulate (structural causal model calibrated to "
        "published Ghana JHS statistics). NOT real student data. Any performance "
        "number below describes the pipeline, not the world."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train the EduTrace risk model.")
    ap.add_argument("--out", default="artifacts/model")
    ap.add_argument("--panel", default=None, help="CSV of real panel data")
    ap.add_argument("--schools", type=int, default=20)
    ap.add_argument("--entrants", type=int, default=45)
    ap.add_argument("--cohorts", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260829)
    ap.add_argument("--rounds", type=int, default=600)
    ap.add_argument("--capacity-pct", type=float, default=1.0,
                    help="Primary intervention capacity, as %% of the cohort.")
    ap.add_argument("--allow-unfair", action="store_true",
                    help="Write the artifact even if the fairness gate fails.")
    ap.add_argument("--skip-cv", action="store_true")
    ap.add_argument("--protected", default="sex,poverty_quintile,region",
                    help="Comma-separated columns to audit for fairness. Never "
                         "model inputs; measured as outcomes.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    t0 = time.perf_counter()
    print("=" * 78)
    print("EduTrace :: training")
    print("=" * 78)

    panel, provenance = load_panel(args)
    print(f"\nprovenance: {provenance}")
    print(f"panel: {len(panel):,} rows, {panel['student_key'].nunique():,} students, "
          f"years {sorted(pd.unique(panel['academic_year']))}")
    print(f"positive rate: {panel['label'].mean():.4%}  "
          f"(P(exit within {HORIZON_WEEKS} weeks | enrolled))")
    print(f"feature contract: {contract_fingerprint()}")

    y_all = panel["label"].to_numpy().astype(int)
    tr_idx, cal_idx, te_idx = final_holdout(panel)

    # The percentile context is fitted on TRAINING ROWS ONLY.  Fitting it on the
    # full panel would leak the test year's mark distribution into training --
    # a small leak, but the kind that quietly inflates every number downstream.
    norm_ctx = GradeNormContext.fit(panel.iloc[tr_idx])
    X_all = build_frame(panel, norm_ctx)

    support = {f: float(np.isfinite(X_all[:, j]).mean())
               for j, f in enumerate(__import__("edutrace.contract", fromlist=["x"]).FEATURE_ORDER)}
    dead = [f for f, v in support.items() if v < 0.05]
    if dead:
        print(f"\n  ! {len(dead)} features have under 5% support in this panel and")
        print(f"    will be ignored by the model. Do NOT rely on them at serving")
        print(f"    time: {', '.join(dead)}")

    years = sorted(pd.unique(panel["academic_year"]))
    print(f"\nsplit (strictly temporal): train {years[:-2]} | "
          f"calibrate {years[-2]} | test {years[-1]}")
    print(f"  train {len(tr_idx):,} | calib {len(cal_idx):,} | test {len(te_idx):,}")

    # ---- 3. forward-chaining curve -------------------------------------
    if not args.skip_cv:
        print("\n" + "-" * 78)
        print("forward-chaining validation (each fold trains only on prior years)")
        print("-" * 78)
        for fold in forward_chaining(panel):
            b = train_booster(
                X_all[fold.train_idx], y_all[fold.train_idx],
                num_boost_round=min(args.rounds, 300),
                early_stopping_rounds=0,
            )
            p = b.inplace_predict(np.ascontiguousarray(X_all[fold.test_idx]))
            rep = evaluate(y_all[fold.test_idx], np.asarray(p, dtype=float))
            k = max(1, int(0.01 * len(fold.test_idx)))
            print(f"  {fold.description:<28} {fold.sizes():<28} "
                  f"ROC-AUC {rep.roc_auc:.4f}  "
                  f"P@1% {rep.capacity_metrics['top 1%']['precision']:.4f}  "
                  f"R@1% {rep.capacity_metrics['top 1%']['recall']:.4f}")

        print("\ngroup-by-school validation (unseen schools, and so unseen regions)")
        for fold in group_by_school(panel, n_folds=3):
            b = train_booster(
                X_all[fold.train_idx], y_all[fold.train_idx],
                num_boost_round=min(args.rounds, 300), early_stopping_rounds=0,
            )
            p = b.inplace_predict(np.ascontiguousarray(X_all[fold.test_idx]))
            rep = evaluate(y_all[fold.test_idx], np.asarray(p, dtype=float))
            print(f"  {fold.name:<28} {fold.sizes():<28} ROC-AUC {rep.roc_auc:.4f}  "
                  f"R@1% {rep.capacity_metrics['top 1%']['recall']:.4f}")

    # ---- 4-6. final model ----------------------------------------------
    print("\n" + "-" * 78)
    print("fitting final booster")
    print("-" * 78)
    booster = train_booster(
        X_all[tr_idx], y_all[tr_idx],
        X_valid=X_all[cal_idx], y_valid=y_all[cal_idx],
        num_boost_round=args.rounds,
    )
    best = getattr(booster, "best_iteration", None)
    print(f"  trees: {booster.num_boosted_rounds()}"
          + (f" (best iteration {best})" if best is not None else ""))

    raw_cal = np.asarray(
        booster.inplace_predict(np.ascontiguousarray(X_all[cal_idx])), dtype=float
    )
    calibrator = fit_calibrator(raw_cal, y_all[cal_idx])
    p_cal_unbounded = np.asarray(calibrator.predict(raw_cal))
    bounds = ProbabilityBounds.from_calibration(p_cal_unbounded, y_all[cal_idx])
    thresholds = Thresholds.from_scores(bounds.apply(p_cal_unbounded))
    print(f"  probability bounds: floor {bounds.floor:.5f}  "
          f"ceiling {bounds.ceiling:.3f}  (isotonic saturates at 1.0 on a thin "
          f"top bin; we do not claim more than the calibration year showed)")
    print(f"  tiers  WATCH >= {thresholds.watch:.5f}   "
          f"ELEVATED >= {thresholds.elevated:.5f}   HIGH >= {thresholds.high:.5f}")

    # ---- 7. held-out evaluation ----------------------------------------
    test = panel.iloc[te_idx]
    raw_te = np.asarray(
        booster.inplace_predict(np.ascontiguousarray(X_all[te_idx])), dtype=float
    )
    p_te = bounds.apply(np.asarray(calibrator.predict(raw_te)))
    y_te = y_all[te_idx]

    n_te = len(te_idx)
    primary_k = max(1, int(args.capacity_pct / 100.0 * n_te))
    capacities = {
        "top 0.5%": max(1, int(0.005 * n_te)),
        "top 1%": max(1, int(0.01 * n_te)),
        "top 2%": max(1, int(0.02 * n_te)),
        "top 5%": max(1, int(0.05 * n_te)),
    }

    print("\n" + "=" * 78)
    print(f"HELD-OUT YEAR {years[-1]} -- the only numbers worth quoting")
    print("=" * 78)
    report = evaluate(
        y_te, p_te,
        capacities=capacities,
        primary_capacity=f"top {args.capacity_pct:g}%"
        if f"top {args.capacity_pct:g}%" in capacities else "top 1%",
        protected={
            c: test[c].astype(str).to_numpy()
            for c in [x.strip() for x in args.protected.split(",") if x.strip()]
            if c in test.columns
        },
        note="Probabilities are calibrated on a separate academic year.",
    )
    print(report.render())

    # ---- 8. baseline comparison ----------------------------------------
    print("-" * 78)
    print(baseline.render(
        baseline.compare(y_te, p_te, baseline.abc_score(test), capacities)
    ))
    print("-" * 78)

    # ---- 9. fairness gate ----------------------------------------------
    gate_ok = report.fairness_passes()
    if not gate_ok:
        print("\n  !! FAIRNESS GATE FAILED")
        for f in report.fairness:
            if not f.passes():
                print(f"     - {f.attribute}: FPR spread {f.fpr_spread:.4f} "
                      f"(<= {f.fpr_tolerance}), worst calibration gap "
                      f"{f.worst_calibration_gap:.4f} "
                      f"(<= {f.calibration_tolerance})"
                      + (f", recall spread {f.recall_spread:.4f}"
                         if f.recall_gate_applicable else ""))
        if not args.allow_unfair:
            print("\n  Artifact NOT written. Options, in order of preference:")
            print("    1. Fix the data or the features causing the disparity.")
            print("    2. Lower the capacity (flagging fewer learners usually "
                  "narrows FPR spread).")
            print("    3. Post-process to equalised odds and accept the "
                  "precision cost.")
            print("    4. Re-run with --allow-unfair; the failure is then "
                  "recorded on the model card and served at /model-card.")
            return 2
        print("  --allow-unfair set: writing artifact with the failure recorded "
              "on the model card.")

    # ---- write ----------------------------------------------------------
    card = make_card(
        n_train_rows=int(len(tr_idx)),
        n_train_students=int(panel.iloc[tr_idx]["student_key"].nunique()),
        train_years=[int(y) for y in years[:-2]],
        calibration_year=int(years[-2]),
        test_year=int(years[-1]),
        base_rate=float(y_all[tr_idx].mean()),
        data_provenance=provenance,
        metrics={
            "roc_auc": report.roc_auc,
            "pr_auc": report.pr_auc,
            "brier": report.brier,
            "ece": report.ece,
            "capacity": report.capacity_metrics,
            "fairness_gate_passed": gate_ok,
            "fairness": [
                {
                    "attribute": f.attribute,
                    "fpr_spread": f.fpr_spread,
                    "recall_spread": f.recall_spread,
                    "worst_calibration_gap": f.worst_calibration_gap,
                    "base_rate_ratio": f.base_rate_ratio,
                    "recall_gate_applicable": f.recall_gate_applicable,
                    "passes": f.passes(),
                }
                for f in report.fairness
            ],
        },
        params={"num_boost_round": booster.num_boosted_rounds()},
        feature_support=support,
    )
    bundle = ModelBundle(
        booster=booster,
        calibrator=calibrator,
        thresholds=thresholds,
        norm_context=norm_ctx,
        card=card,
        bounds=bounds,
    )
    out = bundle.save(args.out)
    (Path(out) / "eval_report.txt").write_text(report.render())

    print(f"\nwrote {out}  (version {card.version})")
    print(f"elapsed {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
