"""Published Ghanaian statistics used to calibrate the simulator.

Every number here is sourced.  The simulator is validated by checking that the
marginals it produces land inside the tolerance bands below; if they do not,
``edutrace.simulate.validate`` fails loudly.  That is the whole point of a
structural simulator over a random one -- it is falsifiable against reality.

What this does NOT buy you
--------------------------
Matching marginals is necessary, not sufficient.  A generator can reproduce
every mean and correlation in this file while getting the *conditional* structure
wrong, so a model trained on this data learns the assumptions encoded in
``generator.py`` and nothing about Ghanaian children.  Feature importances read
back the hand-written coefficients.  Treat the resulting AUC as evidence that
the pipeline works, never as evidence that the predictor works.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    value: float
    tol: float
    source: str

    def check(self, observed: float) -> tuple[bool, str]:
        ok = abs(observed - self.value) <= self.tol
        verdict = "PASS" if ok else "FAIL"
        return ok, (
            f"[{verdict}] {self.name}: observed {observed:.4g} "
            f"vs target {self.value:.4g} +/- {self.tol:.3g}  ({self.source})"
        )


GPE_COMPACT = (
    "Ghana Partnership Compact 2023 (MoE/GPE), "
    "globalpartnership.org/node/document/download?file=document/file/2023-ghana-partnership-compact.pdf"
)
CGD_PREPARE = (
    "CGD/IEPA PREPARE nationally representative household survey, Mar 2021, "
    "cgdev.org/blog/what-happened-dropout-rates-after-covid-19-school-closures-ghana"
)
PHC_2021 = (
    "Ghana 2021 Population & Housing Census, Proximity of Residential Structures "
    "to Essential Service Facilities, Ghana Statistical Service"
)
UNICEF_GH = "UNICEF Ghana, girls' education briefs"


#: The calibration set.  ``dropout_annual_rate`` is the load-bearing one.
#:
#: Note the tension in the literature, which is real and which we resolve
#: explicitly rather than quietly: CGD/PREPARE measures ~2.0% *annual* dropout
#: among previously enrolled children across all grades, while the GPE Compact
#: reports that 33% of the KG2 2012/13 cohort never reached the 2023 BECE.  The
#: second figure spans eleven years and includes primary, so it is not 2% x 11.
#: We target a JHS-specific annual hazard of 4%, which compounds to roughly 12%
#: attrition across the three JHS years -- inside both bounds, and consistent
#: with JHS3 being the spike grade.
TARGETS: Final[tuple[Target, ...]] = (
    Target(
        "dropout_annual_rate",
        0.040,
        0.012,
        f"Bracketed by {CGD_PREPARE} (2.0%/yr all grades) and {GPE_COMPACT} "
        "(33% KG2->BECE non-completion over 11 years)",
    ),
    Target(
        "dropout_ratio_poorest_to_richest",
        9.0,
        3.5,
        f"{CGD_PREPARE}: poorest quintile 4.5% vs richest 0.5%",
    ),
    Target(
        "dropout_ratio_male_to_female",
        1.5,
        0.5,
        f"{CGD_PREPARE}: boys 3% vs girls 2%",
    ),
    Target(
        "share_over_age",
        0.53,
        0.10,
        f"{GPE_COMPACT}: JHS GER 85% vs NER 45% -- the gap is over-age enrolment",
    ),
    Target(
        "repetition_rate",
        0.105,
        0.035,
        f"{CGD_PREPARE}: repetition rose from 3.5% to 10.5% post-closures",
    ),
    Target(
        "share_within_short_walk",
        0.528,
        0.10,
        f"{PHC_2021}: 52.8% of residential structures within 2km of a JHS",
    ),
    Target(
        "jhs3_share_of_all_exits",
        0.45,
        0.15,
        f"{CGD_PREPARE}: dropout concentrates at transition grades (end of "
        "primary and JHS3)",
    ),
    Target(
        "female_exits_attributable_to_pregnancy",
        0.28,
        0.15,
        f"{UNICEF_GH}: up to a third of girls leaving school early cite pregnancy",
    ),
)


#: Official JHS ages, from the Ghana Partnership Compact 2023.
JHS_OFFICIAL_AGES: Final[dict[str, int]] = {"JHS1": 12, "JHS2": 13, "JHS3": 14}

#: Regions used by the simulator, with a rural-share prior.  Deliberately a
#: small, representative subset rather than all sixteen -- the point is to make
#: geographic disparity auditable, not to model Ghana's administrative map.
REGIONS: Final[dict[str, float]] = {
    "Greater Accra": 0.10,
    "Ashanti": 0.45,
    "Central": 0.55,
    "Northern": 0.78,
    "Savannah": 0.85,
    "Volta": 0.65,
}

#: Savannah Region had 43.2% never-attended in the 2021 PHC; the deprivation
#: multiplier below skews the poverty draw for the northern regions accordingly.
REGION_DEPRIVATION: Final[dict[str, float]] = {
    "Greater Accra": -0.85,
    "Ashanti": -0.25,
    "Central": 0.10,
    "Northern": 0.75,
    "Savannah": 1.05,
    "Volta": 0.30,
}


def summary() -> str:
    lines = ["EduTrace simulator calibration targets", "=" * 40]
    for t in TARGETS:
        lines.append(f"  {t.name:<42} {t.value:>8.4g}  +/- {t.tol:<6.3g}")
    return "\n".join(lines)


__all__ = [
    "Target",
    "TARGETS",
    "JHS_OFFICIAL_AGES",
    "REGIONS",
    "REGION_DEPRIVATION",
    "summary",
]
