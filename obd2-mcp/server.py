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


def _hex_pairs(s: str) -> list[str]:
    """Extract hex byte pairs, ignoring headers/CAN frame markers/whitespace."""
    tokens = []
    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper() in ("NO DATA", "OK", "?", "UNABLE TO CONNECT",
                            "BUS INIT: ERROR", "SEARCHING..."):
            continue
        if ":" in line:  # CAN multi-frame line prefix like "0:"
            line = line.split(":", 1)[1]
        parts = line.split()
        if parts and len(parts[0]) == 3:  # CAN header e.g. "7E8"
            parts = parts[1:]
        for p in parts:
            if len(p) == 2 and all(c in "0123456789ABCDEFabcdef" for c in p):
                tokens.append(p.upper())
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
        letter = {"0": "P", "4": "P", "1": "C", "5": "C",
                  "2": "B", "6": "B", "3": "U", "7": "U"}.get(a[0].upper(), "P")
        # low 2 bits of top nibble go into the DTC's high nibble
        top_nibble = format(int(a[0], 16) & 0x3, "X")
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
    pairs = _hex_pairs(raw)
    dtcs = _decode_dtcs(pairs, "43")
    if not dtcs:
        return f"stored DTCs: (none)\nraw: {raw!r}"
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
                skip = 3  # skip 49, 02, 01
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
def send_raw(command: str, timeout_seconds: float = DEFAULT_TIMEOUT) -> str:
    """Send an arbitrary command to the ELM327 (AT... or OBD hex) and return response.

    Escape hatch for AT commands like ATRV (battery voltage), ATDP (describe
    protocol), ATSH (set header), or manual mode-service queries.
    """
    raw = _cmd(command, timeout=timeout_seconds)
    return f"{command} -> {raw!r}"


if __name__ == "__main__":
    mcp.run()
