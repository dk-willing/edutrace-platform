"""SMS provider adapters. Console is the default; local aggregators are opt-in."""

from .base import DeliveryResult, SmsProvider
from .console import ConsoleProvider

__all__ = ["DeliveryResult", "SmsProvider", "ConsoleProvider"]


def get_provider(name: str = "console", **kwargs) -> SmsProvider:
    """Factory. Live providers must be named explicitly in configuration."""
    name = (name or "console").lower()
    if name == "console":
        return ConsoleProvider(**kwargs)
    if name == "arkesel":
        from .arkesel import ArkeselProvider

        return ArkeselProvider(**kwargs)
    raise ValueError(
        f"unknown SMS provider {name!r}. Available: console, arkesel. "
        f"Add an adapter in edutrace/messaging/providers/."
    )
