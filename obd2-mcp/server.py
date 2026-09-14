"""OBD-II MCP server.

Talks to an ELM327- or STN-compatible adapter over a serial COM port and
exposes generic OBD-II Mode 01/02/03/04/07/09/0A operations as MCP tools.

Design rules (see docs/research/MES_DEEP_INTEGRATION_REVIEW.md, Tier A):

* **Nothing holds the port between calls.** Every tool opens the port for
  the duration of one operation and closes it again, so MultiEcuScan can
  take the adapter the moment a call returns. A process-wide lock serialises
  calls inside this server and an advisory lock file warns other processes.
* **MES is the interlock.** Before opening the port the server checks
  whether ``Multiecuscan.exe`` is running and reads its status label. If
  MES reports itself connected, the open is refused.
* **Configuration comes from MES.** Port, speed, log and export folders are
  read from ``HKLM\\SOFTWARE\\Multiecuscan``. Explicit arguments win over
  ``OBD_PORT``/``OBD_BAUD`` env vars, which win over the registry.
* **Headers on, frames reassembled.** ``ATH1`` is set so every response is
  attributed to the ECU that sent it, and ISO-TP multi-frame responses are
  reassembled here rather than by the adapter.
* **Tools return JSON.** Every result is a JSON object; ``error`` is set
  whenever the read did not complete, so a bus fault never reads as "no
  codes".
* **Writes are gated.** ``send_raw`` classifies each command and refuses
  vehicle writes, adapter reconfiguration and monitor modes unless the
  matching flag is passed. Embedded CR/LF and the STN batch separator are
  rejected outright.

Does NOT implement FCA/Alfa-specific actuator tests; those require MES.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import serial
import serial.tools.list_ports
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("obd2")

IS_WINDOWS = sys.platform == "win32"

DEFAULT_TIMEOUT = float(os.environ.get("OBD_TIMEOUT", "4"))
MIN_TIMEOUT, MAX_TIMEOUT = 0.5, 30.0
FALLBACK_BAUD = 38400          # the ELM327 default, used only when nothing else says
MES_EXE = "Multiecuscan.exe"


class ObdError(Exception):
    """A tool could not complete. The message is returned to the caller as JSON."""


# --------------------------------------------------------------------------
# Configuration: MES registry, env, arguments
# --------------------------------------------------------------------------

MES_REG_PATH = r"SOFTWARE\Multiecuscan"
_REDACTED_PREFIXES = ("Lic Number", "Removal Key")


def mes_registry() -> dict[str, Any]:
    """Read ``HKLM\\SOFTWARE\\Multiecuscan`` (64-bit view). Empty if absent.

    MES keeps its interface, folder and session settings here, readable by
    any user. Licence fields are redacted before they leave this function.
    """
    if not IS_WINDOWS:
        return {}
    import winreg  # noqa: WPS433 - Windows only

    out: dict[str, Any] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, MES_REG_PATH, 0,
                             winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except OSError:
        return {}
    with key:
        i = 0
        while True:
            try:
                name, value, _kind = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            if any(name.startswith(p) for p in _REDACTED_PREFIXES):
                value = "<redacted>"
            out[name] = value
    return out


def mes_folders(reg: dict[str, Any] | None = None) -> dict[str, str]:
    """Resolve MES's LOG and Export folders. ``.`` means the install dir."""
    reg = mes_registry() if reg is None else reg
    install = r"C:\Program Files (x86)\Multiecuscan"
    out = {}
    for key, label in (("LOG Folder", "log_folder"), ("Export Folder", "csv_folder")):
        raw = str(reg.get(key, "") or "")
        if not raw or raw == ".":
            out[label] = install
        else:
            out[label] = str(Path(install, raw)) if not os.path.isabs(raw) else raw
    out["csv_separator"] = str(reg.get("CSV Separator", "") or "")
    return out


def resolve_port(arg: str = "") -> tuple[Optional[str], str]:
    """Port to use and where the decision came from."""
    if arg:
        return arg.strip().upper(), "argument"
    env = os.environ.get("OBD_PORT")
    if env:
        return env.strip().upper(), "env OBD_PORT"
    reg = mes_registry()
    port = reg.get("Interface 0 Port")
    if port:
        return str(port).strip().upper(), "MES registry (Interface 0 Port)"
    return None, "unset"


def resolve_baud(arg: int = 0) -> tuple[int, str]:
    """Baud to use and where the decision came from."""
    if arg:
        return int(arg), "argument"
    env = os.environ.get("OBD_BAUD")
    if env:
        try:
            return int(env), "env OBD_BAUD"
        except ValueError:
            pass
    reg = mes_registry()
    speed = reg.get("Interface 0 Port Speed")
    if speed:
        try:
            return int(speed), "MES registry (Interface 0 Port Speed)"
        except (TypeError, ValueError):
            pass
    return FALLBACK_BAUD, "ELM327 fallback"


# --------------------------------------------------------------------------
# MES liveness: process presence and the read-only status label
# --------------------------------------------------------------------------

def mes_pids() -> list[int]:
    """PIDs of running MES instances, via tasklist (no elevation needed)."""
    if not IS_WINDOWS:
        return []
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {MES_EXE}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.strip().split('","')]
        if len(parts) >= 2 and parts[0].lower() == MES_EXE.lower():
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def _window_texts_for_pids(pids: set[int]) -> list[str]:
    """Text of every window and child window owned by the given PIDs.

    Reading window text with GetWindowTextW works across the UIPI boundary
    (MES runs elevated; this server does not), which is why this is the one
    MES state signal available without running elevated ourselves.
    """
    if not IS_WINDOWS or not pids:
        return []
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    texts: list[str] = []
    buf = ctypes.create_unicode_buffer(512)

    def grab(hwnd: int) -> None:
        n = user32.GetWindowTextW(hwnd, buf, 512)
        if n > 0:
            texts.append(buf.value)

    def child_cb(hwnd, _lparam):
        grab(hwnd)
        return True

    def top_cb(hwnd, _lparam):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            grab(hwnd)
            user32.EnumChildWindows(hwnd, WNDENUMPROC(child_cb), 0)
        return True

    user32.EnumWindows(WNDENUMPROC(top_cb), 0)
    return texts


def mes_status() -> dict[str, Any]:
    """Is MES running, and does its status label say it holds the adapter?

    ``state`` is one of ``not_running``, ``disconnected``, ``connected`` or
    ``unknown``. Only ``connected`` blocks this server; ``unknown`` is
    reported and the port open itself becomes the arbiter.
    """
    pids = mes_pids()
    if not pids:
        return {"running": False, "pids": [], "state": "not_running", "label": None}
    texts = _window_texts_for_pids(set(pids))
    label = None
    state = "unknown"
    for t in texts:
        s = t.strip()
        if s == "Disconnected":
            label, state = s, "disconnected"
            break
        if s.startswith(("Connected", "Connecting")):
            label, state = s, "connected"
            break
    return {"running": True, "pids": pids, "state": state, "label": label}


# --------------------------------------------------------------------------
# Advisory lock file
# --------------------------------------------------------------------------

def _lock_path() -> Path:
    base = os.environ.get("PROGRAMDATA")
    candidates = []
    if base:
        candidates.append(Path(base, "cuore"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local, "obd2-mcp"))
    candidates.append(Path.home() / ".obd2-mcp")
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d / "adapter.lock"
        except OSError:
            continue
    return Path("adapter.lock")


def _pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if not IS_WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def read_lock() -> Optional[dict[str, Any]]:
    p = _lock_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    data["stale"] = not _pid_alive(int(data.get("pid", -1)))
    data["path"] = str(p)
    return data


def _acquire_lock(port: str, purpose: str) -> None:
    existing = read_lock()
    if existing and not existing["stale"] and existing.get("pid") != os.getpid():
        raise ObdError(
            f"adapter lock held by pid {existing.get('pid')} "
            f"({existing.get('purpose', '?')} on {existing.get('port', '?')} "
            f"since {existing.get('since', '?')}). Another obd2 server or tool "
            f"is using the adapter. Lock file: {existing['path']}"
        )
    payload = {"pid": os.getpid(), "port": port, "purpose": purpose,
               "since": datetime.now().isoformat(timespec="seconds"),
               "process": "obd2-mcp"}
    try:
        _lock_path().write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass  # advisory only; the serial open is the real arbiter


def _release_lock() -> None:
    p = _lock_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("pid") == os.getpid():
            p.unlink()
    except (OSError, ValueError):
        pass


# --------------------------------------------------------------------------
# Serial session: lazy open, init, close
# --------------------------------------------------------------------------

#: ELM protocol number -> CAN identifier width. Anything else is treated as
#: headerless (K-line/J1850), where ELM already strips framing for us.
_PROTOCOL_HEADER_BITS: dict[str, int] = {
    "6": 11, "7": 29, "8": 11, "9": 29,           # ELM327 ISO 15765 presets
    "31": 11, "32": 29, "33": 11, "34": 29,       # STN HS-CAN presets
    "35": 11, "36": 29, "51": 11, "52": 29,       # STN 250k and MS-CAN presets
    "53": 11, "54": 29,
}


@dataclass
class State:
    ser: Optional[serial.Serial] = None
    port: Optional[str] = None
    baud: int = 0
    port_source: str = ""
    baud_source: str = ""
    protocol: Optional[str] = None      # pinned ELM/STN protocol number once detected
    headers_on: bool = False
    identity: dict[str, str] = field(default_factory=dict)
    last_open: Optional[str] = None
    lock: threading.RLock = field(default_factory=threading.RLock)


STATE = State()


def _clamp_timeout(t: float) -> float:
    try:
        t = float(t)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return max(MIN_TIMEOUT, min(MAX_TIMEOUT, t))


def _validate_command(cmd: str) -> str:
    """One command, one line. Reject anything that could smuggle a second."""
    if not cmd or not cmd.strip():
        raise ObdError("empty command")
    if "\r" in cmd or "\n" in cmd:
        raise ObdError("command contains a line terminator; one command per call")
    if "|" in cmd:
        raise ObdError("command contains '|', the STN batch separator; one command per call")
    if any(ord(c) > 126 or ord(c) < 32 for c in cmd):
        raise ObdError("command contains non-printable or non-ASCII characters")
    return cmd.strip()


def _cmd(cmd: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Send one command and read until the ``>`` prompt or the deadline."""
    ser = STATE.ser
    if ser is None or not ser.is_open:
        raise ObdError("port is not open (internal error: _cmd outside a session)")
    cmd = _validate_command(cmd)
    timeout = _clamp_timeout(timeout)
    ser.reset_input_buffer()
    ser.write((cmd + "\r").encode("ascii"))
    ser.flush()
    deadline = time.monotonic() + timeout
    buf = bytearray()
    got_prompt = False
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if not chunk:
            continue
        buf.extend(chunk)
        if b">" in chunk:
            got_prompt = True
            break
    text = buf.decode("ascii", errors="replace").replace("\r", "\n")
    text = text.strip(" \n>")
    # Some adapters echo the command even after ATE0 during the same session.
    if text.upper().startswith(cmd.upper()):
        text = text[len(cmd):].lstrip(" \n")
    if not got_prompt:
        # No prompt means the adapter had not finished (still SEARCHING, or
        # dead). Tag it so adapter_error() treats the reply as incomplete
        # rather than letting a partial answer read as "nothing found".
        return (text + "\nTIMEOUT").strip()
    return text


def _looks_like_wrong_baud(reply: str) -> bool:
    """Framing errors decode to U+FFFD or control bytes; real ELM replies never do."""
    return "\ufffd" in reply or any(ord(c) < 32 and c != "\n" for c in reply)


def _init_adapter() -> None:
    """Per-open configuration. Cheap; ATZ is reserved for ``connect``."""
    r = _cmd("ATE0", 2)
    if _looks_like_wrong_baud(r):
        raise ObdError(
            f"adapter replied with framing garbage at {STATE.baud} baud "
            f"({STATE.baud_source}); this is almost always the wrong speed. "
            f"MES's registry says {mes_registry().get('Interface 0 Port Speed', '?')}."
        )
    if r == "TIMEOUT":
        raise ObdError(f"no reply from the adapter on {STATE.port}; is it plugged in?")
    for c in ("ATL0", "ATS0"):
        _cmd(c, 2)
    if STATE.protocol and STATE.protocol not in _PROTOCOL_HEADER_BITS:
        _cmd("ATH0", 2)
        STATE.headers_on = False
    else:
        _cmd("ATH1", 2)
        STATE.headers_on = True
    _cmd(f"ATSP{STATE.protocol}" if STATE.protocol else "ATSP0", 2)


def _maybe_pin_protocol() -> None:
    """After a successful vehicle query, remember which protocol was found."""
    if STATE.protocol:
        return
    r = _cmd("ATDPN", 2).strip().upper()
    m = re.fullmatch(r"A?([0-9A-F]{1,2})", r)
    if m and m.group(1) != "0":
        STATE.protocol = m.group(1)


@contextmanager
def _session(purpose: str, port: str = "", baud: int = 0,
             allow_while_mes_connected: bool = False) -> Iterator[None]:
    """Open the adapter for one operation and close it afterwards."""
    with STATE.lock:
        p, psrc = resolve_port(port)
        b, bsrc = resolve_baud(baud)
        if not p:
            raise ObdError("no port configured: pass port=, set OBD_PORT, or configure "
                           "Interface 0 in MultiEcuScan's settings")
        ms = mes_status()
        if ms["state"] == "connected" and not allow_while_mes_connected:
            raise ObdError(
                f"MultiEcuScan is connected to the vehicle (label {ms['label']!r}, "
                f"pids {ms['pids']}). Disconnect in MES first, or pass "
                f"allow_while_mes_connected=True if you are sure it is not on {p}."
            )
        _acquire_lock(p, purpose)
        try:
            ser = serial.Serial(port=p, baudrate=b, timeout=0.25, write_timeout=2)
        except (serial.SerialException, OSError) as e:
            _release_lock()
            hint = ""
            if "denied" in str(e).lower() or "PermissionError" in str(e):
                hint = (" The port is held by another process: MES (if connected), "
                        "another obd2 server instance, or a terminal program.")
            raise ObdError(f"could not open {p}@{b} ({psrc}, {bsrc}): {e}.{hint}")
        STATE.ser, STATE.port, STATE.baud = ser, p, b
        STATE.port_source, STATE.baud_source = psrc, bsrc
        STATE.last_open = datetime.now().isoformat(timespec="seconds")
        try:
            _init_adapter()
            yield
        finally:
            try:
                ser.close()
            except Exception:
                pass
            STATE.ser = None
            _release_lock()


def _run(purpose: str, fn: Callable[[], dict[str, Any]], **session_kw: Any) -> str:
    """Run ``fn`` inside a session and return its dict as JSON, errors included."""
    try:
        with _session(purpose, **session_kw):
            result = fn()
    except ObdError as e:
        result = {"error": str(e), "purpose": purpose}
    except (serial.SerialException, OSError) as e:
        result = {"error": f"serial failure during {purpose}: {e}", "purpose": purpose}
    return json.dumps(result, indent=2)


# --------------------------------------------------------------------------
# Response parsing
# --------------------------------------------------------------------------

#: Adapter/bus conditions that must never be silently discarded.
ADAPTER_ERRORS = (
    "BUFFER FULL", "CAN ERROR", "BUS BUSY", "BUS ERROR", "STOPPED",
    "DATA ERROR", "FB ERROR", "UNABLE TO CONNECT", "BUS INIT: ERROR",
    "ERR", "RX ERROR", "LV RESET", "ACT ALERT", "OUT OF MEMORY", "TIMEOUT",
)

#: Benign and genuinely ignorable.
BENIGN_LINES = ("OK", "NO DATA", "SEARCHING...", "?", "STOPPED SEARCHING")

_HEX_DIGITS = set("0123456789ABCDEF")
_ELM_INDEX_RE = re.compile(r"^([0-9A-F]{1,2}):(.*)$")


def adapter_error(s: str) -> str:
    """Return the adapter/bus error present in a response, or ""."""
    up = s.upper()
    for err in ADAPTER_ERRORS:
        if err in up:
            return err
    return ""


def _hex_pairs(s: str) -> list[str]:
    """Flatten a response into hex bytes, ignoring headers and framing.

    Kept for the readiness decoder and for callers that only need the byte
    stream. Prefer :func:`_reassemble` for anything per-ECU.
    """
    tokens: list[str] = []
    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue
        up = line.upper()
        if up in BENIGN_LINES or adapter_error(up):
            continue
        m = _ELM_INDEX_RE.match(up)
        if m:
            up = m.group(2)
        parts = up.split()
        if len(parts) > 1 and len(parts[0]) in (3, 8) and all(
                c in _HEX_DIGITS for c in parts[0]):
            parts = parts[1:]
        blob = "".join(parts)
        if not blob or any(c not in _HEX_DIGITS for c in blob):
            continue
        if len(blob) % 2:
            blob = blob[:-1]
        tokens.extend(blob[i:i + 2] for i in range(0, len(blob), 2))
    return tokens


def _reassemble(raw: str, headers_on: Optional[bool] = None) -> dict[str, list[str]]:
    """Group a response by sending ECU and reassemble ISO-TP multi-frame data.

    With ``ATH1`` and ``ATS0`` an 11-bit CAN line is ``7E8`` + PCI + data
    (odd length) and a 29-bit line is ``18DAF110`` + PCI + data (even
    length), so the header width is recovered from line parity. PCI types:
    ``0N`` single frame of N bytes, ``1N NN`` first frame with 12-bit length,
    ``2N`` consecutive frame.

    With headers off the adapter has already stripped framing; ELM's own
    multi-frame rendering (``0:``, ``1:`` lines after a bare length line) is
    concatenated under the empty-string key.
    """
    if headers_on is None:
        headers_on = STATE.headers_on
    ecus: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def entry(hdr: str) -> dict[str, Any]:
        if hdr not in ecus:
            ecus[hdr] = {"data": [], "expected": None}
            order.append(hdr)
        return ecus[hdr]

    for line in raw.splitlines():
        up = line.strip().upper()
        if not up or up in BENIGN_LINES or adapter_error(up):
            continue
        m = _ELM_INDEX_RE.match(up)
        if m:
            blob = m.group(2).replace(" ", "")
            if blob and all(c in _HEX_DIGITS for c in blob):
                e = entry("")
                e["data"].extend(blob[i:i + 2] for i in range(0, len(blob) - 1, 2))
            continue
        blob = up.replace(" ", "")
        if not blob or any(c not in _HEX_DIGITS for c in blob):
            continue
        if not headers_on:
            if len(blob) == 3:
                continue          # bare ISO-TP length line before "0:" frames
            e = entry("")
            e["data"].extend(blob[i:i + 2] for i in range(0, len(blob) - 1, 2))
            continue
        hdr_len = 3 if len(blob) % 2 else 8
        if len(blob) < hdr_len + 2:
            continue
        hdr, rest = blob[:hdr_len], blob[hdr_len:]
        bytes_ = [rest[i:i + 2] for i in range(0, len(rest) - 1, 2)]
        if not bytes_:
            continue
        pci = int(bytes_[0], 16)
        ftype = pci >> 4
        e = entry(hdr)
        if ftype == 0:
            n = pci & 0x0F
            e["data"] = bytes_[1:1 + n] if n else bytes_[1:]
            e["expected"] = n or None
        elif ftype == 1 and len(bytes_) >= 2:
            e["expected"] = ((pci & 0x0F) << 8) | int(bytes_[1], 16)
            e["data"] = bytes_[2:]
        elif ftype == 2:
            e["data"].extend(bytes_[1:])
        else:
            # Not ISO-TP framed (K-line style or a non-OBD message): keep raw.
            e["data"].extend(bytes_)
        if e["expected"] and len(e["data"]) > e["expected"]:
            e["data"] = e["data"][:e["expected"]]

    return {hdr: ecus[hdr]["data"] for hdr in order}


def _payloads_for(ecus: dict[str, list[str]], response_byte: str) -> dict[str, list[str]]:
    """Only the ECU payloads that answer the expected service."""
    return {hdr: data for hdr, data in ecus.items() if data and data[0] == response_byte}


def _decode_dtc_bytes(payload: list[str]) -> list[str]:
    """DTCs from a Mode 03/07/0A payload starting with the response byte.

    On CAN the response byte is followed by a count byte; on K-line it is
    not. ``43 02 01 43 04 56`` has an odd number of bytes after the response
    byte, ``43 01 43 04 56`` an even one, so parity decides.
    """
    if not payload:
        return []
    rest = payload[1:]
    if len(rest) % 2:
        rest = rest[1:]           # drop the count byte
    dtcs: list[str] = []
    for i in range(0, len(rest) - 1, 2):
        a, b = rest[i], rest[i + 1]
        if a == "00" and b == "00":
            continue
        try:
            high = int(a[0], 16)
        except ValueError:
            continue
        # ISO 15031-6 / SAE J2012: category in bits 15-14 of the two-byte code.
        letter = "PCBU"[high >> 2]
        dtcs.append(f"{letter}{format(high & 0x3, 'X')}{a[1]}{b}")
    return dtcs


def _decode_dtcs(pairs: list[str], mode_response_byte: str) -> list[str]:
    """Legacy flat decoder kept for the tests; delegates to the parity-aware one."""
    if pairs and pairs[0] == mode_response_byte:
        return _decode_dtc_bytes(pairs)
    return _decode_dtc_bytes([mode_response_byte] + pairs) if pairs else []


# --------------------------------------------------------------------------
# PID table with J1979 formulas
# --------------------------------------------------------------------------

def _u16(d: list[int]) -> int:
    return (d[0] << 8) | d[1]


def _s16(d: list[int]) -> int:
    v = _u16(d)
    return v - 65536 if v & 0x8000 else v


#: name -> (pid, unit, minimum bytes, formula over data bytes)
PIDS: dict[str, tuple[str, str, int, Callable[[list[int]], float]]] = {
    "engine_coolant_temp":     ("05", "C",     1, lambda d: d[0] - 40),
    "short_fuel_trim_b1":      ("06", "%",     1, lambda d: d[0] / 1.28 - 100),
    "long_fuel_trim_b1":       ("07", "%",     1, lambda d: d[0] / 1.28 - 100),
    "short_fuel_trim_b2":      ("08", "%",     1, lambda d: d[0] / 1.28 - 100),
    "long_fuel_trim_b2":       ("09", "%",     1, lambda d: d[0] / 1.28 - 100),
    "fuel_pressure":           ("0A", "kPa",   1, lambda d: d[0] * 3),
    "intake_map":              ("0B", "kPa",   1, lambda d: d[0]),
    "engine_rpm":              ("0C", "rpm",   2, lambda d: _u16(d) / 4),
    "vehicle_speed":           ("0D", "km/h",  1, lambda d: d[0]),
    "timing_advance":          ("0E", "deg",   1, lambda d: d[0] / 2 - 64),
    "intake_air_temp":         ("0F", "C",     1, lambda d: d[0] - 40),
    "maf":                     ("10", "g/s",   2, lambda d: _u16(d) / 100),
    "throttle_position":       ("11", "%",     1, lambda d: d[0] * 100 / 255),
    "o2_b1s1_voltage":         ("14", "V",     1, lambda d: d[0] / 200),
    "runtime_since_start":     ("1F", "s",     2, _u16),
    "distance_with_mil":       ("21", "km",    2, _u16),
    "fuel_rail_pressure":      ("23", "kPa",   2, lambda d: _u16(d) * 10),
    "commanded_evap_purge":    ("2E", "%",     1, lambda d: d[0] * 100 / 255),
    "fuel_level":              ("2F", "%",     1, lambda d: d[0] * 100 / 255),
    "warmups_since_clear":     ("30", "count", 1, lambda d: d[0]),
    "distance_since_clear":    ("31", "km",    2, _u16),
    "evap_vapor_pressure":     ("32", "Pa",    2, lambda d: _s16(d) / 4),
    "barometric_pressure":     ("33", "kPa",   1, lambda d: d[0]),
    "control_module_voltage":  ("42", "V",     2, lambda d: _u16(d) / 1000),
    "absolute_load":           ("43", "%",     2, lambda d: _u16(d) * 100 / 255),
    "commanded_afr":           ("44", "ratio", 2, lambda d: _u16(d) * 2 / 65536),
    "ambient_air_temp":        ("46", "C",     1, lambda d: d[0] - 40),
    "fuel_type":               ("51", "code",  1, lambda d: d[0]),
    "ethanol_percent":         ("52", "%",     1, lambda d: d[0] * 100 / 255),
    "evap_vapor_pressure_abs": ("53", "kPa",   2, lambda d: _u16(d) / 200),
    "engine_oil_temp":         ("5C", "C",     1, lambda d: d[0] - 40),
    "engine_fuel_rate":        ("5E", "L/h",   2, lambda d: _u16(d) / 20),
}

_PID_BY_HEX = {v[0]: k for k, v in PIDS.items()}


def _resolve_pid(pid: str) -> tuple[str, Optional[str]]:
    """Return (hex pid, friendly name or None)."""
    key = pid.strip()
    if key in PIDS:
        return PIDS[key][0], key
    hx = key.upper().replace("0X", "")
    if len(hx) == 1:
        hx = "0" + hx
    if len(hx) != 2 or any(c not in _HEX_DIGITS for c in hx):
        raise ObdError(f"{pid!r} is neither a friendly PID name nor a 2-digit hex PID")
    return hx, _PID_BY_HEX.get(hx)


def _decode_pid(hex_pid: str, name: Optional[str], data: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"pid": hex_pid, "name": name, "bytes": data}
    if name is None:
        out["unit"] = "raw"
        return out
    _, unit, need, fn = PIDS[name]
    out["unit"] = unit
    if len(data) < need:
        out["error"] = f"expected at least {need} data byte(s), got {len(data)}"
        return out
    try:
        ints = [int(b, 16) for b in data]
        value = fn(ints)
        out["value"] = round(value, 3) if isinstance(value, float) else value
    except (ValueError, IndexError) as e:
        out["error"] = f"decode failed: {e}"
    return out


def _query_service(cmd: str, response_byte: str, timeout: float = DEFAULT_TIMEOUT
                   ) -> dict[str, Any]:
    """Send a request and return raw text, error and per-ECU payloads."""
    raw = _cmd(cmd, timeout)
    err = adapter_error(raw)
    ecus = _reassemble(raw) if not err else {}
    answers = _payloads_for(ecus, response_byte)
    if not err and answers:
        _maybe_pin_protocol()
    return {"raw": raw, "error": err or None, "ecus": answers}


def _no_data(raw: str) -> bool:
    return "NO DATA" in raw.upper()


# --------------------------------------------------------------------------
# Tools: configuration and status
# --------------------------------------------------------------------------

@mcp.tool()
def list_ports() -> str:
    """List serial ports on this machine, marking the one MES is configured for."""
    mes_port = (mes_registry().get("Interface 0 Port") or "").upper()
    ports = []
    for p in serial.tools.list_ports.comports():
        ports.append({"device": p.device, "description": p.description,
                      "hwid": p.hwid, "mes_interface_0": p.device.upper() == mes_port})
    return json.dumps({"ports": ports, "mes_port": mes_port or None}, indent=2)


@mcp.tool()
def status() -> str:
    """Configuration in force, MES state, lock state and the last adapter identity.

    The port is never held between calls, so there is no "connected" state to
    report; what matters is whether the next call would be able to open it.
    """
    port, psrc = resolve_port()
    baud, bsrc = resolve_baud()
    reg = mes_registry()
    return json.dumps({
        "port": port, "port_source": psrc,
        "baud": baud, "baud_source": bsrc,
        "protocol_pinned": STATE.protocol,
        "headers_on": STATE.headers_on,
        "adapter_identity": STATE.identity or None,
        "last_open": STATE.last_open,
        "mes": mes_status(),
        "mes_interface_0": {
            "type_ex": reg.get("Interface 0 Type Ex"),
            "port": reg.get("Interface 0 Port"),
            "speed": reg.get("Interface 0 Port Speed"),
        } if reg else None,
        "lock": read_lock(),
        "lock_path": str(_lock_path()),
        "note": "the port is opened per operation and released after each call",
    }, indent=2)


@mcp.tool()
def mes_state() -> str:
    """Is MultiEcuScan running, and is it connected to the vehicle?

    Read-only: process list plus the text of MES's status label. Used as the
    interlock before every port open. ``connected`` blocks this server.
    """
    return json.dumps(mes_status(), indent=2)


@mcp.tool()
def mes_settings() -> str:
    """MultiEcuScan's own settings from the registry: interfaces, folders, CSV separator.

    Licence fields are redacted. ``Recent Vehicles`` and ``Last Selection``
    are live session state and change as MES is used.
    """
    reg = mes_registry()
    if not reg:
        return json.dumps({"error": "HKLM\\SOFTWARE\\Multiecuscan not found"}, indent=2)
    interfaces = []
    for i in range(5):
        if f"Interface {i} Port" in reg:
            interfaces.append({"index": i,
                               "type_ex": reg.get(f"Interface {i} Type Ex"),
                               "port": reg.get(f"Interface {i} Port"),
                               "speed": reg.get(f"Interface {i} Port Speed")})
    return json.dumps({
        "interfaces": interfaces,
        "folders": mes_folders(reg),
        "last_selection": reg.get("Last Selection"),
        "recent_vehicles": reg.get("Recent Vehicles"),
        "ui_language": reg.get("UI Language"),
        "data_language": reg.get("Data Language"),
        "high_latency_mode": reg.get("High Latency mode"),
        "kwp2000_timings": reg.get("KWP2000 Timings"),
        "all_keys": sorted(reg.keys()),
    }, indent=2)


@mcp.tool()
def connect(port: str = "", baud: int = 0, allow_while_mes_connected: bool = False) -> str:
    """Probe the adapter: reset it, read its identity, and pin the protocol if the car answers.

    Despite the name this does not keep the port open; every tool opens and
    closes the port itself. Use this once after plugging in, or when the
    adapter or car has changed.

    Args:
        port: COM port. Falls back to OBD_PORT, then MES's Interface 0 setting.
        baud: UART speed. Falls back to OBD_BAUD, then MES's Interface 0 speed.
        allow_while_mes_connected: skip the MES interlock. Only if MES is
            connected through a different port.
    """
    def body() -> dict[str, Any]:
        out: dict[str, Any] = {
            "port": STATE.port, "port_source": STATE.port_source,
            "baud": STATE.baud, "baud_source": STATE.baud_source,
        }
        reset = _cmd("ATZ", 3)
        if _looks_like_wrong_baud(reset):
            raise ObdError(f"garbage reply to ATZ at {STATE.baud} baud; wrong speed")
        _init_adapter()
        ident: dict[str, str] = {}
        for c in ("ATI", "AT@1", "STI", "STDI", "STMFR", "STSN", "STPRS"):
            r = _cmd(c, 2)
            if r and r != "?" and not adapter_error(r):
                ident[c] = r
        STATE.identity = ident
        out["identity"] = ident
        out["stn_chip"] = ident.get("STI") is not None
        volts = _cmd("ATRV", 2)
        out["battery_voltage"] = volts
        on_car = bool(re.search(r"\d+\.\d+V", volts))
        out["vehicle_power_detected"] = on_car
        if on_car:
            q = _query_service("0100", "41", 6)
            out["protocol_search"] = {"error": q["error"], "ecus_answering": list(q["ecus"])}
            out["protocol_pinned"] = STATE.protocol
        else:
            out["note"] = ("no vehicle voltage on the adapter: the car is not "
                           "connected or ignition is off; protocol not searched")
        out["port_held"] = False
        return out

    STATE.protocol = None  # a probe always re-detects
    return _run("connect/probe", body, port=port, baud=baud,
                allow_while_mes_connected=allow_while_mes_connected)


@mcp.tool()
def disconnect() -> str:
    """Release the port and the lock if anything is held, and forget the pinned protocol."""
    with STATE.lock:
        if STATE.ser and STATE.ser.is_open:
            try:
                STATE.ser.close()
            except Exception:
                pass
        STATE.ser = None
        STATE.protocol = None
        _release_lock()
    return json.dumps({"released": True, "lock": read_lock()}, indent=2)


# --------------------------------------------------------------------------
# Tools: reads
# --------------------------------------------------------------------------

def _dtc_tool(mode: str, response_byte: str, label: str, note: str = "") -> dict[str, Any]:
    q = _query_service(mode, response_byte)
    out: dict[str, Any] = {"kind": label, "raw": q["raw"]}
    if q["error"]:
        out["error"] = (f"ADAPTER/BUS ERROR: {q['error']}. This is NOT 'no codes'; "
                        f"the read did not complete.")
        return out
    per_ecu = {hdr: _decode_dtc_bytes(data) for hdr, data in q["ecus"].items()}
    all_codes = sorted({c for codes in per_ecu.values() for c in codes})
    out["dtcs"] = all_codes
    out["by_ecu"] = per_ecu
    if not q["ecus"]:
        out["warning"] = ("no ECU answered" + (" (NO DATA)" if _no_data(q["raw"]) else "")
                          + "; with the ignition off this is expected")
    if note and not all_codes:
        out["note"] = note
    return out


_MODE03_NOTE = ("Mode 03 returns emissions-related powertrain codes only. Body, "
                "chassis and network faults are UDS 3-byte codes read via service "
                "0x19 and will not appear here.")


@mcp.tool()
def read_dtcs() -> str:
    """Read stored (confirmed) diagnostic trouble codes. Mode 03. Per-ECU, JSON."""
    return _run("read_dtcs", lambda: _dtc_tool("03", "43", "stored", _MODE03_NOTE))


@mcp.tool()
def read_pending_dtcs() -> str:
    """Read pending DTCs (one failure, not yet confirmed). Mode 07. Per-ECU, JSON."""
    return _run("read_pending_dtcs", lambda: _dtc_tool("07", "47", "pending"))


@mcp.tool()
def read_permanent_dtcs() -> str:
    """Read permanent DTCs (cannot be cleared until the monitor passes). Mode 0A."""
    return _run("read_permanent_dtcs", lambda: _dtc_tool("0A", "4A", "permanent"))


@mcp.tool()
def read_pid(pid: str) -> str:
    """Read a live PID (Mode 01) and decode it. Pass a hex PID like "0C" or a friendly name.

    Friendly names: engine_rpm, vehicle_speed, engine_coolant_temp,
    intake_air_temp, ambient_air_temp, fuel_level, commanded_evap_purge,
    evap_vapor_pressure, evap_vapor_pressure_abs, short_fuel_trim_b1,
    long_fuel_trim_b1, control_module_voltage, throttle_position, maf,
    intake_map, barometric_pressure, engine_oil_temp, engine_fuel_rate ...
    Unknown PIDs return raw bytes.
    """
    def body() -> dict[str, Any]:
        hex_pid, name = _resolve_pid(pid)
        q = _query_service(f"01{hex_pid}", "41")
        out: dict[str, Any] = {"pid": hex_pid, "name": name, "raw": q["raw"]}
        if q["error"]:
            out["error"] = f"ADAPTER/BUS ERROR: {q['error']}; the read did not complete"
            return out
        readings = {}
        for hdr, data in q["ecus"].items():
            if len(data) >= 2 and data[1] == hex_pid:
                readings[hdr] = _decode_pid(hex_pid, name, data[2:])
        out["by_ecu"] = readings
        first = next(iter(readings.values()), None)
        if first is not None:
            out["value"] = first.get("value")
            out["unit"] = first.get("unit")
        else:
            out["warning"] = "no ECU answered this PID"
        return out
    return _run("read_pid", body)


@mcp.tool()
def read_voltage() -> str:
    """Battery voltage as measured by the adapter at the OBD port (ATRV)."""
    def body() -> dict[str, Any]:
        r = _cmd("ATRV", 2)
        m = re.search(r"(\d+\.\d+)V", r)
        return {"raw": r, "volts": float(m.group(1)) if m else None,
                "vehicle_power_detected": bool(m)}
    return _run("read_voltage", body)


@mcp.tool()
def read_supported_pids() -> str:
    """Which Mode 01 PIDs each ECU supports (bitmaps 00, 20, 40, 60, 80, A0, C0)."""
    def body() -> dict[str, Any]:
        out: dict[str, Any] = {"by_ecu": {}, "raw": {}}
        for base in ("00", "20", "40", "60", "80", "A0", "C0"):
            q = _query_service(f"01{base}", "41")
            out["raw"][base] = q["raw"]
            if q["error"]:
                out.setdefault("errors", {})[base] = q["error"]
                break
            any_next = False
            for hdr, data in q["ecus"].items():
                if len(data) < 6 or data[1] != base:
                    continue
                bits = int("".join(data[2:6]), 16)
                supported = out["by_ecu"].setdefault(hdr, [])
                start = int(base, 16)
                for i in range(32):
                    if bits & (1 << (31 - i)):
                        supported.append(format(start + 1 + i, "02X"))
                if bits & 1:
                    any_next = True
            if not any_next:
                break
        for hdr, lst in out["by_ecu"].items():
            out["by_ecu"][hdr] = {"count": len(lst), "pids": lst,
                                  "known_names": [_PID_BY_HEX[p] for p in lst if p in _PID_BY_HEX]}
        return out
    return _run("read_supported_pids", body)


@mcp.tool()
def read_freeze_frame(pid: str = "") -> str:
    """Freeze-frame data captured when the DTC set. Mode 02, frame 0.

    Args:
        pid: hex PID or friendly name. Empty reads PID 02, the DTC that
             triggered the freeze frame.
    """
    def body() -> dict[str, Any]:
        if pid.strip():
            hex_pid, name = _resolve_pid(pid)
        else:
            hex_pid, name = "02", None
        q = _query_service(f"02{hex_pid}00", "42")
        out: dict[str, Any] = {"pid": hex_pid, "name": name, "raw": q["raw"]}
        if q["error"]:
            out["error"] = f"ADAPTER/BUS ERROR: {q['error']}; the read did not complete"
            return out
        by_ecu = {}
        for hdr, data in q["ecus"].items():
            if len(data) < 3 or data[1] != hex_pid:
                continue
            payload = data[3:]  # 42 <pid> <frame#> <data>
            if hex_pid == "02":
                by_ecu[hdr] = {"dtc": _decode_dtc_bytes(["43"] + payload[:2]) or None,
                               "bytes": payload}
            else:
                by_ecu[hdr] = _decode_pid(hex_pid, name, payload)
        out["by_ecu"] = by_ecu
        if not by_ecu:
            out["warning"] = "no ECU returned a freeze frame (none stored, or ignition off)"
        return out
    return _run("read_freeze_frame", body)


@mcp.tool()
def read_vin() -> str:
    """Read the vehicle VIN. Mode 09 PID 02, reassembled from ISO-TP frames."""
    def body() -> dict[str, Any]:
        q = _query_service("0902", "49", 6)
        out: dict[str, Any] = {"raw": q["raw"]}
        if q["error"]:
            out["error"] = f"ADAPTER/BUS ERROR: {q['error']}; the read did not complete"
            return out
        for hdr, data in q["ecus"].items():
            if len(data) >= 3 and data[1] == "02":
                chars = []
                for tok in data[3:]:
                    n = int(tok, 16)
                    if 32 <= n < 127:
                        chars.append(chr(n))
                vin = "".join(chars)
                out["vin"] = vin
                out["ecu"] = hdr
                out["length_ok"] = len(vin) == 17
                break
        if "vin" not in out:
            out["warning"] = "no ECU answered Mode 09 PID 02"
        return out
    return _run("read_vin", body)


# Readiness -----------------------------------------------------------------

_NON_CONTINUOUS = (
    (0, "Catalyst"), (1, "Heated catalyst"), (2, "Evaporative system"),
    (3, "Secondary air system"), (4, "A/C refrigerant"), (5, "Oxygen sensor"),
    (6, "Oxygen sensor heater"), (7, "EGR system"),
)
_CONTINUOUS = ((0, 4, "Misfire"), (1, 5, "Fuel system"), (2, 6, "Comprehensive components"))


def _decode_readiness(pairs: list[str], response_byte: str) -> dict | None:
    """Decode a Mode 01 PID 01 / 41 readiness response from a flat byte list."""
    idx = None
    for i in range(len(pairs) - 1):
        if pairs[i] == response_byte and pairs[i + 1] in ("01", "41"):
            idx = i + 2
            break
    if idx is None:
        return None
    try:
        data = [int(x, 16) for x in pairs[idx:idx + 4]]
    except ValueError:
        return None
    if len(data) < 4:
        return None
    a, b, c, d = data
    monitors: list[dict] = []
    for sup_bit, inc_bit, name in _CONTINUOUS:
        if b & (1 << sup_bit):
            monitors.append({"monitor": name, "supported": True,
                             "complete": not (b & (1 << inc_bit))})
    for bit, name in _NON_CONTINUOUS:
        if c & (1 << bit):
            monitors.append({"monitor": name, "supported": True,
                             "complete": not (d & (1 << bit))})
    return {
        "mil_on": bool(a & 0x80),
        "stored_dtc_count": a & 0x7F,
        "ignition": "spark" if not (b & 0x08) else "compression",
        "monitors": monitors,
        "all_complete": all(m["complete"] for m in monitors) if monitors else None,
    }


def _readiness_body() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pid, label in (("01", "since_clear"), ("41", "this_drive_cycle")):
        q = _query_service(f"01{pid}", "41")
        if q["error"]:
            out[label] = {"error": q["error"], "raw": q["raw"]}
            continue
        decoded = None
        for hdr, data in q["ecus"].items():
            decoded = _decode_readiness(data, "41")
            if decoded:
                decoded["ecu"] = hdr
                break
        out[label] = decoded or {"error": "could not decode readiness response", "raw": q["raw"]}

    since = out.get("since_clear") or {}
    evap = next((m for m in since.get("monitors", []) if m["monitor"] == "Evaporative system"), None)
    if evap is not None:
        out["evap_verdict"] = (
            "EVAP monitor has COMPLETED since the last clear; a clean scan is now "
            "meaningful for EVAP." if evap["complete"] else
            "EVAP monitor has NOT run since the last clear. Absence of an EVAP code "
            "right now carries no information. Complete the drive cycle first.")
    elif since.get("monitors"):
        out["evap_verdict"] = "This ECU does not report an evaporative system monitor."

    counters: dict[str, Any] = {}
    for name in ("warmups_since_clear", "distance_since_clear"):
        hex_pid = PIDS[name][0]
        q = _query_service(f"01{hex_pid}", "41")
        if q["error"]:
            continue
        for _hdr, data in q["ecus"].items():
            if len(data) >= 3 and data[1] == hex_pid:
                dec = _decode_pid(hex_pid, name, data[2:])
                if "value" in dec:
                    counters[name] = dec["value"]
                break
    if counters:
        out["drive_cycle_counters"] = counters
    return out


@mcp.tool()
def read_readiness() -> str:
    """OBD-II readiness monitors: has each emissions monitor RUN since the last clear?

    Mode 01 PID 01 (since clear) and PID 41 (this drive cycle), plus warm-up
    and distance counters. After clearing codes an ECU reports nothing until
    each monitor re-runs, so a clean scan minutes later proves almost nothing;
    this tool says whether it can mean anything yet.
    """
    return _run("read_readiness", _readiness_body)


# --------------------------------------------------------------------------
# Tools: clear, with evidence capture
# --------------------------------------------------------------------------

def _evidence_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base, "obd2-mcp", "clears")
    d.mkdir(parents=True, exist_ok=True)
    return d


@mcp.tool()
def clear_dtcs(confirm: bool = False, override_speed_check: bool = False) -> str:
    """Clear stored DTCs, freeze frames and readiness monitors. Mode 04. DESTRUCTIVE.

    Before clearing, this captures stored, pending and permanent codes, the
    freeze-frame DTC and readiness to a JSON file, refuses if the vehicle
    reports it is moving, and reads codes back afterwards so "cleared" is
    verified rather than assumed. Pass confirm=True to proceed.
    """
    if not confirm:
        return json.dumps({"refused": "pass confirm=True to clear DTCs and reset readiness "
                                      "monitors; this destroys the freeze-frame evidence"}, indent=2)

    def body() -> dict[str, Any]:
        out: dict[str, Any] = {"cleared": False}
        speed_q = _query_service("010D", "41")
        speed = None
        for _hdr, data in speed_q["ecus"].items():
            if len(data) >= 3 and data[1] == "0D":
                speed = int(data[2], 16)
                break
        out["vehicle_speed_kmh"] = speed
        if speed is None and not override_speed_check:
            raise ObdError("could not read vehicle speed (ignition off or bus error); "
                           "refusing to clear. Pass override_speed_check=True if the car "
                           "is stationary and you accept that.")
        if speed and not override_speed_check:
            raise ObdError(f"vehicle speed is {speed} km/h; refusing to clear while moving")

        before = {
            "stored": _dtc_tool("03", "43", "stored"),
            "pending": _dtc_tool("07", "47", "pending"),
            "permanent": _dtc_tool("0A", "4A", "permanent"),
            "freeze_frame_dtc": _query_service("020200", "42"),
            "readiness": _readiness_body(),
        }
        before["freeze_frame_dtc"].pop("ecus", None)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = _evidence_dir() / f"clear_{stamp}.json"
        record = {"captured_at": datetime.now().isoformat(timespec="seconds"),
                  "port": STATE.port, "before": before}
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        out["evidence_file"] = str(path)
        out["before"] = {k: before[k].get("dtcs") for k in ("stored", "pending", "permanent")}

        raw = _cmd("04", 6)
        out["clear_raw"] = raw
        err = adapter_error(raw)
        if err:
            out["error"] = f"clear did not complete: {err}"
            return out
        acked = any(data and data[0] == "44" for data in _reassemble(raw).values())
        out["acknowledged"] = acked
        after = _dtc_tool("03", "43", "stored")
        out["after"] = {"stored": after.get("dtcs"), "error": after.get("error")}
        out["cleared"] = acked and not after.get("dtcs") and not after.get("error")
        if acked and after.get("dtcs"):
            out["note"] = ("codes still present immediately after the clear: the fault "
                           "is live and re-set at once, or the module refused the erase")
        out["reminder"] = ("readiness monitors are now incomplete; a clean re-scan proves "
                           "nothing until they run again. Use read_readiness.")
        record["after"] = out
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return out

    return _run("clear_dtcs", body)


# --------------------------------------------------------------------------
# Tools: raw escape hatch with classification
# --------------------------------------------------------------------------

#: UDS services that change vehicle state.
_WRITE_SERVICES = {
    "10": "UDS DiagnosticSessionControl - changes the module's session; an extended "
          "session suppresses normal broadcasts and can itself trigger network DTCs",
    "11": "UDS ECUReset - resets the module",
    "14": "UDS ClearDiagnosticInformation - erases DTCs and readiness monitors",
    "27": "UDS SecurityAccess - repeated failures can lock the module out",
    "28": "UDS CommunicationControl - silences or alters bus traffic",
    "2C": "UDS DynamicallyDefineDataIdentifier - writes a definition into the module",
    "2E": "UDS WriteDataByIdentifier - writes configuration to a module",
    "2F": "UDS InputOutputControl - physically actuates hardware",
    "31": "UDS RoutineControl - runs adaptations and service routines",
    "34": "UDS RequestDownload - reflashing, can brick a module",
    "35": "UDS RequestUpload - reflashing related",
    "36": "UDS TransferData - reflashing, can brick a module",
    "37": "UDS RequestTransferExit - reflashing related",
    "3D": "UDS WriteMemoryByAddress - writes module memory",
    "85": "UDS ControlDTCSetting - suppresses DTC logging",
    "87": "UDS LinkControl - changes bus timing",
}

#: AT commands that only read adapter state. Anything else AT-prefixed
#: reconfigures the adapter and needs allow_adapter_reconfiguration.
_AT_READ_ONLY = {"ATI", "AT@1", "AT@2", "AT@3", "ATRV", "ATDP", "ATDPN", "ATPPS",
                 "ATIGN", "ATRD", "ATCS"}

#: STN commands that only read adapter state (identity, protocol, config).
_ST_READ_ONLY = {"STI", "STIX", "STDI", "STDIX", "STMFR", "STSN", "STPR", "STPRS",
                 "STPBRR", "STSLCS", "STCTRR", "STDICPO", "STDICES", "STDITPO",
                 "STVR", "STVRX", "STPTOR", "STCSWMR"}

#: Monitor modes never return until interrupted; a request/response tool
#: would hang. They need a dedicated streaming tool.
_MONITOR_COMMANDS = ("ATMA", "ATMR", "ATMT", "STM", "STMA")


def classify_command(cmd: str) -> tuple[str, str]:
    """Return (kind, reason). kind is read, vehicle_write, adapter_state or blocked."""
    compact = cmd.strip().upper().replace(" ", "")
    if not compact:
        return "blocked", "empty command"

    if compact.startswith("AT"):
        if compact.startswith(_MONITOR_COMMANDS):
            return "blocked", f"{compact[:4]} is a monitor mode; it never returns to the prompt"
        if compact.startswith("ATSH"):
            return "vehicle_write", ("ATSH redirects requests to another module, which can "
                                     "turn a following command into a write to an unintended ECU")
        if compact in _AT_READ_ONLY:
            return "read", ""
        return "adapter_state", (f"{compact} changes adapter configuration (protocol, "
                                 f"headers, filters, timing, baud or persistent settings)")

    if compact.startswith("ST"):
        if re.match(r"^STMA?\d*$", compact):
            return "blocked", "STM/STMA monitor modes never return to the prompt"
        if compact.startswith("STPX"):
            return "vehicle_write", ("STPX transmits an arbitrary CAN frame with an arbitrary "
                                     "ID and payload; that is a write to the bus")
        if compact in _ST_READ_ONLY:
            return "read", ""
        return "adapter_state", (f"{compact} changes adapter configuration (protocol, "
                                 f"filters, segmentation, periodic messages, baud or "
                                 f"power settings)")

    if any(c not in _HEX_DIGITS for c in compact):
        return "blocked", f"{cmd!r} is neither an AT/ST command nor hex"

    if compact in ("04", "0400"):
        return "vehicle_write", ("OBD-II Mode 04 clears DTCs and resets readiness monitors. "
                                 "Use clear_dtcs(confirm=True), which captures evidence first")
    service = compact[:2]
    if service in _WRITE_SERVICES:
        return "vehicle_write", _WRITE_SERVICES[service]
    return "read", ""


def _classify_write(cmd: str) -> str:
    """Compatibility shim: reason string when the command writes to the vehicle, else ""."""
    kind, reason = classify_command(cmd)
    return reason if kind == "vehicle_write" else ""


@mcp.tool()
def send_raw(command: str, timeout_seconds: float = DEFAULT_TIMEOUT,
             i_understand_this_writes_to_the_vehicle: bool = False,
             allow_adapter_reconfiguration: bool = False,
             allow_while_mes_connected: bool = False) -> str:
    """Send one command to the adapter (AT, ST or OBD/UDS hex) and return the parsed reply.

    Read-only commands run as-is. Vehicle writes (Mode 04, UDS 10/11/14/27/28/
    2C/2E/2F/31/34-37/3D/85/87, ATSH, STPX) need
    i_understand_this_writes_to_the_vehicle=True. Adapter reconfiguration
    (ATSP, ATH, ATCRA, ATPP, STP, STBR, STCMM, filters, and so on) needs
    allow_adapter_reconfiguration=True and does not persist past this call
    because the port is re-initialised on every open. Monitor modes are
    refused. One command per call: CR, LF and '|' are rejected.
    """
    try:
        cmd = _validate_command(command)
    except ObdError as e:
        return json.dumps({"refused": str(e), "command": command}, indent=2)
    kind, reason = classify_command(cmd)
    if kind == "blocked":
        return json.dumps({"refused": reason, "command": cmd}, indent=2)
    if kind == "vehicle_write" and not i_understand_this_writes_to_the_vehicle:
        return json.dumps({
            "refused": reason, "command": cmd, "kind": kind,
            "how_to_proceed": "pass i_understand_this_writes_to_the_vehicle=True; for FCA "
                              "actuator tests and adaptations prefer MultiEcuScan, which "
                              "enforces per-vehicle preconditions",
        }, indent=2)
    if kind == "adapter_state" and not allow_adapter_reconfiguration:
        return json.dumps({
            "refused": reason, "command": cmd, "kind": kind,
            "how_to_proceed": "pass allow_adapter_reconfiguration=True; the change lasts "
                              "only for this call",
        }, indent=2)

    def body() -> dict[str, Any]:
        raw = _cmd(cmd, timeout_seconds)
        err = adapter_error(raw)
        out: dict[str, Any] = {"command": cmd, "kind": kind, "raw": raw}
        if err:
            out["error"] = err
        elif cmd[:2].upper() not in ("AT", "ST"):
            out["ecus"] = _reassemble(raw)
        return out

    return _run(f"send_raw {cmd}", body, allow_while_mes_connected=allow_while_mes_connected)


if __name__ == "__main__":
    mcp.run()
