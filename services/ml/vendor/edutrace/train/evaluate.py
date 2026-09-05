"""Evaluation built around capacity, calibration and fairness.

Accuracy and F1 are the wrong metrics for an early-warning system and are
omitted deliberately.  At a 0.8% positive rate, a model that predicts "no one
leaves" scores 99.2% accuracy, and F1 silently assumes the operating point that
maximises it rather than the one the school can staff.

What a head teacher actually has is a *capacity*: the counsellor can hold forty
conversations this term.  So the metrics here are:

``precision_at_k``   of the k highest-risk learners, how many really left.
``recall_at_k``      of everyone who left, how many were in that top k.
``lift_at_k``        how much better than picking k learners at random.
``ece`` / ``brier``  is a "12% risk" actually a 12% risk.
fairness             are the error rates the same for girls and boys, for the
                     poorest quintile and the richest, for each region.

The fairness block exists because of a specific, documented failure.  Wisconsin
DEWS ran for a decade; a 2021 internal analysis found its false-alarm rate was
42 percentage points higher for Black students than White students; the finding
was never acted on and never told to districts.  The lesson is not "compute
fairness metrics" -- it is that a system which cannot *fail* on them will not
surface them.  ``FairnessReport.passes()`` is therefore a hard gate in the
training CLI, not a printout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


# --------------------------------------------------------------------------
# Capacity-based metrics
# --------------------------------------------------------------------------


def top_k_mask(scores: np.ndarray, k: int) -> np.ndarray:
    k = int(min(max(k, 0), len(scores)))
    mask = np.zeros(len(scores), dtype=bool)
    if k:
        mask[np.argpartition(-scores, k - 1)[:k]] = True
    return mask


def precision_at_k(y: np.ndarray, scores: np.ndarray, k: int) -> float:
    m = top_k_mask(scores, k)
    return float(y[m].mean()) if m.any() else float("nan")


def recall_at_k(y: np.ndarray, scores: np.ndarray, k: int) -> float:
    pos = y.sum()
    if pos == 0:
        return float("nan")
    return float(y[top_k_mask(scores, k)].sum() / pos)


def lift_at_k(y: np.ndarray, scores: np.ndarray, k: int) -> float:
    base = y.mean()
    if base == 0:
        return float("nan")
    return precision_at_k(y, scores, k) / base


def expected_calibration_error(
    y: np.ndarray, p: np.ndarray, n_bins: int = 10
) -> tuple[float, list[tuple[float, float, int]]]:
    """ECE with equal-count bins.

    Equal-count rather than equal-width: at a sub-1% base rate almost every
    prediction lands in the first equal-width bin, and the resulting number is
    dominated by one bucket.
    """
    order = np.argsort(p)
    p_s, y_s = p[order], y[order]
    bins = np.array_split(np.arange(len(p_s)), n_bins)
    ece = 0.0
    curve: list[tuple[float, float, int]] = []
    for b in bins:
        if b.size == 0:
            continue
        conf = float(p_s[b].mean())
        acc = float(y_s[b].mean())
        curve.append((conf, acc, int(b.size)))
        ece += (b.size / len(p_s)) * abs(acc - conf)
    return float(ece), curve


# --------------------------------------------------------------------------


@dataclass(slots=True)
class GroupMetrics:
    group: str
    n: int
    positives: int
    flagged: int
    fpr: float
    fnr: float
    recall: float
    precision: float
    mean_score: float
    mean_outcome: float

    @property
    def calibration_gap(self) -> float:
        """Mean predicted risk minus realised risk.

        This is the metric DEWS failed.  Ranking is only fair if a score of
        0.20 means the same thing for every group; when it does not, ranking by
        score systematically deprioritises the group whose risk is understated.
        """
        return self.mean_score - self.mean_outcome


@dataclass(slots=True)
class FairnessReport:
    attribute: str
    groups: list[GroupMetrics] = field(default_factory=list)
    #: Maximum tolerated spread in false-positive rate between groups.
    fpr_tolerance: float = 0.05
    #: Maximum tolerated spread in recall (equal opportunity).
    recall_tolerance: float = 0.15
    #: Maximum tolerated per-group calibration gap.
    calibration_tolerance: float = 0.02
    #: Recall parity is only *gated* when the groups' realised base rates are
    #: within this factor of each other.  See ``recall_gate_applicable``.
    max_base_rate_ratio_for_recall_gate: float = 2.0

    def _spread(self, values: Iterable[float]) -> float:
        vals = [v for v in values if np.isfinite(v)]
        return float(max(vals) - min(vals)) if len(vals) > 1 else 0.0

    @property
    def fpr_spread(self) -> float:
        return self._spread(g.fpr for g in self.groups)

    @property
    def recall_spread(self) -> float:
        return self._spread(g.recall for g in self.groups)

    @property
    def worst_calibration_gap(self) -> float:
        gaps = [abs(g.calibration_gap) for g in self.groups if np.isfinite(g.calibration_gap)]
        return float(max(gaps)) if gaps else 0.0

    @property
    def base_rate_ratio(self) -> float:
        """Largest / smallest realised outcome rate across groups."""
        rates = [g.mean_outcome for g in self.groups if g.mean_outcome > 0]
        return float(max(rates) / min(rates)) if len(rates) > 1 else 1.0

    @property
    def recall_gate_applicable(self) -> bool:
        """Whether equal-recall is a coherent requirement for this attribute.

        Kleinberg et al. and Chouldechova both show that calibration-within-
        group and equal error rates cannot hold simultaneously unless the
        groups have equal base rates.  Poverty quintile here is the live case:
        the poorest quintile's realised exit rate is ~30x the richest's.  Under
        a single global capacity, any correctly-calibrated ranking *must* give
        the high-base-rate group higher recall.  Gating on equal recall would
        therefore demand that the model stop ranking honestly -- flagging
        better-off learners who are not at risk in order to level a statistic.

        So recall parity is a hard gate only where base rates are comparable
        (sex, typically), and advisory where they are not.  What stays hard
        everywhere is **calibration-within-group** and **false-positive-rate
        parity** -- the two DEWS actually failed, and the two that cannot be
        explained away by differing base rates.
        """
        return self.base_rate_ratio <= self.max_base_rate_ratio_for_recall_gate

    def passes(self) -> bool:
        ok = (
            self.fpr_spread <= self.fpr_tolerance
            and self.worst_calibration_gap <= self.calibration_tolerance
        )
        if self.recall_gate_applicable:
            ok = ok and self.recall_spread <= self.recall_tolerance
        return ok

    def render(self) -> str:
        recall_note = (
            f"recall spread {self.recall_spread:.4f} (<= {self.recall_tolerance})"
            if self.recall_gate_applicable
            else f"recall spread {self.recall_spread:.4f} (advisory: base rates "
            f"differ {self.base_rate_ratio:.0f}x)"
        )
        head = (
            f"  fairness by {self.attribute}"
            f"   FPR spread {self.fpr_spread:.4f} (<= {self.fpr_tolerance})"
            f" | {recall_note}"
            f" | worst calib gap {self.worst_calibration_gap:.4f}"
            f" (<= {self.calibration_tolerance})   "
            f"[{'PASS' if self.passes() else 'FAIL'}]"
        )
        rows = [
            f"      {'group':<18}{'n':>8}{'pos':>7}{'flag':>7}"
            f"{'recall':>9}{'prec':>8}{'FPR':>8}{'calib gap':>11}"
        ]
        for g in sorted(self.groups, key=lambda x: x.group):
            rows.append(
                f"      {g.group:<18}{g.n:>8,}{g.positives:>7,}{g.flagged:>7,}"
                f"{g.recall:>9.3f}{g.precision:>8.3f}{g.fpr:>8.4f}"
                f"{g.calibration_gap:>+11.4f}"
            )
        return "\n".join([head, *rows])


def fairness_report(
    y: np.ndarray,
    p: np.ndarray,
    flagged: np.ndarray,
    attribute_values: np.ndarray,
    attribute: str,
    min_group_n: int = 200,
) -> FairnessReport:
    rep = FairnessReport(attribute=attribute)
    for value in sorted({str(v) for v in attribute_values if v is not None and str(v) != "nan"}):
        m = np.asarray([str(v) == value for v in attribute_values])
        if m.sum() < min_group_n:
            continue
        yg, pg, fg = y[m], p[m], flagged[m]
        pos, neg = yg.sum(), (1 - yg).sum()
        tp = int((fg & (yg == 1)).sum())
        fp = int((fg & (yg == 0)).sum())
        fn = int((~fg & (yg == 1)).sum())
        rep.groups.append(
            GroupMetrics(
                group=value,
                n=int(m.sum()),
                positives=int(pos),
                flagged=int(fg.sum()),
                fpr=float(fp / neg) if neg else float("nan"),
                fnr=float(fn / pos) if pos else float("nan"),
                recall=float(tp / pos) if pos else float("nan"),
                precision=float(tp / (tp + fp)) if (tp + fp) else float("nan"),
                mean_score=float(pg.mean()),
                mean_outcome=float(yg.mean()),
            )
        )
    return rep


# --------------------------------------------------------------------------


@dataclass(slots=True)
class EvalReport:
    n: int
    positives: int
    base_rate: float
    roc_auc: float
    pr_auc: float
    brier: float
    ece: float
    calibration_curve: list[tuple[float, float, int]]
    capacity_metrics: dict[str, dict[str, float]]
    fairness: list[FairnessReport] = field(default_factory=list)
    note: str = ""

    def fairness_passes(self) -> bool:
        return all(f.passes() for f in self.fairness)

    def render(self) -> str:
        lines = [
            f"  n = {self.n:,}   positives = {self.positives:,}"
            f"   base rate = {self.base_rate:.4%}",
            f"  ROC-AUC {self.roc_auc:.4f} | PR-AUC {self.pr_auc:.4f}"
            f" | Brier {self.brier:.6f} | ECE {self.ece:.5f}",
            "",
            f"      {'capacity':<14}{'precision':>11}{'recall':>9}{'lift':>8}",
        ]
        for name, m in self.capacity_metrics.items():
            lines.append(
                f"      {name:<14}{m['precision']:>11.4f}{m['recall']:>9.4f}"
                f"{m['lift']:>8.2f}x"
            )
        lines.append("")
        lines.append("      calibration (equal-count deciles, predicted -> observed)")
        for conf, acc, cnt in self.calibration_curve:
            bar = "#" * min(int(acc * 400), 40)
            lines.append(f"        {conf:>8.4f} -> {acc:>8.4f}  (n={cnt:>6,})  {bar}")
        if self.fairness:
            lines.append("")
            for f in self.fairness:
                lines.append(f.render())
                lines.append("")
        if self.note:
            lines.append(f"  note: {self.note}")
        return "\n".join(lines)


def evaluate(
    y: np.ndarray,
    p: np.ndarray,
    *,
    capacities: dict[str, int] | None = None,
    protected: dict[str, np.ndarray] | None = None,
    primary_capacity: str | None = None,
    note: str = "",
) -> EvalReport:
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    n = len(y)
    pos = int(y.sum())

    if capacities is None:
        # Default capacities expressed as a share of the cohort -- a school can
        # realistically follow up 1-5% of learners in a given week.
        capacities = {
            "top 0.5%": max(1, int(0.005 * n)),
            "top 1%": max(1, int(0.01 * n)),
            "top 2%": max(1, int(0.02 * n)),
            "top 5%": max(1, int(0.05 * n)),
        }

    cap_metrics = {
        name: {
            "k": float(k),
            "precision": precision_at_k(y, p, k),
            "recall": recall_at_k(y, p, k),
            "lift": lift_at_k(y, p, k),
        }
        for name, k in capacities.items()
    }

    ece, curve = expected_calibration_error(y, p)

    rep = EvalReport(
        n=n,
        positives=pos,
        base_rate=float(y.mean()) if n else float("nan"),
        roc_auc=float(roc_auc_score(y, p)) if 0 < pos < n else float("nan"),
        pr_auc=float(average_precision_score(y, p)) if 0 < pos < n else float("nan"),
        brier=float(brier_score_loss(y, p)) if n else float("nan"),
        ece=ece,
        calibration_curve=curve,
        capacity_metrics=cap_metrics,
        note=note,
    )

    if protected:
        cap_name = primary_capacity or next(iter(capacities))
        flagged = top_k_mask(p, capacities[cap_name])
        for attr, values in protected.items():
            rep.fairness.append(
                fairness_report(y, p, flagged, np.asarray(values), attr)
            )
    return rep


__all__ = [
    "EvalReport",
    "FairnessReport",
    "GroupMetrics",
    "evaluate",
    "fairness_report",
    "precision_at_k",
    "recall_at_k",
    "lift_at_k",
    "top_k_mask",
    "expected_calibration_error",
]
