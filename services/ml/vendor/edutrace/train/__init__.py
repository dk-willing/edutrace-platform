"""Training pipeline: splits, model, calibration, evaluation, baseline."""

from .baseline import abc_score, compare
from .evaluate import EvalReport, evaluate
from .model import ModelBundle, ModelCard, Thresholds, fit_calibrator, make_card, train_booster
from .splits import final_holdout, forward_chaining, group_by_school

__all__ = [
    "abc_score", "compare", "EvalReport", "evaluate", "ModelBundle", "ModelCard",
    "Thresholds", "fit_calibrator", "make_card", "train_booster",
    "final_holdout", "forward_chaining", "group_by_school",
]
