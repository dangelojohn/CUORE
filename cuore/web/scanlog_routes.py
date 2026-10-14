"""``/v/{vin}/scans`` and ``/v/{vin}/scans/{id}`` -- the browsable scan log.

Owner's question was "does CUORE have a log area to save the freeze frame
data?" It did not: live reads landed in ``observations.jsonl`` one row per
read, with no browsable grouping. ``cuore.live.scanlog`` groups that log
into "scans" on read (nothing new is written); this module is just the
third client of that bridge -- same posture as ``cuore.web.system_routes``,
reusing ``_dossier``/``_page``/``_set_active_vehicle``/``_vehicle_bar`` from
``cuore.web.routes`` rather than duplicating that plumbing.

Read-only: the export routes (``cuore.api.scanlog``) are the only things
that write, and only under ``CUORE_STATE_DIR/scans/<vin>/`` -- never into
MultiEcuScan's own LOG folder.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..live import scanlog
from ..services import scanlog_bridge, shop_bridge
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _bar_for(vin: str) -> dict[str, Any]:
    dossier = _dossier(vin)
    bar = _vehicle_bar(vin, dossier)
    # Same "(unnamed vehicle)" fallback chain system_routes.py/tests_routes.py/
    # liveboard_routes.py already apply.
    bar["name"] = shop_bridge.resolve_vehicle_name(vin) or bar["name"]
    return bar


@router.get("/v/{vin}/scans", response_class=HTMLResponse)
def scans_page(request: Request, vin: str) -> HTMLResponse:
    scans = scanlog_bridge.list_scans(vin)["scans"]  # newest first
    # "Scan n" numbering runs oldest-to-newest (scan 1 is the first one run
    # this diagnosis), the opposite order the list itself renders in. Only
    # a COMPLETE scan is numbered -- a partial or failed-attempt scan is
    # still listed (see cuore.live.scanlog's own docstring) but stays
    # unnumbered, same honesty rule scan_plan() applies to the "Scan n of
    # 10" chip just below.
    oldest_first = sorted((s for s in scans if s.get("status") == "complete"),
                          key=lambda s: s.get("started") or "")
    numbers = {s["id"]: i for i, s in enumerate(oldest_first, start=1)}
    for s in scans:
        s["number"] = numbers.get(s["id"])
    response = _page(request, "scanlog.html", vin=vin, bar=_bar_for(vin),
                     tab="scans", scans=scans, plan=scanlog_bridge.scan_plan(vin))
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/scans/diff", response_class=HTMLResponse)
def scan_diff_page(request: Request, vin: str, a: str, b: str) -> HTMLResponse:
    """The diff page proper -- ``cuore.live.scanlog.diff`` is the one place
    the comparison itself is computed (codes added/removed/changed-status,
    freeze-frame deltas, Mode $06 flips, readiness and coverage changes);
    this just picks the two scans named by the ``a``/``b`` query params.
    404s (via ``NotFound``) when either id is not a scan on file for this
    VIN -- same as ``scan_page``. Registered BEFORE ``{scan_id}`` below:
    FastAPI matches path routes in registration order, so a literal
    ``/scans/diff`` must be declared ahead of the ``{scan_id}`` catch-all or
    it would be swallowed as a request for a scan literally named "diff"."""
    comparison = scanlog_bridge.diff(vin, a, b)  # raises NotFound -> 404
    scan_a = scanlog_bridge.scan(vin, a)
    scan_b = scanlog_bridge.scan(vin, b)
    response = _page(request, "scan_diff.html", vin=vin, bar=_bar_for(vin), tab="scans",
                     a=scan_a, b=scan_b, comparison=comparison)
    _set_active_vehicle(response, vin)
    return response


@router.get("/v/{vin}/scans/{scan_id}", response_class=HTMLResponse)
def scan_page(request: Request, vin: str, scan_id: str) -> HTMLResponse:
    """404s (via the normal ``BridgeError``/``HTTPException`` machinery
    ``app.py`` wires up) for a scan id not on file for this VIN."""
    found = scanlog_bridge.scan(vin, scan_id)  # raises NotFound -> 404

    previous = next((s for s in scanlog_bridge.list_scans(vin)["scans"]
                     if s["id"] != scan_id and (s.get("started") or "") < (found.get("started") or "")),
                    None)
    comparison = scanlog.diff(vin, previous["id"], scan_id) if previous else None

    response = _page(request, "scan.html", vin=vin, bar=_bar_for(vin), tab="scans",
                     scan=found, previous=previous, comparison=comparison)
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
