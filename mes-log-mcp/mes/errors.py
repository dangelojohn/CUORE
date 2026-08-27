"""Exception types for the MES log bridge."""

from __future__ import annotations


class MesError(Exception):
    """Base class for all MES bridge errors."""


class MesPathError(MesError):
    """A requested path was rejected as unsafe or outside the log roots."""


class MesParseError(MesError):
    """A log file could not be parsed into the expected structure."""


class MesNotFound(MesError):
    """A requested log file does not exist in any configured root."""
