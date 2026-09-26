"""The live link over HTTP. Every route is a plain ``def`` so the blocking
serial work runs in the threadpool, and every route is a thin wrapper over
:mod:`cuore.live.ops`, which the MCP tools also call.

There is no write route. ``actuators`` stays ``False`` and the read-only UDS
allowlist is enforced below this layer, so a write cannot be added here by
accident.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query

from ..live import ops
from ..live import audit as audit_mod
from .deps import require_token

router = APIRouter(tags=["live"], dependencies=[Depends(require_token)])


@router.get("/live/status", summary="Port, speed, MES state, lock, cable and bus verification")
def live_status() -> dict[str, Any]:
    return ops.status()


@router.get("/live/ports", summary="Serial ports, with MES's configured port marked")
def live_ports() -> dict[str, Any]:
    return ops.ports()


@router.get("/live/mes", summary="MultiEcuScan's own settings from the registry")
def live_mes_settings() -> dict[str, Any]:
    return ops.mes_settings()


@router.get("/live/buses", summary="The three buses and their reachability under the declared cable")
def live_buses() -> dict[str, Any]:
    return ops.buses()


@router.get("/live/modules", summary="The module table with addresses and confidence")
def live_modules(bus: Optional[str] = Query(default=None)) -> dict[str, Any]:
    return ops.modules(bus)


@router.post("/live/cable", summary="Declare which adapter cable is fitted")
def live_cable(cable: str = Body(..., embed=True,
                                 description="none | blue_a5 | grey_a6")) -> dict[str, Any]:
    """Declaring a cable clears every bus verification; verify again before transmitting."""
    return ops.set_cable(cable)


@router.post("/live/probe", summary="Reset the adapter and read its identity; holds nothing")
def live_probe(port: str = Query(default=""), baud: int = Query(default=0),
               allow_while_mes_connected: bool = Query(default=False)) -> dict[str, Any]:
    return ops.probe(port=port, baud=baud, allow_while_mes_connected=allow_while_mes_connected)


@router.post("/live/verify", summary="Passive listen on a bus; marks it verified if traffic is seen")
def live_verify(bus: str = Body(..., embed=True), seconds: float = Body(default=2.0, embed=True)
                ) -> dict[str, Any]:
    return ops.verify_bus(bus, seconds=seconds)


@router.post("/live/capture", summary="Passive frame capture on a bus (receive only, no ACK)")
def live_capture(bus: str = Body(..., embed=True), seconds: float = Body(default=2.0, embed=True),
                 max_frames: int = Body(default=500, embed=True),
                 filters: Optional[list[str]] = Body(default=None, embed=True),
                 include_frames: bool = Body(default=True, embed=True)) -> dict[str, Any]:
    return ops.capture(bus, seconds=seconds, max_frames=max_frames, filters=filters,
                       include_frames=include_frames)


# --- legislated OBD -------------------------------------------------------------

@router.get("/live/obd/dtcs", summary="Stored, pending or permanent codes (Mode 03/07/0A)")
def live_obd_dtcs(kind: str = Query(default="stored")) -> dict[str, Any]:
    return ops.obd_all_dtcs() if kind == "all" else ops.obd_dtcs(kind)


@router.get("/live/obd/pid/{pid}", summary="One Mode 01 PID, decoded")
def live_obd_pid(pid: str) -> dict[str, Any]:
    return ops.obd_pid(pid)


@router.get("/live/obd/voltage", summary="Battery voltage at the OBD port")
def live_obd_voltage() -> dict[str, Any]:
    return ops.obd_voltage()


@router.get("/live/obd/supported", summary="Mode 01 PID support bitmaps per ECU")
def live_obd_supported() -> dict[str, Any]:
    return ops.obd_supported_pids()


@router.get("/live/obd/freeze", summary="Mode 02 freeze frame")
def live_obd_freeze(pid: str = Query(default="")) -> dict[str, Any]:
    return ops.obd_freeze_frame(pid)


@router.get("/live/obd/vin", summary="Mode 09 VIN")
def live_obd_vin() -> dict[str, Any]:
    return ops.obd_vin()


@router.get("/live/obd/readiness", summary="Readiness monitors with the EVAP verdict")
def live_obd_readiness() -> dict[str, Any]:
    return ops.obd_readiness()


# --- UDS, read-only -------------------------------------------------------------

@router.get("/live/module/{code}/dtcs", summary="UDS 0x19 02 on one module")
def live_module_dtcs(code: str, vin: str = Query(default=""), mask: int = Query(default=0xFF),
                     confirm: bool = Query(default=False),
                     detail: bool = Query(default=True)) -> dict[str, Any]:
    return ops.module_dtcs(code, vin=vin, mask=mask, confirm=confirm, detail=detail)


@router.get("/live/module/{code}/identity", summary="ISO 14229 Annex C identity of one module")
def live_module_identity(code: str, vin: str = Query(default=""),
                         confirm: bool = Query(default=False)) -> dict[str, Any]:
    return ops.module_identity(code, vin=vin, confirm=confirm)


@router.get("/live/module/{code}/did/{did}", summary="UDS 0x22 on one module")
def live_module_did(code: str, did: str, vin: str = Query(default=""),
                    confirm: bool = Query(default=False)) -> dict[str, Any]:
    return ops.module_did(code, did, vin=vin, confirm=confirm)


@router.get("/live/module/{code}/repair",
            summary="Repair verification: has each test re-run since the clear, and passed?")
def live_module_repair(code: str, codes: str = Query(..., description="P0455,P0456,P0440"),
                       vin: str = Query(default=""), read: bool = Query(default=True),
                       confirm: bool = Query(default=False)) -> dict[str, Any]:
    return ops.repair_status([c.strip() for c in codes.split(",")], module=code, vin=vin,
                             read=read, confirm=confirm)


@router.get("/live/obd/mode06", summary="OBD Mode $06 on-board test results (EVAP summarised)")
def live_obd_mode06(mids: str = Query(default="", description="e.g. 3C,3B; empty = discover")
                    ) -> dict[str, Any]:
    return ops.obd_mode06([m.strip() for m in mids.split(",") if m.strip()] or None)


@router.get("/live/module/{code}/dtc/{dtc}", summary="One code's status, snapshots and counters")
def live_module_dtc_detail(code: str, dtc: str, vin: str = Query(default=""),
                           confirm: bool = Query(default=False)) -> dict[str, Any]:
    return ops.module_dtc_detail(code, dtc, vin=vin, confirm=confirm)


@router.get("/live/module/{code}/all", summary="Identity plus every catalogued identifier, decoded")
def live_module_read_all(code: str, vin: str = Query(default=""),
                         include_unverified: bool = Query(default=True),
                         confirm: bool = Query(default=False)) -> dict[str, Any]:
    return ops.module_read_all(code, vin=vin, include_unverified=include_unverified,
                               confirm=confirm)


@router.post("/live/module/{code}/discover-dids", summary="Read-only sweep for unknown identifiers")
def live_module_discover_dids(code: str, vin: str = Body(default="", embed=True),
                              ranges: Optional[list[str]] = Body(default=None, embed=True),
                              max_dids: int = Body(default=2000, embed=True),
                              confirm: bool = Body(default=False, embed=True)) -> dict[str, Any]:
    return ops.module_discover_dids(code, vin=vin, ranges=ranges, max_dids=max_dids,
                                    confirm=confirm)


@router.post("/live/learn/capture", summary="Passive capture while a dealer tool reads (learning)")
def live_learn_capture(bus: str = Body(default="can_c", embed=True),
                       seconds: float = Body(default=20.0, embed=True)) -> dict[str, Any]:
    return ops.learn_capture(bus, seconds=seconds)


@router.post("/live/learn/correlate", summary="Rank identifiers against values seen in wiTECH")
def live_learn_correlate(capture: str = Body(..., embed=True),
                         marks: list[dict[str, Any]] = Body(..., embed=True)) -> dict[str, Any]:
    return ops.learn_correlate(capture, marks)


@router.post("/live/learn/accept", summary="Save a learned identifier mapping (cuore state only)")
def live_learn_accept(vin: str = Body(..., embed=True), module: str = Body(..., embed=True),
                      did: str = Body(..., embed=True), name: str = Body(..., embed=True),
                      field: dict[str, Any] = Body(..., embed=True),
                      scale: Optional[float] = Body(default=None, embed=True),
                      offset: Optional[float] = Body(default=None, embed=True),
                      unit: Optional[str] = Body(default=None, embed=True)) -> dict[str, Any]:
    return ops.learn_accept(vin, module, did, name, field, scale=scale, offset=offset, unit=unit)


@router.get("/live/learned", summary="Identifier mappings learned from dealer-tool captures")
def live_learned(vin: str = Query(default="")) -> dict[str, Any]:
    return ops.learned_dids(vin)


@router.get("/live/scan", summary="UDS DTC sweep over every confirmed module on a bus")
def live_scan(bus: str = Query(default="can_c"), vin: str = Query(default=""),
              mask: int = Query(default=0xFF), confirm: bool = Query(default=False),
              detail: bool = Query(default=True)) -> dict[str, Any]:
    return ops.scan_modules(bus, vin=vin, mask=mask, confirm=confirm, detail=detail)


@router.post("/live/discover", summary="Address discovery: 22 F190 at each candidate target")
def live_discover(bus: str = Body(default="can_c", embed=True),
                  vin: str = Body(default="", embed=True),
                  confirm: bool = Body(default=False, embed=True),
                  candidates: Optional[list[str]] = Body(default=None, embed=True),
                  per_target_timeout: float = Body(default=0.25, embed=True),
                  stop_after: Optional[int] = Body(default=None, embed=True)) -> dict[str, Any]:
    return ops.discover(bus, vin=vin, confirm=confirm, candidates=candidates,
                        per_target_timeout=per_target_timeout, stop_after=stop_after)


@router.get("/live/coverage", summary="Whole-vehicle coverage session: passes, next step, report")
def live_coverage() -> dict[str, Any]:
    return ops.coverage_status()


@router.post("/live/coverage/start", summary="Start a coverage session for one VIN")
def live_coverage_start(vin: str = Body(..., embed=True),
                        engine_running: Optional[bool] = Body(default=None, embed=True)
                        ) -> dict[str, Any]:
    return ops.coverage_start(vin, engine_running=engine_running)


@router.post("/live/coverage/run", summary="Run one pass: verify, discover, read codes")
def live_coverage_run(key: str = Body(..., embed=True),
                      confirm: bool = Body(default=False, embed=True),
                      seconds: float = Body(default=3.0, embed=True),
                      discover: Optional[bool] = Body(default=None, embed=True)
                      ) -> dict[str, Any]:
    return ops.coverage_run(key, confirm=confirm, seconds=seconds, discover=discover)


@router.post("/live/coverage/skip", summary="Skip a pass (not the baseline)")
def live_coverage_skip(key: str = Body(..., embed=True),
                       reason: str = Body(default="", embed=True)) -> dict[str, Any]:
    return ops.coverage_skip(key, reason)


@router.get("/live/coverage/report", summary="Merged whole-car report with bystander diff")
def live_coverage_report() -> dict[str, Any]:
    return ops.coverage_report()


@router.post("/live/coverage/reset", summary="Discard the coverage session")
def live_coverage_reset() -> dict[str, Any]:
    return ops.coverage_reset()


@router.get("/live/observations", summary="What the car said, for the evidence gate to cite")
def live_observations(n: int = Query(default=50, ge=1, le=1000), vin: str = Query(default=""),
                      kind: str = Query(default="")) -> dict[str, Any]:
    return ops.observations(n, vin=vin, kind=kind)


@router.get("/live/audit", summary="Recent audit-log entries")
def live_audit(n: int = Query(default=50, ge=1, le=1000)) -> dict[str, Any]:
    return {"path": str(audit_mod.log_path()), "entries": audit_mod.read_recent(n)}
