"""About page: GET /about (version, build, state dir, update source) and POST /about/check.

The update source is only read on GET when it is a local folder (one small file); a URL
source is only contacted when the user presses "Check now".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..live import config as live_config
from ..services import updates
from .routes import _page

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _render(request: Request, result: dict | None, note: str) -> HTMLResponse:
    info = updates.installed_info()
    return _page(request, "about.html", info=info, state=str(live_config.state_dir()),
                 source=updates.get_source(), result=result, note=note,
                 source_file=str(updates.source_path()), can_rollback=updates.has_rollback())


@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request) -> HTMLResponse:
    src = updates.get_source()
    if updates.is_local_folder(src):
        return _render(request, updates.check(src), "")
    return _render(request, None, "")


@router.post("/about/check", response_class=HTMLResponse)
def about_check(request: Request) -> HTMLResponse:
    return _render(request, updates.check(), "Checked just now.")
