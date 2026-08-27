"""MultiEcuScan log-bridge: parsing and analysis library.

This package does the real work; ``server.py`` is a thin MCP tool surface over
it. Everything here is import-safe with no MCP dependency, so the parsers can
be unit-tested and reused from scripts.
"""

from __future__ import annotations

__all__ = [
    "errors",
    "paths",
    "encoding",
    "catalog",
    "fes",
    "scan",
    "dtc",
    "analysis",
    "knowledge",
    "render",
]

__version__ = "2.0.0"
