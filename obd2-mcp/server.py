"""OBD-II MCP server.

Talks to any ELM327-compatible dongle over a serial COM port and exposes generic
OBD-II Mode 01/02/03/04/07/09 operations as MCP tools.

Does NOT implement FCA/Alfa-specific actuator tests — those require MES.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import serial
import serial.tools.list_ports
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("obd2")


@dataclass
class Conn:
    ser: Optional[serial.Serial] = None
    port: Optional[str] = None
    baud: int = 38400
    protocol: str = "auto"


STATE = Conn()

DEFAULT_PORT = os.environ.get("OBD_PORT")  # e.g. "COM3"
DEFAULT_BAUD = int(os.environ.get("OBD_BAUD", "38400"))
DEFAULT_TIMEOUT = float(os.environ.get("OBD_TIMEOUT", "4"))

# Common OBD-II Mode 01 PIDs, name -> (pid, formula, unit)
PIDS: dict[str, tuple[str, str]] = {
    "engine_coolant_temp":     ("05", "C"),
    "short_fuel_trim_b1":      ("06", "%"),
    "long_fuel_trim_b1":       ("07", "%"),
    "short_fuel_trim_b2":      ("08", "%"),
    "long_fuel_trim_b2":       ("09", "%"),
    "fuel_pressure":           ("0A", "kPa"),
    "intake_map":              ("0B", "kPa"),
    "engine_rpm":              ("0C", "rpm"),
    "vehicle_speed":           ("0D", "km/h"),
    "timing_advance":          ("0E", "deg"),
    "intake_air_temp":         ("0F", "C"),
    "maf":                     ("10", "g/s"),
    "throttle_position":       ("11", "%"),
    "o2_b1s1_voltage":         ("14", "V"),
    "runtime_since_start":     ("1F", "s"),
    "distance_with_mil":       ("21", "km"),
    "fuel_rail_pressure":      ("23", "kPa"),
    "commanded_evap_purge":    ("2E", "%"),
    "fuel_level":              ("2F", "%"),
    "warmups_since_clear":     ("30", "count"),
    "distance_since_clear":    ("31", "km"),
    "evap_vapor_pressure":     ("32", "Pa"),
    "barometric_pressure":     ("33", "kPa"),
    "control_module_voltage":  ("42", "V"),
    "absolute_load":           ("43", "%"),
    "commanded_afr":           ("44", "ratio"),
    "ambient_air_temp":        ("46", "C"),
    "fuel_type":               ("51", "code"),
    "ethanol_percent":         ("52", "%"),
    "evap_vapor_pressure_abs": ("53", "kPa"),
    "engine_oil_temp":         ("5C", "C"),
    "engine_fuel_rate":        ("5E", "L/h"),
}


def _open(port: str, baud: int) -> serial.Serial:
    return serial.Serial(port=port, baudrate=baud, timeout=DEFAULT_TIMEOUT,
                         write_timeout=DEFAULT_TIMEOUT)


def _write(cmd: str) -> None:
    if not STATE.ser:
        raise RuntimeError("not connected. Call connect(port=...) first.")
    STATE.ser.reset_input_buffer()
    STATE.ser.write((cmd.strip() + "\r").encode("ascii"))
    STATE.ser.flush()


def _read_until_prompt(timeout: float = DEFAULT_TIMEOUT) -> str:
    """Read from ELM327 until '>' prompt or timeout."""
    if not STATE.ser:
        raise RuntimeError("not connected")
    deadline = time.time() + timeout
    buf = bytearray()
    while time.time() < deadline:
        b = STATE.ser.read(1)
        if not b:
            continue
        buf.extend(b)
        if b == b">":
            break
    return buf.decode("ascii", errors="replace").replace("\r", "\n").strip(" \n>")


def _cmd(cmd: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    _write(cmd)
    return _read_until_prompt(timeout)


#: Adapter/bus conditions that must never be silently discarded. The v1 filter
#: dropped only the benign ones and let the rest fall through a length test
#: that quietly removed them, so a bus fault was indistinguishable from "no
#: codes" -- the worst possible failure mode for a diagnostic tool.
ADAPTER_ERRORS = (
    "BUFFER FULL", "CAN ERROR", "BUS BUSY", "BUS ERROR", "STOPPED",
    "DATA ERROR", "FB ERROR", "UNABLE TO CONNECT", "BUS INIT: ERROR",
    "ERR", "RX ERROR", "LV RESET", "ACT ALERT",
)

#: Benign and genuinely ignorable.
BENIGN_LINES = ("OK", "NO DATA", "SEARCHING...", "?", "STOPPED SEARCHING")

_HEX_DIGITS = set("0123456789ABCDEF")


def adapter_error(s: str) -> str:
    """Return the adapter/bus error present in a response, or "".

    Checked before parsing so callers can surface the real condition instead
    of reporting an empty result.
    """
    up = s.upper()
    for err in ADAPTER_ERRORS:
        if err in up:
            return err
    return ""


def _hex_pairs(s: str) -> list[str]:
    """Extract hex bytes from an ELM327 response.

    Handles both spaced (``41 0C 0B 4C``) and unspaced (``410C0B4C``) output.
    That distinction is not cosmetic: ``connect()`` issues ``ATS0`` (spaces
    off), so on this server every response arrives contiguous. The v1 parser
    split on whitespace and then kept only 2-character tokens, which matches
    nothing in an 8-character run -- so it returned an empty list for
    essentially every read, and every DTC and PID query silently reported
    nothing while still echoing the raw string that made it look fine.
    """
    tokens: list[str] = []
    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue
        up = line.upper()
        if up in BENIGN_LINES or adapter_error(up):
            continue
        # ISO-TP multi-line responses are prefixed "0:", "1:", ... Strip the
        # index but keep the payload.
        if ":" in line:
            head, _, tail = line.partition(":")
            if len(head.strip()) <= 2:
                line = tail
        parts = line.split()
        # Drop a CAN header (3 hex chars for 11-bit, 8 for 29-bit) when
        # headers are enabled. Only when the line has more than one token:
        # with spaces off, an 8-character run is a data blob, not a 29-bit
        # header, and stripping it would discard the whole response.
        if len(parts) > 1 and len(parts[0]) in (3, 8) and all(
                c in _HEX_DIGITS for c in parts[0].upper()):
            parts = parts[1:]
        blob = "".join(parts).upper()
        if not blob or any(c not in _HEX_DIGITS for c in blob):
            continue
        if len(blob) % 2:
            blob = blob[:-1]          # odd trailing nibble is truncation
        tokens.extend(blob[i:i + 2] for i in range(0, len(blob), 2))
    return tokens


def _decode_dtcs(pairs: list[str], mode_response_byte: str) -> list[str]:
    """Given hex bytes from a Mode 03/07/0A response, extract DTCs.

    ELM strips the response byte for us in most cases, but we look for it and
    then read (count) followed by DTC pairs. If no header found, assume all
    pairs form DTC bytes.
    """
    idx = 0
    if pairs and pairs[0] == mode_response_byte:
        idx = 2  # skip response byte + count byte
    dtcs = []
    while idx + 1 < len(pairs):
        a, b = pairs[idx], pairs[idx + 1]
        idx += 2
        if a == "00" and b == "00":
            continue
        # ISO 15031-6 / SAE J2012: the DTC category lives in bits 15-14 of the
        # two-byte code, i.e. the top two bits of the first nibble.
        #   0x0-0x3 -> P (powertrain)   0x4-0x7 -> C (chassis)
        #   0x8-0xB -> B (body)         0xC-0xF -> U (network)
        # v1 mapped 1->C, 2->B, 3->U, which is wrong for every non-P code and
        # silently renders C0561 as P0561. P-codes decoded correctly, which is
        # exactly why the bug survived: this car's body and chassis modules
        # store almost exclusively U and C codes.
        try:
            high = int(a[0], 16)
        except ValueError:
            continue
        letter = "PCBU"[high >> 2]
        top_nibble = format(high & 0x3, "X")
        dtc = f"{letter}{top_nibble}{a[1]}{b}"
        dtcs.append(dtc)
    return dtcs


@mcp.tool()
def list_ports() -> str:
    """List serial ports on this machine. Look for FTDI or Silicon Labs devices."""
    ports = serial.tools.list_ports.comports()
    if not ports:
        return "(no serial ports found)"
    lines = []
    for p in ports:
        lines.append(f"{p.device}\t{p.description}\tHWID={p.hwid}")
    return "\n".join(lines)


@mcp.tool()
def connect(port: str = "", baud: int = 0) -> str:
    """Open the OBD dongle. Runs ELM327 init sequence and sets protocol=auto.

    Args:
        port: COM port name (e.g. "COM3"). Falls back to OBD_PORT env var.
        baud: baud rate. Common: 38400 (default), 9600, 115200.

    NOTE: only one program can hold the COM port. Close MultiEcuScan first.
    """
    port = port or DEFAULT_PORT or ""
    baud = baud or DEFAULT_BAUD
    if not port:
        return "ERROR: no port given and OBD_PORT env var not set. Call list_ports() first."

    if STATE.ser and STATE.ser.is_open:
        STATE.ser.close()

    try:
        STATE.ser = _open(port, baud)
    except Exception as e:
        STATE.ser = None
        return f"ERROR opening {port}@{baud}: {e}"

    STATE.port = port
    STATE.baud = baud

    # ELM327 init sequence
    log = []
    for c in ("ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP0"):
        try:
            r = _cmd(c, timeout=3)
        except Exception as e:
            log.append(f"{c}: FAILED ({e})")
            continue
        log.append(f"{c} -> {r!r}")

    # Ask ELM its ID
    try:
        ident = _cmd("ATI", timeout=2)
        log.append(f"ATI -> {ident!r}")
    except Exception:
        pass

    return f"Connected {port}@{baud}\n" + "\n".join(log)


@mcp.tool()
def disconnect() -> str:
    """Close the OBD dongle port."""
    if STATE.ser and STATE.ser.is_open:
        STATE.ser.close()
    STATE.ser = None
    return "disconnected"


@mcp.tool()
def status() -> str:
    """Report current connection state."""
    if not STATE.ser or not STATE.ser.is_open:
        return "not connected"
    return f"connected: port={STATE.port} baud={STATE.baud}"


@mcp.tool()
def read_dtcs() -> str:
    """Read stored (confirmed) diagnostic trouble codes. Mode 03.

    Returns list of DTCs like ['P0455', 'P0440', 'P0456'] or '(none)'.
    """
    raw = _cmd("03")
    err = adapter_error(raw)
    if err:
        return (f"ADAPTER/BUS ERROR: {err}\n"
                f"This is NOT 'no codes' - the read did not complete.\n"
                f"raw: {raw!r}")
    pairs = _hex_pairs(raw)
    dtcs = _decode_dtcs(pairs, "43")
    if not dtcs:
        scope = ("Note: Mode 03 returns emissions-related powertrain codes "
                 "only. Body, chassis and network faults are UDS 3-byte codes "
                 "read via service 0x19 and will not appear here.")
        return f"stored DTCs: (none)\n{scope}\nraw: {raw!r}"
    return f"stored DTCs: {', '.join(dtcs)}\nraw: {raw!r}"


@mcp.tool()
def read_pending_dtcs() -> str:
    """Read pending DTCs (single failure, not yet confirmed). Mode 07."""
    raw = _cmd("07")
    pairs = _hex_pairs(raw)
    dtcs = _decode_dtcs(pairs, "47")
    if not dtcs:
        return f"pending DTCs: (none)\nraw: {raw!r}"
    return f"pending DTCs: {', '.join(dtcs)}\nraw: {raw!r}"


@mcp.tool()
def read_permanent_dtcs() -> str:
    """Read permanent DTCs (cannot be cleared without repair). Mode 0A."""
    raw = _cmd("0A")
    pairs = _hex_pairs(raw)
    dtcs = _decode_dtcs(pairs, "4A")
    if not dtcs:
        return f"permanent DTCs: (none)\nraw: {raw!r}"
    return f"permanent DTCs: {', '.join(dtcs)}\nraw: {raw!r}"


@mcp.tool()
def clear_dtcs(confirm: bool = False) -> str:
    """Clear stored DTCs + freeze frame + monitor readiness. Mode 04.

    DESTRUCTIVE. Pass confirm=True to actually clear. This wipes emissions
    readiness monitors and may take multiple drive cycles to rebuild.
    """
    if not confirm:
        return "refused: pass confirm=True to actually clear DTCs and reset readiness monitors."
    raw = _cmd("04")
    return f"clear result: {raw!r}"


@mcp.tool()
def read_freeze_frame(pid: str = "") -> str:
    """Read freeze-frame data captured when the DTC was set. Mode 02.

    Args:
        pid: hex PID to query (e.g. "0C" for RPM). Empty = read the DTC that
             triggered the freeze frame (PID 02).
    """
    q = pid.strip().upper() or "02"
    raw = _cmd(f"02 {q} 00")
    return f"freeze frame PID {q}: {raw!r}"


@mcp.tool()
def read_pid(pid: str) -> str:
    """Read a live PID (Mode 01). Pass a hex PID like "0C" or a friendly name.

    Friendly names: engine_rpm, vehicle_speed, engine_coolant_temp,
    intake_air_temp, ambient_air_temp, fuel_level, commanded_evap_purge,
    evap_vapor_pressure, evap_vapor_pressure_abs, short_fuel_trim_b1,
    long_fuel_trim_b1, control_module_voltage, throttle_position, maf,
    intake_map, barometric_pressure, engine_oil_temp, engine_fuel_rate ...
    """
    if pid in PIDS:
        hex_pid, unit = PIDS[pid]
    else:
        hex_pid = pid.strip().upper().replace("0X", "")
        unit = "raw"
        if len(hex_pid) == 1:
            hex_pid = "0" + hex_pid

    raw = _cmd(f"01 {hex_pid}")
    pairs = _hex_pairs(raw)
    # response starts with 41 <pid> then data bytes
    data = []
    for i, tok in enumerate(pairs):
        if tok == "41" and i + 1 < len(pairs) and pairs[i + 1] == hex_pid:
            data = pairs[i + 2:]
            break
    return f"PID {hex_pid} ({pid}) unit={unit}: data={data} raw={raw!r}"


@mcp.tool()
def read_supported_pids() -> str:
    """Ask the ECU which Mode 01 PIDs it supports (queries 00,20,40,60,80,A0,C0)."""
    out = []
    for base in ("00", "20", "40", "60", "80", "A0", "C0"):
        raw = _cmd(f"01 {base}")
        out.append(f"01 {base} -> {raw!r}")
        # if the 4th data byte's low bit is 0, next block not supported
    return "\n".join(out)


@mcp.tool()
def read_vin() -> str:
    """Read the vehicle VIN. Mode 09 PID 02."""
    raw = _cmd("09 02")
    pairs = _hex_pairs(raw)
    # response 49 02 01 <17 ASCII bytes across multi-frame>
    ascii_bytes = []
    started = False
    skip = 0
    for tok in pairs:
        if not started:
            if tok == "49":
                started = True
                # The response is 49 02 01 <17 ASCII>. This branch already
                # consumes the 49 via its own `continue`, so only 02 and 01
                # remain to skip. v1 used 3 here and ate the first VIN
                # character, returning a 16-character VIN that still looked
                # plausible.
                skip = 2
            continue
        if skip:
            skip -= 1
            continue
        try:
            n = int(tok, 16)
            if 32 <= n < 127:
                ascii_bytes.append(chr(n))
        except ValueError:
            pass
    vin = "".join(ascii_bytes)
    return f"VIN: {vin!r} raw: {raw!r}"


@mcp.tool()
def send_raw(command: str, timeout_seconds: float = DEFAULT_TIMEOUT,
             i_understand_this_writes_to_the_vehicle: bool = False) -> str:
    """Send an arbitrary command to the ELM327 (AT... or OBD hex).

    Escape hatch for AT commands like ATRV (battery voltage), ATDP (describe
    protocol), or manual read-only service queries.

    Write operations are refused unless explicitly unlocked. Without that gate
    this tool was a hole straight through every other safety check: while
    ``clear_dtcs`` demands ``confirm=True``, ``send_raw("04")`` cleared codes
    with no confirmation at all, and UDS ``0x2F`` could command actuators --
    physically moving hardware on a real car -- from a tool documented as
    read-only.
    """
    cmd = command.strip().upper()
    blocked = _classify_write(cmd)
    if blocked and not i_understand_this_writes_to_the_vehicle:
        return (
            f"refused: {blocked}\n"
            f"command: {command!r}\n"
            "This writes to the vehicle rather than reading from it. If you "
            "genuinely intend it, pass "
            "i_understand_this_writes_to_the_vehicle=True.\n"
            "For FCA actuator tests and adaptations, prefer MultiEcuScan - it "
            "enforces per-vehicle preconditions that a raw command does not."
        )
    raw = _cmd(command, timeout=timeout_seconds)
    return f"{command} -> {raw!r}"


#: UDS services that change vehicle state, mapped to what they actually do.
_WRITE_SERVICES = {
    "14": "UDS ClearDiagnosticInformation - erases DTCs and readiness monitors",
    "27": "UDS SecurityAccess - repeated failures can lock the module out",
    "2E": "UDS WriteDataByIdentifier - writes configuration to a module",
    "2F": "UDS InputOutputControl - physically actuates hardware",
    "31": "UDS RoutineControl - runs adaptations and service routines",
    "34": "UDS RequestDownload - reflashing, can brick a module",
    "35": "UDS RequestUpload - reflashing related",
    "36": "UDS TransferData - reflashing, can brick a module",
    "37": "UDS RequestTransferExit - reflashing related",
}


def _classify_write(cmd: str) -> str:
    """Describe why a command is a write, or "" if it is read-only."""
    compact = cmd.replace(" ", "")

    if compact.startswith("AT"):
        # ATSH redirects requests to an arbitrary ECU, which turns any
        # following service byte into a write against an unintended module.
        if compact.startswith("ATSH"):
            return ("ATSH redirects requests to another module, which can "
                    "turn a following command into a write to an "
                    "unintended ECU")
        return ""

    if not compact or any(c not in _HEX_DIGITS for c in compact):
        return ""

    # Mode 04 is the legacy OBD-II clear.
    if compact in ("04", "0400"):
        return ("OBD-II Mode 04 - clears DTCs and resets readiness monitors. "
                "Use clear_dtcs(confirm=True), which says so plainly")

    service = compact[:2]
    return _WRITE_SERVICES.get(service, "")


if __name__ == "__main__":
    mcp.run()
