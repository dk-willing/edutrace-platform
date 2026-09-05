"""The model bundle: booster + calibrator + thresholds + provenance.

Three decisions worth defending.

**No SMOTE, no resampling.**  The positive rate here is under 1%, which is
exactly where people reach for SMOTE.  The evidence says not to.  van den
Goorbergh et al. (JAMIA 2022) showed random over/under-sampling and SMOTE
produce severely miscalibrated risk models with *no* AUC gain, and that the
same sensitivity/specificity trade-off is available by simply moving the
decision threshold.  Elor & Averbuch-Elor found balancing does not improve
strong learners (XGBoost, LightGBM, CatBoost) at all.  Since this system's
output is a *probability a teacher is asked to trust*, decalibrating it to buy
nothing would be a straight downgrade.  We train on the natural distribution,
use ``scale_pos_weight`` only as a gradient-scaling aid, then undo its
probability distortion with an isotonic calibrator fitted on a held-out year.

**Depth capped at 6.**  Not (only) for regularisation: TreeSHAP cost grows
roughly with depth squared.  Published Fast TreeSHAP figures put a 100-tree
depth-4 model at ~0.24 ms/row and depth-12 at ~48 ms/row.  At depth 6 a
few-hundred-tree model computes exact per-student attributions in single-digit
milliseconds, which is what makes "every score ships with its explanation"
affordable rather than a batch job.

**The contract fingerprint is stored and checked.**  Loading a booster whose
feature contract does not match the running code raises.  A silently reordered
feature vector is the single most expensive bug available in a tabular system,
because nothing crashes -- the model just becomes confidently wrong.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression

from ..contract import FEATURE_ORDER, RiskTier, contract_fingerprint
from ..features import GradeNormContext

log = logging.getLogger(__name__)


#: Monotonic constraints: +1 means risk may only increase with the feature,
#: -1 only decrease, 0 unconstrained.
#:
#: These are not regularisation for its own sake. Without them the booster
#: happily learns a locally *non-monotone* response to attendance -- in an
#: early run, predicted risk at 60% attendance sat above risk at 40%, because
#: that region of the feature space is thinly populated and the trees fit
#: noise. Three consequences, in increasing order of seriousness:
#:
#:   1. The counterfactual search in ``edutrace.explain.recourse`` bisects on
#:      the assumption that risk is monotone in the improving direction. If it
#:      is not, the search returns a wrong answer with a confident interface.
#:   2. A teacher shown "attendance is driving this risk" and then told that
#:      improving attendance raises it has been given nonsense, and will
#:      correctly stop trusting the system.
#:   3. It is indefensible in review. "The model believes worse attendance is
#:      sometimes safer" is not a defensible sentence.
#:
#: Direction is set only where the causal sign is genuinely known. Grade, term,
#: week, sibling count and guardian type are left unconstrained, because their
#: relationship with attrition is real but not sign-obvious.
MONOTONE: dict[str, int] = {
    "attendance_rate_term_to_date": -1,
    "attendance_rate_last_4w": -1,
    "attendance_trend_4w": -1,
    "consecutive_absences": +1,
    "longest_absence_streak_term": +1,
    "absences_prior_year": +1,
    "attendance_rate_prior_term": -1,
    "exam_percentile_in_grade": -1,
    "exam_score_delta_prev_term": -1,
    "assessment_completion_rate": -1,
    "core_subject_failures": +1,
    "age_for_grade_gap": +1,
    "repeated_a_grade": +1,
    "school_transfers_count": +1,
    "fee_status_ord": +1,
    "fee_arrears_terms": +1,
    "has_textbooks": -1,
    "has_uniform": -1,
    "does_paid_or_farm_work": +1,
    "distance_band_ord": +1,
    "distance_x_rainy_term": +1,
    "behaviour_incidents_term": +1,
    "behaviour_severity_max": +1,
    "health_absence_days_term": +1,
    "bece_registered": -1,
}


def monotone_constraint_string() -> str:
    return "(" + ",".join(str(MONOTONE.get(f, 0)) for f in FEATURE_ORDER) + ")"


DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "binary:logistic",
    "eval_metric": ["aucpr", "logloss"],
    "tree_method": "hist",
    "max_depth": 6,            # see module docstring: this is a latency budget
    "min_child_weight": 20.0,  # panel rows are autocorrelated; resist tiny leaves
    "eta": 0.05,
    "subsample": 0.85,
    "colsample_bytree": 0.75,
    "reg_lambda": 2.5,
    "reg_alpha": 0.5,
    "max_bin": 256,
    "nthread": 0,
}
DEFAULT_PARAMS["monotone_constraints"] = monotone_constraint_string()


@dataclass(frozen=True, slots=True)
class ProbabilityBounds:
    """Floor and ceiling applied to every calibrated probability.

    Isotonic regression will happily map the top raw-score bin to exactly 1.0
    when every calibration row in that bin was a positive.  That bin typically
    holds a few dozen learners, so "1.0" means "the eleven similar children we
    saw all left", not certainty -- and a system that prints a 100% chance that
    a named child is about to drop out has stopped being a triage aid and
    started making a claim it cannot support.  It also flattens the recourse
    search: at a saturated score, no change to any feature registers, so the
    system reports "nothing would help", which is false and demoralising.

    So the ceiling is the largest rate actually *observed* in a calibration bin
    with adequate support, hard-capped at ``absolute_max``.  The floor is the
    rule-of-three bound: with n calibration rows and zero events, the upper
    confidence limit on the rate is about 3/n, so claiming less than that is
    claiming more precision than the data holds.
    """

    floor: float
    ceiling: float
    absolute_max: float = 0.95

    @classmethod
    def from_calibration(
        cls,
        calibrated: np.ndarray,
        y: np.ndarray,
        min_bin: int = 50,
        absolute_max: float = 0.95,
    ) -> "ProbabilityBounds":
        n = max(len(calibrated), 1)
        order = np.argsort(calibrated)
        y_sorted = np.asarray(y)[order]
        top = y_sorted[-min_bin:] if len(y_sorted) >= min_bin else y_sorted
        observed_max = float(top.mean()) if len(top) else absolute_max
        return cls(
            floor=float(min(3.0 / n, 0.001)),
            ceiling=float(min(max(observed_max, 0.05), absolute_max)),
            absolute_max=absolute_max,
        )

    def apply(self, p: np.ndarray) -> np.ndarray:
        return np.clip(p, self.floor, self.ceiling)


@dataclass(slots=True)
class Thresholds:
    """Tier boundaries derived from capacity, not from round numbers.

    The tiers are quantiles of the *training-year score distribution*, so
    "HIGH" means "in the top 1% of risk this school can see", which is a
    statement a head teacher can staff.  A fixed 0.7 cutoff on a calibrated
    probability at a 0.8% base rate would flag nobody, ever.
    """

    watch: float
    elevated: float
    high: float

    def tier(self, p: float) -> RiskTier:
        if p >= self.high:
            return RiskTier.HIGH
        if p >= self.elevated:
            return RiskTier.ELEVATED
        if p >= self.watch:
            return RiskTier.WATCH
        return RiskTier.LOW

    @classmethod
    def from_scores(
        cls,
        scores: np.ndarray,
        watch_q: float = 0.90,
        elevated_q: float = 0.97,
        high_q: float = 0.99,
    ) -> "Thresholds":
        return cls(
            watch=float(np.quantile(scores, watch_q)),
            elevated=float(np.quantile(scores, elevated_q)),
            high=float(np.quantile(scores, high_q)),
        )


@dataclass(slots=True)
class ModelCard:
    """Provenance that ships with the artifact and is served at /model-card.

    A model whose limitations live only in a README does not have limitations;
    it has a README.  These fields are surfaced in the API response and in the
    admin UI.
    """

    version: str
    trained_at: str
    contract_fingerprint: str
    n_features: int
    n_train_rows: int
    n_train_students: int
    train_years: list[int]
    calibration_year: int | None
    test_year: int | None
    base_rate: float
    data_provenance: str
    intended_use: str
    out_of_scope: list[str]
    known_limitations: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    #: Share of training rows with a value, per feature. A feature at ~0 was
    #: never learned and must not be trusted if it appears at serving time.
    feature_support: dict[str, float] = field(default_factory=dict)


DEFAULT_OUT_OF_SCOPE = [
    "Any decision about a child taken without a named member of staff reviewing it.",
    "Streaming, setting, exclusion, disciplinary action, or exam entry decisions.",
    "Sharing a risk score with the learner, or with anyone outside the school's "
    "safeguarding and pastoral chain.",
    "Ranking schools, teachers, or districts.",
    "Any use where no support is actually available to the learners it flags -- "
    "screening without services is a labelling harm, not a benefit.",
]

DEFAULT_LIMITATIONS = [
    "Trained on simulated data unless the provenance field says otherwise. A model "
    "fitted to a simulator learns the simulator's assumptions, not Ghana's schools.",
    "Predicts a statistical pattern over a fixed horizon, not an individual's future.",
    "Sex, region and poverty quintile are excluded as inputs and audited as "
    "outcomes; residual disparity in error rates is reported, not eliminated.",
    "Performance degrades under distribution shift (fee policy changes, closures, "
    "curriculum reform). Re-validate every academic year against realised outcomes.",
    "A simple attendance-and-course-failure rule is a strong baseline. If this "
    "model does not clearly beat one, prefer the rule -- it is explainable for free.",
]


@dataclass
class ModelBundle:
    booster: xgb.Booster
    calibrator: IsotonicRegression | None
    thresholds: Thresholds
    norm_context: GradeNormContext
    card: ModelCard
    bounds: ProbabilityBounds = field(
        default_factory=lambda: ProbabilityBounds(floor=1e-4, ceiling=0.95)
    )

    # ---- prediction ----------------------------------------------------

    def raw_score(self, X: np.ndarray) -> np.ndarray:
        """Uncalibrated booster output.

        ``inplace_predict`` rather than ``DMatrix`` + ``predict``: DMatrix
        construction is 45-90% of total predict time on small batches, and on a
        single row the difference is roughly 1.9 ms vs 0.7 ms.
        """
        out = self.booster.inplace_predict(np.ascontiguousarray(X, dtype=np.float32))
        return np.asarray(out, dtype=np.float64).reshape(-1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Calibrated probability."""
        raw = self.raw_score(X)
        if self.calibrator is None:
            return self.bounds.apply(raw)
        return self.bounds.apply(np.asarray(self.calibrator.predict(raw)))

    def contributions(self, X: np.ndarray) -> np.ndarray:
        """Exact TreeSHAP values, shape ``(n, n_features + 1)``.

        Uses XGBoost's native C++ implementation via ``pred_contribs`` rather
        than the ``shap`` package -- same algorithm, no extra dependency, and
        it works directly on the Booster the server already holds.  The final
        column is the expected value (base margin).
        """
        dm = xgb.DMatrix(np.ascontiguousarray(X, dtype=np.float32),
                         feature_names=list(FEATURE_ORDER))
        return np.asarray(self.booster.predict(dm, pred_contribs=True))

    def tier(self, p: float) -> RiskTier:
        return self.thresholds.tier(p)

    def probability_of_raw(self, raw: float) -> float:
        """Calibrated probability for a single raw margin."""
        if self.calibrator is None:
            return float(self.bounds.apply(np.asarray([raw]))[0])
        return float(
            self.bounds.apply(np.asarray(self.calibrator.predict([raw])))[0]
        )

    def raw_for_probability(self, p_target: float, grid: int = 2048) -> float:
        """Invert the calibrator: smallest raw margin scoring at least ``p_target``.

        The calibrator is monotone, so this is well defined. A grid scan rather
        than an analytic inverse because isotonic's inverse is set-valued on
        every plateau, and we want the *smallest* raw value that reaches the
        threshold -- the conservative choice, since it makes recourse harder to
        claim rather than easier.
        """
        if self.calibrator is None:
            return float(p_target)
        xs = np.asarray(self.calibrator.X_thresholds_, dtype=float)
        lo, hi = float(xs.min()), float(xs.max())
        probe = np.linspace(lo, hi, grid)
        vals = self.bounds.apply(np.asarray(self.calibrator.predict(probe)))
        hits = np.flatnonzero(vals >= p_target)
        return float(probe[hits[0]]) if hits.size else hi

    # ---- persistence ---------------------------------------------------

    def save(self, directory: str | Path) -> Path:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(str(d / "booster.json"))
        payload: dict[str, Any] = {
            "thresholds": asdict(self.thresholds),
            "bounds": asdict(self.bounds),
            "norm_context": self.norm_context.to_dict(),
            "card": asdict(self.card),
            "feature_order": list(FEATURE_ORDER),
        }
        if self.calibrator is not None:
            payload["calibrator"] = {
                "x": self.calibrator.X_thresholds_.tolist(),
                "y": self.calibrator.y_thresholds_.tolist(),
            }
        (d / "bundle.json").write_text(json.dumps(payload, indent=2))
        log.info("saved model bundle to %s", d)
        return d

    @classmethod
    def load(cls, directory: str | Path) -> "ModelBundle":
        d = Path(directory)
        payload = json.loads((d / "bundle.json").read_text())

        stored = payload["card"]["contract_fingerprint"]
        current = contract_fingerprint()
        if stored != current:
            raise RuntimeError(
                f"feature contract mismatch: model was trained against "
                f"{stored}, this code is {current}. Refusing to load -- a "
                f"reordered feature vector produces confident nonsense rather "
                f"than an error. Retrain, or check out the matching revision."
            )

        booster = xgb.Booster()
        booster.load_model(str(d / "booster.json"))
        booster.set_param({"nthread": 1})  # per-request latency beats throughput

        calibrator = None
        if "calibrator" in payload:
            calibrator = IsotonicRegression(out_of_bounds="clip")
            x = np.asarray(payload["calibrator"]["x"], dtype=float)
            y = np.asarray(payload["calibrator"]["y"], dtype=float)
            calibrator.fit(x, y)

        return cls(
            booster=booster,
            calibrator=calibrator,
            thresholds=Thresholds(**payload["thresholds"]),
            bounds=ProbabilityBounds(**payload["bounds"])
            if "bounds" in payload
            else ProbabilityBounds(floor=1e-4, ceiling=0.95),
            norm_context=GradeNormContext.from_dict(payload["norm_context"]),
            card=ModelCard(**payload["card"]),
        )


# --------------------------------------------------------------------------


def train_booster(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_valid: np.ndarray | None = None,
    y_valid: np.ndarray | None = None,
    params: dict[str, Any] | None = None,
    num_boost_round: int = 600,
    early_stopping_rounds: int = 40,
    use_scale_pos_weight: bool = True,
) -> xgb.Booster:
    p = {**DEFAULT_PARAMS, **(params or {})}
    if use_scale_pos_weight:
        pos = float(y_train.sum())
        neg = float(len(y_train) - pos)
        # Capped: the raw neg/pos ratio here is ~120:1, which pushes the model
        # into a regime where a handful of positives dominate every split.
        # sqrt-damping keeps the gradient signal without that instability, and
        # the isotonic step repairs the resulting probability shift anyway.
        p["scale_pos_weight"] = float(np.sqrt(neg / max(pos, 1.0)))

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=list(FEATURE_ORDER))
    evals = [(dtrain, "train")]
    if X_valid is not None and y_valid is not None:
        evals.append(
            (xgb.DMatrix(X_valid, label=y_valid, feature_names=list(FEATURE_ORDER)),
             "valid")
        )

    return xgb.train(
        p,
        dtrain,
        num_boost_round=num_boost_round,
        evals=evals,
        early_stopping_rounds=early_stopping_rounds if len(evals) > 1 else None,
        verbose_eval=False,
    )


def fit_calibrator(raw_scores: np.ndarray, y: np.ndarray) -> IsotonicRegression:
    """Isotonic calibration on a held-out year.

    Isotonic over Platt because ``scale_pos_weight`` produces a monotone but
    distinctly non-sigmoidal distortion, which a two-parameter logistic cannot
    absorb.  Isotonic needs more data; a full academic year of panel rows is
    ample.
    """
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(raw_scores, y)
    return iso


def make_card(**kwargs: Any) -> ModelCard:
    kwargs.setdefault("version", datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    kwargs.setdefault("trained_at", datetime.now(timezone.utc).isoformat())
    kwargs.setdefault("contract_fingerprint", contract_fingerprint())
    kwargs.setdefault("n_features", len(FEATURE_ORDER))
    kwargs.setdefault("out_of_scope", list(DEFAULT_OUT_OF_SCOPE))
    kwargs.setdefault("known_limitations", list(DEFAULT_LIMITATIONS))
    kwargs.setdefault(
        "intended_use",
        "Advisory triage. Ranks currently-enrolled JHS learners by modelled "
        "probability of ceasing attendance within the next 8 weeks, so that a "
        "school can direct a fixed number of pastoral conversations at the "
        "learners most likely to need one.",
    )
    return ModelCard(**kwargs)


__all__ = [
    "DEFAULT_PARAMS",
    "MONOTONE",
    "monotone_constraint_string",
    "ModelBundle",
    "ProbabilityBounds",
    "ModelCard",
    "Thresholds",
    "train_booster",
    "fit_calibrator",
    "make_card",
]
