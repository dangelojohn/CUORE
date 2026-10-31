"""The module-tree pages: ``/v/{vin}/modules`` and ``/v/{vin}/modules/{code}``.

MultiEcuScan shows a vehicle as a tree of modules, each with Info, Errors,
Parameters, Actuators and Adjustments tabs. These two pages are CUORE's
read of the same tree, backed entirely by ``cuore.services.modules_bridge``
(see that module for where every field comes from).

Kept as a second router rather than added to ``cuore.web.routes``, same
posture as ``dossier_routes.py``: it reuses that module's own page/dossier
helpers (``_page``, ``_dossier``, ``_vehicle_bar``, ``_set_active_vehicle``)
so rendering never forks from the rest of the ``/v/`` surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..live.addressing import by_code as _addr_by_code
from ..services import module_workspace, modules_bridge
from . import routes as web_routes

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _annotate(m: dict) -> dict:
    """Add the address, bus label and search haystack the page shows per module.

    Everything the row lists is in the haystack, so a search can only match
    text the reader can see (or that a chip/label spells out).
    """
    addr = _addr_by_code(m["code"])
    target = getattr(addr, "target", None)
    ids: list[str] = []
    if target is not None:
        ids = [f"0x{target:02X}", f"{target:02X}", f"0x{target:02x}",
               f"{addr.request_id:08X}", f"{addr.response_id:08X}"]
    m["addr"] = ids[0] if ids else ""
    m["addr_ids"] = f"{ids[3]} / {ids[4]}" if ids else ""
    bus = (m.get("bus") or "").lower()
    m["bus_label"] = bus.replace("_", "-").upper() if bus else "unknown"
    err = m.get("errors") or {}
    words = [m["code"], m.get("name") or "not in the module registry",
             m.get("domain") or "", m.get("tier") or "", m["bus_label"], bus,
             bus.replace("_", " "), (m.get("status") or "").replace("_", " "),
             m.get("status") or "", *ids]
    if addr is not None:
        words += [str(addr.confidence.value), str(addr.bus_confidence),
                  str(addr.present)]
    ident = m.get("identity") or {}
    words += [f"SW {ident['software']}" if ident.get("software") else "",
              f"HW {ident['hardware']}" if ident.get("hardware") else ""]
    if not ident.get("software") and not ident.get("hardware"):
        words.append("no SCAN identity")
    words += list(err.get("codes") or [])
    for key, label in (("active", "active"), ("cleared_unverified", "cleared"),
                       ("stale", "stale")):
        if err.get(key):
            words.append(label)
    if (m.get("actuators") or {}).get("blocked"):
        words.append("blocked")
    m["_hay"] = " ".join(w for w in words if w).lower()
    return m


@router.get("/v/{vin}/modules", response_class=HTMLResponse)
def vmodules(request: Request, vin: str, q: str = "") -> HTMLResponse:
    """The module tree: one row per module, status chips, counts.

    ``?q=`` is a server-side search over what the page lists per module
    (works without JavaScript).
    """
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    rows = [_annotate(m) for m in modules_bridge.list_modules(vin)]
    total = len(rows)
    _rank = {"active": 0, "cleared_unverified": 1, "stale": 2}
    rows.sort(key=lambda m: _rank.get(m.get("status"), 3))  # worst first (stable)
    q = (q or "").strip()[:80]
    if q:
        needles = q.lower().split()
        rows = [m for m in rows if all(n in m["_hay"] for n in needles)]
    response = web_routes._page(request, "vmodules.html", vin=vin, bar=bar,
                                rows=rows, total=total, q=q, tab="modules")
    web_routes._set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/modules/{code}", response_class=HTMLResponse)
def vmodule_detail(request: Request, vin: str, code: str) -> HTMLResponse:
    """One module's tabs: errors, parameters, actuators, adjustments, info."""
    dossier = web_routes._dossier(vin)
    bar = web_routes._vehicle_bar(vin, dossier)
    detail = modules_bridge.module_detail(vin, code)
    response = web_routes._page(request, "vmodule.html", vin=vin, bar=bar,
                                m=detail, ws=module_workspace.build(vin, code),
                                tab="modules")
    web_routes._set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
