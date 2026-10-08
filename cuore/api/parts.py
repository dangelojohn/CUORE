"""``/api/parts*``: the parts catalog (names, OEM/aftermarket numbers,
supersessions, torque specs, price, images), fed by
:mod:`cuore.services.parts_bridge` -- see that module's docstring for the
fixture it falls back to while ``mes-log-mcp/mes/parts.py`` is still being
built in parallel.

Every page that renders a part card (``/v/{vin}/parts``, and the inline
cards on ``code.html``/``maintenance.html``/``oil_change.html``/
``brakes_tires.html``) reaches the same bridge functions this router calls,
so the page and the JSON cannot disagree.

Not registered on the app here -- ``app.py`` is owned by another agent while
this was built. The one line needed there (next to the other ``api``
router includes):

    ``app.include_router(parts_api.router, prefix="/api")``

(importing this module as ``from .api import parts as parts_api``.)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..services import parts_bridge
from ..services.errors import NotFound
from .deps import require_token

router = APIRouter(tags=["parts"], dependencies=[Depends(require_token)])


@router.get("/parts", summary="Every part known, with resolved torques")
def list_parts(q: str = "") -> dict[str, Any]:
    rows = parts_bridge.search_parts(q=q) if q else parts_bridge.all_parts()
    return {"parts": rows, "count": len(rows)}


@router.get("/parts/for-code/{code}", summary="Parts related to a DTC")
def parts_for_code(code: str) -> dict[str, Any]:
    rows = parts_bridge.parts_for_code(code)
    return {"code": code.strip().upper(), "parts": rows, "count": len(rows)}


@router.get("/parts/for-job/{job}", summary="Parts related to a service/maintenance job")
def parts_for_job(job: str) -> dict[str, Any]:
    rows = parts_bridge.parts_for_job(job)
    return {"job": job, "parts": rows, "count": len(rows)}


@router.get("/parts/{key}", summary="One part by key")
def get_part(key: str) -> dict[str, Any]:
    row = parts_bridge.part(key)
    if row is None:
        raise NotFound(f"no part known by key {key!r}")
    return row


__all__ = ["router"]
