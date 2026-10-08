"""``GET /v/{vin}/parts``: the parts catalog page -- search box, grouped by
job, each part rendered through ``_part_card.html``.

Same posture as ``cuore.web.dashboard_routes``/``service_routes``/
``timeline_routes`` (all built the same way, concurrently with other
agents): reuses ``_dossier``/``_page``/``_set_active_vehicle``/
``_vehicle_bar`` from :mod:`cuore.web.routes` by import rather than
duplicating that plumbing.

Registers a ``parts_for`` Jinja global the same way
:mod:`cuore.web.timeline_routes` registers ``code_feel`` -- except on *both*
``Jinja2Templates`` instances this feature's pages use: ``cuore.web.routes``'s
(for ``code.html``) and ``cuore.web.service_routes``'s, a separate instance
(for ``maintenance.html``/``oil_change.html``/``brakes_tires.html``) -- the
same two-environments wrinkle :mod:`cuore.web.experience_globals` already
documents and works around for ``experience_links``. So
``{% if parts_for is defined %}`` resolves true on every page that wants it,
whichever of those two environments rendered it.

The data contract lives in :mod:`cuore.services.parts_bridge` (``part(key)``,
``parts_for_code(code)``, ``parts_for_job(job)``, ``all_parts()``,
``search_parts(q)``), built in parallel with ``mes-log-mcp/mes/parts.py`` --
see that bridge's docstring for the fixture it falls back to until that
module lands.

Not registered on the app here -- ``app.py`` is owned by another agent
while this was built. The two lines needed there (next to the other ``web``
router imports/includes):

    ``from .web import parts_routes``
    ``app.include_router(parts_routes.router)``
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import parts_bridge
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar
from .routes import templates as _shared_templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: Human labels for the job keys parts_bridge's fixture (and, once it
#: lands, mes.parts) groups parts under -- heads each group on the page.
#: An unrecognised key just title-cases itself (see ``_job_label``).
_JOB_LABELS = {
    "oil_change": "Oil change",
    "evap_leak": "EVAP system",
    "engine_air_filter": "Engine air filter",
    "cabin_air_filter": "Cabin air filter",
    "spark_plugs": "Spark plugs",
    "brake_fluid": "Brake fluid",
    "drive_belt": "Drive belt",
    "battery_12v": "12V battery",
    "brakes_front": "Brakes, front",
    "brakes_rear": "Brakes, rear",
    "wheels": "Wheels / tyres",
    "transmission_fluid": "Transmission fluid",
    "transfer_case": "Transfer case",
}


def _job_label(job: str) -> str:
    return _JOB_LABELS.get(job, job.replace("_", " ").title())


def _media_page_exists(request: Request) -> bool:
    """Whether ``/v/{vin}/media`` is registered on this app -- lets
    ``_part_card.html`` show its "Save a photo of mine" link only once that
    page actually exists, without this module needing to know whether it
    has landed yet."""
    try:
        for r in request.app.routes:
            if getattr(r, "path", "") == "/v/{vin}/media":
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _group_by_job(rows: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """Rows grouped by each of their ``related_jobs`` (a part with two jobs
    appears in both groups -- the same deliberate duplication
    ``mes.service_specs``'s torque rows use for the same reason). Parts with
    no job land in a trailing "Other" group rather than being dropped."""
    groups: dict[str, list[dict[str, Any]]] = {}
    unassigned: list[dict[str, Any]] = []
    for p in rows:
        jobs = p.get("related_jobs") or []
        if not jobs:
            unassigned.append(p)
            continue
        for j in jobs:
            groups.setdefault(j, []).append(p)
    out = [(j, _job_label(j), groups[j]) for j in sorted(groups)]
    if unassigned:
        out.append(("", "Other", unassigned))
    return out


@router.get("/v/{vin}/parts", response_class=HTMLResponse)
def parts_page(request: Request, vin: str, q: str = "", job: str = "") -> HTMLResponse:
    """``?job=`` (from a service-hub/maintenance "Parts" link) pre-filters
    to that job instead of listing the whole catalog; ``?q=`` searches it.
    ``job`` wins if both are given -- a deep link should not be clobbered
    by whatever was last typed into the search box."""
    dossier = _dossier(vin)
    if job:
        rows = parts_bridge.parts_for_job(job)
    elif q:
        rows = parts_bridge.search_parts(q=q)
    else:
        rows = parts_bridge.all_parts()
    response = _page(request, "parts.html", vin=vin, q=q, job=job,
                     groups=_group_by_job(rows), count=len(rows),
                     bar=_vehicle_bar(vin, dossier), tab="parts",
                     media_page_exists=_media_page_exists(request))
    _set_active_vehicle(response, vin)
    return response


# --- the parts_for Jinja global ---------------------------------------------

def _parts_for(**kw: Any) -> list[dict[str, Any]]:
    """``parts_for(code=...)`` or ``parts_for(job=...)`` -- never raises, so
    a template can call it unconditionally once guarded with ``is defined``."""
    try:
        if kw.get("code"):
            return parts_bridge.parts_for_code(kw["code"])
        if kw.get("job"):
            return parts_bridge.parts_for_job(kw["job"])
    except Exception:  # noqa: BLE001 -- a template global must never 500 a page
        return []
    return []


def _register(templates: Any) -> None:
    templates.env.globals["parts_for"] = _parts_for


_register(_shared_templates)

# code.html renders through cuore.web.routes's templates (registered just
# above). maintenance.html/oil_change.html/brakes_tires.html render through
# cuore.web.service_routes's own, separate Jinja2Templates instance -- the
# same two-environments situation cuore.web.experience_globals documents
# and works around for experience_links.
try:
    from . import service_routes as _service_routes
    _register(_service_routes.templates)
except Exception:  # noqa: BLE001 -- import-time side effect, must never raise
    pass


__all__ = ["router"]
