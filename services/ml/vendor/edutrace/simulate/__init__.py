"""Ghana-calibrated structural simulator for JHS attendance and attrition."""

from .generator import BETA, SimConfig, SimResult, simulate
from .targets import TARGETS, summary
from .validate import observed_statistics, report

__all__ = [
    "BETA",
    "SimConfig",
    "SimResult",
    "simulate",
    "TARGETS",
    "summary",
    "observed_statistics",
    "report",
]
