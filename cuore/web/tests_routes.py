"""``GET /v/{vin}/tests`` -- the shop-floor Tests surface.

Same posture as ``cuore/web/liveboard_routes.py``: a second router reusing
``cuore.web.routes``'s own ``_page``/``_dossier``/``_vehicle_bar`` helpers,
so rendering stays identical to every other ``/v/{vin}`` page and this
module needs no template environment of its own -- ``static_url``/``icon``/
``t``/``experience_links`` are already registered on that shared one
(``cuore.web.static_version``/``icons``/``i18n``/``experience_globals``,
wired in once by ``cuore.app``'s own import list).

Unlike the liveboard, this page keeps the normal vehicle bar/tab row
(``_vbar.html``) -- it's a catalogue to browse and work through alongside
the rest of the job, not a single-purpose cockpit view.

This module renders the page shell only. Everything the page shows
(catalogue, latest results, relevance ranking, counts) comes from
``GET /api/tests/{vin}`` (``cuore/api/tests.py`` ->
``cuore/services/tests_bridge.py``); results are posted to
``POST /api/tests/{vin}/{test_id}/result`` from ``cuore/web/static/tests.js``,
with a plain HTML form fallback (see ``tests.html``) for no-JS.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..services import tests_bridge
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

#: Server-rendered page: same posture as ``cuore.web.routes.router`` and
#: ``cuore.web.liveboard_routes.router``.
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


@router.get("/v/{vin}/tests", response_class=HTMLResponse)
def tests_page(request: Request, vin: str) -> HTMLResponse:
    """The Tests catalogue: summary strip, filter chips, every test as a
    row with its latest result and a PASS/FAIL/Inconclusive/Not possible
    result form."""
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    view = tests_bridge.build_tests_view(vin)
    response = _page(request, "tests.html", vin=vin, bar=bar, tab="tests", view=view)
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/tests/{test_id}/result", response_class=HTMLResponse)
def tests_result_form(request: Request, vin: str, test_id: str,
                      result: str = Form(...), value: str = Form(""),
                      unit: str = Form(""), reason: str = Form(""),
                      hypothesis_id: str = Form(""), supports: str = Form("for"),
                      by: str = Form("")) -> HTMLResponse:
    """No-JS fallback for the result form: plain POST/redirect back to the
    same row, same contract as every other form-degrades-with-no-JS route
    in this package (e.g. ``/v/{vin}/dealer``, ``/v/{vin}/notes``)."""
    val = float(value) if value.strip() else None
    tests_bridge.record_result(vin, test_id, result or None, reason=reason, value=val,
                               unit=unit, hypothesis_id=hypothesis_id or None,
                               supports=supports or "for", by=by)
    return RedirectResponse(url=f"/v/{vin}/tests#test-{test_id}", status_code=303)


__all__ = ["router"]
