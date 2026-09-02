"""Transport-neutral errors the routers map onto HTTP status codes.

The bridge raises these instead of returning ``{"error": ...}`` dicts, so a
missing vehicle is a 404 rather than a 200 carrying a failure the caller has to
notice. The exception is content that is *informative* even when it reports no
result -- ``fault_tree`` on codes no tree covers returns the list of trees that
do exist, and that is a successful answer to a reasonable question.
"""

from __future__ import annotations


class BridgeError(Exception):
    """Base for anything the service layer refuses to do."""

    status = 400


class NotFound(BridgeError):
    """The vehicle, log, code or recording does not exist in the corpus."""

    status = 404


class BadRequest(BridgeError):
    """Caller-supplied input is malformed, unsafe, or out of range."""

    status = 400


class Unavailable(BridgeError):
    """A real capability this profile does not have."""

    status = 503
