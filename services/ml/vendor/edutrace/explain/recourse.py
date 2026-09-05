"""Counterfactual recourse: what would actually have to change.

SHAP says which features the model leaned on.  It does not say what to do, and
the gap between those two things is where early-warning systems fail in
practice.  Peru's Alerta Escuela is the cautionary case: a national ML system
where only 7% of schools with flagged students ever opened the platform, 2%
downloaded the guidance, and an SMS campaign that raised platform *use*
produced no increase in preventive action and no reduction in dropout.
Principals could see a risk score and could not see a next step.

So every elevated assessment ships with a recourse step: the smallest coherent
change that would move this learner down a tier.

Three design decisions, each of which the first draft got wrong and the data
caught.

**Search the raw margin, not the calibrated probability.**  Isotonic regression
is a step function, and at a sub-1% base rate its upper region is a few very
wide plateaus.  Bisecting on calibrated output reported that lifting a
learner's four-week attendance from 30% to 70% changed the risk by exactly
nothing -- not because the model is indifferent, but because both values land
on the same isotonic step.  The calibrator is monotone, so thresholding the raw
margin at ``calibrator⁻¹(target)`` is equivalent, and that surface is smooth.

**Move correlated features together.**  Setting ``attendance_rate_last_4w`` to
70 while ``attendance_rate_term_to_date`` stays at 20 describes a learner who
cannot exist.  The model has never seen that combination, its response there is
extrapolation, and a teacher acting on it is acting on an artefact.  So a lever
is a *bundle*: one scalar the school can actually influence, plus a coherent
propagation to every feature that would move with it.  Term-to-date attendance,
for instance, is a running mean -- lifting the last four weeks shifts it by
``4 * delta / weeks_elapsed``, which is arithmetic, not a guess.

**Aim one tier down, not at LOW.**  Targeting the WATCH threshold from a HIGH
learner asks for a change no single lever can deliver, so every card read "no
intervention would help" -- demoralising, and false.  Moving a learner from HIGH
to ELEVATED is a real, reachable outcome that changes what the school does this
week.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..contract import FEATURE_ORDER
from ..records import RecourseStep

_IX = {f: i for i, f in enumerate(FEATURE_ORDER)}


# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Lever:
    """One thing a school can influence, plus its coherent side effects.

    ``read`` extracts the current scalar; ``apply`` writes the scalar *and*
    every feature that would move with it.  ``direction`` is +1 when increasing
    the scalar should lower risk.
    """

    key: str
    label: str
    direction: int
    lo: float
    hi: float
    #: Largest change considered achievable within one term.
    max_delta: float
    read: Callable[[np.ndarray], float]
    apply: Callable[[np.ndarray, float], None]
    phrasing: str
    requires: tuple[str, ...] = ()

    def bounds(self, current: float) -> tuple[float, float]:
        if self.direction > 0:
            return current, min(self.hi, current + self.max_delta)
        return max(self.lo, current - self.max_delta), current

    def available(self, x: np.ndarray) -> bool:
        return all(np.isfinite(x[_IX[f]]) for f in self.requires if f in _IX)


def _set(x: np.ndarray, feat: str, value: float) -> None:
    i = _IX.get(feat)
    if i is not None:
        x[i] = value


def _get(x: np.ndarray, feat: str) -> float:
    i = _IX.get(feat)
    return float(x[i]) if i is not None else float("nan")


# --- attendance -----------------------------------------------------------


def _apply_attendance(x: np.ndarray, target_4w: float) -> None:
    """Lift four-week attendance to ``target_4w`` and propagate consistently."""
    cur_4w = _get(x, "attendance_rate_last_4w")
    delta = target_4w - (cur_4w if np.isfinite(cur_4w) else target_4w)
    _set(x, "attendance_rate_last_4w", target_4w)

    # Term-to-date is a running mean over `week` weeks; replacing the last four
    # weeks shifts it by 4*delta/week.
    week = _get(x, "week")
    ttd = _get(x, "attendance_rate_term_to_date")
    if np.isfinite(ttd) and np.isfinite(week) and week > 0:
        _set(
            x,
            "attendance_rate_term_to_date",
            float(np.clip(ttd + delta * min(4.0, week) / week, 0.0, 100.0)),
        )

    # A recovering learner has an improving trend and no live absence streak.
    if delta > 0:
        _set(x, "attendance_trend_4w", float(delta / 4.0))
        _set(x, "consecutive_absences", 0.0)


# --- fees -----------------------------------------------------------------


def _apply_arrears(x: np.ndarray, terms: float) -> None:
    _set(x, "fee_arrears_terms", terms)
    if terms <= 0.0:
        # Cleared arrears also clears UNPAID(3)/PART_PAID(2) standing. EXEMPT(0)
        # stays EXEMPT -- a capitation-covered learner never owed anything.
        cur = _get(x, "fee_status_ord")
        if np.isfinite(cur) and cur > 1.0:
            _set(x, "fee_status_ord", 1.0)


# --- classwork ------------------------------------------------------------


def _apply_completion(x: np.ndarray, rate: float) -> None:
    cur = _get(x, "assessment_completion_rate")
    _set(x, "assessment_completion_rate", rate)
    # Sustained submission pulls failing core subjects down with it.
    fails = _get(x, "core_subject_failures")
    if np.isfinite(fails) and np.isfinite(cur) and rate > cur:
        _set(x, "core_subject_failures", float(max(0.0, fails - (rate - cur) / 30.0)))


def _binary(feature: str):
    def apply(x: np.ndarray, v: float) -> None:
        _set(x, feature, 1.0 if v >= 0.5 else 0.0)

    return apply


LEVERS: tuple[Lever, ...] = (
    # Attendance first: the causal evidence for school-driven attendance
    # change is the strongest available. Bergman & Chan's parent text-message
    # trial cut course failures 27% and raised class attendance 12%; Rogers &
    # Feller's mailed nudges cut chronic absenteeism ~10-15% at roughly 1/50th
    # the cost of a mentor programme.
    Lever(
        key="attendance",
        label="attendance over the coming weeks",
        direction=+1, lo=0.0, hi=100.0, max_delta=35.0,
        read=lambda x: _get(x, "attendance_rate_last_4w"),
        apply=_apply_attendance,
        phrasing="get attendance over the next four weeks up from {cur:.0f}% to "
                 "about {tgt:.0f}%",
        requires=("attendance_rate_last_4w",),
    ),
    Lever(
        key="arrears",
        label="levy arrears",
        direction=-1, lo=0.0, hi=9.0, max_delta=4.0,
        read=lambda x: _get(x, "fee_arrears_terms"),
        apply=_apply_arrears,
        phrasing="clear or waive levy arrears, from {cur:.0f} terms owing to {tgt:.0f}",
        requires=("fee_arrears_terms",),
    ),
    Lever(
        key="classwork",
        label="classwork submission",
        direction=+1, lo=0.0, hi=100.0, max_delta=40.0,
        read=lambda x: _get(x, "assessment_completion_rate"),
        apply=_apply_completion,
        phrasing="bring classwork submission up from {cur:.0f}% to around {tgt:.0f}%",
        requires=("assessment_completion_rate",),
    ),
    Lever(
        key="textbooks",
        label="textbooks",
        direction=+1, lo=0.0, hi=1.0, max_delta=1.0,
        read=lambda x: _get(x, "has_textbooks"),
        apply=_binary("has_textbooks"),
        phrasing="make sure the learner has the required textbooks",
        requires=("has_textbooks",),
    ),
    Lever(
        key="uniform",
        label="uniform",
        direction=+1, lo=0.0, hi=1.0, max_delta=1.0,
        read=lambda x: _get(x, "has_uniform"),
        apply=_binary("has_uniform"),
        phrasing="resolve the uniform gap",
        requires=("has_uniform",),
    ),
    Lever(
        key="bece",
        label="BECE registration",
        direction=+1, lo=0.0, hi=1.0, max_delta=1.0,
        read=lambda x: _get(x, "bece_registered"),
        apply=_binary("bece_registered"),
        phrasing="complete BECE registration",
        requires=("bece_registered", "grade_ordinal"),
    ),
)


# --------------------------------------------------------------------------


def _bisect(
    score: Callable[[np.ndarray], float],
    x: np.ndarray,
    lever: Lever,
    lo: float,
    hi: float,
    target: float,
    iters: int = 14,
) -> tuple[float, float]:
    """Smallest scalar in [lo, hi] whose bundle brings the score to ``target``.

    The improving endpoint comes from the lever's declared ``direction``, not
    from comparing the model at the two ends.  Where the model saturates, that
    comparison is a coin flip and would report "target = current value", which
    a teacher reads as "this would not help" when the truth is "the model
    cannot distinguish at this extreme".  Domain knowledge -- more attendance
    is better -- is reliable here in a way the response surface is not.
    """
    def f(v: float) -> float:
        probe = x.copy()
        lever.apply(probe, v)
        return score(probe)

    improve_end, fail_end = (hi, lo) if lever.direction > 0 else (lo, hi)
    p_best = f(improve_end)
    if p_best > target:
        return improve_end, p_best       # even the best feasible value falls short

    a, b = fail_end, improve_end
    for _ in range(iters):
        mid = 0.5 * (a + b)
        if f(mid) <= target:
            b = mid
        else:
            a = mid
    return b, f(b)


def find_recourse(
    x: np.ndarray,
    score: Callable[[np.ndarray], float],
    target: float,
    max_steps: int = 2,
    to_probability: Callable[[float], float] | None = None,
) -> list[RecourseStep]:
    """Rank coherent single-lever interventions by how little has to change.

    ``score`` returns the **raw margin**; ``target`` is the raw value matching
    the tier boundary we are aiming to clear; ``to_probability`` converts back
    to a calibrated probability for display.
    """
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    current_raw = score(x)
    if current_raw <= target:
        return []
    current_p = to_probability(current_raw) if to_probability else current_raw

    ranked: list[tuple[float, RecourseStep]] = []
    for lever in LEVERS:
        if not lever.available(x):
            continue
        cur = lever.read(x)
        if not np.isfinite(cur):
            continue
        lo, hi = lever.bounds(cur)
        if abs(hi - lo) < 1e-9:
            continue

        tgt, raw_at = _bisect(score, x, lever, lo, hi, target)
        feasible = raw_at <= target
        p_at = to_probability(raw_at) if to_probability else raw_at
        effort = abs(tgt - cur) / max(abs(hi - lo), 1e-9)

        if feasible:
            note = lever.phrasing.format(cur=cur, tgt=tgt).capitalize() + "."
            rank = effort
        elif p_at < current_p * 0.98:
            note = (
                lever.phrasing.format(cur=cur, tgt=tgt).capitalize()
                + f". That would bring the estimate down from {current_p:.0%} to "
                f"{p_at:.0%}, but not below the review threshold on its own."
            )
            rank = 1.0 + (p_at / max(current_p, 1e-9))
        else:
            note = (
                f"Changing {lever.label} alone does not move the estimate here; "
                f"the concern is broader than any single factor."
            )
            rank = 2.0 + effort

        ranked.append(
            (
                rank,
                RecourseStep(
                    feature=lever.key,
                    label=lever.label,
                    current_value=float(cur),
                    target_value=float(tgt),
                    projected_risk=float(p_at),
                    feasible=bool(feasible),
                    note=note,
                ),
            )
        )

    ranked.sort(key=lambda t: t[0])
    return [s for _, s in ranked][:max_steps]


__all__ = ["Lever", "LEVERS", "find_recourse"]
