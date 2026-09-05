"""Outbound messaging: encoding, templates, provider adapters, dispatcher."""

from .dispatcher import Channel, Dispatcher, DispatcherSettings, MessageRejected
from .encoding import plan, prepare, transliterate
from .providers import ConsoleProvider, get_provider

__all__ = [
    "Channel", "Dispatcher", "DispatcherSettings", "MessageRejected",
    "plan", "prepare", "transliterate", "ConsoleProvider", "get_provider",
]
