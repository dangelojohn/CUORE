"""``GET /v/{vin}/harnesses``: the nine Mopar harness diagrams placed by area on
a top view, with route in words, ends, related fuses/sensors/modules and the
parts diagram. Data: :mod:`cuore.services.harnesses`. Read-only; never contacts the car."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from . import page_search
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _search_text(h: dict) -> str:
    """The words a harness card shows: title, areas / route, ends, direction, related items, part names."""
    parts = [h.get("title"), h.get("id"), h.get("route_words"), h.get("ends"), h.get("direction")]
    for a in h.get("route") or []:
        parts += [a.get("label"), a.get("id")]
    for kind in ("fuse_boxes", "sensors", "elements"):
        for r in (h.get("related") or {}).get(kind, []):
            parts += [r.get("label"), r.get("id")]
    for dg in h.get("diagrams") or []:
        for p in dg.get("parts") or []:
            parts += [p.get("name"), p.get("description")]
    return page_search.haystack(parts)


def search_harnesses(q: str, harnesses: list) -> list:
    return [h for h in harnesses if page_search.matches(q, _search_text(h), page_search.HARNESS_SYNONYMS)]


@router.get("/v/{vin}/harnesses", response_class=HTMLResponse)
def harnesses_page(request: Request, vin: str, q: str = "") -> HTMLResponse:
    from ..services import harnesses as svc  # lazy
    dossier = _dossier(vin)
    v = svc.view(vin)
    q = page_search.clean_q(q)
    results = [{"id": h["id"], "n": h["n"], "title": h["title"], "line": h.get("route_words") or ""}
               for h in (search_harnesses(q, v["harnesses"]) if q else [])]
    response = _page(request, "harnesses.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="harnesses",
                     v=v, svg=svc.map_svg(v["harnesses"]), colour=svc.colour,
                     q=q, results=results, results_shown=results[:10], no_match_hint=page_search.HINT_HARNESSES,
                     base=f"/v/{vin}/harnesses")
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
