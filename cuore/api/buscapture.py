"""HTTP surface for bus capture, signal learning and per-bus presets on a
declared bypass cable (blue A5 -> CAN-IHS, grey A6 -> CAN-CH).

Thin wrapper over :mod:`cuore.live.buscapture`, same posture as the Freeze
frame panel in :mod:`cuore.api.liveboard`: every route here only ever reads
the car (a passive listen) until ``/buscapture/{bus}/save`` writes the one
from-car observation. Exceptions from :mod:`cuore.live.errors` are
``BridgeError`` subclasses already handled by the app's global exception
handler, so nothing here needs its own try/except.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from ..live import buscapture
from .deps import require_token

router = APIRouter(tags=["buscapture"], dependencies=[Depends(require_token)])


# --- cable header -----------------------------------------------------------

@router.get("/buscapture/cable", summary="Declared cable, reachable buses, unlocked presets")
def get_cable() -> dict[str, Any]:
    return buscapture.cable_header()


@router.post("/buscapture/cable", summary="Declare the fitted cable; lists what it enables")
def set_cable(cable: str = Body(..., embed=True)) -> dict[str, Any]:
    return buscapture.set_cable(cable)


# --- bus capture: Start / Stop / Save ---------------------------------------

@router.post("/buscapture/{bus}/start", summary="Start a passive bus capture")
def capture_start(bus: str) -> dict[str, Any]:
    return buscapture.capture_start(bus)


@router.get("/buscapture/{bus}/status", summary="Live frame rate and distinct-ID counts")
def capture_status(bus: str) -> dict[str, Any]:
    return buscapture.capture_status(bus)


@router.post("/buscapture/{bus}/stop", summary="Stop a running bus capture")
def capture_stop(bus: str) -> dict[str, Any]:
    return buscapture.capture_stop(bus)


@router.post("/buscapture/{bus}/save",
            summary="Save a stopped capture as a tagged CSV recording + observation")
def capture_save(bus: str, vin: str = Body("", embed=True)) -> dict[str, Any]:
    return buscapture.capture_save(bus, vin=vin)


# --- learn a signal: Start / Stop / Accept ----------------------------------

@router.post("/buscapture/{bus}/learn/start", summary="Start a learn capture for one action")
def learn_start(bus: str, action: str = Body(..., embed=True)) -> dict[str, Any]:
    return buscapture.learn_start(bus, action)


@router.get("/buscapture/{bus}/learn/status", summary="Poll a running learn capture")
def learn_status(bus: str) -> dict[str, Any]:
    return buscapture.learn_status(bus)


@router.post("/buscapture/{bus}/learn/stop",
            summary="Stop a learn capture; returns ranked (id, byte) candidates")
def learn_stop(bus: str) -> dict[str, Any]:
    return buscapture.learn_stop(bus)


@router.post("/buscapture/{bus}/learn/accept",
            summary="Name a ranked candidate and save it as a learned broadcast signal")
def learn_accept(bus: str, vin: str = Body(..., embed=True), can_id: str = Body(..., embed=True),
                 offset: int = Body(..., embed=True), name: str = Body(..., embed=True)
                 ) -> dict[str, Any]:
    return buscapture.learn_accept(vin, bus, can_id, offset, name)


# --- per-bus presets ---------------------------------------------------------

@router.get("/buscapture/presets/{name}",
           summary="One bus-capture preset's items, catalogue/learned only")
def preset_info(name: str, vin: str = "") -> dict[str, Any]:
    return buscapture.preset_info(name, vin)


@router.post("/buscapture/presets/{name}/start",
            summary="Start a capture scoped to one preset's bus; refuses without its cable")
def preset_start(name: str, vin: str = Body("", embed=True)) -> dict[str, Any]:
    return buscapture.preset_capture_start(name, vin=vin)


__all__ = ["router"]
