"""Arkesel (Ghana) adapter.

Chosen as the reference local integration: published per-message pricing
(GHS 0.0219-0.0288 with a three-month expiry, 0.025-0.031 non-expiring),
documented REST API with a sandbox, direct MTN/Telecel/AirtelTigo routes, and
credits that do not expire on the higher tier -- which matters when volume is
seasonal and clusters around term boundaries.

Sender-ID registration is a **carrier-level** step, not a regulator filing:
there is no NCA bulk-SMS licence and no regulator-run sender-ID registry, but
MTN (the largest network) does enforce pre-registration. Budget roughly two
weeks of lead time before a launch.

The HTTP call is intentionally left unimplemented here rather than stubbed with
a fake success. A provider that silently pretends to deliver is worse than one
that raises.
"""

from __future__ import annotations

import os

from .base import DeliveryResult, SmsProvider

ENDPOINT = "https://sms.arkesel.com/api/v2/sms/send"


class ArkeselProvider(SmsProvider):
    name = "arkesel"

    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or os.environ.get("ARKESEL_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError(
                "ARKESEL_API_KEY is not set. Refusing to construct a live SMS "
                "provider without credentials -- the alternative is a provider "
                "that fails at 2am on the first real send."
            )

    def send(self, to: str, text: str, sender_id: str) -> DeliveryResult:
        import httpx

        recipient = self.normalise_msisdn(to)
        if len(recipient) != 12 or not recipient.startswith("233"):
            return DeliveryResult(
                accepted=False,
                message_id=None,
                provider=self.name,
                error="recipient must be a valid Ghana mobile number",
            )
        payload = {
            "sender": sender_id,
            "message": text,
            "recipients": [recipient],
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(
                    ENDPOINT, json=payload, headers={"api-key": self.api_key}
                )
                r.raise_for_status()
                body = r.json()
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller
            return DeliveryResult(
                accepted=False, message_id=None, provider=self.name, error=str(exc)
            )

        data = (body.get("data") or [{}])[0] if isinstance(
            body.get("data"), list) else {}
        return DeliveryResult(
            accepted=str(body.get("status", "")).lower() in {"success", "ok"},
            message_id=data.get("id"),
            provider=self.name,
            raw=body,
        )
