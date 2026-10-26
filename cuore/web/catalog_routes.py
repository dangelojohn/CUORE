"""The full parts catalogue: ``/catalog`` (search, group tiles), ``/catalog/g/{group}`` (its sections and
schematics),
``/catalog/d/{diagram}`` (schematic + its parts), ``/catalog/p/{pn}`` (one part
number: every diagram it appears in, images, torque, mechanic notes, CUORE
records, TSBs, curated card) and ``/catalog/img/{name}`` (local images).

Read-only. Data: :mod:`cuore.services.parts_catalog`. The curated job parts
page (``/v/{vin}/parts``, :mod:`cuore.web.parts_routes`) links here and back.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from ..api.deps import require_token
from ..services import parts_catalog as pc
from ..services import standard_parts as sp
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _ctx(request: Request, cat) -> dict:
    vin = web_routes._active_vehicle(request)
    return {"cat": cat, "cid": cat["id"] if cat else "", "vin": vin or "", "live_strip": None, "tab": "catalog",
            "rail": pc.rail(cat) if cat else [], "standard": sp.for_vin(vin or sp.sole_vin())}


@router.get("/catalog", response_class=HTMLResponse)
def catalog_index(request: Request, q: str = "") -> Response:
    cat = pc.load()
    ctx = _ctx(request, cat)
    if not cat:
        return web_routes._page(request, "catalog_index.html", **ctx, groups=[], hits=None, spec_hits=[], q=q, stats=None)
    hits = pc.search(cat, q) if q.strip() else None
    if hits is not None and q.strip():
        pns = {h["pn"] for h in hits}
        if len(pns) == 1 and pc.norm_pn(q) == pc.norm_pn(next(iter(pns))):
            return RedirectResponse(f"/catalog/p/{next(iter(pns))}", status_code=303)
    spec_hits = pc.search_specs(cat, q) if q.strip() else []
    return web_routes._page(request, "catalog_index.html", **ctx, groups=pc.groups_view(cat),
                            hits=hits, spec_hits=spec_hits, q=q, stats=pc.stats(cat),
                            listing_hits=pc.search_listings(cat, q))


@router.get("/catalog/other", response_class=HTMLResponse)
def catalog_other(request: Request):
    cat = pc.load()
    ctx = _ctx(request, cat)
    return web_routes._page(request, "catalog_other.html", **ctx,
                            shops=pc.listings_view(cat) if cat else [])


@router.get("/catalog/g/{gid}", response_class=HTMLResponse)
def catalog_group(request: Request, gid: str) -> Response:
    cat = pc.load()
    g = pc.group(cat, gid) if cat else None
    if not g:
        return RedirectResponse("/catalog", status_code=303)
    return web_routes._page(request, "catalog_group.html", **_ctx(request, cat), g=g)


@router.get("/catalog/d/{did}", response_class=HTMLResponse)
def catalog_diagram(request: Request, did: str, all: int = 0, side: str = "", opt: str = "") -> Response:
    cat = pc.load()
    d = pc.diagram(cat, did) if cat else None
    if not d:
        return RedirectResponse("/catalog", status_code=303)
    show_all = bool(all)
    shown = [r for r in d["rows"] if (show_all or r.get("fitment") != "other-engine") and pc.row_passes(r, side, opt)]
    return web_routes._page(request, "catalog_diagram.html", **_ctx(request, cat), d=d, show_all=show_all,
                            shown=shown, side=side, opt=opt)


@router.get("/catalog/api/typeahead")
def catalog_typeahead(q: str = "") -> Response:
    cat = pc.load()
    return JSONResponse(pc.typeahead(cat, q) if cat else {"parts": [], "specs": []})


@router.get("/catalog/p/{pn}", response_class=HTMLResponse)
def catalog_part(request: Request, pn: str) -> Response:
    cat = pc.load()
    p = pc.part(cat, pn) if cat else None
    if not p:
        return RedirectResponse(f"/catalog?q={pc.norm_pn(pn)}", status_code=303)
    return web_routes._page(request, "catalog_part.html", **_ctx(request, cat), p=p)


@router.get("/catalog/standard-img/{name}")
def standard_image(name: str) -> Response:
    path = sp.image_path(name)
    if not path:
        return Response(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "max-age=86400"})


@router.get("/catalog/w/{wid}", response_class=HTMLResponse)
def catalog_wrangler_diagram(request: Request, wid: str) -> Response:
    cat = pc.load()
    d = pc.wrangler_diagram(cat, wid) if cat else None
    if not d:
        return RedirectResponse("/catalog/other", status_code=303)
    return web_routes._page(request, "catalog_wrangler.html", **_ctx(request, cat), d=d)


@router.get("/catalog/wrangler-img/{name}")
def wrangler_image(name: str) -> Response:
    path = pc.wrangler_image_path(name)
    if not path:
        return Response(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "max-age=86400"})


@router.get("/catalog/img/{cid}/{name}")
def catalog_image(cid: str, name: str) -> Response:
    path = pc.image_path(cid, name)
    if not path:
        return Response(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "max-age=86400"})


__all__ = ["router"]
