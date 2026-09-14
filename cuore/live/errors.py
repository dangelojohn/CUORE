"""Errors raised by the live link, mapped onto HTTP by the app's handlers.

They subclass :class:`cuore.services.errors.BridgeError` so the existing
exception handler renders them as the uniform ``ErrorBody`` with the right
status. The MCP adapter catches the same classes and returns ``{"error": ...}``
JSON instead.
"""

from __future__ import annotations

from ..services.errors import BridgeError


class LiveError(BridgeError):
    """Base for everything the live link refuses or cannot do."""

    status = 503


class LinkUnavailable(LiveError):
    """No port, port busy, MES holds the adapter, or the adapter did not answer."""

    status = 503


class Refused(LiveError):
    """A safety rule blocked the request before it reached the adapter."""

    status = 403


class BadCommand(LiveError):
    """Caller input is malformed: bad PID, bad hex, unknown module, bad cable."""

    status = 400


class AdapterFault(LiveError):
    """The adapter or bus reported an error mid-operation (BUS ERROR, TIMEOUT...)."""

    status = 502
