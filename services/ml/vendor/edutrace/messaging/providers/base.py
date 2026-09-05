"""Provider interface.

Deliberately narrow, and abstracted from day one, because provider choice in
Ghana is an operational lever rather than a one-time decision: per-carrier rates
differ (Hubtel publishes MTN 0.0201, AirtelTigo 0.0151, Telecel 0.0303 GHS),
delivery quality differs by network, and the ability to fail over between
aggregators is worth more than any single integration.

Cost context that should decide the default: Twilio charges about $0.374 per
outbound segment to Ghana, while local aggregators sit near GHS 0.02-0.03
(~$0.002). At 500,000 alerts a year that is roughly $800 locally against
~$187,000 on global CPaaS. There is no version of this product where a global
CPaaS is the primary Ghana route; keep one configured as failover only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DeliveryResult:
    accepted: bool
    message_id: str | None
    provider: str
    segments: int | None = None
    cost_estimate: float | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class SmsProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def send(self, to: str, text: str, sender_id: str) -> DeliveryResult:
        ...

    @staticmethod
    def normalise_msisdn(msisdn: str, default_cc: str = "233") -> str:
        """Normalise to E.164 without the plus, Ghana by default.

        Ghana's NCA announced a phased ground-up SIM re-registration in March
        2026 that invalidates the 2022 exercise, so guardian numbers will churn
        harder than usual. Treat a normalisation failure as a data-quality
        signal worth surfacing to the school, not as a send-time error.
        """
        digits = "".join(ch for ch in msisdn if ch.isdigit())
        if digits.startswith("00"):
            digits = digits[2:]
        if digits.startswith("0"):
            digits = default_cc + digits[1:]
        if not digits.startswith(default_cc) and len(digits) == 9:
            digits = default_cc + digits
        return digits
