"""``GET /v/{vin}/harnesses``: the nine Mopar harness diagrams placed by area on
a top view, with route in words, ends, related fuses/sensors/modules and the
parts diagram. Data: :mod:`cuore.services.harnesses`. Read-only; never contacts the car."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from . import page_search
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

DATA = Path(__file__).resolve().parents[1] / "data"
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


def _inputs(vin: str, dossier: dict) -> tuple:
    """(codes, open symptoms, {code: description}, path_for_code, fuse items) from the car's own records. Never raises."""
    try:
        from ..services import electrical_bridge, fuse_direct as fd, mes_bridge
        codes = mes_bridge.open_codes_for(dossier)
        syms, ctext = fd.job_inputs(vin, codes, dossier)
        items = (json.loads((DATA / "fuses_stelvio_2018.json").read_text(encoding="utf-8")).get("items") or [])
        return codes, syms, ctext, electrical_bridge.path_for_code, items
    except Exception:  # noqa: BLE001
        return [], [], {}, (lambda c: {"path": []}), []


@router.get("/v/{vin}/harnesses", response_class=HTMLResponse)
def harnesses_page(request: Request, vin: str, q: str = "") -> HTMLResponse:
    from ..services import harnesses as svc  # lazy
    dossier = _dossier(vin)
    v = svc.view(vin)
    codes, syms, ctext, path_fn, items = _inputs(vin, dossier)
    d = svc.direct(vin, v["harnesses"], items, v["elem_labels"], syms, codes, ctext, path_fn)
    for h in v["harnesses"]:
        h["why"] = d["hits"].get(h["id"], [])
    linked = [h for h in v["harnesses"] if h["why"] or h["has_related"]]
    bare = [h for h in v["harnesses"] if not (h["why"] or h["has_related"])]
    linked.sort(key=lambda h: (not h["why"], h["n"]))
    q = page_search.clean_q(q)
    results = [{"id": h["id"], "n": h["n"], "title": h["title"], "line": h.get("route_words") or ""}
               for h in (search_harnesses(q, v["harnesses"]) if q else [])]
    response = _page(request, "harnesses.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="harnesses",
                     v=v, d=d, linked=linked, bare=bare, drawn_n=sum(1 for h in v["harnesses"] if not h["low"]),
                     svg=svc.map_svg(v["harnesses"]), colour=svc.colour,
                     q=q, results=results, results_shown=results[:10], no_match_hint=page_search.HINT_HARNESSES,
                     base=f"/v/{vin}/harnesses")
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
