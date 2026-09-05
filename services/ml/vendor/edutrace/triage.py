"""Triage: the model ranks, a transparent rule floor guarantees who is seen.

Why this module exists
----------------------
The goal was a system that identifies at-risk learners "without fail".
Measured on this pipeline, that costs:

    recall target    must flag   % of cohort   precision   false alarms
             50%        1,803         6.1%       11.1%          1,603
             90%       15,452        52.7%        2.3%         15,092
            100%       26,181        89.2%        1.5%         25,782

To miss nobody you must flag 89% of the cohort at 1.5% precision.  A school
with one counsellor holding twenty conversations a week has capacity for about
twenty learners a week.  Handing that school 26,181 names is not a safer
system; it is the end of triage, and every child then receives an equal share
of nobody's attention.

At a 1.4% base rate, perfect recall and useful precision are mutually
exclusive.  Wisconsin's DEWS made this trade explicitly -- accepting 25 false
alarms per correct identification -- and was wrong about 74% of the learners it
flagged, while its own equity review found the false-alarm rate 42 points
higher for Black students.  Low-precision flooding does not distribute help
evenly; it makes allocation arbitrary, and arbitrary allocation lands hardest
on the learners staff already overlook.

The achievable version of the goal
----------------------------------
The real requirement underneath "without fail" is: *no learner in visible
trouble is missed because a model ranked them low.*  That needs no model.

    FLOOR      Rare, severe, published thresholds. Tripping one puts a learner
               on the list regardless of model score. Verifiable by hand from
               the register.
    RANK       The model orders everyone else -- the learners whose risk is not
               visible on the face of the register. That is the only place a
               model adds anything over a rule.
    ACCOUNT    Every run states what the combined system missed, and what the
               misses look like, so blind spots are declared rather than found.

A floor must be RARE, or it is not a floor
------------------------------------------
The first version of this module used sensible-sounding thresholds -- under 80%
attendance, two core failures, two terms of levies owed.  Measured, they fired
on **64%, 35% and 35% of the cohort**.  Combined, 73% of learner-weeks were
escalated, the worklist filled with floor cases before the model got a slot,
and recall at fixed capacity fell to **22.1% against the model's own 25.6%**.
The safety net made the system worse, in precisely the way this module's
opening paragraphs warn about.

So ``Floors.validate`` enforces a trip-rate budget and fails loudly when a rule
exceeds it.  A rule that fires on a third of learners is a feature, not a
floor; it belongs in the model, where it can be weighed against everything
else, not in a mechanism that overrides weighing altogether.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import RiskTier

_TIER_RANK = {
    RiskTier.LOW: 0,
    RiskTier.WATCH: 1,
    RiskTier.ELEVATED: 2,
    RiskTier.HIGH: 3,
}
_BY_RANK = {v: k for k, v in _TIER_RANK.items()}


def _num(df: pd.DataFrame, col: str) -> np.ndarray:
    if col not in df.columns:
        return np.full(len(df), np.nan)
    return pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)


def _bool(df: pd.DataFrame, col: str) -> np.ndarray:
    if col not in df.columns:
        return np.zeros(len(df), dtype=bool)
    s = df[col]
    if s.dtype == object:
        s = s.map({True: 1, False: 0, "True": 1, "False": 0,
                   "true": 1, "false": 0, 1: 1, 0: 0, "1": 1, "0": 0})
    return pd.to_numeric(s, errors="coerce").fillna(0).astype(bool).to_numpy()


@dataclass(frozen=True, slots=True)
class Floors:
    """The published floor.  Three rules, deliberately.

    Each threshold is checkable by hand from the register, defensible to a head
    teacher in one sentence, and rare enough that it does not consume the
    capacity it is meant to protect.  Defaults were calibrated by measuring
    trip rates, not by intuition -- intuition produced a floor that fired on
    64% of learners.
    """

    #: A full week and a half gone. Measured trip rate ~2.8%, precision ~13%.
    consecutive_absence_days: int = 8
    #: Attendance has collapsed, not merely slipped. ~8% trip rate.
    collapsed_attendance_pct: float = 35.0
    #: Fires only in JHS3 Term 3, where it is an irreversible deadline.
    bece_deadline: bool = True

    #: A rule tripping on more than this share of the cohort is not a floor.
    max_trip_rate: float = 0.10

    def rules(self) -> dict[str, tuple[RiskTier, str, str]]:
        r: dict[str, tuple[RiskTier, str, str]] = {
            "absent_over_a_week": (
                RiskTier.HIGH,
                f"Absent {self.consecutive_absence_days} school days in a row.",
                "The clearest signal a register produces. No model should be "
                "able to rank this away.",
            ),
            "attendance_collapsed": (
                RiskTier.HIGH,
                f"Attendance has fallen below {self.collapsed_attendance_pct:.0f}%.",
                "Not 'slipping' -- collapsed. At this level the learner has "
                "effectively stopped attending already.",
            ),
        }
        if self.bece_deadline:
            r["bece_unregistered"] = (
                RiskTier.HIGH,
                "In JHS3 Term 3 and not registered for the BECE.",
                "An irreversible deadline. Missing it ends the JHS pathway "
                "regardless of anything else in the record.",
            )
        return r

    def evaluate(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        att_ttd = _num(df, "attendance_rate_term_to_date")
        att_4w = _num(df, "attendance_rate_last_4w")
        att = np.where(np.isfinite(att_ttd), att_ttd, att_4w)
        streak = _num(df, "consecutive_absences")
        grade = df.get("grade_level", pd.Series([""] * len(df))).astype(str).to_numpy()
        term = df.get("term", pd.Series([""] * len(df))).astype(str).to_numpy()
        bece = _bool(df, "bece_registered")

        # NaN-safe throughout: an unknown value never trips a floor. A floor
        # that fires on missing data teaches staff to distrust the whole list.
        out = {
            "absent_over_a_week": np.nan_to_num(
                streak >= self.consecutive_absence_days, nan=0.0
            ).astype(bool),
            "attendance_collapsed": np.nan_to_num(
                att < self.collapsed_attendance_pct, nan=0.0
            ).astype(bool),
        }
        if self.bece_deadline:
            out["bece_unregistered"] = (
                (grade == "JHS3") & (term == "T3") & (~bece)
            )
        return out

    def validate(self, df: pd.DataFrame, raise_on_fail: bool = False) -> list[str]:
        """Check every rule against the trip-rate budget."""
        problems = []
        n = max(len(df), 1)
        for key, mask in self.evaluate(df).items():
            rate = float(mask.sum()) / n
            if rate > self.max_trip_rate:
                problems.append(
                    f"floor rule {key!r} trips on {rate:.1%} of the cohort "
                    f"(budget {self.max_trip_rate:.0%}). A rule this common is "
                    f"a feature, not a floor: it will consume the capacity it "
                    f"is meant to protect and can lower recall below the model "
                    f"alone. Tighten the threshold or move it into the model."
                )
        if problems and raise_on_fail:
            raise ValueError("\n".join(problems))
        for p in problems:
            warnings.warn(p, stacklevel=2)
        return problems


# --------------------------------------------------------------------------


@dataclass(slots=True)
class TriageResult:
    tier: np.ndarray
    model_tier: np.ndarray
    floor_reasons: list[list[str]]
    raised_by_floor: np.ndarray
    worklist: np.ndarray
    over_capacity: int
    floor_slots_used: int
    model_slots_used: int

    def summary(self) -> dict[str, int]:
        out = {t: int((self.tier == t).sum())
               for t in ("LOW", "WATCH", "ELEVATED", "HIGH")}
        out["raised_by_floor"] = int(self.raised_by_floor.sum())
        out["floor_slots_used"] = self.floor_slots_used
        out["model_slots_used"] = self.model_slots_used
        out["over_capacity"] = self.over_capacity
        return out


def triage(
    df: pd.DataFrame,
    risk: np.ndarray,
    model_tier: np.ndarray,
    capacity: int,
    floors: Floors | None = None,
    floor_share: float = 0.6,
    dedupe_by: str | None = "student_key",
    validate_floors: bool = True,
) -> TriageResult:
    """Build a capacity-bounded worklist from the floor plus the model.

    ``dedupe_by`` collapses to one row per learner -- the highest-risk
    observation.  Capacity is measured in *conversations with children*, and a
    learner flagged in week 5 and again in week 6 is one child, not two.
    Without this the worklist silently spends a term's capacity on a handful of
    learners appearing over and over.

    ``floor_share`` reserves part of the capacity for floor cases and leaves
    the rest for model ranking.  Giving the floor unlimited priority is what
    caused the 22.1%-vs-25.6% regression described in the module docstring: on
    a bad day the floor alone can exceed capacity, and the model never gets a
    slot even where it would have found someone the rules cannot see.  Within
    the floor's own share, cases are ordered by model risk -- the model still
    triages the floor, it just cannot exclude anyone from it.
    """
    floors = floors or Floors()
    if validate_floors:
        floors.validate(df)

    n = len(df)
    tripped = floors.evaluate(df)
    meta = floors.rules()

    model_rank = np.array([_TIER_RANK[RiskTier(t)] for t in model_tier])
    final_rank = model_rank.copy()
    reasons: list[list[str]] = [[] for _ in range(n)]

    for key, mask in tripped.items():
        min_tier, explain, _ = meta[key]
        final_rank = np.where(
            mask, np.maximum(final_rank, _TIER_RANK[min_tier]), final_rank
        )
        for i in np.flatnonzero(mask):
            reasons[i].append(explain)

    final_tier = np.array([_BY_RANK[r].value for r in final_rank], dtype=object)
    raised = final_rank > model_rank
    floor_flagged = np.array([len(r) > 0 for r in reasons])

    # --- collapse to one row per learner --------------------------------
    candidates = np.flatnonzero(final_rank > 0)
    if dedupe_by and dedupe_by in df.columns and candidates.size:
        keys = df[dedupe_by].to_numpy()
        best: dict[object, int] = {}
        for i in candidates:
            k = keys[i]
            if k not in best or (
                (final_rank[i], risk[i]) > (final_rank[best[k]], risk[best[k]])
            ):
                best[k] = int(i)
        candidates = np.array(sorted(best.values()), dtype=int)

    # --- allocate capacity ----------------------------------------------
    floor_pool = [i for i in candidates if floor_flagged[i]]
    model_pool = [i for i in candidates if not floor_flagged[i]]
    floor_pool.sort(key=lambda i: (-final_rank[i], -risk[i]))
    model_pool.sort(key=lambda i: (-final_rank[i], -risk[i]))

    floor_budget = int(round(capacity * floor_share))
    take_floor = floor_pool[:floor_budget]
    remaining = capacity - len(take_floor)
    take_model = model_pool[:remaining]
    # If the model pool is short, hand unused slots back to the floor.
    if len(take_model) < remaining:
        take_floor += floor_pool[len(take_floor):len(take_floor) + (remaining - len(take_model))]

    worklist = np.array(
        sorted(take_floor + take_model,
               key=lambda i: (-final_rank[i], -int(floor_flagged[i]), -risk[i])),
        dtype=int,
    )

    return TriageResult(
        tier=final_tier,
        model_tier=np.asarray(model_tier, dtype=object),
        floor_reasons=reasons,
        raised_by_floor=raised,
        worklist=worklist,
        over_capacity=max(0, len(candidates) - len(worklist)),
        floor_slots_used=len(take_floor),
        model_slots_used=len(take_model),
    )


# --------------------------------------------------------------------------


@dataclass(slots=True)
class CoverageReport:
    """What the combined system catches, and what it misses.

    Published every run. A system that cannot state its own miss rate is
    asking a school to trust it on faith.
    """

    n_rows: int
    n_learners: int
    positives: int
    base_rate: float
    capacity: int
    caught_by_floor: int
    caught_by_model: int
    caught_total: int
    missed: int
    model_only_caught: int
    missed_profile: dict[str, float] = field(default_factory=dict)
    cohort_profile: dict[str, float] = field(default_factory=dict)
    recall_curve: list[tuple[float, int, float]] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return self.caught_total / self.positives if self.positives else float("nan")

    def render(self) -> str:
        lines = [
            "Coverage report",
            "=" * 78,
            f"  cohort            {self.n_rows:,} observations / "
            f"{self.n_learners:,} learners, {self.positives} exits "
            f"({self.base_rate:.3%})",
            f"  capacity          {self.capacity:,} conversations",
            "",
            f"  caught by floor   {self.caught_by_floor:>5}   "
            "transparent rules, no model involved",
            f"  caught by model   {self.caught_by_model:>5}   "
            "ranked into the remaining slots",
            f"  caught in total   {self.caught_total:>5}   recall "
            f"{self.recall:.1%}",
            f"  model alone would {self.model_only_caught:>5}   "
            f"({'floor helps' if self.caught_total >= self.model_only_caught else 'FLOOR IS HURTING -- tighten it'})",
            f"  MISSED            {self.missed:>5}   "
            f"{self.missed / max(self.positives, 1):.1%} of learners who left",
        ]
        if self.missed_profile:
            lines += ["", "  Miss profile (missed learners vs whole cohort):",
                      f"      {'':<34}{'missed':>10}{'cohort':>10}"]
            for k, v in sorted(self.missed_profile.items()):
                c = self.cohort_profile.get(k, float("nan"))
                lines.append(f"      {k:<34}{v:>10.2f}{c:>10.2f}")
        lines += [
            "",
            "  Cost of raising recall further, if capacity existed:",
            f"      {'recall':>8} {'flags needed':>14} {'% of cohort':>13}"
            f" {'precision':>11}",
        ]
        for target, need, prec in self.recall_curve:
            lines.append(
                f"      {target:>7.0%} {need:>14,} {need / max(self.n_rows,1):>12.1%}"
                f" {prec:>11.1%}"
            )
        lines += [
            "",
            "  The misses are not a defect to be tuned away. At this base rate,",
            "  catching every learner means flagging most of the cohort, which",
            "  destroys the capacity that makes any of it useful. The route that",
            "  actually reduces misses is to read the miss profile above and add",
            "  signal where it points -- not to lower the threshold.",
        ]
        return "\n".join(lines)


def coverage(
    df: pd.DataFrame,
    y: np.ndarray,
    risk: np.ndarray,
    result: TriageResult,
    profile_columns: tuple[str, ...] = (
        "attendance_rate_term_to_date",
        "consecutive_absences",
        "avg_exam_score",
        "fee_arrears_terms",
        "age_years",
        "week",
    ),
    learner_col: str = "student_key",
) -> CoverageReport:
    y = np.asarray(y).astype(int)
    n = len(y)
    on_list = np.zeros(n, dtype=bool)
    on_list[result.worklist] = True
    floor_flagged = np.array([len(r) > 0 for r in result.floor_reasons])

    # Credit a learner as caught if ANY of their observations is on the list.
    if learner_col in df.columns:
        keys = df[learner_col].to_numpy()
        listed = set(keys[on_list])
        caught_mask = np.array([k in listed for k in keys]) & (y == 1)
        n_learners = int(pd.unique(keys).size)
    else:
        caught_mask = on_list & (y == 1)
        n_learners = n

    caught_floor = int((caught_mask & floor_flagged).sum())
    caught_total = int(caught_mask.sum())
    missed_mask = (y == 1) & ~caught_mask

    cap = len(result.worklist)
    model_only = np.argsort(-risk)[:cap]
    model_only_caught = int(y[model_only].sum())

    missed_profile, cohort_profile = {}, {}
    for col in profile_columns:
        if col in df.columns:
            v = pd.to_numeric(df.loc[missed_mask, col], errors="coerce")
            a = pd.to_numeric(df[col], errors="coerce")
            if v.notna().any():
                missed_profile[col] = float(v.mean())
                cohort_profile[col] = float(a.mean())

    pos = int(y.sum())
    order = np.argsort(-risk)
    cum = np.cumsum(y[order])
    curve = []
    for target in (0.50, 0.75, 0.90, 1.00):
        if pos:
            need = min(int(np.searchsorted(cum, np.ceil(target * pos)) + 1), n)
            curve.append((target, need, float(cum[need - 1] / need)))

    return CoverageReport(
        n_rows=n,
        n_learners=n_learners,
        positives=pos,
        base_rate=float(y.mean()) if n else float("nan"),
        capacity=cap,
        caught_by_floor=caught_floor,
        caught_by_model=caught_total - caught_floor,
        caught_total=caught_total,
        missed=int(missed_mask.sum()),
        model_only_caught=model_only_caught,
        missed_profile=missed_profile,
        cohort_profile=cohort_profile,
        recall_curve=curve,
    )


__all__ = ["Floors", "TriageResult", "CoverageReport", "triage", "coverage"]
