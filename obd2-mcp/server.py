"""OBD-II / live-link MCP server: thin tool wrappers over ``cuore.live``.

Everything that touches the adapter lives in ``cuore/live``; this file only
exposes it as MCP tools, keeps the tool names earlier Claude sessions know,
and adds the two things that belong on the MCP surface rather than in HTTP:

* ``send_raw`` with its consent flags (vehicle writes, adapter reconfiguration);
* ``clear_dtcs`` with evidence capture, a speed check and a read-back.

Every call that can change the car (``clear_dtcs``, ``clear_module_dtcs``,
``run_actuator``, a ``send_raw`` vehicle write) needs a PERSON's approval on the
CUORE ``/approve/<request_id>`` page (cuore/live/consent_gate.py). The tool
cannot approve for itself: without a valid ``request_id`` it is refused and a
pending request is created; the ``consent`` / ``confirm`` parameters alone
authorise nothing. Approval state lives in the CUORE server's memory, so when
CUORE cannot be reached these tools refuse (no in-process fallback for writes).

Since 2026-09-25 cuore owns the adapter. Every read tool here is a request
to cuore's HTTP API (``cuore_client``), which is started automatically if it
is not running, so the cable declaration, bus verification and code in force
are cuore's, one set of them. Only when cuore cannot be reached at all does a
tool run the same code in-process (``served_by`` says so). The two writes
stay in-process by design (there is no write route on HTTP) and adopt cuore's
cable declaration before opening the adapter. The lock file still keeps the
two processes from opening COM3 at once.

Reads verify their own bus: a request on an unverified or stale bus runs the
passive listen first and proceeds if the bus is live (``auto_verified`` in the
result), or refuses with the reason if it is silent.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from cuore.live import ops  # noqa: E402
from cuore.live import responders  # noqa: E402
import cuore_client  # noqa: E402  -- sibling module; this directory is on sys.path
from cuore.live import audit  # noqa: E402
from cuore.live import fullscan  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.config import state_dir  # noqa: E402
from cuore.live.errors import LiveError, Refused  # noqa: E402
from cuore.live import addressing as _addressing  # noqa: E402
from cuore.live import clear as _clear  # noqa: E402
from cuore.live import consent_gate  # noqa: E402
from cuore.live.consent_gate import ConsentRefused, ConsentRequired  # noqa: E402
from cuore.live.framing import adapter_error, reassemble  # noqa: E402
from cuore.live.obd import decode_obd_dtcs  # noqa: E402
from cuore.live.safety import (assert_raw_write_allowed, classify_command, is_adapter_only,  # noqa: E402
                               raw_write_phrase, validate_command)
from cuore.live.transport import DEFAULT_TIMEOUT, link  # noqa: E402

# Name this process in the advisory lock so the bench UI can show "held by
# obd2-mcp" rather than mistaking it for itself.
link().process = "obd2-mcp"

# Approvals live in the CUORE server's memory, never here: this process only asks CUORE.
consent_gate.set_remote(cuore_client.call,
                        (cuore_client.CuoreUnavailable, cuore_client.CuoreTimeout))

mcp = FastMCP("obd2")


def _json(fn: Callable[[], Any]) -> str:
    try:
        return json.dumps(fn(), indent=2)
    except LiveError as e:
        return json.dumps({"error": str(e), "kind": type(e).__name__}, indent=2)
    except Exception as e:  # serial or OS failures mid-operation
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2)


def _gated(fn: Callable[[], Any]) -> str:
    """Like :func:`_json`, for the car-affecting tools: a refused approval is a normal answer
    (with the request id and the page to open), never an exception text with a phrase in it."""
    def run() -> Any:
        try:
            return fn()
        except ConsentRequired as e:
            return e.payload(cuore_client.base_url())
        except ConsentRefused as e:
            return {"refused": str(e)}
    return _json(run)


def _in_scope(grant: Any, fn: Callable[[], Any]) -> Any:
    """Run ``fn`` with the approved write scope open (the transport refuses gated requests outside)."""
    with consent_gate.write_scope(grant):
        return fn()


def _via(method: str, path: str, local: Callable[[], Any], *,
         query: Optional[dict[str, Any]] = None, body: Optional[dict[str, Any]] = None,
         timeout: float = 120.0) -> str:
    """Serve a tool from cuore, the adapter's one owner.

    Falls back to ``local`` (in-process, same code) only when cuore cannot be
    reached at all, so there is still exactly one owner. A timeout is not a
    reason to fall back: the request may still be running in cuore, and
    repeating it here would transmit twice.
    """
    try:
        return json.dumps(cuore_client.call(method, path, query=query, body=body,
                                            timeout=timeout), indent=2)
    except cuore_client.CuoreTimeout as e:
        return json.dumps({"error": str(e), "kind": "Timeout"}, indent=2)
    except cuore_client.CuoreUnavailable as e:
        if os.environ.get("CUORE_FALLBACK", "1") == "0":
            return json.dumps({"error": str(e), "kind": "CuoreUnavailable"}, indent=2)
        out = json.loads(_json(local))
        if isinstance(out, dict):
            out["served_by"] = f"in-process fallback ({e})"
        return json.dumps(out, indent=2)


def _sync_cable() -> Optional[str]:
    """Adopt cuore's cable declaration before an in-process write.

    Writes stay off HTTP by design, so clear_dtcs and send_raw still open the
    adapter here; they must not disagree with cuore about which cable is
    fitted. Returns the cable adopted, or None if cuore was unreachable.
    """
    try:
        st = cuore_client.call("GET", "/live/status", timeout=10)
    except (cuore_client.CuoreUnavailable, cuore_client.CuoreTimeout):
        return None
    cable = ((st or {}).get("cable") or {}).get("cable") if isinstance(st, dict) else None
    if cable and cable != link().cable:
        link().set_cable(cable)
    return cable


# --- configuration and status ---------------------------------------------

@mcp.tool()
def list_ports() -> str:
    """Serial ports on this machine, with MES's configured port marked."""
    return _via("GET", "/live/ports", ops.ports)


@mcp.tool()
def status() -> str:
    """Port and speed in force and their sources, MES state, lock state, declared cable,
    bus verification, and the last adapter identity. The port is never held between calls."""
    return _via("GET", "/live/status", ops.status)


@mcp.tool()
def mes_state() -> str:
    """Is MultiEcuScan running, and does its status label say it is connected? The interlock."""
    from cuore.live.interlock import mes_status
    return _json(mes_status)


@mcp.tool()
def mes_settings() -> str:
    """MultiEcuScan's own settings from the registry: interfaces, folders, CSV separator."""
    return _via("GET", "/live/mes", ops.mes_settings)


@mcp.tool()
def connect(port: str = "", baud: int = 0, allow_while_mes_connected: bool = False) -> str:
    """Probe the adapter: reset it, read its identity, report vehicle power. Holds nothing.

    Port falls back to OBD_PORT / CUORE_OBD_PORT, then MES's Interface 0; baud likewise.
    """
    return _via("POST", "/live/probe", lambda: ops.probe(port=port, baud=baud,
                allow_while_mes_connected=allow_while_mes_connected),
                query={"port": port, "baud": baud or None,
                       "allow_while_mes_connected": allow_while_mes_connected})


@mcp.tool()
def disconnect() -> str:
    """Release the lock if this process holds it. Nothing is held between calls anyway."""
    from cuore.live import interlock
    interlock.release()
    return _json(lambda: {"released": True, "lock": interlock.read_lock()})


@mcp.tool()
def set_cable(cable: str) -> str:
    """Declare the adapter cable fitted: none, blue_a5 (CAN-IHS) or grey_a6 (CAN-CH).

    Clears every bus verification; run verify_bus before transmitting on a bus.
    """
    return _via("POST", "/live/cable", lambda: ops.set_cable(cable), body={"cable": cable})


@mcp.tool()
def buses() -> str:
    """The three Giorgio buses, their reachability under the declared cable, and verification."""
    return _via("GET", "/live/buses", ops.buses)


@mcp.tool()
def modules(bus: str = "") -> str:
    """The module table: bus, 29-bit address, confidence, presence on this car."""
    return _via("GET", "/live/modules", lambda: ops.modules(bus or None), query={"bus": bus})


@mcp.tool()
def verify_bus(bus: str = "can_c", seconds: float = 2.0) -> str:
    """Passive listen (receive only, no ACK). Marks the bus verified if traffic is seen.

    Optional: reads run this automatically when the bus has no fresh proof.
    """
    return _via("POST", "/live/verify", lambda: ops.verify_bus(bus, seconds=seconds),
                body={"bus": bus, "seconds": seconds})


@mcp.tool()
def capture(bus: str = "can_c", seconds: float = 2.0, max_frames: int = 500,
            filters: Optional[list[str]] = None, include_frames: bool = False,
            state_note: str = "") -> str:
    """Passive raw frame capture on a bus. Works with the Security Gateway locked.

    filters: pass filters like "7E8,7FF" or "18DAF110,1FFFFFFF".
    state_note: car state for the saved raw-frame file header, e.g. "parked idle,
    wheel centred". Raw frames are saved under bus_captures/<vin>/ (see
    raw_capture_file in the result). Any DBC decoding of them is an UNVERIFIED scale.
    """
    return _via("POST", "/live/capture",
                lambda: ops.capture(bus, seconds=seconds, max_frames=max_frames,
                                    filters=filters, include_frames=include_frames,
                                    state_note=state_note),
                body={"bus": bus, "seconds": seconds, "max_frames": max_frames,
                      "filters": filters, "include_frames": include_frames,
                      "state_note": state_note},
                timeout=seconds + 60)


# --- legislated OBD reads ---------------------------------------------------

@mcp.tool()
def read_dtcs() -> str:
    """Stored (confirmed) codes. Mode 03. Per ECU, JSON."""
    return _via("GET", "/live/obd/dtcs", lambda: ops.obd_dtcs("stored"), query={"kind": "stored"})


@mcp.tool()
def read_pending_dtcs() -> str:
    """Pending codes. Mode 07."""
    return _via("GET", "/live/obd/dtcs", lambda: ops.obd_dtcs("pending"), query={"kind": "pending"})


@mcp.tool()
def read_permanent_dtcs() -> str:
    """Permanent codes. Mode 0A."""
    return _via("GET", "/live/obd/dtcs", lambda: ops.obd_dtcs("permanent"),
                query={"kind": "permanent"})


@mcp.tool()
def read_pid(pid: str) -> str:
    """Live Mode 01 PID, decoded. Hex like "0C" or a name like engine_rpm."""
    return _via("GET", f"/live/obd/pid/{pid}", lambda: ops.obd_pid(pid))


@mcp.tool()
def read_voltage() -> str:
    """Battery voltage at the OBD port (ATRV)."""
    return _via("GET", "/live/obd/voltage", ops.obd_voltage)


@mcp.tool()
def read_supported_pids() -> str:
    """Which Mode 01 PIDs each ECU supports."""
    return _via("GET", "/live/obd/supported", ops.obd_supported_pids)


@mcp.tool()
def read_freeze_frame(pid: str = "") -> str:
    """Mode 02 freeze frame. Empty pid reads the DTC that set it."""
    return _via("GET", "/live/obd/freeze", lambda: ops.obd_freeze_frame(pid), query={"pid": pid})


@mcp.tool()
def read_vin() -> str:
    """VIN via Mode 09 PID 02."""
    return _via("GET", "/live/obd/vin", ops.obd_vin)


@mcp.tool()
def read_readiness() -> str:
    """Readiness monitors since clear and this drive cycle, counters, EVAP verdict."""
    return _via("GET", "/live/obd/readiness", ops.obd_readiness)


# --- UDS, read-only ---------------------------------------------------------

@mcp.tool()
def read_module_dtcs(code: str, vin: str = "", mask: int = 255, confirm: bool = False,
                     detail: bool = False) -> str:
    """UDS 0x19 02 on one module (ECM, TCM, BCM, IPC, RFHUB...). Codes in MES form P0456-00.

    confirm=True is required on CAN-CH (brakes, airbag, steering). By default
    (detail=False) the DTC list is summarised to active codes, history codes,
    a tracked count and the full records for the active codes only -- a
    module like the ECM otherwise lists every one of the ~278 codes it
    tracks, active or not. Pass detail=True for the full untouched reply.
    """
    return _via("GET", f"/live/module/{code}/dtcs",
                lambda: ops.module_dtcs(code, vin=vin, mask=mask, confirm=confirm, detail=detail),
                query={"vin": vin, "mask": mask, "confirm": confirm, "detail": detail})


@mcp.tool()
def read_module_identity(code: str, vin: str = "", confirm: bool = False) -> str:
    """ISO 14229 Annex C identity of one module: VIN, part and software numbers."""
    return _via("GET", f"/live/module/{code}/identity",
                lambda: ops.module_identity(code, vin=vin, confirm=confirm),
                query={"vin": vin, "confirm": confirm})


@mcp.tool()
def name_responders(vin: str) -> str:
    """Propose a module name for each stored discovery responder by matching its identity
    strings with the MES log text (SCAN_*/FESLog_*), citing log and line. No car contact;
    proposals only, nothing is promoted."""
    return _via("GET", "/live/responders", lambda: {**responders.list_responders(vin), "naming": responders.name_responders(vin)},
                query={"vin": vin, "propose": True})


@mcp.tool()
def accept_responder(vin: str, address: str, module: str) -> str:
    """Owner decision: promote a stored responder address (e.g. 29 or 18DA29F1) to
    'confirmed (owner)' for a module code (e.g. DTCM). No car contact."""
    return _via("POST", "/live/responders/accept",
                lambda: responders.accept_responder(vin, address, module),
                body={"vin": vin, "address": address, "module": module})


@mcp.tool()
def read_did(code: str, did: str, vin: str = "", confirm: bool = False) -> str:
    """UDS 0x22 ReadDataByIdentifier on one module. did is hex, e.g. F190 or 195A."""
    return _via("GET", f"/live/module/{code}/did/{did}",
                lambda: ops.module_did(code, did, vin=vin, confirm=confirm),
                query={"vin": vin, "confirm": confirm})


@mcp.tool()
def scan_modules(bus: str = "can_c", vin: str = "", mask: int = 255, confirm: bool = False,
                 detail: bool = False) -> str:
    """UDS DTC sweep over every confirmed module on a bus.

    By default (detail=False) each module's DTC list is summarised to active
    codes, history codes, a tracked count and the full records for the active
    codes only, instead of every code the module tracks. Pass detail=True for
    the full untouched reply per module.
    """
    return _via("GET", "/live/scan",
                lambda: ops.scan_modules(bus, vin=vin, mask=mask, confirm=confirm, detail=detail),
                query={"bus": bus, "vin": vin, "mask": mask, "confirm": confirm, "detail": detail},
                timeout=300)


@mcp.tool()
def discover_modules(bus: str = "can_c", vin: str = "", confirm: bool = False,
                     candidates: Optional[list[str]] = None, per_target_timeout: float = 0.25,
                     stop_after: Optional[int] = None) -> str:
    """Address discovery: 22 F190 at each candidate target byte. Any reply, positive or
    negative, proves a node; its Annex C identity is matched to this car's Table A
    hardware/software numbers to name it. Pass vin to persist confirmations for this car.
    candidates are hex target bytes.
    """
    return _via("POST", "/live/discover",
                lambda: ops.discover(bus, vin=vin, confirm=confirm, candidates=candidates,
                                     per_target_timeout=per_target_timeout,
                                     stop_after=stop_after),
                body={"bus": bus, "vin": vin, "confirm": confirm, "candidates": candidates,
                      "per_target_timeout": per_target_timeout, "stop_after": stop_after},
                timeout=600)


@mcp.tool()
def audit_log(n: int = 50) -> str:
    """Recent audit-log entries: every session, cable declaration, discovery and capture."""
    return _via("GET", "/live/audit",
                lambda: {"path": str(audit.log_path()), "entries": audit.read_recent(n)},
                query={"n": n})


@mcp.tool()
def verify_repair(codes: str, module: str = "ECM", vin: str = "", read: bool = True,
                  confirm: bool = False) -> str:
    """After a repair and clear: has each named test re-run, and did it pass?

    Reads the module's UDS status byte for each code (codes="P0455,P0456,P0440")
    and says per code: failing / failed since clear / not run since clear / passed
    since clear, with an overall verdict and a timeline of every earlier real read.
    read=False gives the timeline only, without touching the car.
    """
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    return _via("GET", f"/live/module/{module}/repair",
                lambda: ops.repair_status(code_list, module=module, vin=vin, read=read,
                                          confirm=confirm),
                query={"codes": ",".join(code_list), "vin": vin, "read": read,
                       "confirm": confirm})


@mcp.tool()
def read_mode06(mids: str = "") -> str:
    """OBD Mode $06: the ECM's measured on-board test results against its own limits.

    Includes the EVAP leak tests (MIDs 39-3D) summarised as value vs limit, pass/fail.
    mids="3C,3B" reads just those; empty discovers what the ECM supports.
    """
    mid_list = [m.strip() for m in mids.split(",") if m.strip()]
    return _via("GET", "/live/obd/mode06", lambda: ops.obd_mode06(mid_list or None),
                query={"mids": ",".join(mid_list)})


@mcp.tool()
def read_dtc_detail(code: str, dtc: str, vin: str = "", confirm: bool = False) -> str:
    """One code on one module: status bits, snapshot records and extended data (counters)."""
    return _via("GET", f"/live/module/{code}/dtc/{dtc}",
                lambda: ops.module_dtc_detail(code, dtc, vin=vin, confirm=confirm),
                query={"vin": vin, "confirm": confirm})


@mcp.tool()
def read_all_module(code: str, vin: str = "", include_unverified: bool = True,
                    confirm: bool = False) -> str:
    """Identity plus every catalogued identifier for one module (ECM, TCM, BCM, IPC, RFHUB...),
    decoded with its formula where known; confidence shown per item."""
    return _via("GET", f"/live/module/{code}/all",
                lambda: ops.module_read_all(code, vin=vin, include_unverified=include_unverified,
                                            confirm=confirm),
                query={"vin": vin, "include_unverified": include_unverified, "confirm": confirm},
                timeout=300)


@mcp.tool()
def discover_module_dids(code: str, vin: str = "", ranges: str = "", max_dids: int = 2000,
                         confirm: bool = False) -> str:
    """Read-only 0x22 sweep for identifiers not in the catalogue. ranges "F180-F1FF,1000-10FF"."""
    rng = [r.strip() for r in ranges.split(",") if r.strip()] or None
    return _via("POST", f"/live/module/{code}/discover-dids",
                lambda: ops.module_discover_dids(code, vin=vin, ranges=rng, max_dids=max_dids,
                                                 confirm=confirm),
                body={"vin": vin, "ranges": rng, "max_dids": max_dids, "confirm": confirm},
                timeout=900)


@mcp.tool()
def service_dids_plan(vin: str) -> str:
    """Service-value discovery plan plus the values MES logged for this car (16000 km, 365 days,
    odometer, last service date). No car contact. Candidates stay unconfirmed until the value
    changes after a real reset."""
    def local() -> dict[str, Any]:
        from cuore.live import service_dids
        return {"expected": service_dids.expected_values(vin), "plan": service_dids.plan(vin)}
    return _via("GET", "/live/service-dids/plan", local, query={"vin": vin})


@mcp.tool()
def service_dids_discover(vin: str, max_seconds: float = 180) -> str:
    """Read-only UDS 0x22 sweep of the cluster/ECM, matched against the MES-logged service values.
    Refused while MES holds the adapter or a live poll session runs. Never writes."""
    def local() -> dict[str, Any]:
        from cuore.live import service_dids
        return service_dids.run(vin, max_seconds=max_seconds)
    return _via("POST", "/live/service-dids/discover", local,
                body={"vin": vin, "max_seconds": max_seconds}, timeout=max_seconds + 120)


@mcp.tool()
def service_dids_results(vin: str) -> str:
    """Last service-value discovery candidates with status and the next step. No car contact."""
    def local() -> dict[str, Any]:
        from cuore.live import service_dids
        return service_dids.results(vin)
    return _via("GET", "/live/service-dids/results", local, query={"vin": vin})



@mcp.tool()
def proxi_discover(vin: str) -> str:
    """Read-only UDS 0x22 sweep of the Body computer (BCM, CAN-C) for the vehicle configuration block;
    ranks candidates, never promotes one. Refused while MES holds the adapter. Never writes."""
    def local() -> dict[str, Any]:
        from cuore.live import proxi_read
        return proxi_read.discover(vin)
    return _via("POST", "/live/proxi/discover", local, body={"vin": vin}, timeout=1800)


@mcp.tool()
def proxi_accept(vin: str, did: str, reason: str) -> str:
    """Record the owner's acceptance of one candidate identifier as the PROXI block, with the reason
    (for example "matches MES CAN Setup screenshot of <date>"). No car contact."""
    def local() -> dict[str, Any]:
        from cuore.live import proxi_read
        return proxi_read.accept_candidate(vin, did, reason)
    return _via("POST", "/live/proxi/accept", local, body={"vin": vin, "did": did, "reason": reason})


@mcp.tool()
def proxi_read(vin: str) -> str:
    """One read-only 0x22 read of the accepted PROXI identifier, saved, with a byte diff against the
    previous read. Never writes."""
    def local() -> dict[str, Any]:
        from cuore.live import proxi_read as pr
        return pr.read(vin)
    return _via("POST", "/live/proxi/read", local, body={"vin": vin}, timeout=300)


@mcp.tool()
def learn_capture(bus: str = "can_c", seconds: float = 20.0) -> str:
    """Passive capture while wiTECH reads live data (splitter cable); lists identifiers seen."""
    return _via("POST", "/live/learn/capture", lambda: ops.learn_capture(bus, seconds=seconds),
                body={"bus": bus, "seconds": seconds}, timeout=seconds + 90)


@mcp.tool()
def learn_correlate(capture: str, marks_json: str) -> str:
    """Rank identifiers against values noted in wiTECH. marks_json: [{"t":12.4,"label":"EVAP
    switch","value":"Closed"}, ...] with t in seconds from the capture start."""
    marks = json.loads(marks_json)
    return _via("POST", "/live/learn/correlate", lambda: ops.learn_correlate(capture, marks),
                body={"capture": capture, "marks": marks})


@mcp.tool()
def learned_dids(vin: str = "") -> str:
    """Identifier mappings learned from dealer-tool captures."""
    return _via("GET", "/live/learned", lambda: ops.learned_dids(vin), query={"vin": vin})


@mcp.tool()
def full_scan(vin: str = "", buses: Optional[list[str]] = None, budget_s: float = 0,
             confirm: bool = False) -> str:
    """One read-only full-vehicle scan: VIN/cal, every DTC status plus freeze frame for
    every supported PID, readiness, Mode 06, a Mode 01 snapshot, and a UDS sweep (DTCs,
    identity, a short known-DID list) on every bus the declared cable reaches. Replaces
    the 15-call manual sequence in docs/handbook/07-first-live-session.md; see that doc
    for the fallback if a step needs to be run by hand. ``buses`` defaults to trying both
    can_ihs and can_ch (only the ones the declared cable actually reaches run; the rest
    show up in the result's coverage as not reachable, with why). Returns a coverage
    summary; every reading is separately recorded as an observation (read_* tools/
    the dossier/health report pick those up without replaying this call."""
    return _via("POST", "/live/fullscan",
                lambda: fullscan.run(vin, buses=buses, budget_s=budget_s or None,
                                     confirm=confirm),
                body={"vin": vin, "buses": buses, "budget_s": budget_s or None,
                      "confirm": confirm},
                timeout=max(300.0, (budget_s or 0) + 60))


@mcp.tool()
def read_fullscan_last() -> str:
    """The most recent full_scan() result (coverage summary), without re-running it."""
    return _via("GET", "/live/fullscan/last", fullscan.last)


@mcp.tool()
def guided_scan_start(vin: str = "") -> str:
    """Start a resumable guided full scan for the coloured bypass cables: runs CAN-C in full
    (no cable needed) then pauses, returning which cable to fit next (blue A5 -> CAN-IHS)
    and the modules it unlocks. One scan_id covers the whole session. Refuses if a guided
    scan is already open -- continue, skip, or abandon it first."""
    return _via("POST", "/live/fullscan/guided/start", lambda: fullscan.run_guided(vin),
               body={"vin": vin})


@mcp.tool()
def guided_scan_state() -> str:
    """The open (or most recently closed) guided scan: scan_id, which segments are done/
    skipped/pending, coverage so far, and what to do next (if anything)."""
    return _via("GET", "/live/fullscan/guided/state", fullscan.guided_state)


@mcp.tool()
def guided_scan_continue(scan_id: str, cable_fitted: str) -> str:
    """Declare the cable just fitted (blue_a5, grey_a6, or "none" on the closing step),
    verify its bus with a passive listen, sweep its modules, and pause for the next step --
    or close the session on the final "remove the cable" step. cable_fitted must match what
    the open session is waiting for."""
    return _via("POST", "/live/fullscan/guided/continue",
               lambda: fullscan.continue_guided(scan_id, cable_fitted),
               body={"scan_id": scan_id, "cable_fitted": cable_fitted})


@mcp.tool()
def guided_scan_skip(scan_id: str) -> str:
    """Skip the guided scan's currently paused-on cable segment (no cable on hand) --
    recorded as "not reachable: skipped, needs <cable>", never silently dropped."""
    return _via("POST", "/live/fullscan/guided/skip", lambda: fullscan.skip_guided(scan_id),
               body={"scan_id": scan_id})


@mcp.tool()
def learn_actuator(capture: str, module: str, name: str, tool: str = "MES") -> str:
    """Extract a replayable actuator-test procedure for one module from a learn_capture file.

    FCA does not publish InputOutputControl/RoutineControl identifiers: this only works
    after learn_capture recorded a real actuator test run once in MultiEcuScan or wiTECH.
    Classifies the procedure replayable or not (no SecurityAccess, no configuration/reflash/
    reset service) and works out its terminating request. In-process: this only parses a
    saved capture file, it never opens the adapter.
    """
    return _json(lambda: ops.learn_actuator(capture, module, name, tool))


@mcp.tool()
def list_actuators(vin: str = "") -> str:
    """Learned actuator-test procedures: module, name, tool, and whether they replay (and why not)."""
    return _via("GET", "/live/actuators", lambda: ops.actuators(vin), query={"vin": vin})


@mcp.tool()
def run_actuator(module: str, name: str, consent: str = "", vin: str = "", max_seconds: float = 10.0,
                 confirm: bool = False, request_id: str = "") -> str:
    """Replay a learned actuator test (UDS 0x2F InputOutputControl / 0x31 RoutineControl).

    MCP-only, in-process (no run route over HTTP: writes stay off HTTP by design). A PERSON must
    approve this exact call first: the first call is refused and returns a request_id and the
    CUORE page /approve/<request_id>; the person reads it and types the consent phrase THERE
    (the phrase is shown only on that page). Then repeat the same call with request_id.
    `consent` is ignored and authorises nothing. Also refuses unless the module is not safety-critical
    (ABS, EPS, ORC, HALF, DASM, ESL/NBS, TVM, TCM, ESM, DTCM, RFHUB, or anything on CAN-CH --
    use MultiEcuScan or wiTECH for those, never a replay here);
    the learned procedure is replayable; and the vehicle reads engine-off and stationary
    (refuses if RPM or speed cannot be read, not just if they are nonzero). Bounded to
    max_seconds (hard cap 30 s, counting learned gaps and request timeouts). Returning control
    to the ECU -- and the module to its default session -- is ALWAYS ATTEMPTED afterwards, even
    if a step's response is an NRC or sending raises, and counts only if the module accepts it:
    read "outcome", "control_returned" and "session_restored"; if either is false, switch the
    ignition off at once. Adopts cuore's cable declaration first.
    """
    def body() -> Any:
        _sync_cable()
        return ops.run_actuator(vin, module, name, max_seconds=max_seconds,
                                confirm=confirm, request_id=request_id)
    return _gated(body)


@mcp.tool()
def clear_module_dtcs(code: str, consent: str = "", vin: str = "", confirm: bool = False,
                      override_speed_check: bool = False, request_id: str = "") -> str:
    """Clear ONE module's DTCs (UDS 0x14) after saving every code, snapshot and counter.

    DESTRUCTIVE to evidence. A PERSON must approve this exact call first: the first call is
    refused and returns a request_id and the CUORE page /approve/<request_id>; the person types
    the consent phrase THERE. Then repeat the same call with request_id. `consent` is ignored
    and authorises nothing. Refuses while moving; confirm=True required on CAN-CH. Reads back and flags codes that
    return immediately (live faults). A clear is not a repair: use verify_repair later.
    In-process by design (no write route on HTTP); adopts cuore's cable declaration first.
    """
    def body() -> Any:
        _sync_cable()
        return ops.clear_module_dtcs(code, vin=vin, confirm=confirm,
                                     override_speed_check=override_speed_check,
                                     request_id=request_id)
    return _gated(body)


# --- the two MCP-only surfaces ------------------------------------------------

@mcp.tool()
def clear_dtcs(confirm: bool = False, override_speed_check: bool = False,
               consent: str = "", request_id: str = "", vin: str = "") -> str:
    """Clear stored DTCs, freeze frames and readiness. Mode 04. DESTRUCTIVE. MCP-only.

    Needs confirm=True AND a PERSON's approval: the first call is refused and returns a
    request_id and the CUORE page /approve/<request_id>; the person types the consent phrase
    THERE. Then repeat the same call with request_id. `consent` is ignored and authorises
    nothing; vin is shown to the person. Captures stored, pending
    and permanent codes, the freeze-frame DTC and readiness to a file first, refuses while
    the vehicle reports motion, refuses while MultiEcuScan is connected or a live-data poll
    holds the adapter, and reads back afterwards.
    """
    if not confirm:
        audit.record("clear_dtcs_refused", reason="confirm=True missing")
        return json.dumps({"refused": "pass confirm=True; this destroys the freeze-frame "
                                      "evidence and resets readiness monitors"}, indent=2)

    def body() -> dict[str, Any]:
        _sync_cable()
        ops._poller_active_guard()
        lk = link()
        with lk.session("clear_dtcs", bus=CAN_C) as sess:
            sess.untarget()
            out: dict[str, Any] = {"cleared": False}
            q = sess.query("010D", "41")
            speed = None
            for _h, data in q["ecus"].items():
                if len(data) >= 3 and data[1] == "0D":
                    speed = int(data[2], 16)
                    break
            out["vehicle_speed_kmh"] = speed
            if speed is None and not override_speed_check:
                raise LiveError("could not read vehicle speed (ignition off or bus error); "
                                "refusing to clear. Pass override_speed_check=True if the car "
                                "is stationary and you accept that.")
            if speed:   # the override is for an unreadable speed only, never for a moving car
                raise LiveError(f"vehicle speed is {speed} km/h; refusing to clear while moving")
            before = {k: ops._dtc_read(sess, m, r, k) for k, (m, r) in ops._KINDS.items()}
            before["freeze_frame_dtc"] = sess.query("020200", "42")["raw"]
            before["readiness"] = ops.readiness_in(sess)
            d = state_dir() / "clears"
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"clear_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            record = {"captured_at": datetime.now().isoformat(timespec="seconds"),
                      "port": lk.port, "before": before}
            path.write_text(json.dumps(record, indent=2), encoding="utf-8")
            out["evidence_file"] = str(path)
            out["before"] = {k: before[k].get("dtcs") for k in ops._KINDS}
            raw = sess.cmd("04", 6)
            out["clear_raw"] = raw
            err = adapter_error(raw)
            if err:
                out["error"] = f"clear did not complete: {err}"
                # the request was transmitted: it belongs in the audit log either way
                audit.record("clear_dtcs", acknowledged=False, error=err, raw=raw[:200],
                             evidence=str(path))
                return out
            acked = any(d and d[0] == "44" for d in reassemble(raw, headers_on=True).values())
            out["acknowledged"] = acked
            after = ops._dtc_read(sess, "03", "43", "stored")
            out["after"] = {"stored": after.get("dtcs"), "error": after.get("error")}
            out["cleared"] = acked and not after.get("dtcs") and not after.get("error")
            if acked and after.get("dtcs"):
                out["note"] = ("codes still present immediately after the clear: the fault is "
                               "live and re-set at once, or the module refused the erase")
            out["reminder"] = ("readiness monitors are now incomplete; a clean re-scan proves "
                               "nothing until they run again. Use read_readiness.")
            record["after"] = out
            path.write_text(json.dumps(record, indent=2), encoding="utf-8")
            audit.record("clear_dtcs", acknowledged=acked, evidence=str(path))
            return out

    def gated() -> Any:
        grant = consent_gate.authorize(
            consent_gate.Action(tool="clear_dtcs", module="ALL", service="04", vin=vin,
                                args={"confirm": True,
                                      "override_speed_check": bool(override_speed_check)}),
            request_id)                    # consumed here: before any traffic
        return _in_scope(grant, body)

    return _gated(gated)


@mcp.tool()
def send_raw(command: str, timeout_seconds: float = DEFAULT_TIMEOUT,
             i_understand_this_writes_to_the_vehicle: bool = False,
             allow_adapter_reconfiguration: bool = False,
             allow_while_mes_connected: bool = False, bus: str = "can_c",
             confirm: bool = False, module: str = "", consent: str = "",
             request_id: str = "", vin: str = "") -> str:
    """One AT/ST/OBD/UDS command on the adapter with the reply parsed. MCP-only.

    Reads (OBD modes 01-03/05-07/09/0A and UDS 19/22/3E) need nothing extra. ANY OTHER service is
    treated as a VEHICLE WRITE (UDS 10/11/14/28/2C/2F/3D/87 ..., and services not on the read
    allowlist) and needs ALL of: i_understand_this_writes_to_the_vehicle=True,
    module=<target module code, e.g. ECM>, and a PERSON's approval: the first call is refused and
    returns a request_id and the CUORE page /approve/<request_id>; the person types the consent
    phrase THERE. Then repeat the same call with request_id. `consent` is ignored and authorises
    nothing; vin is shown to the person. Writes are refused outright on ABS, EPS, ORC (airbag),
    HALF, DASM, ESL, TVM, TCM, ESM, DTCM, RFHUB (immobiliser), IPC (odometer) and anything on
    CAN-CH; UDS 27/2E/31/34/36/37/85 are blocked on every module; ATSH, STPX and Mode 04 are
    not accepted as writes here (use clear_dtcs for Mode 04). Writes also refuse while
    MultiEcuScan is connected (allow_while_mes_connected is ignored) or a live-data poll holds
    the adapter. Adapter reconfiguration needs allow_adapter_reconfiguration=True and lasts
    only this call; monitor modes are refused (use capture). One command per call.
    """
    def refuse(why: str, **extra: Any) -> str:
        audit.record("send_raw_refused", command=command[:80], reason=why, module=module or None)
        return json.dumps({"refused": why, "command": command, **extra}, indent=2)

    try:
        cmd = validate_command(command)
    except LiveError as e:
        return refuse(str(e))
    kind, reason = classify_command(cmd)
    if kind == "blocked":
        return refuse(reason)
    if kind == "read" and consent_gate.gated_service(cmd) is not None:
        # classify_command is a deny-list; the gate is an allowlist. A hex service that is not on
        # the read allowlist is treated as a write rather than trusted as a read.
        kind, reason = "vehicle_write", (f"service 0x{consent_gate.gated_service(cmd)} is not on "
                                         "the read allowlist, so it is treated as a write")
    write_ecu = None
    grant = None
    if kind == "vehicle_write":
        if not i_understand_this_writes_to_the_vehicle:
            return refuse(reason, kind=kind,
                          how_to_proceed="pass i_understand_this_writes_to_the_vehicle=True "
                                         "plus module=; a person must then approve the call on the "
                                         "CUORE approve page (the first call returns its address); "
                                         "prefer MultiEcuScan for FCA actuator tests")
        try:
            known = _addressing.by_code(module.strip().upper()) if module.strip() else None
            if module.strip() and known is None:
                raise Refused(f"unknown module code {module!r}")
            # structural gates (no module, Mode 04, AT/ST, blocklists, CAN-CH); the phrase argument
            # is the canonical one because the person types it on the approve page, not here
            assert_raw_write_allowed(cmd, module, raw_write_phrase(cmd, module.strip().upper()),
                                     bus_key=known.bus_key if known else "")
            write_ecu = ops.uds_mod.resolve_module(module.strip())
            grant = consent_gate.authorize(
                consent_gate.Action(
                    tool="send_raw", module=write_ecu.code,
                    service=cmd.upper().replace(" ", "")[:2], vin=vin,
                    args={"command": cmd.upper().replace(" ", ""), "bus": write_ecu.bus_key,
                          "confirm": bool(confirm)}),
                request_id)                # consumed here: before any traffic
        except ConsentRequired as e:
            audit.record("send_raw_refused", command=command[:80], module=module or None,
                         reason="approval required", request_id=e.info.get("request_id"))
            return json.dumps({**e.payload(cuore_client.base_url()), "command": command}, indent=2)
        except (Refused, LiveError) as e:
            return refuse(str(e), kind=kind)
        allow_while_mes_connected = False
    if kind == "adapter_state" and not allow_adapter_reconfiguration:
        return json.dumps({"refused": reason, "command": cmd, "kind": kind,
                           "how_to_proceed": "pass allow_adapter_reconfiguration=True; the change "
                                             "lasts only for this call"}, indent=2)

    def body() -> dict[str, Any]:
        _sync_cable()
        if write_ecu is not None:
            ops._poller_active_guard()
        b = ops._bus(write_ecu.bus_key if write_ecu is not None else bus)
        # Pure adapter commands (ATI, ATRV, STPRS, ATDPN, STI, STDI, ...) and
        # adapter reconfiguration are passive: they never put a frame on the
        # vehicle bus, so the bus-silence guard (auto-verify / the transmit
        # gate) must not apply to them. Anything else that reaches the wire
        # still has to transmit on the bus, so it must pass the transmit gate
        # and must not run under STCMM 0 (receive-only, no ACK).
        passive = kind == "adapter_state" or is_adapter_only(cmd)
        with link().session(f"send_raw {cmd}", bus=b, passive=passive, confirm=confirm,
                            allow_while_mes_connected=allow_while_mes_connected) as sess:
            audit.record("send_raw_request", command=cmd, kind=kind, bus=b.key, passive=passive,
                         module=write_ecu.code if write_ecu is not None else None)
            if write_ecu is not None:
                sess.target(write_ecu)
            raw = sess.cmd(cmd, timeout_seconds)
            err = adapter_error(raw)
            out: dict[str, Any] = {"command": cmd, "kind": kind, "raw": raw, "bus": b.key}
            if err:
                out["error"] = err
            elif cmd[:2].upper() not in ("AT", "ST"):
                out["ecus"] = reassemble(raw, headers_on=sess.headers_on)
            audit.record("send_raw", command=cmd, kind=kind, error=err or None, raw=raw[:200])
            return out

    if grant is not None:
        return _gated(lambda: _in_scope(grant, body))
    return _json(body)


@mcp.tool()
def coverage(action: str = "status", vin: str = "", pass_key: str = "",
             confirm: bool = False, reason: str = "",
             engine_running: Optional[bool] = None) -> str:
    """Whole-vehicle coverage across CAN-C, grey A6 (CAN-CH) and blue A5 (CAN-IHS).

    action: "status" | "start" (needs vin) | "run" (needs pass_key) | "skip"
    (needs pass_key) | "report" | "reset". Passes, in order: c_first (baseline,
    no cable), ch (grey), ihs (blue), c_final (re-read, no cable). The final
    re-read is diffed against the baseline so codes set by cable re-plugs are
    reported as bystanders. The ch pass transmits on the brakes/airbag bus and
    needs confirm=True. Read-only throughout; nothing is cleared.
    """
    routes = {
        "status": ("GET", "/live/coverage", None),
        "start": ("POST", "/live/coverage/start",
                  {"vin": vin, "engine_running": engine_running}),
        "run": ("POST", "/live/coverage/run", {"key": pass_key, "confirm": confirm}),
        "skip": ("POST", "/live/coverage/skip", {"key": pass_key, "reason": reason}),
        "report": ("GET", "/live/coverage/report", None),
        "reset": ("POST", "/live/coverage/reset", None),
    }

    def body() -> Any:
        if action == "status":
            return ops.coverage_status()
        if action == "start":
            return ops.coverage_start(vin, engine_running=engine_running)
        if action == "run":
            return ops.coverage_run(pass_key, confirm=confirm)
        if action == "skip":
            return ops.coverage_skip(pass_key, reason)
        if action == "report":
            return ops.coverage_report()
        if action == "reset":
            return ops.coverage_reset()
        return {"error": f"unknown action {action!r}"}
    if action not in routes:
        return _json(body)
    method, path, payload = routes[action]
    return _via(method, path, body, body=payload, timeout=900)


# --- live-data engine ------------------------------------------------------

@mcp.tool()
def live_channels() -> str:
    """Channel registry for the live-data engine: every Mode 01 PID, every catalogued
    UDS DID for ECM/TCM/BCM/IPC/RFHUB (with confidence), computed channels (boost) and
    battery voltage -- plus presets (engine_basics, boost, evap_job, transmission, tpms)."""
    return _via("GET", "/live/channels", ops.live_channels)


@mcp.tool()
def live_session_start(channels: Optional[list[str]] = None, preset: str = "",
                       rates_json: str = "", monitor_dtcs: bool = False,
                       dtc_interval_s: float = 10.0, code_watch: bool = False) -> str:
    """Start a live-data poll session (code_watch=True adds the read-only new-code alert): round-robins the given channels (and/or preset) at
    their configured rates, holding the adapter until stopped. Read-only (Mode 01, UDS
    0x22, ATRV) but refuses other live operations while it runs, and itself refuses while
    MultiEcuScan is connected. rates_json overrides per-channel Hz, e.g. '{"engine_rpm": 10}'.

    monitor_dtcs (MultiEcuScan's "Monitor DTCs" convention): every dtc_interval_s seconds
    (minimum 5, default 10) the poller also reads Mode 03/07 between channel reads and, on
    any change, publishes it on the live stream, writes a "DTC+/- <code> stored|pending" TAG
    entry into any active recording, and records an observation.
    """
    rates = json.loads(rates_json) if rates_json else None
    body: dict[str, Any] = {"channels": channels, "preset": preset, "rates": rates}
    if monitor_dtcs:
        body["monitor_dtcs"] = True
        body["dtc_interval_s"] = dtc_interval_s
    if code_watch:
        body["code_watch"] = True
    return _via("POST", "/live/session/start",
                lambda: ops.live_session_start(channels, preset=preset, rates=rates,
                                               monitor_dtcs=monitor_dtcs,
                                               dtc_interval_s=dtc_interval_s,
                                               code_watch=code_watch),
                body=body)


@mcp.tool()
def live_session_stop() -> str:
    """Stop the running live-data poll session and release the adapter."""
    return _via("POST", "/live/session/stop", ops.live_session_stop)


@mcp.tool()
def live_snapshot() -> str:
    """Latest value (and alarm state) of every channel in the running live-data session."""
    return _via("GET", "/live/snapshot", ops.live_snapshot)


# --- media library ---------------------------------------------------------
#
# Pure HTTP-client tools: evidence media (photos, scans, borescope clips)
# lives in cuore's state directory, written through cuore's own API
# (cuore.live.media), so there is no in-process fallback to offer here --
# unlike _via's adapter tools, a media read with cuore unreachable has
# nothing useful to fall back to.

@mcp.tool()
def list_media(vin: str, q: str = "", kind: str = "") -> str:
    """Search a vehicle's evidence media (photos, scans, borescope clips).

    ``q`` matches caption, tags, filename, and target id, case-insensitive.
    ``kind`` narrows to photo|scan|video|document. Hidden items are excluded.
    Requires cuore to be reachable -- there is no in-process fallback.
    """
    try:
        return json.dumps(cuore_client.call(
            "GET", f"/vehicles/{vin}/media", query={"q": q, "kind": kind}), indent=2)
    except cuore_client.CuoreTimeout as e:
        return json.dumps({"error": str(e), "kind": "Timeout"}, indent=2)
    except cuore_client.CuoreUnavailable as e:
        return json.dumps({"error": str(e), "kind": "Unavailable"}, indent=2)


@mcp.tool()
def media_note(id: str, caption: str = "", tags: str = "") -> str:
    """Edit a media item's caption and/or tags (comma-separated). Leaves either
    alone when left blank. Requires cuore to be reachable."""
    query: dict[str, Any] = {}
    if caption:
        query["caption"] = caption
    if tags:
        query["tags"] = tags
    try:
        return json.dumps(cuore_client.call("POST", f"/media/{id}", query=query), indent=2)
    except cuore_client.CuoreTimeout as e:
        return json.dumps({"error": str(e), "kind": "Timeout"}, indent=2)
    except cuore_client.CuoreUnavailable as e:
        return json.dumps({"error": str(e), "kind": "Unavailable"}, indent=2)


# ===========================================================================
# ADDITIVE: bus capture + learn-a-signal (cuore/api/buscapture.py,
# cuore.live.buscapture). New block, appended at the end on purpose --
# nothing above this line is touched. Same _via posture as every other
# adapter tool above: cuore (the adapter's one owner) first, in-process
# fallback only if cuore cannot be reached at all.
# ===========================================================================

from cuore.live import buscapture as _buscapture  # noqa: E402


@mcp.tool()
def bus_capture_start(bus: str) -> str:
    """Start a passive bus capture on ``bus`` (``can_ihs`` or ``can_ch``).

    Refuses if no bypass cable is declared for that bus (blue A5 for
    CAN-IHS, grey A6 for CAN-CH -- see ``set_cable``) or if the adapter is
    held by the live poller or MultiEcuScan.
    """
    return _via("POST", f"/buscapture/{bus}/start", lambda: _buscapture.capture_start(bus))


@mcp.tool()
def bus_capture_stop(bus: str) -> str:
    """Stop a running bus capture on ``bus``. Frames already read are kept
    for ``bus_capture_save``."""
    return _via("POST", f"/buscapture/{bus}/stop", lambda: _buscapture.capture_stop(bus))


@mcp.tool()
def bus_capture_save(bus: str, vin: str = "") -> str:
    """Save a stopped bus capture on ``bus`` to a CSV recording (same wire
    format cuore's own live sessions use) tagged with the bus, declared
    cable and time, and log it as a from-car ``"bus_capture"`` observation
    for ``vin`` so the Scans area can show it."""
    return _via("POST", f"/buscapture/{bus}/save", lambda: _buscapture.capture_save(bus, vin=vin),
               body={"vin": vin})


@mcp.tool()
def learn_start(bus: str, action: str) -> str:
    """Start a learn capture on ``bus``: the same passive listen as
    ``bus_capture_start``, tagged with the physical action about to be
    performed (e.g. "press the brake pedal") so ``learn_stop`` can rank
    which CAN id/byte changed with it."""
    return _via("POST", f"/buscapture/{bus}/learn/start",
               lambda: _buscapture.learn_start(bus, action), body={"action": action})


@mcp.tool()
def learn_stop(bus: str) -> str:
    """Stop a learn capture on ``bus`` and return the ranked ``(CAN id, byte
    offset)`` candidates -- the bytes that changed the most while the
    action was held. Naming and saving one is a web action (``/v/{vin}/
    learn``), not exposed here."""
    return _via("POST", f"/buscapture/{bus}/learn/stop", lambda: _buscapture.learn_stop(bus))


# ===========================================================================
# ADDITIVE: learn module DIDs by listening to MES over a second adapter
# (cuore/api/mes_learn.py, cuore.live.mes_learn). New block, appended at the
# end on purpose -- nothing above this line is touched. Same _via posture as
# every other adapter tool above: cuore (the adapter's one owner) first,
# in-process fallback only if cuore cannot be reached at all.
# ===========================================================================

from cuore.live import mes_learn as _mes_learn  # noqa: E402


@mcp.tool()
def mes_learn_start(port: str, vin: str = "") -> str:
    """Start listening passively on ``port`` -- a SECOND adapter (another
    STN/vLinker on its own COM port, or a USB-CAN interface) wired to a
    Y-splitter on CAN-C (pins 6/14), alongside MultiEcuScan's own adapter.
    Refuses if ``port`` is MES's own port or only one adapter is detected at
    all -- both name exactly what hardware is missing. Never transmits."""
    return _via("POST", "/mes-learn/start", lambda: _mes_learn.start(port, vin=vin),
               body={"port": port, "vin": vin})


@mcp.tool()
def mes_learn_stop(csv: str = "") -> str:
    """Stop the listener and align every UDS request/response it overheard
    against ``csv`` (an MES CSV recording -- bare filename or full path).
    Each named column MES graphed is fit by least squares against every
    module/DID/byte-field this session saw; a column clears the bar at R²
    >= 0.98 over >= 20 distinct raw values, else it is reported "no
    confident match" rather than guessed."""
    return _via("POST", "/mes-learn/stop", lambda: _mes_learn.stop(csv=csv), body={"csv": csv})


@mcp.tool()
def mes_learn_status() -> str:
    """Poll the running (or just-stopped) MES-learn listener."""
    return _via("GET", "/mes-learn/status", lambda: _mes_learn.status())


@mcp.tool()
def mes_learn_review(vin: str = "") -> str:
    """Read-only: the newest stored procedure review (services, 0x27, writes,
    replay verdict) and gate result for the MES-learn captures of ``vin``.
    Nothing is replayed. Also shown on ``/v/{vin}/learn-mes``."""
    return _via("GET", "/mes-learn/review", lambda: _mes_learn.latest_review(vin))


@mcp.tool()
def mes_learn_candidates() -> str:
    """Fit candidates from the last alignment, with their fit numbers (R²,
    scale, offset, sample count) -- review on ``/v/{vin}/learn-mes`` before
    accepting."""
    return _via("GET", "/mes-learn/candidates", lambda: _mes_learn.candidates())


@mcp.tool()
def mes_learn_accept(candidate_id: str, vin: str, name: str) -> str:
    """Accept a fit candidate: saved through ``cuore.live.learned`` as a
    MES-learned, scaled DID mapping (confidence ``SINGLE-SOURCE (learned)``,
    never a catalogue DID) -- usable by the Live board as a named channel."""
    return _via("POST", f"/mes-learn/candidates/{candidate_id}/accept",
               lambda: _mes_learn.accept(candidate_id, vin, name), body={"vin": vin, "name": name})


from cuore.live import decode_confirm as _decode_confirm  # noqa: E402


@mcp.tool()
def decode_confirm_run(vin: str, mes_log_path: str, cuore_recording_path: str, tolerance: float = 0.05,
                       mes_interval_s: float = 0.0, mes_start: str = "", mode: str = "static") -> str:
    """Offline, no car contact. mode=static (default): MES and CUORE logs made one after the other,
    cut by tag number 1-4 (1 ign on/engine off/pedal up, 2 pedal down, 3 warm idle, 4 2000 rpm),
    medians compared per condition. mode=timestamp: pair a time-stamped MES graph CSV with a CUORE
    live-session CSV (state dir recordings/live_*.csv) row by time and
    value. Per CUORE channel: confirmed | wrong_scale (with the proposed transform) | no_data |
    ambiguous, sample count, fitted transform, residual. Saved under decode_confirm/<run_id>.json;
    nothing is changed until decode_confirm_accept."""
    body = {"vin": vin, "mes_log_path": mes_log_path, "cuore_recording_path": cuore_recording_path,
            "tolerance": tolerance, "mes_interval_s": mes_interval_s or None, "mes_start": mes_start, "mode": mode}
    return _via("POST", "/live/decode-confirm/run",
                lambda: _decode_confirm.run(vin, mes_log_path, cuore_recording_path, tolerance=tolerance,
                                            mes_interval_s=mes_interval_s or None, mes_start=mes_start, mode=mode),
                body=body)


@mcp.tool()
def decode_confirm_accept(vin: str, run_id: str, channel: str, confirm_pairing: bool = False) -> str:
    """Offline, no car contact: write one confirmed / wrong_scale verdict of a saved run into
    did_overrides.json (read by did_catalog at load time; the shipped catalogue is not edited).
    A candidate MES pairing needs confirm_pairing=true. Sensor health drops its suspect flag."""
    return _via("POST", "/live/decode-confirm/accept",
                lambda: _decode_confirm.accept(vin, run_id, channel, confirm_pairing=confirm_pairing),
                body={"vin": vin, "run_id": run_id, "channel": channel, "confirm_pairing": confirm_pairing})


if __name__ == "__main__":
    mcp.run()
