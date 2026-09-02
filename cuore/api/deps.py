"""Shared route dependencies.

Auth here is a single shared token, and that is the right amount for T1 and T2:
one shop, one LAN, devices the owner controls. It exists because the moment
``host`` is widened past loopback every device on the network can read a corpus
containing customer VINs -- so there has to be *something*, and something
simple that gets used beats something proper that gets disabled.

When the token is unset, auth is off. That is safe paired with the loopback
default and is checked at startup, which warns if the two disagree.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Query, Request

from ..config import Settings


def settings_of(request: Request) -> Settings:
    """The live settings object, stashed on app state at startup."""
    return request.app.state.settings


async def require_token(
    request: Request,
    x_cuore_token: str | None = Header(default=None),
    token: str | None = Query(default=None,
                              description="Alternative to the header, for "
                                          "links opened on a tablet."),
) -> None:
    """Reject the request unless it carries the configured token.

    A no-op when no token is configured. Compared with
    :func:`hmac.compare_digest` so a wrong guess takes the same time as a
    right one.
    """
    expected = settings_of(request).token.strip()
    if not expected:
        return
    offered = (x_cuore_token or token or "").strip()
    if not offered or not hmac.compare_digest(offered, expected):
        raise HTTPException(
            status_code=401,
            detail="missing or incorrect token",
            headers={"WWW-Authenticate": "Token"},
        )
