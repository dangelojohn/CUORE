"""OBD-II / live-link MCP server: thin tool wrappers over ``cuore.live``.

Everything that touches the adapter lives in ``cuore/live``; this file only
exposes it as MCP tools, keeps the tool names earlier Claude sessions know,
and adds the two things that belong on the MCP surface rather than in HTTP:

* ``send_raw`` with its consent flags (vehicle writes, adapter reconfiguration);
* ``clear_dtcs`` with evidence capture, a speed check and a read-back. It is
  the only vehicle write anywhere in the toolchain.

Both surfaces share one process-wide link, one lock file, one interlock, so
running this server and cuore together cannot open COM3 twice.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from cuore.live import ops  # noqa: E402
from cuore.live import audit  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.config import state_dir  # noqa: E402
from cuore.live.errors import LiveError  # noqa: E402
from cuore.live.framing import adapter_error, reassemble  # noqa: E402
from cuore.live.obd import decode_obd_dtcs  # noqa: E402
from cuore.live.safety import classify_command, validate_command  # noqa: E402
from cuore.live.transport import DEFAULT_TIMEOUT, link  # noqa: E402

mcp = FastMCP("obd2")


def _json(fn: Callable[[], Any]) -> str:
    try:
        return json.dumps(fn(), indent=2)
    except LiveError as e:
        return json.dumps({"error": str(e), "kind": type(e).__name__}, indent=2)
    except Exception as e:  # serial or OS failures mid-operation
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2)


# --- configuration and status ---------------------------------------------

@mcp.tool()
def list_ports() -> str:
    """Serial ports on this machine, with MES's configured port marked."""
    return _json(ops.ports)


@mcp.tool()
def status() -> str:
    """Port and speed in force and their sources, MES state, lock state, declared cable,
    bus verification, and the last adapter identity. The port is never held between calls."""
    return _json(ops.status)


@mcp.tool()
def mes_state() -> str:
    """Is MultiEcuScan running, and does its status label say it is connected? The interlock."""
    from cuore.live.interlock import mes_status
    return _json(mes_status)


@mcp.tool()
def mes_settings() -> str:
    """MultiEcuScan's own settings from the registry: interfaces, folders, CSV separator."""
    return _json(ops.mes_settings)


@mcp.tool()
def connect(port: str = "", baud: int = 0, allow_while_mes_connected: bool = False) -> str:
    """Probe the adapter: reset it, read its identity, report vehicle power. Holds nothing.

    Port falls back to OBD_PORT / CUORE_OBD_PORT, then MES's Interface 0; baud likewise.
    """
    return _json(lambda: ops.probe(port=port, baud=baud,
                                   allow_while_mes_connected=allow_while_mes_connected))


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
    return _json(lambda: ops.set_cable(cable))


@mcp.tool()
def buses() -> str:
    """The three Giorgio buses, their reachability under the declared cable, and verification."""
    return _json(ops.buses)


@mcp.tool()
def modules(bus: str = "") -> str:
    """The module table: bus, 29-bit address, confidence, presence on this car."""
    return _json(lambda: ops.modules(bus or None))


@mcp.tool()
def verify_bus(bus: str = "can_c", seconds: float = 2.0) -> str:
    """Passive listen (receive only, no ACK). Marks the bus verified if traffic is seen."""
    return _json(lambda: ops.verify_bus(bus, seconds=seconds))


@mcp.tool()
def capture(bus: str = "can_c", seconds: float = 2.0, max_frames: int = 500,
            filters: Optional[list[str]] = None, include_frames: bool = False) -> str:
    """Passive raw frame capture on a bus. Works with the Security Gateway locked.

    filters: pass filters like "7E8,7FF" or "18DAF110,1FFFFFFF".
    """
    return _json(lambda: ops.capture(bus, seconds=seconds, max_frames=max_frames,
                                     filters=filters, include_frames=include_frames))


# --- legislated OBD reads ---------------------------------------------------

@mcp.tool()
def read_dtcs() -> str:
    """Stored (confirmed) codes. Mode 03. Per ECU, JSON."""
    return _json(lambda: ops.obd_dtcs("stored"))


@mcp.tool()
def read_pending_dtcs() -> str:
    """Pending codes. Mode 07."""
    return _json(lambda: ops.obd_dtcs("pending"))


@mcp.tool()
def read_permanent_dtcs() -> str:
    """Permanent codes. Mode 0A."""
    return _json(lambda: ops.obd_dtcs("permanent"))


@mcp.tool()
def read_pid(pid: str) -> str:
    """Live Mode 01 PID, decoded. Hex like "0C" or a name like engine_rpm."""
    return _json(lambda: ops.obd_pid(pid))


@mcp.tool()
def read_voltage() -> str:
    """Battery voltage at the OBD port (ATRV)."""
    return _json(ops.obd_voltage)


@mcp.tool()
def read_supported_pids() -> str:
    """Which Mode 01 PIDs each ECU supports."""
    return _json(ops.obd_supported_pids)


@mcp.tool()
def read_freeze_frame(pid: str = "") -> str:
    """Mode 02 freeze frame. Empty pid reads the DTC that set it."""
    return _json(lambda: ops.obd_freeze_frame(pid))


@mcp.tool()
def read_vin() -> str:
    """VIN via Mode 09 PID 02."""
    return _json(ops.obd_vin)


@mcp.tool()
def read_readiness() -> str:
    """Readiness monitors since clear and this drive cycle, counters, EVAP verdict."""
    return _json(ops.obd_readiness)


# --- UDS, read-only ---------------------------------------------------------

@mcp.tool()
def read_module_dtcs(code: str, vin: str = "", mask: int = 255, confirm: bool = False) -> str:
    """UDS 0x19 02 on one module (ECM, TCM, BCM, IPC, RFHUB...). Codes in MES form P0456-00.

    confirm=True is required on CAN-CH (brakes, airbag, steering).
    """
    return _json(lambda: ops.module_dtcs(code, vin=vin, mask=mask, confirm=confirm))


@mcp.tool()
def read_module_identity(code: str, vin: str = "", confirm: bool = False) -> str:
    """ISO 14229 Annex C identity of one module: VIN, part and software numbers."""
    return _json(lambda: ops.module_identity(code, vin=vin, confirm=confirm))


@mcp.tool()
def read_did(code: str, did: str, vin: str = "", confirm: bool = False) -> str:
    """UDS 0x22 ReadDataByIdentifier on one module. did is hex, e.g. F190 or 195A."""
    return _json(lambda: ops.module_did(code, did, vin=vin, confirm=confirm))


@mcp.tool()
def scan_modules(bus: str = "can_c", vin: str = "", mask: int = 255, confirm: bool = False) -> str:
    """UDS DTC sweep over every confirmed module on a bus."""
    return _json(lambda: ops.scan_modules(bus, vin=vin, mask=mask, confirm=confirm))


@mcp.tool()
def discover_modules(bus: str = "can_c", vin: str = "", confirm: bool = False,
                     candidates: Optional[list[str]] = None, per_target_timeout: float = 0.25,
                     stop_after: Optional[int] = None) -> str:
    """Address discovery: send 22 F190 at each candidate target byte; a VIN reply proves the node.

    Pass vin to persist confirmations for this car. candidates are hex target bytes.
    """
    return _json(lambda: ops.discover(bus, vin=vin, confirm=confirm, candidates=candidates,
                                      per_target_timeout=per_target_timeout,
                                      stop_after=stop_after))


@mcp.tool()
def audit_log(n: int = 50) -> str:
    """Recent audit-log entries: every session, cable declaration, discovery and capture."""
    return _json(lambda: {"path": str(audit.log_path()), "entries": audit.read_recent(n)})


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
        b = ops._bus(bus)
        passive = kind in ("read", "adapter_state")
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


if __name__ == "__main__":
    mcp.run()
