"""The live link over HTTP. Every route is a plain ``def`` so the blocking
serial work runs in the threadpool, and every route is a thin wrapper over
:mod:`cuore.live.ops`, which the MCP tools also call.

There is no write route. ``actuators`` stays ``False`` and the read-only UDS
allowlist is enforced below this layer, so a write cannot be added here by
accident.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query, Request

from ..live import dtc_records
from ..live import ops
from ..live import responders as responders_mod
from ..live import ui_store
from ..live import audit as audit_mod
from .deps import require_role, require_token

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
                 include_frames: bool = Body(default=True, embed=True),
                 state_note: str = Body(default="", embed=True)) -> dict[str, Any]:
    return ops.capture(bus, seconds=seconds, max_frames=max_frames, filters=filters,
                       include_frames=include_frames, state_note=state_note)


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


@router.post("/live/module/{code}/connect-test",
             summary="Bounded read-only ladder of routes to one CAN-CH module (grey cable, 500k)")
def live_module_connect_test(code: str, vin: str = Query(default=""),
                             confirm: bool = Query(default=False)) -> dict[str, Any]:
    return ops.abs_connect_test(code, vin=vin, confirm=confirm)


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


@router.get("/live/round", summary="Module code round: 19 02, then 19 04 and 19 06 per code")
def live_module_round(bus: str = Query(default="can_c"), modules: str = Query(default=""),
                      vin: str = Query(default=""), confirm: bool = Query(default=False)
                      ) -> dict[str, Any]:
    mods = [m.strip() for m in modules.split(",") if m.strip()] or None
    return ops.module_code_round(bus, mods, vin=vin, confirm=confirm)


@router.post("/live/snapshot-bind", summary="Owner binds a snapshot DID to a field name")
def live_snapshot_bind(vin: str = Body(..., embed=True), module: str = Body(..., embed=True),
                       did: str = Body(..., embed=True), field_name: str = Body(..., embed=True),
                       length: Optional[int] = Body(default=None, embed=True),
                       unit: Optional[str] = Body(default=None, embed=True),
                       div: Optional[int] = Body(default=None, embed=True)) -> dict[str, Any]:
    from ..live import snapshot_bindings
    return snapshot_bindings.bind(vin, module, did, field_name, length=length, unit=unit, div=div)


@router.get("/live/module/{code}/dtc/{dtc}", summary="One code's status, snapshots and counters")
def live_module_dtc_detail(code: str, dtc: str, vin: str = Query(default=""),
                           confirm: bool = Query(default=False)) -> dict[str, Any]:
    # Honest best-effort decode of whatever ops.module_dtc_detail's snapshot
    # (19 04) / extended (19 06) walk stopped on and reported raw under
    # "undecoded_from" -- see cuore.live.dtc_records module docstring. Every
    # key dtc_detail already decoded is passed through unchanged.
    return dtc_records.enrich_dtc_detail(ops.module_dtc_detail(code, dtc, vin=vin, confirm=confirm))


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


@router.get("/live/service-dids/plan", summary="Service-value discovery plan and expected values (no car contact)")
def live_service_dids_plan(vin: str = Query(...)) -> dict[str, Any]:
    from ..live import service_dids
    return {"expected": service_dids.expected_values(vin), "plan": service_dids.plan(vin)}


@router.post("/live/service-dids/discover", summary="Read-only UDS 0x22 sweep for the cluster's service values")
def live_service_dids_discover(vin: str = Body(..., embed=True),
                               max_seconds: float = Body(default=180, embed=True)) -> dict[str, Any]:
    from ..live import service_dids
    return service_dids.run(vin, max_seconds=max_seconds)


@router.get("/live/service-dids/results", summary="Last service-value discovery results")
def live_service_dids_results(vin: str = Query(...)) -> dict[str, Any]:
    from ..live import service_dids
    return service_dids.results(vin)


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
                  stop_after: Optional[int] = Body(default=None, embed=True),
                  deadline_s: float = Body(default=60.0, embed=True),
                  max_targets: Optional[int] = Body(default=None, embed=True)) -> dict[str, Any]:
    return ops.discover(bus, vin=vin, confirm=confirm, candidates=candidates,
                        per_target_timeout=per_target_timeout, stop_after=stop_after,
                        deadline_s=deadline_s, max_targets=max_targets)


@router.get("/live/responders", summary="Stored discovery responders, each with a proposed MES-log name (no car contact)")
def live_responders(vin: str = Query(..., description="car VIN"),
                    propose: bool = Query(default=True)) -> dict[str, Any]:
    out = responders_mod.list_responders(vin)
    if propose:
        out["naming"] = responders_mod.name_responders(vin)
    return out


@router.post("/live/responders/accept",
             summary="Owner decision: promote one responder address to 'confirmed (owner)' (no car contact)")
def live_responders_accept(vin: str = Body(..., embed=True), address: str = Body(..., embed=True),
                           module: str = Body(..., embed=True)) -> dict[str, Any]:
    return responders_mod.accept_responder(vin, address, module)


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


@router.get("/live/actuators",
            summary="Learned actuator-test procedures (list only; replay never over HTTP)")
def live_actuators(vin: str = Query(default="")) -> dict[str, Any]:
    return ops.actuators(vin)


# --- full scan: every subsystem the adapter can reach, read-only -------------------

@router.post("/live/fullscan",
            summary="One read-only full-vehicle scan; every reading recorded as an observation")
def live_fullscan(vin: str = Body(default="", embed=True),
                  buses: Optional[list[str]] = Body(default=None, embed=True),
                  budget_s: Optional[float] = Body(default=None, embed=True),
                  confirm: bool = Body(default=False, embed=True)) -> dict[str, Any]:
    from ..live import fullscan
    return fullscan.run(vin, buses=buses, budget_s=budget_s, confirm=confirm)


@router.get("/live/fullscan/last", summary="The most recent full scan's result")
def live_fullscan_last() -> dict[str, Any]:
    from ..live import fullscan
    return fullscan.last()


# --- guided full scan: paused at each coloured-cable swap --------------------

@router.post("/live/fullscan/guided/start",
            summary="Start a guided scan: CAN-C in full, then pause for the blue A5 cable")
def live_fullscan_guided_start(vin: str = Body(default="", embed=True)) -> dict[str, Any]:
    from ..live import fullscan
    return fullscan.run_guided(vin)


@router.get("/live/fullscan/guided/state",
           summary="The open (or most recently closed) guided scan")
def live_fullscan_guided_state() -> dict[str, Any]:
    from ..live import fullscan
    return fullscan.guided_state()


@router.post("/live/fullscan/guided/continue",
            summary="Declare the cable just fitted, sweep its bus, and pause for the next step")
def live_fullscan_guided_continue(scan_id: str = Body(..., embed=True),
                                  cable_fitted: str = Body(..., embed=True)) -> dict[str, Any]:
    from ..live import fullscan
    return fullscan.continue_guided(scan_id, cable_fitted)


@router.post("/live/fullscan/guided/skip",
            summary="Skip the guided scan's currently paused-on cable segment")
def live_fullscan_guided_skip(scan_id: str = Body(..., embed=True)) -> dict[str, Any]:
    from ..live import fullscan
    return fullscan.skip_guided(scan_id)


@router.post("/live/fullscan/guided/abandon", summary="Close an open guided scan honestly")
def live_fullscan_guided_abandon(scan_id: str = Body(..., embed=True)) -> dict[str, Any]:
    from ..live import fullscan
    return fullscan.abandon_guided(scan_id)


# --- live-data engine: channels, poll sessions, alarms, recording ---------------

@router.get("/live/channels", summary="Channel registry (PID/DID/computed/battery) and presets")
def live_channels_route() -> dict[str, Any]:
    return ops.live_channels()


@router.post("/live/session/start",
            summary="Start the live-data poll session; read-only but holds the adapter")
def live_session_start_route(channels: Optional[list[str]] = Body(default=None, embed=True),
                             preset: str = Body(default="", embed=True),
                             rates: Optional[dict[str, float]] = Body(default=None, embed=True),
                             monitor_dtcs: bool = Body(default=False, embed=True),
                             dtc_interval_s: float = Body(default=10.0, embed=True),
                             code_watch: bool = Body(default=False, embed=True),
                             code_watch_interval_s: float = Body(default=10.0, embed=True),
                             vin: str = Body(default="", embed=True),
                             priorities: Optional[dict[str, int]] = Body(
                                 default=None, embed=True,
                                 description="Per-channel recording priority 1-5 = poll divisor "
                                             "(1 every cycle, the default; 5 every 5th)"),
                             simulation: bool = Body(default=False, embed=True)
                             ) -> dict[str, Any]:
    return ops.live_session_start(channels, preset=preset, rates=rates,
                                  monitor_dtcs=monitor_dtcs, dtc_interval_s=dtc_interval_s,
                                  code_watch=code_watch,
                                  code_watch_interval_s=code_watch_interval_s, vin=vin,
                                  priorities=priorities, simulation=simulation)


@router.post("/live/session/code-watch/ack",
             summary="Mark the live new-code alerts seen (banner clears; events stay listed)")
def live_code_watch_ack_route(request: Request):
    """JSON for fetch/API callers; a plain form post with a same-site ``return_to``
    (the banner's no-JS Seen button) gets a 303 back to that page instead."""
    out = ops.live_code_watch_ack()
    ctype = request.headers.get("content-type", "")
    if "application/json" in request.headers.get("accept", "") or "form" not in ctype:
        return out
    from anyio import from_thread
    from fastapi.responses import RedirectResponse
    from ..web.fault_board_routes import _safe_return
    back = _safe_return(str(from_thread.run(request.form).get("return_to", "")), "")
    return RedirectResponse(url=back, status_code=303) if back else out


@router.post("/live/session/stop", summary="Stop the live-data poll session, release the adapter")
def live_session_stop_route() -> dict[str, Any]:
    return ops.live_session_stop()


@router.get("/live/session", summary="Live-data session status: channels, achieved rates, alarms")
def live_session_status_route() -> dict[str, Any]:
    return ops.live_session_status()


@router.get("/live/snapshot", summary="Latest value of every channel in the running session")
def live_snapshot_route() -> dict[str, Any]:
    return ops.live_snapshot()


# --- decoding confirmation: MES recording vs CUORE recording (offline, no car contact) ---------

@router.get("/live/decode-confirm/runs", summary="Saved decode-confirmation runs, newest first")
def decode_confirm_runs_route(vin: str = Query(default=""), run_id: str = Query(default="")) -> dict[str, Any]:
    from ..live import decode_confirm
    return decode_confirm.get_run(run_id) if run_id else decode_confirm.list_runs(vin)


@router.post("/live/decode-confirm/run",
             summary="Pair an MES recording with a CUORE live recording; verdict per channel (reads files only)")
def decode_confirm_run_route(vin: str = Body(..., embed=True), mes_log_path: str = Body(..., embed=True),
                             cuore_recording_path: str = Body(..., embed=True),
                             tolerance: float = Body(default=0.05, embed=True),
                             mes_interval_s: Optional[float] = Body(default=None, embed=True),
                             mes_start: str = Body(default="", embed=True),
                             lag_s: Optional[float] = Body(default=None, embed=True),
                             mode: str = Body(default="static", embed=True)) -> dict[str, Any]:
    from ..live import decode_confirm
    return decode_confirm.run(vin, mes_log_path, cuore_recording_path, tolerance=tolerance,
                              mes_interval_s=mes_interval_s, mes_start=mes_start, lag_s=lag_s, mode=mode)


@router.post("/live/decode-confirm/accept",
             summary="Accept one channel's verdict into did_overrides.json (catalogue file untouched)")
def decode_confirm_accept_route(vin: str = Body(..., embed=True), run_id: str = Body(..., embed=True),
                                channel: str = Body(..., embed=True),
                                confirm_pairing: bool = Body(default=False, embed=True)) -> dict[str, Any]:
    from ..live import decode_confirm
    return decode_confirm.accept(vin, run_id, channel, confirm_pairing=confirm_pairing)


@router.post("/live/record/start", summary="Start mirroring the live session to an MES-format CSV")
def live_record_start_route() -> dict[str, Any]:
    return ops.live_record_start()


@router.post("/live/record/tag", summary="Insert keyed tag 0-9 into the running recording")
def live_record_tag_route(key: str = Body(..., embed=True), vin: str = Body(default="", embed=True)
                          ) -> dict[str, Any]:
    """One instantaneous tag event (a single CSV row whose TAG cell is ``TAG <key>: <label>``,
    and a ``tag`` line in a running drive recording). 409 when nothing is recording."""
    from fastapi import HTTPException
    from ..services import recordings as rec_svc
    ev = ops.live_record_tag(key, vin=vin)
    drive = rec_svc.add_tag(key, ui_store.load_tag_labels(vin)[str(key).strip()])
    if ev is None and drive is None:
        raise HTTPException(status_code=409, detail="not recording")
    return {"tag": ev or drive, "csv": ev is not None, "drive_recording": drive is not None}


@router.get("/live/record/tag-labels", summary="The ten tag labels for a VIN")
def live_record_tag_labels_get(vin: str = Query(default="")) -> dict[str, Any]:
    return {"vin": vin, "labels": ui_store.load_tag_labels(vin)}


@router.post("/live/record/tag-labels", summary="Rename tags 0-9 for a VIN")
def live_record_tag_labels_set(labels: dict[str, str] = Body(..., embed=True),
                               vin: str = Body(default="", embed=True)) -> dict[str, Any]:
    return {"vin": vin, "labels": ui_store.save_tag_labels(vin, labels)}


@router.post("/live/record/stop", summary="Stop the live-session CSV recording")
def live_record_stop_route() -> dict[str, Any]:
    return ops.live_record_stop()


@router.get("/live/load-step", summary="Load-step voltage test: preset, owner script, channels")
def live_load_step_route() -> dict[str, Any]:
    return ops.live_load_step()


@router.post("/live/load-step/start",
            summary="Start the load-step voltage test as a named recording (read-only, 3 min)")
def live_load_step_start_route(label: str = Body(default="", embed=True)) -> dict[str, Any]:
    return ops.live_load_step_start(label)


@router.post("/live/load-step/stop", summary="Stop the load-step test early")
def live_load_step_stop_route() -> dict[str, Any]:
    return ops.live_load_step_stop()


@router.get("/live/load-step/status", summary="Load-step test: elapsed, current step, live values")
def live_load_step_status_route() -> dict[str, Any]:
    return ops.live_load_step_status()


@router.get("/live/load-step/analysis",
            summary="Per-step voltage drop of each module vs the adapter, from a saved recording")
def live_load_step_analysis_route(recording: str = Query(default="")) -> dict[str, Any]:
    return ops.live_load_step_analysis(recording)


@router.post("/live/purge-trim/start",
            summary="Start the passive purge-trim EVAP test as a named recording (read-only, 4 min)")
def live_purge_trim_start_route(label: str = Body(default="", embed=True)) -> dict[str, Any]:
    return ops.live_purge_trim_start(label)


@router.post("/live/purge-trim/stop", summary="Stop the purge-trim test early")
def live_purge_trim_stop_route() -> dict[str, Any]:
    return ops.live_purge_trim_stop()


@router.get("/live/purge-trim/status", summary="Purge-trim test: elapsed and live values")
def live_purge_trim_status_route() -> dict[str, Any]:
    return ops.live_purge_trim_status()


@router.get("/live/purge-trim/analysis",
            summary="Purge-off vs purge-on trims and the trim dip when purge opens, from a saved recording")
def live_purge_trim_analysis_route(recording: str = Query(default="")) -> dict[str, Any]:
    return ops.live_purge_trim_analysis(recording)


@router.post("/live/alarms", summary="Set a warn/alarm threshold on one live channel")
def live_alarms_route(channel: str = Body(..., embed=True),
                      warn: Optional[float] = Body(default=None, embed=True),
                      alarm: Optional[float] = Body(default=None, embed=True),
                      direction: str = Body(default="above", embed=True),
                      hysteresis: float = Body(default=0.0, embed=True)) -> dict[str, Any]:
    return ops.live_set_alarm(channel, warn=warn, alarm=alarm, direction=direction,
                              hysteresis=hysteresis)


# --- Connect to car: one button, adapter -> bus -> VIN -> guided full scan --

@router.post("/live/connect/start",
            summary="Adapter probe, bus verify, VIN match, then start (or resume) the guided scan")
def live_connect_start(vin: str = Body(..., embed=True)) -> dict[str, Any]:
    """The vehicle status strip's "Connect to car" button: the same honest
    checks a mechanic would do by hand, in order, each one a tick the
    drawer can show before it moves on -- adapter found, bus verified, VIN
    matches, then the guided full scan starts (``fullscan.run_guided``).

    Refuses outright, at whichever stage it fails, with the live layer's own
    wording (a live-data poll session holding the adapter, MultiEcuScan
    connected, no reply from the adapter, the wrong VIN on the cable) --
    never invented copy. Never starts anything on its own: this route is
    reached only by the button's own tap (see ``connect.js``), never on page
    load, and it never clears a code (there is no clear route behind it).

    If a guided scan for this VIN is already open (paused mid cable-swap),
    this reports that session instead of trying to start a second one --
    :func:`cuore.live.fullscan.run_guided` already refuses a second start
    outright, so this checks first and skips straight to the open session's
    own state, same as a plain reload of ``/v/{vin}/scan`` would show.
    """
    from ..live import fullscan
    from ..live.errors import LiveError

    checks: list[dict[str, Any]] = []

    def _refused(stage: str, label: str, error: str) -> dict[str, Any]:
        checks.append({"stage": stage, "label": label, "ok": False, "error": error})
        return {"ok": False, "stage": stage, "error": error, "checks": checks}

    existing = fullscan.guided_state()
    if existing.get("status") == "paused" and existing.get("vin") == vin:
        checks.append({"stage": "resume", "label": "Guided scan already open", "ok": True})
        return {"ok": True, "resumed": True, "checks": checks, "guided": existing}

    try:
        ops._poller_active_guard()
        probe = ops.probe()
    except LiveError as e:
        return _refused("adapter", "Find the adapter", str(e))
    checks.append({"stage": "adapter", "label": "Adapter found", "ok": True,
                  "detail": {"port": probe.get("port"), "identity": probe.get("identity"),
                             "voltage": probe.get("battery_voltage")}})

    try:
        verify = ops.verify_bus("can_c")
    except LiveError as e:
        return _refused("bus", "Verify the bus", str(e))
    checks.append({"stage": "bus", "label": "Bus verified", "ok": True,
                  "detail": {"bus": "can_c", "frames": verify.get("frames")}})

    try:
        vin_read = ops.obd_vin()
    except LiveError as e:
        return _refused("vin", "Read the VIN", str(e))
    car_vin = (vin_read or {}).get("vin") or ""
    if vin and car_vin and car_vin != vin:
        return _refused("vin", "VIN matches",
                        f"the car on the cable reads VIN {car_vin}, not {vin}; wrong car on "
                        f"the cable?")
    checks.append({"stage": "vin", "label": "VIN matches", "ok": True,
                  "detail": {"vin": car_vin or vin}})

    try:
        guided = fullscan.run_guided(vin)
    except LiveError as e:
        return _refused("scan", "Start the guided scan", str(e))
    checks.append({"stage": "scan", "label": "Guided scan started", "ok": True})
    return {"ok": True, "resumed": False, "checks": checks, "guided": guided}


@router.get("/live/stream", summary="Server-sent events: live channel samples and alarms")
def live_stream_route():
    import json as _json

    from fastapi.responses import StreamingResponse

    def gen():
        for msg in ops.live_stream_events():
            yield (": keepalive\n\n" if msg is None else f"data: {_json.dumps(msg)}\n\n")

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/live/proxi/discover", summary="Read-only UDS 0x22 sweep of the Body computer for the configuration block")
def live_proxi_discover(vin: str = Body(..., embed=True)) -> dict[str, Any]:
    from ..live import proxi_read
    return proxi_read.discover(vin)


@router.post("/live/proxi/accept", summary="Owner accepts a candidate as the PROXI block (no car contact)",
             dependencies=[Depends(require_role("shop_lead"))])
def live_proxi_accept(vin: str = Body(..., embed=True), did: str = Body(..., embed=True),
                      reason: str = Body(..., embed=True)) -> dict[str, Any]:
    from ..live import proxi_read
    return proxi_read.accept_candidate(vin, did, reason)


@router.post("/live/proxi/read", summary="Read-only UDS 0x22 read of the accepted PROXI block, with diff")
def live_proxi_read(vin: str = Body(..., embed=True)) -> dict[str, Any]:
    from ..live import proxi_read
    return proxi_read.read(vin)
