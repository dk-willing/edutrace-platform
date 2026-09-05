"""Console/dry-run provider.

The default in development and in tests. Sending real SMS about real children
from a test run is a failure mode worth designing out: the production provider
must be selected explicitly by configuration, never by default.
"""

from __future__ import annotations

import logging
import uuid

from .base import DeliveryResult, SmsProvider

log = logging.getLogger(__name__)


class ConsoleProvider(SmsProvider):
    name = "console"

    def __init__(self, echo: bool = True):
        self.echo = echo
        self.outbox: list[dict] = []

    def send(self, to: str, text: str, sender_id: str) -> DeliveryResult:
        to = self.normalise_msisdn(to)
        mid = f"dry-{uuid.uuid4().hex[:12]}"
        self.outbox.append({"to": to, "text": text, "sender_id": sender_id, "id": mid})
        if self.echo:
            log.info("[DRY RUN] %s -> %s: %s", sender_id, to, text)
        return DeliveryResult(accepted=True, message_id=mid, provider=self.name)
