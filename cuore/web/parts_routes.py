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
from ..services import codes_call, parts_bridge
from . import page_search
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


_CONF_RANK = {"CONFIRMED": 0, "CORROBORATED": 1, "SINGLE-SOURCE": 2}
_UNKNOWN_RANK = 9
_REST_RANK = 3        # any other stated confidence: ranked after the three above, before UNKNOWN


def _rank(conf: Any) -> int:
    c = str(conf or "UNKNOWN").upper()
    return _UNKNOWN_RANK if c == "UNKNOWN" else _CONF_RANK.get(c, _REST_RANK)


_LISTS = (("oem", "OEM number", "number"), ("aftermarket", "Aftermarket", "number"),
          ("torques", "Torque", "display"))


def _shape_part(p: dict[str, Any], job_codes: set[str]) -> dict[str, Any]:
    """A copy of ``p`` for the page: UNKNOWN entries are lifted out of the card's
    tables into ``unknown`` (identical notes folded into one counted line), plus
    ``rank`` (best stated confidence), ``active`` (its related codes open on the job)."""
    out = dict(p)
    unknown: dict[str, dict[str, Any]] = {}
    ranks = []
    n_unknown = 0
    for key, label, field in _LISTS:
        keep = []
        for e in p.get(key) or []:
            ranks.append(_rank(e.get("confidence")))
            if _rank(e.get("confidence")) == _UNKNOWN_RANK:
                n_unknown += 1
                note = (e.get("note") or e.get("notes") or "").strip()
                g = unknown.setdefault(note, {"note": note, "count": 0, "labels": []})
                g["count"] += 1
                g["labels"].append(f"{label} {e.get(field) or e.get('brand') or e.get('component') or ''}".strip())
            else:
                keep.append(e)
        out[key] = keep
    out["rank"] = min(ranks) if ranks else _UNKNOWN_RANK
    out["unknown_n"] = n_unknown
    out["unknown"] = list(unknown.values())
    out["active"] = sorted(c for c in (p.get("related_codes") or []) if codes_call.base(c) in job_codes)
    out["shown_rows"] = sum(len(out[k]) for k, _l, _f in _LISTS)
    return out


def _part_text(p: dict[str, Any]) -> str:
    bits = [p.get("name"), p.get("what_it_does"), p.get("key"), p.get("location"),
            " ".join(p.get("related_jobs") or []), " ".join(p.get("related_codes") or [])]
    for k in ("oem", "aftermarket"):
        bits += [f"{e.get('number')} {e.get('brand')}" for e in p.get(k) or []]
    return page_search.haystack(bits)


def _group_by_job(rows: list[dict[str, Any]], job_codes: set[str]) -> list[dict[str, Any]]:
    """Job groups, each part once per job it belongs to (a part with two jobs
    appears in both -- the deliberate duplication ``mes.service_specs``'s torque
    rows use). Parts with no job land in a trailing "Other" group.

    Inside a group: parts tied to the open job's codes first, then by best
    confidence; parts whose every number is UNKNOWN fold into one counted
    ``unverified`` list. Groups are ordered the same way (active, confidence)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for p in rows:
        for j in (p.get("related_jobs") or [""]):
            groups.setdefault(j, []).append(_shape_part(p, job_codes))
    out = []
    for j, ps in groups.items():
        ps.sort(key=lambda p: (-len(p["active"]), p["rank"], str(p.get("name"))))
        main = [p for p in ps if p["rank"] != _UNKNOWN_RANK or p["active"]]
        out.append({"key": j, "label": _job_label(j) if j else "Other", "main": main,
                    "unverified": [p for p in ps if p not in main], "n": len(ps),
                    "active_n": sum(1 for p in ps if p["active"]),
                    "rank": min(p["rank"] for p in ps)})
    out.sort(key=lambda g: (g["key"] == "", -g["active_n"], g["rank"], g["label"]))
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
    elif page_search.clean_q(q):
        q = page_search.clean_q(q)
        rows = [p for p in parts_bridge.all_parts() if page_search.matches(q, _part_text(p), ())]
    else:
        rows = parts_bridge.all_parts()
    response = _page(request, "parts.html", vin=vin, q=q, job=job,
                     groups=_group_by_job(rows, codes_call.job_state(vin, dossier)[0]), count=len(rows),
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
