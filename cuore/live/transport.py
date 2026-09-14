"""AdapterLink: one adapter, opened per operation, one bus per session.

The link owns no open port between calls. ``session()`` resolves port and
speed, checks the MES interlock, takes the process lock and the advisory lock
file, opens the stream, initialises the adapter, selects the bus route for
the declared cable, enforces the transmit policy, yields a :class:`Session`,
and closes everything on the way out. That is the whole contract, and it is
what lets MultiEcuScan take the adapter the moment a call returns.

Cable state lives here too. It is declared, not detected; every result names
it; changing it clears every bus verification.
"""

from __future__ import annotations

import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Iterator, Optional

from . import audit, interlock
from .addressing import ECUAddress
from .buses import CABLES, CAN_C, BUSES, Bus, Route, header_bits_for_protocol, route_for
from .config import default_cable, resolve_baud, resolve_port
from .errors import AdapterFault, BadCommand, LinkUnavailable
from .framing import (adapter_error, looks_like_wrong_baud, negative_responses,
                      payloads_for, reassemble)
from .safety import assert_transmit_allowed, validate_command
from .stream import SerialStream, Stream

DEFAULT_TIMEOUT = 4.0
MIN_TIMEOUT, MAX_TIMEOUT = 0.2, 30.0

#: STN preset -> ELM327 protocol number for adapters without ST commands.
_ELM_EQUIVALENT = {"33": "6", "34": "7", "35": "8", "36": "9", "31": "6", "32": "7"}


def clamp_timeout(t: float) -> float:
    try:
        t = float(t)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return max(MIN_TIMEOUT, min(MAX_TIMEOUT, t))


class Session:
    """An open adapter, configured for one bus. Valid only inside ``session()``."""

    def __init__(self, link: "AdapterLink", stream: Stream, bus: Bus, route: Route,
                 *, passive: bool, confirmed: bool) -> None:
        self.link = link
        self.stream = stream
        self.bus = bus
        self.route = route
        self.passive = passive
        self.confirmed = confirmed
        self.headers_on = True
        self.header_bits = header_bits_for_protocol(route.stn_protocol)
        self._target: Optional[tuple[str, str]] = None
        self.opened_at = datetime.now().isoformat(timespec="seconds")

    # --- wire ----------------------------------------------------------

    def cmd(self, command: str, timeout: float = DEFAULT_TIMEOUT) -> str:
        """Send one command and read until the ``>`` prompt or the deadline.

        A reply with no prompt is tagged ``TIMEOUT`` so it counts as an
        incomplete read rather than an empty result.
        """
        command = validate_command(command)
        timeout = clamp_timeout(timeout)
        s = self.stream
        s.reset_input_buffer()
        s.write((command + "\r").encode("ascii"))
        s.flush()
        deadline = time.monotonic() + timeout
        buf = bytearray()
        got_prompt = False
        while time.monotonic() < deadline:
            chunk = s.read(s.in_waiting() or 1)
            if not chunk:
                continue
            buf.extend(chunk)
            if b">" in chunk:
                got_prompt = True
                break
        text = buf.decode("ascii", errors="replace").replace("\r", "\n").strip(" \n>")
        if text.upper().startswith(command.upper()):
            text = text[len(command):].lstrip(" \n")
        if not got_prompt:
            text = (text + "\nTIMEOUT").strip()
        return text

    def query(self, request_hex: str, response_byte: str,
              timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        """Send a request; return raw text, error, and per-ECU positive payloads."""
        raw = self.cmd(request_hex, timeout)
        err = adapter_error(raw)
        ecus = reassemble(raw, headers_on=self.headers_on) if not err else {}
        return {"raw": raw, "error": err or None, "ecus": payloads_for(ecus, response_byte),
                "all_ecus": ecus}

    # --- addressing -----------------------------------------------------

    def target(self, ecu: ECUAddress) -> None:
        """Point requests at one module; idempotent within the session."""
        if not ecu.usable and ecu.target is None:
            raise BadCommand(f"module {ecu.code} has no known address")
        self.target_raw(ecu.request_hex or "", ecu.response_hex or "")

    def target_raw(self, request_hex: str, response_hex: str) -> None:
        pair = (request_hex.upper(), response_hex.upper())
        if self._target == pair:
            return
        self.cmd(f"ATSH{pair[0]}", 2)
        self.cmd(f"ATCRA{pair[1]}", 2)
        if self.link.is_stn:
            self.cmd(f"STCFCPA {pair[0]},{pair[1]}", 2)
        else:
            self.cmd(f"ATFCSH{pair[0]}", 2)
            self.cmd("ATFCSD300000", 2)
            self.cmd("ATFCSM1", 2)
        self._target = pair

    def untarget(self) -> None:
        """Back to functional/broadcast addressing for legislated OBD."""
        if self._target is None:
            return
        self.cmd("ATSH18DB33F1" if self.header_bits == 29 else "ATSH7DF", 2)
        self.cmd("ATCRA", 2)
        if self.link.is_stn:
            self.cmd("STCFCPC", 2)
        self._target = None

    # --- UDS primitive --------------------------------------------------

    def uds(self, ecu: ECUAddress, service: int, payload: bytes = b"",
            timeout: float = DEFAULT_TIMEOUT, retries_on_pending: int = 3) -> dict[str, Any]:
        """One UDS request to one module. Read-only services only (enforced upstream).

        NRC ``0x78`` (responsePending) is handled by re-issuing the request
        after a short wait, up to ``retries_on_pending`` times, which is the
        practical equivalent of waiting P2* on an adapter that returns to its
        prompt after the first reply.
        """
        self.target(ecu)
        req = f"{service:02X}{payload.hex().upper()}"
        resp_byte = f"{service + 0x40:02X}"
        svc_hex = f"{service:02X}"
        attempts = 0
        while True:
            attempts += 1
            q = self.query(req, resp_byte, timeout)
            nrc = negative_responses(q["all_ecus"], svc_hex)
            pending = [h for h, code in nrc.items() if code == "78"]
            if pending and not q["ecus"] and attempts <= retries_on_pending:
                time.sleep(0.3 * attempts)
                continue
            break
        mine = {h: d for h, d in q["ecus"].items()
                if not ecu.response_hex or h == ecu.response_hex or h == ""}
        return {"request": req, "raw": q["raw"], "error": q["error"],
                "positive": mine, "nrc": {h: int(c, 16) for h, c in nrc.items()},
                "attempts": attempts, "ecu": ecu.code, "bus": self.bus.key}


class AdapterLink:
    """The one object that opens the adapter. Create one per process."""

    def __init__(self, stream_factory: Optional[Callable[[str, int], Stream]] = None,
                 process: str = "cuore") -> None:
        self.stream_factory = stream_factory or (lambda p, b: SerialStream(p, b))
        self.process = process
        self.lock = threading.RLock()
        self.cable: str = default_cable()
        self.identity: dict[str, str] = {}
        self.is_stn: bool = False
        self.port: Optional[str] = None
        self.baud: int = 0
        self.port_source = ""
        self.baud_source = ""
        self.last_open: Optional[str] = None
        self.last_error: Optional[str] = None
        self.verified: dict[str, dict[str, Any]] = {}   # bus_key -> {cable, frames, at}
        self.vin: str = ""                               # last VIN the car reported
        self.current: Optional[Session] = None

    # --- cable state ----------------------------------------------------

    def set_cable(self, cable: str) -> dict[str, Any]:
        cable = (cable or "none").lower()
        if cable not in CABLES:
            raise BadCommand(f"unknown cable {cable!r}; one of {list(CABLES)}")
        with self.lock:
            changed = cable != self.cable
            self.cable = cable
            if changed:
                self.verified.clear()
            audit.record("cable_declared", cable=cable, cleared_verifications=changed)
        return self.cable_state()

    def cable_state(self) -> dict[str, Any]:
        buses = []
        for key, bus in BUSES.items():
            route = route_for(bus, self.cable)
            ver = self.verified.get(key)
            buses.append({
                "bus": key, "name": bus.name, "pins": list(bus.pins), "bitrate": bus.bitrate,
                "reachable_with_cable": route is not None,
                "route": (None if route is None else {
                    "stn_protocol": route.stn_protocol, "bitrate_override": route.bitrate_override,
                    "status": route.status, "note": route.note}),
                "verified": bool(ver), "verified_at": (ver or {}).get("at"),
                "verified_frames": (ver or {}).get("frames"),
                "transmit_needs_confirmation": bus.transmit_needs_confirmation,
            })
        return {"cable": self.cable, "buses": buses}

    def mark_verified(self, bus: Bus, frames: int) -> None:
        self.verified[bus.key] = {"cable": self.cable, "frames": frames,
                                  "at": datetime.now().isoformat(timespec="seconds")}

    # --- sessions -------------------------------------------------------

    @contextmanager
    def session(self, purpose: str, *, bus: Bus = CAN_C, port: str = "", baud: int = 0,
                passive: bool = False, confirm: bool = False,
                allow_while_mes_connected: bool = False,
                stream: Optional[Stream] = None) -> Iterator[Session]:
        """Open the adapter for one operation on one bus, then close it.

        ``passive=True`` sets receive-only mode (no CAN ACK) and skips the
        transmit policy; it is how a bus gets verified in the first place.
        """
        with self.lock:
            route = route_for(bus, self.cable)
            if route is None:
                raise LinkUnavailable(
                    f"bus {bus.key} is not reachable with cable {self.cable!r}; declare the "
                    f"right cable first")
            if not passive:
                assert_transmit_allowed(
                    bus_key=bus.key, bus_cable_ok=True,
                    verified=bus.key in self.verified,
                    needs_confirmation=bus.transmit_needs_confirmation, confirmed=confirm)
            p, psrc = resolve_port(port)
            b, bsrc = resolve_baud(baud)
            if not p and stream is None:
                raise LinkUnavailable("no port configured: pass port=, set CUORE_OBD_PORT or "
                                      "OBD_PORT, or configure Interface 0 in MultiEcuScan")
            ms = interlock.mes_status()
            if ms["state"] == "connected" and not allow_while_mes_connected:
                raise LinkUnavailable(
                    f"MultiEcuScan is connected to the vehicle (label {ms['label']!r}, pids "
                    f"{ms['pids']}). Disconnect in MES first, or pass "
                    f"allow_while_mes_connected=True if MES is on a different port.")
            interlock.acquire(p or "stream", purpose, process=self.process)
            st = stream or self.stream_factory(p or "", b)
            try:
                st.open()
            except Exception as e:  # serial.SerialException, OSError
                interlock.release()
                hint = ""
                if "denied" in str(e).lower() or "PermissionError" in str(e):
                    hint = (" The port is held by another process: MES if connected, another "
                            "cuore/obd2 instance, or a terminal program.")
                self.last_error = f"open {p}@{b} failed: {e}"
                raise LinkUnavailable(f"could not open {p}@{b} ({psrc}, {bsrc}): {e}.{hint}")
            self.port, self.baud, self.port_source, self.baud_source = p, b, psrc, bsrc
            self.last_open = datetime.now().isoformat(timespec="seconds")
            sess = Session(self, st, bus, route, passive=passive, confirmed=confirm)
            self.current = sess
            audit.record("session_open", purpose=purpose, bus=bus.key, cable=self.cable,
                         passive=passive, port=p, baud=b, stream=st.describe)
            try:
                self._init(sess)
                yield sess
                audit.record("session_close", purpose=purpose, bus=bus.key, ok=True)
            except Exception as e:
                self.last_error = str(e)
                audit.record("session_close", purpose=purpose, bus=bus.key, ok=False,
                             error=str(e))
                raise
            finally:
                self.current = None
                try:
                    st.close()
                except Exception:
                    pass
                interlock.release()

    def _init(self, sess: Session) -> None:
        """Per-open adapter configuration; never inherits interpreter state."""
        r = sess.cmd("ATE0", 2)
        if looks_like_wrong_baud(r):
            raise LinkUnavailable(
                f"adapter replied with framing garbage at {self.baud} baud ({self.baud_source}); "
                f"almost always the wrong speed")
        if "TIMEOUT" in r and not r.replace("TIMEOUT", "").strip():
            raise LinkUnavailable(f"no reply from the adapter on {self.port}; is it plugged in?")
        for c in ("ATL0", "ATS0", "ATH1", "ATAT1"):
            sess.cmd(c, 2)
        if not self.identity:
            self._probe_identity(sess)
        route = sess.route
        if self.is_stn:
            sess.cmd(f"STP {route.stn_protocol}", 2)
            if route.bitrate_override:
                sess.cmd(f"STPBR {route.bitrate_override}", 2)
            if sess.passive:
                sess.cmd("STCMM 0", 2)
        else:
            elm = _ELM_EQUIVALENT.get(route.stn_protocol)
            if elm is None or route.bitrate_override:
                raise LinkUnavailable(
                    f"bus {sess.bus.key} via route {route.stn_protocol} needs an STN adapter; "
                    f"this adapter identifies as {self.identity.get('ATI', 'unknown')}")
            sess.cmd(f"ATSP{elm}", 2)
        sess.headers_on = True

    def _probe_identity(self, sess: Session) -> None:
        ident: dict[str, str] = {}
        for c in ("ATI", "AT@1", "STI", "STDI", "STMFR", "STSN"):
            r = sess.cmd(c, 2)
            if r and r != "?" and not adapter_error(r):
                ident[c] = r
        self.identity = ident
        self.is_stn = "STI" in ident

    # --- reporting ------------------------------------------------------

    def adapter_info(self) -> dict[str, Any]:
        """The ``AdapterInfo`` fields for ``/api/capabilities``, never raising."""
        try:
            port, _ = resolve_port()
            blocked = interlock.blocked_by()
            return {"present": bool(port) and blocked is None, "port": port,
                    "blocked_by": blocked,
                    "note": ("port opened per operation; " +
                             (f"adapter {self.identity.get('STDI') or self.identity.get('ATI')}"
                              if self.identity else "adapter not probed yet"))}
        except Exception as e:  # pragma: no cover - defensive
            return {"present": False, "port": None, "blocked_by": None, "note": str(e)}

    def status(self) -> dict[str, Any]:
        port, psrc = resolve_port()
        baud, bsrc = resolve_baud()
        return {
            "port": port, "port_source": psrc, "baud": baud, "baud_source": bsrc,
            "adapter_identity": self.identity or None, "is_stn": self.is_stn,
            "last_open": self.last_open, "last_error": self.last_error,
            "mes": interlock.mes_status(), "lock": interlock.read_lock(),
            "lock_path": str(interlock.lock_path()),
            "cable": self.cable_state(), "vin": self.vin or None,
            "note": "the port is opened per operation and released after each call",
        }


_LINK: Optional[AdapterLink] = None
_LINK_LOCK = threading.Lock()


def link() -> AdapterLink:
    """The process-wide link, created on first use."""
    global _LINK
    with _LINK_LOCK:
        if _LINK is None:
            _LINK = AdapterLink()
        return _LINK


def set_link(new: AdapterLink) -> None:
    """Replace the process-wide link (tests inject a playback-backed one)."""
    global _LINK
    with _LINK_LOCK:
        _LINK = new


__all__ = ["DEFAULT_TIMEOUT", "clamp_timeout", "Session", "AdapterLink", "link", "set_link"]
