"""OBD-II / live-link MCP server: thin tool wrappers over ``cuore.live``.

Everything that touches the adapter lives in ``cuore/live``; this file only
exposes it as MCP tools, keeps the tool names earlier Claude sessions know,
and adds the two things that belong on the MCP surface rather than in HTTP:

* ``send_raw`` with its consent flags (vehicle writes, adapter reconfiguration);
* ``clear_dtcs`` with evidence capture, a speed check and a read-back. It is
  the only vehicle write anywhere in the toolchain.

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
import cuore_client  # noqa: E402  -- sibling module; this directory is on sys.path
from cuore.live import audit  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.config import state_dir  # noqa: E402
from cuore.live.errors import LiveError  # noqa: E402
from cuore.live.framing import adapter_error, reassemble  # noqa: E402
from cuore.live.obd import decode_obd_dtcs  # noqa: E402
from cuore.live.safety import classify_command, validate_command  # noqa: E402
from cuore.live.transport import DEFAULT_TIMEOUT, link  # noqa: E402

# Name this process in the advisory lock so the bench UI can show "held by
# obd2-mcp" rather than mistaking it for itself.
link().process = "obd2-mcp"

mcp = FastMCP("obd2")


def _json(fn: Callable[[], Any]) -> str:
    try:
        return json.dumps(fn(), indent=2)
    except LiveError as e:
        return json.dumps({"error": str(e), "kind": type(e).__name__}, indent=2)
    except Exception as e:  # serial or OS failures mid-operation
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2)


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
            filters: Optional[list[str]] = None, include_frames: bool = False) -> str:
    """Passive raw frame capture on a bus. Works with the Security Gateway locked.

    filters: pass filters like "7E8,7FF" or "18DAF110,1FFFFFFF".
    """
    return _via("POST", "/live/capture",
                lambda: ops.capture(bus, seconds=seconds, max_frames=max_frames,
                                    filters=filters, include_frames=include_frames),
                body={"bus": bus, "seconds": seconds, "max_frames": max_frames,
                      "filters": filters, "include_frames": include_frames},
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
def run_actuator(module: str, name: str, consent: str, vin: str = "", max_seconds: float = 10.0,
                 confirm: bool = False) -> str:
    """Replay a learned actuator test (UDS 0x2F InputOutputControl / 0x31 RoutineControl).

    MCP-only, in-process (no run route over HTTP: writes stay off HTTP by design). Refuses
    unless consent is exactly "ACTUATE <MODULE> <NAME>" (e.g. "ACTUATE ECM EVAPORATION
    CONTROL VALVE"), or "RUN ROUTINE <MODULE> <NAME>" when the procedure starts a module routine
    (routine IDs are opaque and may be adaptation resets); the module is not safety-critical
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
        return ops.run_actuator(vin, module, name, consent, max_seconds=max_seconds,
                                confirm=confirm)
    return _json(body)


@mcp.tool()
def clear_module_dtcs(code: str, consent: str, vin: str = "", confirm: bool = False,
                      override_speed_check: bool = False) -> str:
    """Clear ONE module's DTCs (UDS 0x14) after saving every code, snapshot and counter.

    DESTRUCTIVE to evidence. consent must be exactly "CLEAR <MODULE>" (e.g. "CLEAR ECM").
    Refuses while moving; confirm=True required on CAN-CH. Reads back and flags codes that
    return immediately (live faults). A clear is not a repair: use verify_repair later.
    In-process by design (no write route on HTTP); adopts cuore's cable declaration first.
    """
    def body() -> Any:
        _sync_cable()
        return ops.clear_module_dtcs(code, consent, vin=vin, confirm=confirm,
                                     override_speed_check=override_speed_check)
    return _json(body)


# --- the two MCP-only surfaces ------------------------------------------------

@mcp.tool()
def clear_dtcs(confirm: bool = False, override_speed_check: bool = False) -> str:
    """Clear stored DTCs, freeze frames and readiness. Mode 04. DESTRUCTIVE. MCP-only.

    Captures stored, pending and permanent codes, the freeze-frame DTC and readiness to
    a file first, refuses while the vehicle reports motion, and reads back afterwards.
    """
    if not confirm:
        return json.dumps({"refused": "pass confirm=True; this destroys the freeze-frame "
                                      "evidence and resets readiness monitors"}, indent=2)

    def body() -> dict[str, Any]:
        _sync_cable()
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
            if speed and not override_speed_check:
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

    return _json(body)


@mcp.tool()
def send_raw(command: str, timeout_seconds: float = DEFAULT_TIMEOUT,
             i_understand_this_writes_to_the_vehicle: bool = False,
             allow_adapter_reconfiguration: bool = False,
             allow_while_mes_connected: bool = False, bus: str = "can_c",
             confirm: bool = False) -> str:
    """One AT/ST/OBD/UDS command on the adapter with the reply parsed. MCP-only.

    Vehicle writes need i_understand_this_writes_to_the_vehicle=True; adapter
    reconfiguration needs allow_adapter_reconfiguration=True and lasts only this call;
    monitor modes are refused (use capture). One command per call.
    """
    try:
        cmd = validate_command(command)
    except LiveError as e:
        return json.dumps({"refused": str(e), "command": command}, indent=2)
    kind, reason = classify_command(cmd)
    if kind == "blocked":
        return json.dumps({"refused": reason, "command": cmd}, indent=2)
    if kind == "vehicle_write" and not i_understand_this_writes_to_the_vehicle:
        return json.dumps({"refused": reason, "command": cmd, "kind": kind,
                           "how_to_proceed": "pass i_understand_this_writes_to_the_vehicle=True; "
                                             "prefer MultiEcuScan for FCA actuator tests"}, indent=2)
    if kind == "adapter_state" and not allow_adapter_reconfiguration:
        return json.dumps({"refused": reason, "command": cmd, "kind": kind,
                           "how_to_proceed": "pass allow_adapter_reconfiguration=True; the change "
                                             "lasts only for this call"}, indent=2)

    def body() -> dict[str, Any]:
        _sync_cable()
        b = ops._bus(bus)
        # Only pure adapter commands are passive: a read request still has to
        # transmit on the bus, so it must pass the transmit gate and must not
        # run under STCMM 0 (receive-only, no ACK).
        passive = kind == "adapter_state"
        with link().session(f"send_raw {cmd}", bus=b, passive=passive, confirm=confirm,
                            allow_while_mes_connected=allow_while_mes_connected) as sess:
            raw = sess.cmd(cmd, timeout_seconds)
            err = adapter_error(raw)
            out: dict[str, Any] = {"command": cmd, "kind": kind, "raw": raw, "bus": b.key}
            if err:
                out["error"] = err
            elif cmd[:2].upper() not in ("AT", "ST"):
                out["ecus"] = reassemble(raw, headers_on=sess.headers_on)
            audit.record("send_raw", command=cmd, kind=kind, error=err or None)
            return out

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
                       rates_json: str = "") -> str:
    """Start a live-data poll session: round-robins the given channels (and/or preset) at
    their configured rates, holding the adapter until stopped. Read-only (Mode 01, UDS
    0x22, ATRV) but refuses other live operations while it runs, and itself refuses while
    MultiEcuScan is connected. rates_json overrides per-channel Hz, e.g. '{"engine_rpm": 10}'.
    """
    rates = json.loads(rates_json) if rates_json else None
    return _via("POST", "/live/session/start",
                lambda: ops.live_session_start(channels, preset=preset, rates=rates),
                body={"channels": channels, "preset": preset, "rates": rates})


@mcp.tool()
def live_session_stop() -> str:
    """Stop the running live-data poll session and release the adapter."""
    return _via("POST", "/live/session/stop", ops.live_session_stop)


@mcp.tool()
def live_snapshot() -> str:
    """Latest value (and alarm state) of every channel in the running live-data session."""
    return _via("GET", "/live/snapshot", ops.live_snapshot)


if __name__ == "__main__":
    mcp.run()
