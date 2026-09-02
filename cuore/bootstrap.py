"""Make the ``mes`` package importable, in exactly one place.

``mes-log-mcp`` contains a hyphen, so it is not itself an importable package --
the importable package is ``mes`` *inside* it. Every consumer so far has solved
that with an inline ``sys.path.insert`` (see ``web-ui/app.py``), which means the
hack is repeated wherever a new entry point appears and drifts when the layout
moves.

This module is the single place that does it. Import it before anything that
touches ``mes``; ``cuore/__main__.py`` does so first, and
``cuore.services.mes_bridge`` imports it defensively so the package also works
when driven from a test runner or an ASGI server that never ran ``__main__``.

Importing this module twice is harmless.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Repository root -- the directory holding ``mes-log-mcp``, ``obd2-mcp`` and us.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: Where the ``mes`` package lives.
MES_ROOT = REPO_ROOT / "mes-log-mcp"

#: Where the OBD-II server lives. Not imported at P1; recorded here so the P2
#: live path has one authoritative answer rather than a second copy of this.
OBD_ROOT = REPO_ROOT / "obd2-mcp"


def ensure_paths() -> None:
    """Put ``mes-log-mcp`` on ``sys.path`` if it is not already there."""
    target = str(MES_ROOT)
    if target not in sys.path:
        sys.path.insert(0, target)


ensure_paths()
