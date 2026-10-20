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

import os
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
from .errors import AdapterFault, BadCommand, LinkUnavailable, Refused
from .framing import (adapter_error, looks_like_wrong_baud, negative_responses,
                      payloads_for, reassemble)
from .obd import PIDS_BY_HEX
from .safety import assert_transmit_allowed, validate_command
from .stream import SerialStream, Stream

try:  # OBD_TIMEOUT is honoured for compatibility with the obd2-mcp registration
    DEFAULT_TIMEOUT = float(os.environ.get("OBD_TIMEOUT", "4"))
except ValueError:
    DEFAULT_TIMEOUT = 4.0
MIN_TIMEOUT, MAX_TIMEOUT = 0.2, 30.0

#: STN preset -> ELM327 protocol number for adapters without ST commands.
_ELM_EQUIVALENT = {"33": "6", "34": "7", "35": "8", "36": "9", "31": "6", "32": "7"}

#: J1979 Mode 01 multi-PID cap: up to 6 PIDs may be requested in one frame.
#: Shared with :mod:`cuore.live.poller`, which batches live-data channels
#: the same way; this is the session-level primitive any other caller (the
#: fullscan PID snapshot, a future dossier reader) can use for the same win
#: without duplicating the ISO-TP splitting logic. See
#: docs/research/OBD_CONNECTIVITY_REVIEW_2026-10-14.md.
MAX_MULTI_PID = 6


def _split_multi_pid(data: list[str], pids: list[str]) -> dict[str, list[str]]:
    """Split one ECU's ``41 <pid> <data> 41 <pid> <data> ...`` reply by the
    PIDs asked, in order. Stops at the first group that does not match the
    next PID asked -- the ECU answered fewer than requested, which is how a
    caller learns multi-PID does not fully work here and should fall back
    to single requests for the rest. (Same contract as the private
    ``_parse_multi_pid`` historically kept in ``poller.py``.)
    """
    out: dict[str, list[str]] = {}
    i = 0
    for pid in pids:
        if i + 1 >= len(data) or data[i] != "41" or data[i + 1] != pid:
            break
        spec = PIDS_BY_HEX.get(pid)
        n = spec.n_bytes if spec else 1
        if i + 2 + n > len(data):
            break
        out[pid] = data[i + 2:i + 2 + n]
        i += 2 + n
    return out


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
        self._reset_done = False
        #: Seconds the adapter itself waits for a reply (ATST x 4 ms).
        #: Conservative default = ATSTFF (1.02 s): untarget() sets it and the
        #: adapter keeps it across sessions, so it is assumed in force until
        #: a later ATSTxx / reset says otherwise.
        self.adapter_wait = 1.02
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
        self._drain_stale(command)
        s.reset_input_buffer()
        s.write((command + "\r").encode("ascii"))
        s.flush()
        self._track_adapter_wait(command)
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
            self._interrupt_and_drain()
        return text

    _STALE_FUNCTIONAL = re.compile(r"^(?:7E[0-9A-F]|18DAF1[0-9A-F]{2})[0-9A-F]{4,}$")

    def _drain_stale(self, before: str) -> None:
        """Read and discard whatever is already in the input buffer before a
        request goes out (non-blocking, bounded 100 ms). A late reply or a
        late 0x78 left over from the previous request would otherwise be read
        as this request's answer. If the discarded text holds a complete
        reply frame for the current target, audit it as ``stale_input`` so
        the car shows whether stale replies actually happen."""
        s = self.stream
        got = bytearray()
        try:
            deadline = time.monotonic() + 0.1
            while time.monotonic() < deadline:
                n = s.in_waiting()
                if not n:
                    break
                chunk = s.read(n)
                if not chunk:
                    break
                got.extend(chunk)
        except Exception:  # noqa: BLE001 -- draining must never fail the caller
            return
        if not got:
            return
        text = got.decode("ascii", errors="replace")
        want = self._target[1].upper() if self._target else ""
        for line in re.split(r"[\r\n>]+", text):
            frame = re.sub(r"\s+", "", line).upper()
            if not frame:
                continue
            if want:
                hit = frame.startswith(want) and re.fullmatch(r"[0-9A-F]+", frame) \
                    and len(frame) >= len(want) + 4
            else:
                hit = bool(self._STALE_FUNCTIONAL.match(frame))
            if hit:
                audit.record("stale_input", bytes=text[:200], before=before,
                             target=want or "functional", bus=self.bus.key)
                break

    def _track_adapter_wait(self, command: str) -> None:
        u = command.strip().upper()
        if u in ("ATWS", "ATZ", "ATD"):
            self.adapter_wait = 0.2  # firmware default ATST 0x32
        elif u.startswith("ATST") and len(u) > 4:
            try:
                self.adapter_wait = int(u[4:], 16) * 0.004
            except ValueError:
                pass

    def _interrupt_and_drain(self) -> None:
        """After a python-side timeout the adapter may still be waiting on
        the bus. Send one CR (any byte interrupts it) and read to the ``>``
        prompt so the next command is not swallowed ("STOPPED")."""
        s = self.stream
        try:
            s.write(b"\r")
            s.flush()
            deadline = time.monotonic() + min(1.5, self.adapter_wait + 0.3)
            while time.monotonic() < deadline:
                chunk = s.read(s.in_waiting() or 1)
                if chunk and b">" in chunk:
                    break
        except Exception:  # noqa: BLE001 -- recovery must never fail the caller
            pass
        finally:
            try:
                s.reset_input_buffer()
            except Exception:  # noqa: BLE001
                pass

    def query(self, request_hex: str, response_byte: str,
              timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        """Send a request; return raw text, error, and per-ECU positive payloads."""
        # Never give up before the adapter does: an earlier python deadline
        # interrupts the adapter mid-wait and desynchronises the next command.
        timeout = max(float(timeout), self.adapter_wait + 0.2)
        raw = self.cmd(request_hex, timeout)
        err = adapter_error(raw)
        ecus = reassemble(raw, headers_on=self.headers_on) if not err else {}
        return {"raw": raw, "error": err or None, "ecus": payloads_for(ecus, response_byte),
                "all_ecus": ecus}

    def query_pids(self, pids: list[str], timeout: float = DEFAULT_TIMEOUT,
                   allow_multi: bool = True) -> dict[str, Any]:
        """Mode 01 multi-PID: up to :data:`MAX_MULTI_PID` PIDs per request
        (J1979), split per responding ECU, with an automatic per-PID fallback
        for whichever PIDs a batch left unanswered.

        This is the session-level primitive behind the live-data poller's
        own multi-PID batching (:mod:`cuore.live.poller`); it exists here so
        any other caller holding a session -- a PID snapshot, a dossier
        reader -- gets the same request-count reduction without re-deriving
        the ISO-TP splitting. One session, one or more batched requests, then
        singles only for the PIDs a batch did not answer in full.

        Returns ``{"by_ecu": {header: {pid: [databytes]}}, "multi_pid_used":
        bool, "requests_sent": int}``. ``multi_pid_used`` is False only when
        every PID ended up needing its own request (``allow_multi=False``,
        a single PID asked, or every batch came back short).
        """
        pids = list(dict.fromkeys(pids))  # de-dup, keep the caller's order
        by_ecu: dict[str, dict[str, list[str]]] = {}
        sent = 0
        multi_used = False
        singles: list[str] = list(pids)
        if allow_multi and len(pids) > 1:
            singles = []
            for start in range(0, len(pids), MAX_MULTI_PID):
                batch = pids[start:start + MAX_MULTI_PID]
                q = self.query("01" + "".join(batch), "41", timeout)
                sent += 1
                if q["error"] or not q["ecus"]:
                    singles.extend(batch)
                    continue
                for hdr, data in q["ecus"].items():
                    parsed = _split_multi_pid(data, batch)
                    if parsed:
                        by_ecu.setdefault(hdr, {}).update(parsed)
                        multi_used = True
                    # Any PID this ECU's reply did not cover (short group,
                    # or no reply at all) is retried as its own request --
                    # one ECU's partial answer never drops a PID silently.
                    for p in batch:
                        if p not in parsed and p not in singles:
                            singles.append(p)
        for pid in singles:
            q = self.query(f"01{pid}", "41", timeout)
            sent += 1
            for hdr, data in q["ecus"].items():
                if len(data) >= 2 and data[1] == pid:
                    by_ecu.setdefault(hdr, {})[pid] = data[2:]
        return {"by_ecu": by_ecu, "multi_pid_used": multi_used, "requests_sent": sent}

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
            if self.header_bits == 29:
                # Explicit ISO-TP flow control (STmin/BS) for the 29-bit UDS
                # pair. STCFCPA alone only tells the adapter which header to
                # answer flow control on; it does not state STmin/BS, so a
                # gateway-routed 29-bit target is left on the adapter's
                # un-stated default. STN chips are documented as an ELM327
                # command-set superset, so the same ATFCSx commands proven on
                # non-STN adapters below are sent here too (flag=0x30/CTS,
                # BS=0, STmin=0 -- send consecutive frames back-to-back, no
                # throttling expected from this side). Additive: on a
                # firmware that does not honour ATFCSx under an ST protocol
                # select, the adapter answers "?" and STCFCPA's own routing
                # still holds, so this never removes working behaviour.
                # UNVERIFIED on the real adapter -- see
                # docs/research/OBD_CONNECTIVITY_REVIEW_2026-10-14.md.
                self.cmd(f"ATFCSH{pair[0]}", 2)
                self.cmd("ATFCSD300000", 2)
                self.cmd("ATFCSM1", 2)
        else:
            self.cmd(f"ATFCSH{pair[0]}", 2)
            self.cmd("ATFCSD300000", 2)
            self.cmd("ATFCSM1", 2)
        self._target = pair
        self.link._last_target = pair

    def untarget(self) -> None:
        """Back to functional/broadcast addressing for legislated OBD.

        The adapter keeps ATSH/ATCRA across port closes, so a fresh session
        inherits the link's last physical target and clears it here rather
        than trusting its own (empty) memory.
        """
        if self._target is None:
            self._target = getattr(self.link, "_last_target", None)
        if (self._target is not None and not self._reset_done
                and getattr(self.link, "reset_before_legislated", False)):
            # Opt-in (CUORE_RESET_BEFORE_LEGISLATED=1): physical -> functional
            # switch gets one clean adapter reset per session.
            self.hard_reset()
        # Always restate the functional header: the adapter remembers the last
        # ATSH across port closes and protocol switches, and a process restart
        # forgets what that was.
        if self.header_bits == 29:
            # 29-bit functional header the way the ELM/STN command set takes
            # it: priority byte via ATCP, lower 24 bits via ATSH. A single
            # 8-digit ATSH is not accepted by every firmware and silently
            # leaves the last header in force (read as NO DATA on the bench,
            # 2026-10-13, while the probe built this way got answers).
            self.cmd("ATCP18", 2)
            self.cmd("ATSHDB33F1", 2)
            self.cmd("ATSTFF", 2)
        else:
            self.cmd("ATSH7DF", 2)
        self.cmd("ATCRA", 2)
        if self.link.is_stn:
            mode = self.link._probe_pass_filter(self)
            if mode == "pass_filter":
                # Lighter restore: re-apply the functional header's own pass
                # filter directly instead of clearing the whole filter table
                # and reissuing STP (which also resets protocol/baud and
                # costs a full re-init). Probe-gated by
                # AdapterLink._probe_pass_filter; falls back to the proven
                # STCFCPC+STP path below whenever that probe does not
                # clearly confirm support, so a firmware that does not
                # understand this path never loses the working behaviour.
                if self.header_bits == 29:
                    self.cmd("ATCP18", 2)
                    self.cmd("ATSHDB33F1", 2)
                    self.cmd("ATSTFF", 2)
                    self.cmd("STFAP 1,DB33F1,FFFFFFFF", 2)
                else:
                    self.cmd("ATSH7DF", 2)
                    self.cmd("STFAP 1,7DF,FFFFFFFF", 2)
            else:
                # Bench finding 2026-10-13 (vLinker FS r2, STN1170 v4.3.2): STFAC
                # removes the firmware's default pass filters too, after which
                # every reply is dropped and each request reads NO DATA. Re-issuing
                # the protocol select restores the defaults, and the functional
                # header must then be restated because STP resets it as well.
                self.cmd("STCFCPC", 2)
                self.cmd(f"STP {self.route.stn_protocol}", 2)
                if self.header_bits == 29:
                    self.cmd("ATCP18", 2)
                    self.cmd("ATSHDB33F1", 2)
                    self.cmd("ATSTFF", 2)
                else:
                    self.cmd("ATSH7DF", 2)
        self._target = None
        self.link._last_target = None

    def hard_reset(self) -> None:
        """ATWS, verify the banner, then restate the session init and clear
        targeting. Never called automatically; untarget() calls it once per
        session only when ``AdapterLink.reset_before_legislated`` is set."""
        self._reset_done = True
        time.sleep(0.2)
        r = self.cmd("ATWS", 3)
        ok = "ELM327 v" in r
        time.sleep(0.5)
        route = self.route
        for c in ("ATE0", "ATL0", "ATS0", "ATH1", "ATAT1", "ATCAF1"):
            self.cmd(c, 2)
        if self.link.is_stn:
            self.cmd(f"STP {route.stn_protocol}", 2)
            if route.bitrate_override:
                self.cmd(f"STPBR {route.bitrate_override}", 2)
            self.cmd("STCMM 0" if self.passive else "STCMM 1", 2)
            self.cmd("ATCRA", 2)
            self.cmd("STCFCPC", 2)
            self.cmd(f"STP {route.stn_protocol}", 2)
            if route.bitrate_override:
                self.cmd(f"STPBR {route.bitrate_override}", 2)
        else:
            elm = _ELM_EQUIVALENT.get(route.stn_protocol)
            if elm:
                self.cmd(f"ATSP{elm}", 2)
            self.cmd("ATCRA", 2)
        self.headers_on = True
        self._target = None
        self.link._last_target = None
        audit.record("hard_reset", bus=self.bus.key, ok=ok, reply=(r or "")[:120])

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
        # The audit log otherwise records only session open/close, so a
        # module that answered discovery and then went silent to the sweep
        # (ABS, 2026-10-15) left nothing to compare. Raw reply, capped.
        audit.record("uds", ecu=ecu.code, bus=self.bus.key, req=req,
                     header=ecu.request_hex, raw=(q["raw"] or "")[:200],
                     error=q["error"], attempts=attempts)
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
        self.verified: dict[str, dict[str, Any]] = {}   # bus_key -> {cable, frames, at, ts}
        # Auto-verify: a transmit session on an unverified (or stale) bus runs
        # the passive listen itself instead of refusing. Off with
        # CUORE_AUTO_VERIFY=0; the proof window is CUORE_VERIFY_TTL seconds.
        self.auto_verify: bool = os.environ.get("CUORE_AUTO_VERIFY", "1") != "0"
        self.verify_ttl: float = float(os.environ.get("CUORE_VERIFY_TTL", "600"))
        self.verifier: Optional[Callable[..., dict[str, Any]]] = None
        self.last_auto_verify: Optional[dict[str, Any]] = None
        self.vin: str = ""                               # last VIN the car reported
        self.current: Optional[Session] = None
        # Probe-based lighter pass-filter restore for untarget() (point d of
        # docs/research/OBD_CONNECTIVITY_REVIEW_2026-10-14.md). None until
        # the first untarget() on an STN link probes it; then "pass_filter"
        # or "stp_reissue", cached for the life of this AdapterLink.
        self.pass_filter_mode: Optional[str] = None
        # Off by default: untarget() keeps its exact proven STCFCPC+STP
        # path unless this is explicitly turned on. A generic fake adapter
        # in a test (anything echoing "OK" to any AT/ST-prefixed command)
        # cannot be told apart from real STFAP support, so this stays
        # opt-in rather than auto-probed, to never change default
        # behaviour. CUORE_PASS_FILTER_PROBE=1 to try it.
        self.pass_filter_probe_enabled: bool = os.environ.get("CUORE_PASS_FILTER_PROBE", "0") == "1"
        # Optional higher adapter UART baud, negotiated via STSBR and always
        # reverted -- off by default (0). See AdapterLink.raised_baud().
        try:
            self.adapter_baud_requested: int = int(os.environ.get("CUORE_ADAPTER_BAUD", "0") or 0)
        except ValueError:
            self.adapter_baud_requested = 0
        self.last_baud_raise: Optional[dict[str, Any]] = None
        # Opt-in: one ATWS hard reset per session when untarget() switches
        # from a physical target to functional (P1: NO DATA after UDS).
        self.reset_before_legislated: bool = os.environ.get(
            "CUORE_RESET_BEFORE_LEGISLATED", "0") == "1"

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
            ver = self.verified.get(key) if self.is_verified(bus) else None
            buses.append({
                "bus": key, "name": bus.name, "pins": list(bus.pins), "bitrate": bus.bitrate,
                "reachable_with_cable": route is not None,
                "route": (None if route is None else {
                    "stn_protocol": route.stn_protocol, "bitrate_override": route.bitrate_override,
                    "status": route.status, "note": route.note}),
                "verified": bool(ver), "verified_at": (ver or {}).get("at"),
                "verified_frames": (ver or {}).get("frames"),
                "verified_by": (ver or {}).get("verified_by"),
                "transmit_needs_confirmation": bus.transmit_needs_confirmation,
            })
        return {"cable": self.cable, "buses": buses}

    def mark_verified(self, bus: Bus, frames: int, *, verified_by: str = "passive_listen",
                      **extra: Any) -> None:
        """Record a bus as proven live under the declared cable.

        ``verified_by`` names how: ``"passive_listen"`` (frames overheard
        with no transmission at all) or ``"active_probe_0100"`` (CAN-C behind
        a Security Gateway Module carries no broadcast traffic, so the only
        proof available is a reply to one legislated Mode 01 PID 00 request
        -- see :func:`cuore.live.ops._active_probe_0100`). ``extra`` is
        merged in for callers that want to carry e.g. the responding ECU ids.
        """
        self.verified[bus.key] = {"cable": self.cable, "frames": frames,
                                  "verified_by": verified_by,
                                  "at": datetime.now().isoformat(timespec="seconds"),
                                  "ts": time.monotonic(), **extra}

    def is_verified(self, bus: Bus) -> bool:
        """Verified under the declared cable, and recently enough to trust.

        A proof older than ``verify_ttl`` is treated as absent: an adapter
        can lose the bus without the port noticing (a moved HS/MS switch, a
        half-seated plug), and a stale flag then turns every read into a
        confident-looking NO DATA.
        """
        ver = self.verified.get(bus.key)
        if not ver or ver.get("cable") != self.cable:
            return False
        ts = ver.get("ts")
        return ts is None or self.verify_ttl <= 0 or time.monotonic() - ts <= self.verify_ttl

    def _auto_verify(self, bus: Bus, allow_while_mes_connected: bool) -> None:
        """Run the passive listen for a transmit session that lacks a fresh proof."""
        verifier = self.verifier
        if verifier is None:
            from . import ops  # late: ops imports this module
            verifier = ops.verify_bus
        result = verifier(bus.key, seconds=self.auto_verify_seconds,
                          allow_while_mes_connected=allow_while_mes_connected)
        self.last_auto_verify = {"bus": bus.key, "verified": bool(result.get("verified")),
                                 "frames": result.get("frames"),
                                 "stn_protocol": result.get("stn_protocol"),
                                 "error": result.get("error"),
                                 "at": datetime.now().isoformat(timespec="seconds")}
        audit.record("auto_verify", **self.last_auto_verify)
        if not result.get("verified"):
            # On can_c the passive listen is tried first, but behind a 2018+
            # Security Gateway Module that bus carries no broadcast traffic
            # at all -- verify_bus() then falls back to one active Mode 01
            # PID 00 probe (see ops._active_probe_0100) before giving up, and
            # result["note"] already says so when that also got no reply.
            raise Refused(
                f"bus {bus.key} is silent: an automatic passive listen under cable "
                f"{self.cable!r} heard no traffic, so nothing was sent. Check the cable is "
                f"fitted and declared, the adapter's HS/MS switch, that it is fully seated, "
                f"and the ignition. Listen detail: {result.get('note') or result.get('error')}")

    auto_verify_seconds: float = 2.0

    # --- sessions -------------------------------------------------------

    @contextmanager
    def session(self, purpose: str, *, bus: Bus = CAN_C, port: str = "", baud: int = 0,
                passive: bool = False, confirm: bool = False,
                allow_while_mes_connected: bool = False,
                stream: Optional[Stream] = None,
                route: Optional[Route] = None,
                _bypass_silence_guard: bool = False) -> Iterator[Session]:
        """Open the adapter for one operation on one bus, then close it.

        ``passive=True`` sets receive-only mode (no CAN ACK) and skips the
        transmit policy; it is how a bus gets verified in the first place.

        ``route`` overrides the preferred route for this one session, so a
        passive listen can try a bus's other protocols. It must belong to the
        declared cable; reachability is still decided by the cable, never by
        the override.

        ``_bypass_silence_guard`` is a private escape hatch for exactly one
        caller: :func:`cuore.live.ops._active_probe_0100`, which transmits
        the single legislated request that *establishes* verification on
        CAN-C in the first place and so cannot itself be blocked by the
        guard it is trying to satisfy, or trigger another round of
        auto-verify. It is never reached from send_raw, HTTP, or any other
        MCP tool, and the caller is responsible for only ever using it on
        can_c.
        """
        with self.lock:
            chosen = route_for(bus, self.cable)
            if chosen is None:
                raise LinkUnavailable(
                    f"bus {bus.key} is not reachable with cable {self.cable!r}; declare the "
                    f"right cable first")
            if route is not None:
                if route.cable != self.cable:
                    raise LinkUnavailable(
                        f"route for cable {route.cable!r} cannot be used while cable "
                        f"{self.cable!r} is declared")
                chosen = route
            auto: Optional[dict[str, Any]] = None
            if not passive and not _bypass_silence_guard:
                if bus.transmit_needs_confirmation and not confirm:
                    # Refuse before listening: consent comes first on CAN-CH.
                    assert_transmit_allowed(
                        bus_key=bus.key, bus_cable_ok=True, verified=True,
                        needs_confirmation=True, confirmed=False)
                if not self.is_verified(bus) and self.auto_verify and stream is None:
                    self._auto_verify(bus, allow_while_mes_connected)
                    auto = self.last_auto_verify
                assert_transmit_allowed(
                    bus_key=bus.key, bus_cable_ok=True,
                    verified=self.is_verified(bus),
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
            sess = Session(self, st, bus, chosen, passive=passive, confirmed=confirm)
            sess.auto_verified = auto
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
        # ATCAF1 is restated every session: the adapter keeps settings across
        # port closes, a monitor session may have switched formatting off,
        # and a request sent without the ISO-TP PCI byte is ignored by every
        # ECU -- read as NO DATA on the bench (2026-10-13) while the probe,
        # which set ATCAF1 itself, got answers on the same bus.
        for c in ("ATL0", "ATS0", "ATH1", "ATAT1", "ATCAF1"):
            sess.cmd(c, 2)
        if not self.identity:
            self._probe_identity(sess)
        route = sess.route
        if self.is_stn:
            sess.cmd(f"STP {route.stn_protocol}", 2)
            if route.bitrate_override:
                sess.cmd(f"STPBR {route.bitrate_override}", 2)
            # STCMM persists across port closes; a passive listen must not
            # leave the next request session in receive-only (no-ACK) mode.
            sess.cmd("STCMM 0" if sess.passive else "STCMM 1", 2)
        else:
            elm = _ELM_EQUIVALENT.get(route.stn_protocol)
            if elm is None or route.bitrate_override:
                raise LinkUnavailable(
                    f"bus {sess.bus.key} via route {route.stn_protocol} needs an STN adapter; "
                    f"this adapter identifies as {self.identity.get('ATI', 'unknown')}")
            sess.cmd(f"ATSP{elm}", 2)
        sess.headers_on = True

    def _probe_pass_filter(self, sess: Session) -> str:
        """Once per link: can ``STFAP`` restore the functional pass filter
        without the full ``STCFCPC`` clear + ``STP`` reissue that
        :meth:`Session.untarget` otherwise needs (point d of
        docs/research/OBD_CONNECTIVITY_REVIEW_2026-10-14.md)?

        Returns ``"pass_filter"`` only on an unambiguous ``OK``; anything
        else -- ``"?"`` (unrecognised), a timeout, an adapter error, or an
        exception -- is ``"stp_reissue"``, which is the exact path this
        codebase already proved works on the bench. The result is cached
        on this link for its whole life, so the probe runs at most once per
        process even though ``untarget()`` is called constantly.
        """
        if self.pass_filter_mode is not None:
            return self.pass_filter_mode
        if not self.pass_filter_probe_enabled:
            self.pass_filter_mode = "stp_reissue"
            return self.pass_filter_mode
        target = "STFAP 1,DB33F1,FFFFFFFF" if sess.header_bits == 29 else "STFAP 1,7DF,FFFFFFFF"
        try:
            r = sess.cmd(target, 1.5)
        except Exception as e:  # noqa: BLE001 -- a probe must never fail the caller
            audit.record("pass_filter_probe", mode="stp_reissue", error=str(e))
            self.pass_filter_mode = "stp_reissue"
            return self.pass_filter_mode
        mode = "pass_filter" if r.strip().upper() == "OK" else "stp_reissue"
        audit.record("pass_filter_probe", mode=mode, reply=r)
        self.pass_filter_mode = mode
        return mode

    @contextmanager
    def raised_baud(self, sess: Session, target: int = 0) -> Iterator[bool]:
        """Best-effort, self-reverting UART-speed raise for the life of this
        ``with`` block (point c of
        docs/research/OBD_CONNECTIVITY_REVIEW_2026-10-14.md).

        Uses the STN's temporary ``STSBR`` (never ``STWBR``, so a lost
        revert still clears itself at the adapter's next power cycle) and
        the stream's own :meth:`~cuore.live.stream.Stream.set_baud`. Yields
        ``True`` only once the new rate is confirmed with ``STI``; on any
        failure along the way -- the command not acknowledged, the
        transport unable to change its own baud live, or the post-switch
        ``STI`` not coming back clean -- it yields ``False`` and the caller
        just keeps going at the session's existing speed. Either way, the
        adapter and host stream are back at the original baud when this
        block exits; the revert itself never raises.

        ``target`` defaults to :attr:`adapter_baud_requested`
        (``CUORE_ADAPTER_BAUD``, 0 = feature off). Never engaged
        automatically by :meth:`AdapterLink.session`/``_init`` -- a caller
        (e.g. the live-data poller, once it holds a session) opts in per
        block. UNVERIFIED on the real adapter.
        """
        target = target or self.adapter_baud_requested
        original = self.baud
        raised = False
        result: dict[str, Any] = {"requested": target, "from": original, "ok": False}
        try:
            can_follow = getattr(sess.stream, "supports_set_baud", False)
            if target and target != original and self.is_stn and can_follow:
                # Ask the transport before the adapter: a transport that
                # cannot change its own baud live is never asked to follow,
                # which is how this avoids ever leaving the adapter at a
                # rate the host side cannot speak back to it on.
                r = sess.cmd(f"STSBR {target}", 1.5)
                if "OK" in r.upper() or r.strip() == "":
                    if sess.stream.set_baud(target):
                        time.sleep(0.05)
                        sess.stream.reset_input_buffer()
                        check = sess.cmd("STI", 1.5)
                        if (check and "TIMEOUT" not in check.upper()
                                and not adapter_error(check)):
                            raised = True
                            result["ok"] = True
                        else:
                            result["note"] = f"STI check failed after switch: {check!r}"
                            sess.stream.set_baud(original)
                    else:
                        # The adapter already switched; the host side could
                        # not follow (rare -- supports_set_baud said it
                        # could), so tell the adapter to go back immediately,
                        # at the ORIGINAL baud the host is still speaking.
                        result["note"] = "set_baud failed despite advertised support"
                        try:
                            sess.cmd(f"STSBR {original}", 1.5)
                        except Exception:  # noqa: BLE001 -- best effort only
                            pass
                else:
                    result["note"] = f"STSBR not acknowledged: {r!r}"
            elif target and target != original and self.is_stn:
                result["note"] = "transport cannot change baud live; adapter never asked"
            self.last_baud_raise = result
            if raised:
                self.baud = target
                audit.record("baud_raised", **result)
            yield raised
        finally:
            if raised:
                try:
                    sess.stream.set_baud(original)
                    time.sleep(0.02)
                    sess.stream.reset_input_buffer()
                    sess.cmd(f"STSBR {original}", 1.5)
                    sess.cmd("STI", 1.0)
                except Exception as e:  # noqa: BLE001 -- revert must never raise
                    audit.record("baud_revert_failed", error=str(e))
                self.baud = original
                audit.record("baud_reverted", to=original)

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
            "pass_filter_mode": self.pass_filter_mode,
            "adapter_baud_requested": self.adapter_baud_requested or None,
            "last_baud_raise": self.last_baud_raise,
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


__all__ = ["DEFAULT_TIMEOUT", "MAX_MULTI_PID", "clamp_timeout", "Session", "AdapterLink",
           "link", "set_link"]
