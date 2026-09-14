"""The live vehicle link: one adapter, opened per operation, one bus per session.

Read-only by construction. See ``docs/design/CUORE_LIVE_LINK_PLAN.md``.

Layers, bottom up: :mod:`stream` (serial, TCP, recording, playback),
:mod:`interlock` (MES liveness, lock file), :mod:`transport` (the
``AdapterLink`` and ``Session``), :mod:`framing` (pure parsers),
:mod:`safety` (the gates), :mod:`buses` and :mod:`addressing` (data with
confidence), :mod:`obd` and :mod:`uds` (decoders and the read-only client),
:mod:`capture` (passive listen), :mod:`ops` (what the HTTP routes and the MCP
tools call).
"""

from __future__ import annotations

from . import ops
from .errors import AdapterFault, BadCommand, LinkUnavailable, LiveError, Refused
from .transport import AdapterLink, Session, link, set_link

__all__ = ["ops", "AdapterLink", "Session", "link", "set_link", "LiveError",
           "LinkUnavailable", "Refused", "BadCommand", "AdapterFault"]
