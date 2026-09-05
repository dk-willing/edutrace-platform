"""A structural causal simulator for Ghanaian JHS attendance and attrition.

Why a structural simulator and not ``np.random.rand``
----------------------------------------------------
Drawing each column independently destroys the only thing a dropout model has
to learn: that poverty drives levy arrears and child work, that those drive
absence, that absence drives exam collapse, and that the whole chain -- not any
single column -- ends in a child leaving.  A model fitted to independent columns
learns nothing and reports a flattering AUC while doing so.

So the generator is an explicit DAG, sampled forward:

    region ─┬─▶ rural ──┬─▶ distance_band ─────────────┐
            └─▶ poverty ┤                              │
                        ├─▶ fee_arrears ───────┐       │
                        ├─▶ books / uniform ───┤       │
                        ├─▶ paid_or_farm_work ─┤       ▼
                        ├─▶ over_age ──────┐   ├──▶ weekly absence ──┐
                        └─▶ guardian_type ─┘   │        │            │
                                               │        ▼            ▼
     ability ──────────────────────────────────┴──▶ exam score ──▶ EXIT HAZARD
                                                                     ▲
     frailty (unobserved heterogeneity) ─────────────────────────────┤
     pregnancy (female, JHS2-3) ─────────────────────────────────────┘

Two deliberate design choices, both of which exist so the fairness machinery
downstream has something real to find:

1.  ``sex`` never enters the hazard directly.  It acts only through pregnancy
    (which raises exits for girls) and through paid/farm work (which raises
    exits for boys).  These pull in opposite directions and reproduce the
    observed 3% vs 2% male/female gap.  A model trained without ``sex`` should
    therefore recover most, but not all, of that gap -- and the residual is
    exactly what the fairness audit is for.

2.  Year 3 of the window carries an economic shock: levy arrears rise, and the
    coefficient linking arrears to exit strengthens.  Under a random
    train/test split this is invisible.  Under the forward-chaining temporal
    split the pipeline actually uses, it produces a visible, honest performance
    drop -- which is what happens to every deployed model and what a portfolio
    project should be able to show rather than hide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..contract import HORIZON_WEEKS, TERMS_PER_YEAR, WEEKS_PER_TERM
from .targets import REGION_DEPRIVATION, REGIONS

log = logging.getLogger(__name__)

WEEKS_PER_YEAR = WEEKS_PER_TERM * TERMS_PER_YEAR      # 42
JHS_WEEKS = WEEKS_PER_YEAR * 3                        # 126
SESSIONS_PER_WEEK = 5
GRADES = ("JHS1", "JHS2", "JHS3")
TERMS = ("T1", "T2", "T3")


# --------------------------------------------------------------------------


@dataclass(slots=True)
class SimConfig:
    n_schools: int = 20
    entrants_per_school: int = 45
    #: Academic years in which a JHS1 cohort enters.  Each cohort is followed
    #: for up to three years, so the panel spans ``first_year`` to
    #: ``first_year + n_cohorts + 1``.
    first_year: int = 2021
    n_cohorts: int = 4
    seed: int = 20260829

    #: Baseline annual exit hazard before covariates.  Tuned against
    #: ``targets.TARGETS['dropout_annual_rate']``.
    base_annual_hazard: float = 0.040
    #: Multiplier on the hazard during JHS3 Term 3 -- the transition spike.
    jhs3_exit_multiplier: float = 1.75
    #: Academic year (offset from ``first_year``) in which the economic shock
    #: lands.  Set to ``None`` to disable drift.
    shock_year_offset: int | None = 3

    #: Standard deviation of the per-student unobserved frailty.  This is the
    #: irreducible-uncertainty dial: raise it and no model can do well, which
    #: is a useful thing to be able to demonstrate.
    frailty_sd: float = 0.55

    #: Secant rounds used to land the realised annual hazard on target.
    calibration_rounds: int = 3

    def total_students(self) -> int:
        return self.n_schools * self.entrants_per_school * self.n_cohorts


@dataclass(slots=True)
class SimResult:
    panel: pd.DataFrame
    students: pd.DataFrame
    config: SimConfig
    coefficients: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Hazard coefficients (log-odds per unit).  These ARE the ground truth: any
# feature-importance plot from a model trained on this data is a readout of
# this dict, which is why the README says not to over-interpret it.
# --------------------------------------------------------------------------

BETA: dict[str, float] = {
    # Scale discipline: the spread of ``eta`` across the population should be
    # roughly 4 log-odds -- a ~50x hazard ratio between the safest and the most
    # precarious child.  The first draft of these numbers spanned 10 log-odds
    # (~22,000x), which is not a thing that happens in education data, and the
    # calibration report caught the consequence: once the intercept was pushed
    # down far enough to hit 4%/yr, only the two most extreme causes could
    # clear the bar, and pregnancy alone accounted for 82% of girls' exits.
    # Published per-predictor hazard ratios for dropout sit around 1.5x-5x,
    # which is what these encode.
    "absence_rate_4w": 1.90,        # per unit of (1 - attendance), 0..1
    "consecutive_absences": 0.075,  # per school day in the current run, capped
    "exam_z": -0.34,                # per SD of standardised exam score
    "fee_arrears": 0.28,            # per term owed, capped
    "unpaid_levies": 0.24,
    "child_work": 0.74,
    "over_age_years": 0.16,
    "distance_ord": 0.13,
    "distance_x_rainy": 0.17,
    "repeated": 0.26,
    "no_textbooks": 0.19,
    "guardian_ord": 0.10,
    "siblings_in_school": -0.05,    # protective: a household already investing
    "behaviour_serious": 0.30,
    "bece_unregistered_jhs3": 0.70,
    "pregnancy": 1.55,
}


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


def _logit(p: float) -> float:
    return float(np.log(p / (1.0 - p)))


# --------------------------------------------------------------------------


def _draw_students(cfg: SimConfig, rng: np.random.Generator) -> pd.DataFrame:
    """Sample the time-invariant layer of the DAG."""
    n_per_cohort = cfg.n_schools * cfg.entrants_per_school
    n = n_per_cohort * cfg.n_cohorts

    school_idx = np.tile(
        np.repeat(np.arange(cfg.n_schools), cfg.entrants_per_school), cfg.n_cohorts
    )
    cohort = np.repeat(np.arange(cfg.n_cohorts), n_per_cohort)
    entry_year = cfg.first_year + cohort

    # --- region: assigned per school, so region and school are collinear the
    # way they are in reality (and so a group-split by school is also a
    # region-split, which is the harder and more honest generalisation test).
    region_names = list(REGIONS.keys())
    school_region = rng.choice(region_names, size=cfg.n_schools)
    region = school_region[school_idx]
    rural_p = np.array([REGIONS[r] for r in region])
    rural = rng.random(n) < rural_p

    deprivation = np.array([REGION_DEPRIVATION[r] for r in region])

    # --- poverty quintile: latent continuous, then cut.  Rural and deprived
    # regions shift the latent down.
    ses_latent = rng.normal(0.0, 1.0, n) - 0.55 * deprivation - 0.45 * rural
    quintile = np.digitize(
        ses_latent, np.quantile(ses_latent, [0.2, 0.4, 0.6, 0.8])
    ) + 1                                    # 1 = poorest .. 5 = richest
    poverty = (6 - quintile) / 5.0           # 0.2 .. 1.0, higher = poorer

    sex = np.where(rng.random(n) < 0.495, "F", "M")

    # --- distance.  Calibrated so ~53% are within a short walk, matching the
    # 2021 PHC finding that 52.8% of residential structures are within 2km of
    # a JHS.  Rural households sit further out.
    dist_latent = rng.normal(0.0, 1.0, n) + 1.05 * rural + 0.35 * poverty
    dist_ord = np.digitize(dist_latent, [0.10, 0.95, 1.75])   # 0..3
    distance_band = np.array(
        ["UNDER_15_MIN", "M15_TO_30", "M30_TO_60", "OVER_60_MIN"]
    )[dist_ord]

    # --- over-age.  The GER/NER gap (85 vs 45) implies roughly half of enrolled
    # JHS pupils are above the official age.  Late entry and prior repetition
    # both load on poverty.
    over_age_p = _sigmoid(-1.25 + 1.9 * poverty + 0.5 * rural)
    is_over_age = rng.random(n) < over_age_p
    over_age_years = np.where(
        is_over_age, 1 + rng.poisson(0.85, n).clip(0, 4), 0
    ).astype(float)
    age_at_entry = 12.0 + over_age_years + rng.normal(0.0, 0.25, n)

    repeated = rng.random(n) < _sigmoid(-3.9 + 2.1 * poverty + 0.9 * is_over_age)

    guardian_latent = rng.random(n) + 0.45 * poverty
    guardian_ord = np.digitize(guardian_latent, [0.55, 0.95, 1.30])
    guardian_type = np.array(
        ["BOTH_PARENTS", "SINGLE_PARENT", "RELATIVE", "UNRELATED_OR_SELF"]
    )[guardian_ord]

    # Child work: strongly poverty- and rural-linked, and more common among
    # boys.  This is the pathway that makes boys' exits exceed girls'.
    work_p = _sigmoid(-2.2 + 1.9 * poverty + 0.75 * rural + 1.45 * (sex == "M"))
    child_work = rng.random(n) < work_p

    siblings = rng.poisson(1.1 + 1.3 * poverty, n).clip(0, 8)

    ability = rng.normal(0.0, 1.0, n) + 0.30 * (1.0 - poverty) - 0.18 * is_over_age
    frailty = rng.normal(0.0, cfg.frailty_sd, n)

    # Baseline propensity to attend, before any weekly shock.
    attend_latent = (
        2.35
        - 0.52 * poverty
        - 0.28 * dist_ord
        - 0.60 * child_work
        + 0.30 * (1.0 - rural.astype(float))
        + rng.normal(0.0, 0.42, n)
    )

    return pd.DataFrame(
        {
            "student_key": [f"S{i:07d}" for i in range(n)],
            "school_id": [f"SCH{j:03d}" for j in school_idx],
            "region": region,
            "rural": rural,
            "cohort": cohort,
            "entry_year": entry_year,
            "sex": sex,
            "poverty_quintile": quintile,
            "poverty": poverty,
            "distance_band": distance_band,
            "distance_ord": dist_ord.astype(float),
            "age_at_entry": age_at_entry,
            "over_age_years": over_age_years,
            "repeated_a_grade": repeated,
            "guardian_type": guardian_type,
            "guardian_ord": guardian_ord.astype(float),
            "does_paid_or_farm_work": child_work,
            "siblings_in_school": siblings.astype(float),
            "ability": ability,
            "frailty": frailty,
            "attend_latent": attend_latent,
        }
    )


# --------------------------------------------------------------------------


def _core(
    cfg: SimConfig,
    students: pd.DataFrame,
    rng: np.random.Generator,
    offset: float,
    *,
    allow_exit: bool = True,
    collect: bool = True,
) -> tuple[list[dict], np.ndarray, np.ndarray, float]:
    """The weekly loop.

    Run twice per simulation.  The first pass (``allow_exit=False``,
    ``collect=False``) exists only to measure the population mean of the
    covariate part of the linear predictor, so the second pass can be
    re-centred to hit the target annual hazard.  Without this, the intercept
    implied by ``base_annual_hazard`` is swamped by the covariate sum and every
    child leaves within a year -- which is what the first version of this file
    did, and which the calibration report caught.
    """
    n = len(students)

    poverty = students["poverty"].to_numpy()
    ability = students["ability"].to_numpy()
    frailty = students["frailty"].to_numpy()
    attend_latent = students["attend_latent"].to_numpy()
    dist_ord = students["distance_ord"].to_numpy()
    child_work = students["does_paid_or_farm_work"].to_numpy().astype(float)
    over_age = students["over_age_years"].to_numpy()
    repeated = students["repeated_a_grade"].to_numpy().astype(float)
    guardian_ord = students["guardian_ord"].to_numpy()
    siblings = students["siblings_in_school"].to_numpy()
    is_female = (students["sex"].to_numpy() == "F").astype(float)
    entry_year = students["entry_year"].to_numpy()

    # Weekly baseline hazard implied by the target annual rate.
    weekly_base = 1.0 - (1.0 - cfg.base_annual_hazard) ** (1.0 / WEEKS_PER_YEAR)
    intercept = _logit(weekly_base) - offset

    eta_sum = 0.0
    eta_count = 0

    alive = np.ones(n, dtype=bool)
    exit_week = np.full(n, -1, dtype=np.int32)
    exit_reason = np.full(n, "", dtype=object)

    # Rolling per-student state
    att_hist = np.zeros((n, 8), dtype=np.float32)      # trailing 8 weeks
    consec_abs = np.zeros(n, dtype=np.float32)
    longest_streak = np.zeros(n, dtype=np.float32)
    term_sessions = np.zeros(n, dtype=np.float32)
    term_present = np.zeros(n, dtype=np.float32)
    prior_term_rate = np.full(n, np.nan, dtype=np.float32)
    prior_year_absences = np.full(n, np.nan, dtype=np.float32)
    year_absences = np.zeros(n, dtype=np.float32)
    exam_score = np.full(n, np.nan, dtype=np.float32)
    prev_exam_score = np.full(n, np.nan, dtype=np.float32)
    behaviour_incidents = np.zeros(n, dtype=np.float32)
    health_days = np.zeros(n, dtype=np.float32)
    fee_arrears = np.zeros(n, dtype=np.float32)
    fee_status = np.full(n, "EXEMPT", dtype=object)
    has_books = np.ones(n, dtype=bool)
    has_uniform = np.ones(n, dtype=bool)
    pregnant = np.zeros(n, dtype=bool)
    bece_registered = np.zeros(n, dtype=bool)

    chunks: list[dict] = []

    for w in range(JHS_WEEKS):
        if not alive.any():
            break

        year_in_jhs = w // WEEKS_PER_YEAR                 # 0,1,2
        week_in_year = w % WEEKS_PER_YEAR
        term_idx = week_in_year // WEEKS_PER_TERM         # 0,1,2
        week_in_term = week_in_year % WEEKS_PER_TERM + 1  # 1..14
        grade = GRADES[year_in_jhs]
        term = TERMS[term_idx]
        rainy = term == "T3"
        academic_year = entry_year + year_in_jhs

        shock = (
            cfg.shock_year_offset is not None
            and np.any(academic_year == cfg.first_year + cfg.shock_year_offset)
        )
        shock_mask = (
            (academic_year == cfg.first_year + cfg.shock_year_offset)
            if cfg.shock_year_offset is not None
            else np.zeros(n, dtype=bool)
        )

        # ---- start of term bookkeeping ----------------------------------
        if week_in_term == 1:
            done = term_sessions > 0
            prior_term_rate = np.where(
                done, 100.0 * term_present / np.maximum(term_sessions, 1), prior_term_rate
            ).astype(np.float32)
            term_sessions[:] = 0.0
            term_present[:] = 0.0
            behaviour_incidents[:] = 0.0
            health_days[:] = 0.0

            # Levies are set per term.  The shock year raises arrears sharply.
            arrears_p = _sigmoid(-1.55 + 1.75 * poverty + 0.9 * shock_mask.astype(float))
            new_arrear = rng.random(n) < arrears_p
            # Arrears are whole terms owed. The first version decayed by 0.35
            # per term, which produced values like "1.6 terms owing" -- not a
            # thing a bursar's ledger can contain, and it violated the ordinal
            # declared in the contract.
            fee_arrears = np.where(
                new_arrear, fee_arrears + 1.0, np.maximum(fee_arrears - 1.0, 0.0)
            )
            fee_arrears = np.clip(fee_arrears, 0.0, 6.0)
            fee_status = np.where(
                fee_arrears >= 2.0, "UNPAID",
                np.where(fee_arrears >= 1.0, "PART_PAID",
                         np.where(poverty > 0.7, "EXEMPT", "PAID_IN_FULL")),
            ).astype(object)

            has_books = rng.random(n) > _sigmoid(-1.9 + 2.1 * poverty)
            has_uniform = rng.random(n) > _sigmoid(-2.6 + 2.4 * poverty)

            if grade == "JHS3" and term == "T3":
                bece_registered = rng.random(n) > _sigmoid(-1.35 + 1.9 * poverty + 0.55 * (fee_arrears > 0))

        if week_in_year == 0:
            prior_year_absences = np.where(w == 0, np.nan, year_absences).astype(np.float32)
            year_absences[:] = 0.0

        # ---- pregnancy (female, JHS2 onwards) ----------------------------
        # A small weekly hazard that, once realised, drives absence sharply up
        # and exit close to certain.  This is the mechanism behind the
        # sex-linked exit pattern; sex itself never enters the hazard.
        preg_eligible = (is_female == 1.0) & alive & (~pregnant) & (year_in_jhs >= 1)
        preg_hazard = 0.00075 * (1.0 + 1.6 * poverty)
        newly_pregnant = preg_eligible & (rng.random(n) < preg_hazard)
        pregnant |= newly_pregnant

        # ---- weekly attendance -------------------------------------------
        weekly_noise = rng.normal(0.0, 0.55, n)
        p_attend = _sigmoid(
            attend_latent
            + weekly_noise
            - 0.55 * (fee_arrears > 0)
            - 0.30 * (~has_books)
            - 0.45 * rainy * dist_ord
            - 1.30 * pregnant
            - 0.22 * (week_in_term > 11)          # end-of-term drift
        )
        present = rng.binomial(SESSIONS_PER_WEEK, np.clip(p_attend, 0.01, 0.99)).astype(np.float32)
        week_rate = 100.0 * present / SESSIONS_PER_WEEK

        absent_days = SESSIONS_PER_WEEK - present
        consec_abs = np.where(present == 0, consec_abs + SESSIONS_PER_WEEK, absent_days)
        longest_streak = np.maximum(longest_streak, consec_abs)
        term_sessions += SESSIONS_PER_WEEK
        term_present += present
        year_absences += absent_days

        att_hist = np.roll(att_hist, -1, axis=1)
        att_hist[:, -1] = week_rate

        att_ttd = 100.0 * term_present / np.maximum(term_sessions, 1.0)
        win = min(4, week_in_term)
        att_4w = att_hist[:, -win:].mean(axis=1)

        # OLS slope over the trailing window -- computed with the SAME formula
        # as ``edutrace.features.attendance_trend``, vectorised.  The first
        # version of this file emitted a two-point slope here while the feature
        # builder computed a least-squares one, which is train/serve skew of
        # the exact kind the shared feature module exists to prevent.  It cost
        # a high-risk test profile roughly ten percentiles of rank, and nothing
        # failed.  ``tests/test_no_train_serve_skew.py`` now asserts equality.
        if win >= 2:
            xs = np.arange(win, dtype=np.float64)
            xs -= xs.mean()
            att_trend = (att_hist[:, -win:] * xs).sum(axis=1) / float((xs * xs).sum())
        else:
            att_trend = np.full(n, np.nan, dtype=np.float64)

        # Illness accounts for part of absence; recorded separately because
        # schools do record it and because it changes what a teacher should do.
        health_flag = rng.random(n) < 0.06
        health_days += np.where(health_flag, np.minimum(absent_days, 3.0), 0.0)

        behaviour_incidents += (
            rng.random(n) < _sigmoid(-4.1 + 1.3 * poverty + 1.9 * (att_4w < 60) / 1.0)
        ).astype(np.float32)
        behaviour_flag = np.where(
            behaviour_incidents >= 3, "SERIOUS",
            np.where(behaviour_incidents >= 1, "MINOR", "NONE"),
        ).astype(object)

        # ---- end-of-term exam --------------------------------------------
        if week_in_term == WEEKS_PER_TERM:
            prev_exam_score = exam_score.copy()
            raw = (
                52.0
                + 9.5 * ability
                + 0.28 * (att_ttd - 80.0)
                - 3.0 * (fee_arrears > 0)
                + rng.normal(0.0, 5.5, n)
            )
            exam_score = np.clip(raw, 0.0, 100.0).astype(np.float32)

        exam_z = np.where(np.isfinite(exam_score), (exam_score - 52.0) / 10.0, 0.0)
        core_failures = np.where(
            np.isfinite(exam_score), np.clip((55.0 - exam_score) / 9.0, 0, 6).round(), np.nan
        )
        assessment_completion = np.clip(
            att_ttd - 6.0 + 4.0 * ability + rng.normal(0, 6.0, n), 0.0, 100.0
        )

        # ---- exit hazard --------------------------------------------------
        arrears_beta = BETA["fee_arrears"] * (1.45 if cfg.shock_year_offset is not None else 1.0)
        arrears_effect = np.where(shock_mask, arrears_beta, BETA["fee_arrears"]) * np.minimum(fee_arrears, 4.0)

        eta_cov = (
            frailty
            + BETA["absence_rate_4w"] * (1.0 - att_4w / 100.0)
            + BETA["consecutive_absences"] * np.minimum(consec_abs, 15.0)
            + BETA["exam_z"] * exam_z
            + arrears_effect
            + BETA["unpaid_levies"] * (fee_status == "UNPAID").astype(float)
            + BETA["child_work"] * child_work
            + BETA["over_age_years"] * over_age
            + BETA["distance_ord"] * dist_ord
            + BETA["distance_x_rainy"] * dist_ord * float(rainy)
            + BETA["repeated"] * repeated
            + BETA["no_textbooks"] * (~has_books).astype(float)
            + BETA["guardian_ord"] * guardian_ord
            + BETA["siblings_in_school"] * siblings
            + BETA["behaviour_serious"] * (behaviour_flag == "SERIOUS").astype(float)
            + BETA["pregnancy"] * pregnant
        )
        if grade == "JHS3":
            eta_cov = eta_cov + np.log(cfg.jhs3_exit_multiplier) * (
                1.0 if term == "T3" else 0.30
            )
            if term == "T3":
                eta_cov = eta_cov + BETA["bece_unregistered_jhs3"] * (
                    ~bece_registered
                ).astype(float)

        if alive.any():
            # Accumulate on the HAZARD scale, not the log-odds scale.  At small
            # probabilities sigmoid(x) ~ exp(x), so E[h] is driven by
            # E[exp(eta)], which Jensen puts well above exp(E[eta]).  Centring
            # on the arithmetic mean of eta -- the obvious thing to do --
            # overshot the target annual rate by 5x.
            eta_sum += float(np.exp(np.clip(eta_cov[alive], -30.0, 30.0)).sum())
            eta_count += int(alive.sum())

        h = _sigmoid(intercept + eta_cov)
        exits = alive & (rng.random(n) < h) if allow_exit else np.zeros(n, dtype=bool)

        # ---- emit the row (before applying the exit, so the row describes a
        # student who was present and enrolled at scoring time) --------------
        idx = np.flatnonzero(alive) if collect else np.empty(0, dtype=np.int64)
        if idx.size:
            chunks.append(
                {
                    "student_key": students["student_key"].to_numpy()[idx],
                    "school_id": students["school_id"].to_numpy()[idx],
                    "academic_year": academic_year[idx],
                    "term": np.full(idx.size, term),
                    "week": np.full(idx.size, week_in_term, dtype=np.int16),
                    "career_week": np.full(idx.size, w, dtype=np.int16),
                    "grade_level": np.full(idx.size, grade),
                    "attendance_rate_term_to_date": att_ttd[idx],
                    "attendance_rate_last_4w": att_4w[idx],
                    "attendance_trend_4w": att_trend[idx],
                    "consecutive_absences": consec_abs[idx],
                    "longest_absence_streak_term": longest_streak[idx],
                    "absences_prior_year": prior_year_absences[idx],
                    "attendance_rate_prior_term": prior_term_rate[idx],
                    "avg_exam_score": exam_score[idx],
                    "avg_exam_score_prev_term": prev_exam_score[idx],
                    "assessment_completion_rate": assessment_completion[idx],
                    "core_subject_failures": core_failures[idx],
                    "age_years": (students["age_at_entry"].to_numpy()[idx] + year_in_jhs),
                    "repeated_a_grade": repeated[idx].astype(bool),
                    "school_transfers_count": np.zeros(idx.size),
                    "bece_registered": bece_registered[idx],
                    "fee_status": fee_status[idx],
                    "fee_arrears_terms": fee_arrears[idx],
                    "has_textbooks": has_books[idx],
                    "has_uniform": has_uniform[idx],
                    "siblings_in_school": siblings[idx],
                    "does_paid_or_farm_work": child_work[idx].astype(bool),
                    "guardian_type": students["guardian_type"].to_numpy()[idx],
                    "distance_band": students["distance_band"].to_numpy()[idx],
                    "behaviour_flag": behaviour_flag[idx],
                    "behaviour_incidents_term": behaviour_incidents[idx],
                    "health_absence_days_term": health_days[idx],
                    "sex": students["sex"].to_numpy()[idx],
                    "region": students["region"].to_numpy()[idx],
                    "poverty_quintile": students["poverty_quintile"].to_numpy()[idx],
                }
            )

        if exits.any():
            e = np.flatnonzero(exits)
            exit_week[e] = w
            exit_reason[e] = np.where(
                pregnant[e], "pregnancy",
                np.where(fee_arrears[e] >= 2, "cost",
                         np.where(child_work[e] == 1.0, "work",
                                  np.where(att_4w[e] < 55, "disengagement", "other"))),
            )
            alive[e] = False

    log_mean_exp_eta = float(np.log(max(eta_sum / max(eta_count, 1), 1e-12)))
    return chunks, exit_week, exit_reason, log_mean_exp_eta


def simulate(cfg: SimConfig | None = None) -> SimResult:
    """Run the simulation and return a weekly panel plus the student table.

    Two passes.  The first disables exits and records the mean covariate
    linear predictor; the second re-centres the intercept by that mean so the
    realised annual hazard matches ``cfg.base_annual_hazard``.  Both passes use
    independently seeded generators so the calibration pass cannot leak its
    random draws into the data pass.
    """
    cfg = cfg or SimConfig()
    students = _draw_students(cfg, np.random.default_rng(cfg.seed))

    def annual_rate(exit_week: np.ndarray) -> float:
        observed = np.where(exit_week >= 0, exit_week, JHS_WEEKS).sum() / WEEKS_PER_YEAR
        return float((exit_week >= 0).sum() / max(observed, 1e-9))

    # Pass 1: measure E[exp(eta)] with exits disabled.  Cheap -- no row
    # collection, no DataFrame building.
    _, _, _, offset = _core(
        cfg, students, np.random.default_rng(cfg.seed + 1),
        offset=0.0, allow_exit=False, collect=False,
    )

    # Passes 2..k: secant correction.  The analytic offset gets within a factor
    # of ~2; survivor selection (high-hazard students leave early, so the
    # surviving population is progressively lower-risk) accounts for the rest.
    # Each round is a full weekly loop with no row collection, which is cheap.
    for _ in range(cfg.calibration_rounds):
        _, ew, _, _ = _core(
            cfg, students, np.random.default_rng(cfg.seed + 100),
            offset=offset, allow_exit=True, collect=False,
        )
        realised = annual_rate(ew)
        if realised <= 0.0:
            break
        offset += float(np.log(realised / cfg.base_annual_hazard))

    # Final pass: generate.
    chunks, exit_week, exit_reason, _ = _core(
        cfg, students, np.random.default_rng(cfg.seed + 2),
        offset=offset, allow_exit=True, collect=True,
    )
    mean_eta = offset

    panel = pd.DataFrame({k: np.concatenate([c[k] for c in chunks]) for k in chunks[0]})
    students = students.assign(
        exit_week=exit_week,
        exit_reason=exit_reason,
        exited=exit_week >= 0,
        weeks_observed=np.where(exit_week >= 0, exit_week, JHS_WEEKS),
    )
    panel = _attach_labels(panel, students)
    log.info(
        "simulated %d students, %d panel rows, %.2f%% ever exited (eta offset %.3f)",
        len(students), len(panel), 100.0 * students["exited"].mean(), mean_eta,
    )
    return SimResult(
        panel=panel,
        students=students,
        config=cfg,
        coefficients={**BETA, "_intercept_offset": mean_eta},
    )


# --------------------------------------------------------------------------


def _attach_labels(panel: pd.DataFrame, students: pd.DataFrame) -> pd.DataFrame:
    """Discrete-time hazard label with correct administrative censoring.

    ``label`` = 1 if the student's exit falls in ``(w, w + HORIZON_WEEKS]``.

    Rows whose horizon extends past the end of observation *and* which have no
    event are **dropped**, not labelled 0.  Keeping them would teach the model
    that the last eight weeks of every child's record are safe, which is both
    false and exactly the kind of quiet leakage that produces a beautiful
    offline AUC and a useless deployed system.
    """
    exit_by_key = students.set_index("student_key")["exit_week"].to_dict()
    obs_by_key = students.set_index("student_key")["weeks_observed"].to_dict()

    ew = panel["student_key"].map(exit_by_key).to_numpy()
    ow = panel["student_key"].map(obs_by_key).to_numpy()
    w = panel["career_week"].to_numpy()

    has_event = ew >= 0
    label = has_event & (ew > w) & (ew <= w + HORIZON_WEEKS)

    horizon_end = w + HORIZON_WEEKS
    fully_observed = horizon_end <= ow
    keep = label | fully_observed

    panel = panel.assign(
        label=label.astype(np.int8),
        weeks_to_exit=np.where(has_event, ew - w, -1),
    )
    dropped = int((~keep).sum())
    if dropped:
        log.info("dropped %d administratively censored rows (%.1f%%)", dropped, 100 * dropped / len(panel))
    return panel.loc[keep].reset_index(drop=True)


__all__ = ["SimConfig", "SimResult", "simulate", "BETA", "JHS_WEEKS", "WEEKS_PER_YEAR"]
