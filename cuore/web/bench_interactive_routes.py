"""Two Bench fragments: the live-proof block and the fault map (cuore/services/bench_interactive.py).

* ``GET /v/{vin}/bench/proof``              the live-proof partial as an HTML fragment
* ``GET /v/{vin}/bench/fault-map?fault=KEY`` the fault-map partial; no ``fault`` = the top present fault;
                                            a key that is not a fault on this car = 404

Both read saved data and the in-process live snapshot only; nothing here contacts the adapter. Importing this
module also registers the Jinja globals ``bench_live_proof(vin)`` and ``bench_fault_map(vin, fault)`` so
bench.html can ``{% include "_bench_live_proof.html" %}`` / ``{% include "_bench_fault_map.html" %}`` with no
extra context (the partials call them when ``proof`` / ``fmap`` are not already defined).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import bench_interactive
from .routes import templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _token(request: Request) -> str:
    return request.query_params.get("token") or ""


@router.get("/v/{vin}/bench/proof", response_class=HTMLResponse)
def bench_proof(request: Request, vin: str) -> HTMLResponse:
    proof = bench_interactive.live_proof(vin, token=_token(request))
    return templates.TemplateResponse(request, "_bench_live_proof.html", {"vin": vin, "proof": proof})


@router.get("/v/{vin}/bench/fault-map", response_class=HTMLResponse)
def bench_fault_map_route(request: Request, vin: str, fault: str = "") -> HTMLResponse:
    fmap = bench_interactive.fault_map(vin, fault or None, token=_token(request))
    if fmap is None:
        return HTMLResponse("Unknown fault for this vehicle", status_code=404)
    return templates.TemplateResponse(request, "_bench_fault_map.html", {"vin": vin, "fmap": fmap})


# --- Jinja globals for bench.html -------------------------------------------------------------------

def bench_live_proof(vin: str, token: str = "") -> dict[str, Any]:
    return bench_interactive.live_proof(vin, token=token)


def bench_fault_map(vin: str, fault: Optional[str] = None, token: str = "") -> Optional[dict[str, Any]]:
    return bench_interactive.fault_map(vin, fault or None, token=token)


templates.env.globals["bench_live_proof"] = bench_live_proof
templates.env.globals["bench_fault_map"] = bench_fault_map
