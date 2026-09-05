"""Real-data ingestion.

Two model families, two contracts, deliberately not interchangeable:

    emis       school registers  -> WEEKLY hazard panel (edutrace.contract)
    household  DHS / MICS        -> ANNUAL enrolment panel (ingest.base)
    young_lives                  -> ANNUAL enrolment panel (ingest.base)

Read ``base.py``'s docstring before choosing. The short version: only a partner
school can give you the weekly triage model; DHS/MICS give you a real Ghanaian
annual model in weeks.
"""

from .base import (
    ENROLMENT_FEATURES,
    ENROLMENT_LABEL,
    ColumnMap,
    QualityReport,
    enrolment_fingerprint,
)

__all__ = [
    "ENROLMENT_FEATURES",
    "ENROLMENT_LABEL",
    "ColumnMap",
    "QualityReport",
    "enrolment_fingerprint",
]
