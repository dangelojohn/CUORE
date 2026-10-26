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

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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


def dx_ago(iso: Any) -> str:
    """'2 d ago' from an ISO timestamp; '' when there is no date."""
    try:
        secs = (datetime.now() - datetime.fromisoformat(str(iso)[:19])).total_seconds()
    except (TypeError, ValueError):
        return ""
    if secs < 0 or secs < 3600:
        return "just now" if secs < 120 else f"{int(secs // 60)} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    return f"{int(secs // 86400)} d ago"


_shared_templates.env.filters["dx_ago"] = dx_ago


@router.post("/v/{vin}/diagnosis/hypothesis/{job_id}/{hyp_id}/status", response_class=HTMLResponse,
             include_in_schema=False)
def diagnosis_set_status(vin: str, job_id: str, hyp_id: str, status: str = Form(...),
                         return_to: str = Form(default="")) -> RedirectResponse:
    """One-tap Rule out (refuted) / Confirmed through the existing hypothesis status
    API. The engine's own rules apply unchanged: a confirm without passed/failed test
    evidence (or with unresolved evidence against) is refused and its message shown."""
    from ..services import jobs_bridge
    from .jobs_routes import _rule_violation_msg
    back = return_to if return_to.startswith(f"/v/{vin}/") else f"/v/{vin}/diagnosis"
    back = back.split("#")[0].split("?")[0]
    if status not in ("refuted", "confirmed"):
        msg, mk = "Only Rule out or Confirmed can be set from here.", "err"
    else:
        try:
            jobs_bridge.set_hypothesis(job_id, hyp_id, status=status)
            msg, mk = ("Ruled out." if status == "refuted" else "Confirmed."), "ok"
        except jobs_bridge.RuleViolation as exc:
            msg, mk = _rule_violation_msg(exc), "err"
        except Exception as exc:  # noqa: BLE001 -- BridgeError / unknown ids: say so, never a 500
            msg, mk = str(exc) or "That could not be saved.", "err"
    return RedirectResponse(url=f"{back}?msg={quote(msg)}&mk={mk}#dx-suspects", status_code=303)


@router.get("/v/{vin}/diagnosis", response_class=HTMLResponse, include_in_schema=False)
def diagnosis_page(request: Request, vin: str) -> HTMLResponse:
    dossier = _dossier(vin)
    dx = diagnosis_for(vin)
    flash = (request.query_params.get("msg") or "")[:400]
    response = _page(request, "diagnosis.html", vin=vin, bar=_vehicle_bar(vin, dossier), dx=dx,
                     tab="diagnosis", dx_flash=flash,
                     dx_flash_kind="err" if request.query_params.get("mk") == "err" else "ok")
    _set_active_vehicle(response, vin)
    return response


@router.get("/api/vehicles/{vin}/diagnosis", tags=["vehicles"])
def diagnosis_json(vin: str) -> dict[str, Any]:
    """Ranked suspects (band + reasons with source ids), shared-cause sets with
    dependency paths, uncovered faults and the best next test. No percentages."""
    return suspect_ranking.diagnose(vin)
