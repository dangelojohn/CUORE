"""HTTP surface for learning module DIDs by listening to MES over a second
adapter -- thin wrapper over :mod:`cuore.live.mes_learn`, same posture as
:mod:`cuore.api.buscapture`: exceptions from :mod:`cuore.live.errors` are
``BridgeError`` subclasses already handled by the app's global exception
handler, so nothing here needs its own try/except.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from ..live import mes_learn
from .deps import require_token

router = APIRouter(tags=["mes-learn"], dependencies=[Depends(require_token)])


@router.post("/mes-learn/start", summary="Start the passive listener on a second adapter")
def start(port: str = Body(..., embed=True), vin: str = Body("", embed=True)) -> dict[str, Any]:
    return mes_learn.start(port, vin=vin)


@router.get("/mes-learn/status", summary="Poll the running (or just-stopped) listener")
def status() -> dict[str, Any]:
    return mes_learn.status()


@router.post("/mes-learn/stop",
            summary="Stop the listener and align its capture against an MES CSV recording")
def stop(csv: str = Body("", embed=True)) -> dict[str, Any]:
    return mes_learn.stop(csv=csv)


@router.get("/mes-learn/candidates", summary="Fit candidates from the last alignment")
def candidates() -> dict[str, Any]:
    return mes_learn.candidates()


@router.post("/mes-learn/candidates/{candidate_id}/accept",
            summary="Accept a candidate: saved as a learned, scaled channel")
def accept(candidate_id: str, vin: str = Body(..., embed=True),
          name: str = Body(..., embed=True)) -> dict[str, Any]:
    return mes_learn.accept(candidate_id, vin, name)


@router.post("/mes-learn/candidates/{candidate_id}/reject",
            summary="Reject a candidate: kept observed-but-unscaled")
def reject(candidate_id: str, vin: str = Body(..., embed=True),
          reason: str = Body("", embed=True)) -> dict[str, Any]:
    return mes_learn.reject(candidate_id, vin, reason=reason)


__all__ = ["router"]
