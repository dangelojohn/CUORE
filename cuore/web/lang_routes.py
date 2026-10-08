"""POST /lang: the header language chooser's target.

A thin HTTP face over ``cuore.web.i18n``'s own ``set_lang_cookie`` -- all
the real logic (which languages are supported, what the cookie is called,
how long it lives) stays in i18n.py; this file only wires it to a route.
Same posture as every other page router here: ``require_token`` gated,
plain POST/redirect, no JavaScript needed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse

from ..api.deps import require_token
from . import i18n

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.post("/lang")
async def set_lang(lang: str = Form(...), next: str = Form(default="/")) -> RedirectResponse:
    """Set the ``lang`` cookie and redirect back to wherever the chooser
    was submitted from. ``next`` is trusted only as a same-site path --
    anything not starting with ``/`` falls back to ``/`` rather than
    letting this become an open redirect."""
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    response = RedirectResponse(url=safe_next, status_code=303)
    return i18n.set_lang_cookie(response, lang)


__all__ = ["router"]
