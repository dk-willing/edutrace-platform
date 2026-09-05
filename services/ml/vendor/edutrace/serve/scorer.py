"""The scoring engine.  Everything latency-sensitive lives here.

Hot-path budget, per single-student request:

    feature build (pure numpy, no DataFrame)     ~0.02 ms
    inplace_predict, nthread=1                   ~0.7  ms
    TreeSHAP pred_contribs, depth 6              ~2-8  ms
    recourse bisection (2 levers x 18 probes)    ~5-12 ms
    narrative assembly                           ~0.05 ms
    ------------------------------------------------------
    total                                        ~10-20 ms

Two choices that account for most of that.

``inplace_predict`` over ``DMatrix`` + ``predict``: DMatrix construction is
historically 45-90% of predict time, and on a single row the measured gap is
roughly 1.9 ms versus 0.7 ms.

``nthread=1``: on a 1-row batch, thread coordination costs more than the work.
Per-request latency is the objective; batch scoring gets its own path that lets
XGBoost use every core.

Recourse is the most expensive component and is therefore computed only for
tiers at or above ELEVATED -- for a LOW-tier learner there is nothing to
recommend, and paying 10 ms to discover that is waste.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..contract import FEATURE_COUNT, HORIZON_WEEKS, RiskTier, contract_fingerprint
from ..contract import FEATURE_ORDER
from ..explain import attribution as attr
from ..explain import narrative
from ..explain.recourse import find_recourse
from ..features import build_frame, build_row
from ..records import RiskAssessment, StudentObservation
from ..train.model import ModelBundle

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ScorerSettings:
    explain_from_tier: RiskTier = RiskTier.WATCH
    recourse_from_tier: RiskTier = RiskTier.ELEVATED
    max_raising_drivers: int = 3
    max_lowering_drivers: int = 2
    max_recourse_steps: int = 2

    #: Tiers at or above this require a named member of staff to review before
    #: any contact with a guardian. Ghana's Data Protection Act 2012 s.41 gives
    #: a data subject the right to object to a significant decision taken
    #: solely by automatic means; a dropout flag that triggers an SMS home is
    #: exactly that. The gate is a legal control, not a UX preference.
    review_required_from_tier: RiskTier = RiskTier.WATCH


_TIER_RANK = {
    RiskTier.LOW: 0,
    RiskTier.WATCH: 1,
    RiskTier.ELEVATED: 2,
    RiskTier.HIGH: 3,
}


class Scorer:
    def __init__(self, bundle: ModelBundle, settings: ScorerSettings | None = None):
        self.bundle = bundle
        self.settings = settings or ScorerSettings()
        self._fingerprint = contract_fingerprint()
        # Precomputed once: the raw margin equivalent of the WATCH threshold,
        # so the recourse search never touches the quantised isotonic output.
        # Recourse aims one tier DOWN from wherever the learner sits, not at
        # LOW. Asking a HIGH learner's card what would reach the WATCH
        # threshold produces "no single change would help" every time --
        # accurate, useless, and demoralising. Moving HIGH -> ELEVATED is a
        # reachable outcome that changes what the school does this week.
        t = bundle.thresholds
        self._raw_target_for_tier = {
            RiskTier.HIGH: bundle.raw_for_probability(t.elevated),
            RiskTier.ELEVATED: bundle.raw_for_probability(t.watch),
            RiskTier.WATCH: bundle.raw_for_probability(t.watch * 0.5),
        }
        # Warm the booster: the first inplace_predict pays one-off setup that
        # would otherwise land on a real user's request.
        self.bundle.predict(np.zeros((1, FEATURE_COUNT), dtype=np.float32))

    # -- helpers ---------------------------------------------------------

    def _at_least(self, tier: RiskTier, floor: RiskTier) -> bool:
        return _TIER_RANK[tier] >= _TIER_RANK[floor]

    def _raw(self, x: np.ndarray) -> float:
        return float(self.bundle.raw_score(x.reshape(1, -1))[0])

    # -- single ----------------------------------------------------------

    def score(self, obs: StudentObservation, explain: bool = True) -> RiskAssessment:
        t0 = time.perf_counter()
        x = build_row(obs, self.bundle.norm_context)
        p = float(self.bundle.predict(x)[0])
        tier = self.bundle.tier(p)

        raising: list = []
        lowering: list = []
        steps: list = []

        if explain and self._at_least(tier, self.settings.explain_from_tier):
            contribs = self.bundle.contributions(x)[0]
            a = attr.attribute(contribs)
            raising, lowering = attr.drivers(
                a,
                values=x[0],
                max_raising=self.settings.max_raising_drivers,
                max_lowering=self.settings.max_lowering_drivers,
            )
            if self._at_least(tier, self.settings.recourse_from_tier):
                steps = find_recourse(
                    x[0],
                    self._raw,
                    target=self._raw_target_for_tier[tier],
                    max_steps=self.settings.max_recourse_steps,
                    to_probability=self.bundle.probability_of_raw,
                )

        text = narrative.compose(tier, p, raising, lowering, steps, HORIZON_WEEKS)

        return RiskAssessment(
            observation_id=obs.observation_id,
            student_key=obs.student_key,
            school_id=obs.school_id,
            risk=p,
            tier=tier,
            drivers=raising,
            protective=lowering,
            recourse=steps,
            narrative=text,
            model_version=self.bundle.card.version,
            contract_fingerprint=self._fingerprint,
            requires_human_review=self._at_least(
                tier, self.settings.review_required_from_tier
            ),
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )

    def score_vector(
        self,
        x: np.ndarray,
        *,
        observation_id: str = "vector",
        student_key: str = "vector",
        school_id: str = "vector",
        explain: bool = True,
    ) -> RiskAssessment:
        """Score a prebuilt feature vector, bypassing ``StudentObservation``.

        The validated-record path is deliberately domain-locked: JHS1-3, ages
        8-25, Ghanaian academic years. That guard is worth keeping -- it is what
        stops a caller posting arbitrary data at a model trained for schools.

        But it also, correctly, rejects the OULAD validation panel, whose
        learners are UK adults on lettered course modules. Rather than loosen
        the guard to admit them, this path takes a vector that has already been
        built by ``build_frame`` (the same route batch scoring uses) and runs
        the full explanation stack on it. Used for cross-domain validation and
        for batch rows; the single-learner API keeps its validation.
        """
        t0 = time.perf_counter()
        x = np.asarray(x, dtype=np.float32).reshape(1, -1)
        p = float(self.bundle.predict(x)[0])
        tier = self.bundle.tier(p)

        raising: list = []
        lowering: list = []
        steps: list = []
        if explain and self._at_least(tier, self.settings.explain_from_tier):
            a = attr.attribute(self.bundle.contributions(x)[0])
            raising, lowering = attr.drivers(
                a, values=x[0],
                max_raising=self.settings.max_raising_drivers,
                max_lowering=self.settings.max_lowering_drivers,
            )
            if self._at_least(tier, self.settings.recourse_from_tier):
                steps = find_recourse(
                    x[0], self._raw,
                    target=self._raw_target_for_tier[tier],
                    max_steps=self.settings.max_recourse_steps,
                    to_probability=self.bundle.probability_of_raw,
                )

        return RiskAssessment(
            observation_id=observation_id,
            student_key=student_key,
            school_id=school_id,
            risk=p,
            tier=tier,
            drivers=raising,
            protective=lowering,
            recourse=steps,
            narrative=narrative.compose(tier, p, raising, lowering, steps, HORIZON_WEEKS),
            model_version=self.bundle.card.version,
            contract_fingerprint=self._fingerprint,
            requires_human_review=self._at_least(
                tier, self.settings.review_required_from_tier
            ),
            latency_ms=(time.perf_counter() - t0) * 1000.0,
        )

    # -- batch -----------------------------------------------------------

    def score_frame(
        self, df: pd.DataFrame, explain_top_k: int | None = None
    ) -> tuple[np.ndarray, np.ndarray, list[RiskAssessment]]:
        """Score a whole CSV.

        Scores every row with the multithreaded vectorised path, then computes
        full explanations only for the top ``explain_top_k``.  Explaining
        10,000 rows would cost ~30 s in TreeSHAP alone, and a school is never
        going to read 10,000 explanations -- it is going to read the ones it has
        capacity to act on.
        """
        X = build_frame(df, self.bundle.norm_context)
        self.bundle.booster.set_param({"nthread": 0})  # all cores for the bulk pass
        try:
            p = self.bundle.predict(X)
        finally:
            self.bundle.booster.set_param({"nthread": 1})

        tiers = np.array([self.bundle.tier(v).value for v in p], dtype=object)

        assessments: list[RiskAssessment] = []
        if explain_top_k:
            k = min(explain_top_k, len(p))
            top = np.argpartition(-p, k - 1)[:k]
            top = top[np.argsort(-p[top])]
            for i in top:
                row = df.iloc[int(i)]
                obs = _row_to_observation(row)
                assessments.append(self.score(obs, explain=True))
        return p, tiers, assessments


def _row_to_observation(row: pd.Series) -> StudentObservation:
    """Coerce a CSV row into a validated observation.

    Unknown columns are dropped rather than rejected: real school exports carry
    ten columns nobody remembers adding, and failing a whole upload over one of
    them is not a defensible product decision.
    """
    fields = set(StudentObservation.model_fields)
    data: dict = {}
    for key, value in row.items():
        if key not in fields:
            continue
        # `isinstance(v, float)` is NOT enough: pandas hands back np.float32 /
        # np.float64, which are not Python floats, so a NaN sails past the
        # guard and pydantic rejects it against a 0-100 bound with a confusing
        # "input should be less than or equal to 100" for a missing value.
        if value is None or (np.isscalar(value) and pd.isna(value)):
            data[key] = None
        elif isinstance(value, np.generic):
            data[key] = value.item()
        else:
            data[key] = value
    return StudentObservation.model_validate(data)


__all__ = ["Scorer", "ScorerSettings"]
