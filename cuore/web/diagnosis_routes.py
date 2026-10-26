"""Diagnosis view: shared-cause finder + ranked suspects + best next test.

    GET /v/{vin}/diagnosis             full page
    GET /api/vehicles/{vin}/diagnosis  the same data as JSON

Reads saved data only; nothing here opens the adapter or writes any state.
Plain ``def`` handlers (FastAPI runs them in the thread pool).

Registered in app.py with:
    from .web import diagnosis_routes
    app.include_router(diagnosis_routes.router)

Embedding on other pages: this module registers the Jinja global
``diagnosis_for(vin)`` on the shared template environment, so any template can do

    {% set dx = diagnosis_for(vin) %}{% include "_diagnosis_panel.html" %}
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import suspect_ranking
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar
from .routes import templates as _shared_templates

router = APIRouter(dependencies=[Depends(require_token)])


def diagnosis_for(vin: str) -> dict[str, Any]:
    """Jinja global used by ``_diagnosis_panel.html``. Never raises: a broken
    input becomes ``{"error": ...}`` and the panel says so instead of a 500."""
    try:
        return suspect_ranking.diagnose(vin)
    except Exception as exc:  # noqa: BLE001 -- an embedded panel must never sink its host page
        return {"error": f"{type(exc).__name__}: {exc}", "suspects": [], "next_test": None,
                "common_cause": {"sets": [], "partial": [], "uncovered": [], "faults": [],
                                 "n_faults": 0, "n_covered": 0}, "call": "", "weights": []}


_shared_templates.env.globals["diagnosis_for"] = diagnosis_for


@router.get("/v/{vin}/diagnosis", response_class=HTMLResponse, include_in_schema=False)
def diagnosis_page(request: Request, vin: str) -> HTMLResponse:
    dossier = _dossier(vin)
    dx = diagnosis_for(vin)
    response = _page(request, "diagnosis.html", vin=vin, bar=_vehicle_bar(vin, dossier), dx=dx,
                     tab="diagnosis")
    _set_active_vehicle(response, vin)
    return response


@router.get("/api/vehicles/{vin}/diagnosis", tags=["vehicles"])
def diagnosis_json(vin: str) -> dict[str, Any]:
    """Ranked suspects (band + reasons with source ids), shared-cause sets with
    dependency paths, uncovered faults and the best next test. No percentages."""
    return suspect_ranking.diagnose(vin)
