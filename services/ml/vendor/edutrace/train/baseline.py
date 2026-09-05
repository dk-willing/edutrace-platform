"""The ABC baseline the model has to beat.

Attendance / Behaviour / Course performance is the framework behind Chicago's
Freshman On-Track indicator and the Everyone Graduates Center early-warning
manual, and it is a transparent rule, not a model.  Two findings make it the
right benchmark rather than a courtesy comparison:

* Chicago found course attendance roughly eight times more predictive of course
  failure than incoming test scores, and the on-track *rule* -- not a model --
  drove system-wide graduation gains.
* The REL Mid-Atlantic / Mathematica study in Pittsburgh built an ML risk model
  with in-school data plus county child-welfare and justice records, and found
  it "similarly accurate" to a simple prior-performance rule at matched flag
  rates.  ML pulled ahead only at a much tighter cutoff.

So the honest question is never "what AUC did we get" but "did we beat the rule
at the capacity the school actually has".  ``compare()`` answers that, and the
training CLI prints the answer whether or not it is flattering.  If the model
does not win, ship the rule: it explains itself, costs nothing to serve, and
cannot be accused of hiding a protected attribute in a hidden layer.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .evaluate import lift_at_k, precision_at_k, recall_at_k


@dataclass(frozen=True, slots=True)
class ABCThresholds:
    attendance_pct: float = 85.0
    consecutive_absences: int = 3
    core_failures: int = 1
    behaviour_incidents: int = 2


def abc_score(df: pd.DataFrame, t: ABCThresholds | None = None) -> np.ndarray:
    """Count of tripped ABC flags, plus a small continuous tie-break.

    The integer flag count is the rule as a school would run it.  The
    tie-break -- the attendance shortfall below threshold, scaled to stay
    smaller than one flag -- exists only so that ranking by this score is
    well-defined at a fixed capacity; it never changes which learners are
    flagged, only their order within a flag count.
    """
    t = t or ABCThresholds()
    att = pd.to_numeric(df.get("attendance_rate_term_to_date"), errors="coerce").to_numpy()
    streak = pd.to_numeric(df.get("consecutive_absences"), errors="coerce").to_numpy()
    fails = pd.to_numeric(df.get("core_subject_failures"), errors="coerce").to_numpy()
    behav = pd.to_numeric(df.get("behaviour_incidents_term"), errors="coerce").to_numpy()

    flags = (
        np.nan_to_num(att < t.attendance_pct, nan=0.0).astype(float)
        + np.nan_to_num(streak >= t.consecutive_absences, nan=0.0).astype(float)
        + np.nan_to_num(fails >= t.core_failures, nan=0.0).astype(float)
        + np.nan_to_num(behav >= t.behaviour_incidents, nan=0.0).astype(float)
    )
    shortfall = np.clip(t.attendance_pct - np.nan_to_num(att, nan=t.attendance_pct), 0, 100)
    return flags + 0.9 * (shortfall / 100.0)


@dataclass(slots=True)
class Comparison:
    capacity: str
    k: int
    model_precision: float
    model_recall: float
    model_lift: float
    baseline_precision: float
    baseline_recall: float
    baseline_lift: float

    @property
    def model_wins(self) -> bool:
        return self.model_recall > self.baseline_recall

    @property
    def recall_delta(self) -> float:
        return self.model_recall - self.baseline_recall


def compare(
    y: np.ndarray,
    model_scores: np.ndarray,
    baseline_scores: np.ndarray,
    capacities: dict[str, int],
) -> list[Comparison]:
    out = []
    for name, k in capacities.items():
        out.append(
            Comparison(
                capacity=name,
                k=k,
                model_precision=precision_at_k(y, model_scores, k),
                model_recall=recall_at_k(y, model_scores, k),
                model_lift=lift_at_k(y, model_scores, k),
                baseline_precision=precision_at_k(y, baseline_scores, k),
                baseline_recall=recall_at_k(y, baseline_scores, k),
                baseline_lift=lift_at_k(y, baseline_scores, k),
            )
        )
    return out


def render(comparisons: list[Comparison]) -> str:
    lines = [
        "  model vs ABC rule (attendance / behaviour / course failure)",
        f"      {'capacity':<12}{'k':>7}{'model P':>10}{'rule P':>9}"
        f"{'model R':>10}{'rule R':>9}{'ΔR':>9}  verdict",
    ]
    for c in comparisons:
        verdict = "model" if c.model_wins else "RULE WINS"
        lines.append(
            f"      {c.capacity:<12}{c.k:>7,}{c.model_precision:>10.4f}"
            f"{c.baseline_precision:>9.4f}{c.model_recall:>10.4f}"
            f"{c.baseline_recall:>9.4f}{c.recall_delta:>+9.4f}  {verdict}"
        )
    wins = sum(c.model_wins for c in comparisons)
    lines.append(
        f"      model beats the rule at {wins}/{len(comparisons)} capacities."
        + (
            ""
            if wins == len(comparisons)
            else "  Consider shipping the rule where it wins -- it is free to "
            "explain and free to serve."
        )
    )
    return "\n".join(lines)


__all__ = ["ABCThresholds", "abc_score", "Comparison", "compare", "render"]
