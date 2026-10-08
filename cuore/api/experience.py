"""HTTP face of ``cuore.services.experience_bridge``: what other owners,
forums and video creators have published about a code, family or job.

Same posture as the rest of ``cuore.api``: payload shape comes from the
bridge unchanged.

Not registered on the app here -- ``app.py`` is owned by another agent. The
one line needed there (next to the other ``/api``-prefixed includes):

    ``app.include_router(experience_api.router, prefix="/api")``

(importing this module as ``from .api import experience as experience_api``,
alongside the sibling ``api`` imports.)
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends

from ..services import experience_bridge
from .deps import require_token

# Import-time side effect: registers the `experience_links` Jinja global on
# every page's template environment (see that module's docstring). Done here
# rather than in cuore/web/* directly so none of those route modules (owned
# by other agents) need to change.
from ..web import experience_globals  # noqa: F401

router = APIRouter(tags=["experience"], dependencies=[Depends(require_token)])


@router.get("/experience", summary="Others' experience: videos, threads, teardowns")
def experience(code: Optional[str] = None, family: Optional[str] = None,
               job: Optional[str] = None) -> dict[str, Any]:
    """Merged, de-duplicated, ordered links for whichever of ``code``,
    ``family`` or ``job`` are passed. See
    :func:`cuore.services.experience_bridge.links_for`."""
    return experience_bridge.links_for(code=code, family=family, job=job)


__all__ = ["router"]
