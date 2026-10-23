"""The operations both surfaces call: HTTP routes and MCP tools are wrappers over these.

Every function returns a plain dict, opens the adapter for exactly its own
operation through :func:`link`, and names the bus and cable it used. Errors
are :class:`LiveError` subclasses; the surfaces decide how to render them.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import serial.tools.list_ports

from . import audit
from . import capture as capture_mod
from . import store
from . import uds as uds_mod
from .addressing import MODULES, by_code, on_bus
from .buses import BUSES, CAN_C, Bus, Route, routes_for
from .config import mes_folders, mes_interfaces, mes_registry, resolve_port
from .errors import BadCommand, LiveError, Refused
from .framing import adapter_error, no_data
from .safety import assert_read_only_uds
from .obd import (decode_obd_dtcs, decode_pid, decode_readiness, decode_supported_pids,
                  dtc_from_two_bytes, evap_verdict, resolve_pid, PIDS_BY_HEX)
from .transport import (DEFAULT_TIMEOUT, HEARD_MIN_FRAMES, AdapterLink, Session, declared_rate,
                        is_risky_route, link, rate_label, silence_reason, tlog)

_MODE03_NOTE = ("Mode 03 returns emissions-related powertrain codes only. Body, chassis and "
                "network faults are UDS 3-byte codes; use module DTC reads for those.")


def _bus(key: str) -> Bus:
    bus = BUSES.get((key or "can_c").lower())
    if bus is None:
        raise BadCommand(f"unknown bus {key!r}; one of {list(BUSES)}")
    return bus


def _stamp(sess: Session, out: dict[str, Any]) -> dict[str, Any]:
    out.setdefault("bus", sess.bus.key)
    out.setdefault("cable", sess.link.cable)
    auto = getattr(sess, "auto_verified", None)
    if auto:
        out.setdefault("auto_verified", auto)
    return out


def _observe(sess: Session, kind: str, out: dict[str, Any], vin: str = "") -> dict[str, Any]:
    """Stamp and persist a result as an observation the evidence gate can cite."""
    _stamp(sess, out)
    v = vin or getattr(sess.link, "vin", "") or ""
    store.record_observation(kind, out, vin=v, bus=sess.bus.key, cable=sess.link.cable,
                             stream=sess.stream.describe)
    return out


# --- status and configuration -------------------------------------------------

def status() -> dict[str, Any]:
    return link().status()


def ports() -> dict[str, Any]:
    mes_port = (mes_registry().get("Interface 0 Port") or "").upper()
    found = [{"device": p.device, "description": p.description, "hwid": p.hwid,
              "mes_interface_0": p.device.upper() == mes_port}
             for p in serial.tools.list_ports.comports()]
    return {"ports": found, "mes_port": mes_port or None}


def mes_settings() -> dict[str, Any]:
    reg = mes_registry()
    if not reg:
        return {"error": "HKLM\\SOFTWARE\\Multiecuscan not found"}
    return {"interfaces": mes_interfaces(reg), "folders": mes_folders(reg),
            "last_selection": reg.get("Last Selection"),
            "recent_vehicles": reg.get("Recent Vehicles"),
            "ui_language": reg.get("UI Language"), "data_language": reg.get("Data Language"),
            "all_keys": sorted(reg.keys())}


def set_cable(cable: str) -> dict[str, Any]:
    return link().set_cable(cable)


def cable_state() -> dict[str, Any]:
    return link().cable_state()


def buses() -> dict[str, Any]:
    st = link().cable_state()
    return {"cable": st["cable"], "buses": st["buses"]}


def modules(bus: Optional[str] = None) -> dict[str, Any]:
    rows = on_bus(_bus(bus).key) if bus else list(MODULES)
    return {"modules": [{
        "code": m.code, "name": m.name, "bus": m.bus_key, "bus_confidence": m.bus_confidence,
        "target": None if m.target is None else f"{m.target:02X}",
        "request": m.request_hex, "response": m.response_hex,
        "confidence": m.confidence.value, "usable": m.usable, "present": m.present,
        "source": m.source, "hazard": m.hazard, "note": m.note,
    } for m in rows]}


# --- probe and verification --------------------------------------------------

def probe(port: str = "", baud: int = 0, allow_while_mes_connected: bool = False) -> dict[str, Any]:
    """Reset the adapter, read its identity, report vehicle power. Holds nothing."""
    lk = link()
    lk.identity = {}
    with lk.session("probe", bus=CAN_C, port=port, baud=baud, passive=True,
                    allow_while_mes_connected=allow_while_mes_connected) as sess:
        out: dict[str, Any] = {"port": lk.port, "port_source": lk.port_source,
                               "baud": lk.baud, "baud_source": lk.baud_source,
                               "identity": lk.identity, "stn_chip": lk.is_stn}
        volts = sess.cmd("ATRV", 2)
        m = re.search(r"(\d+\.\d+)V", volts)
        out["battery_voltage"] = float(m.group(1)) if m else None
        out["vehicle_power_detected"] = bool(m)
        if lk.is_stn:
            out["protocol"] = sess.cmd("STPRS", 2)
        if not m:
            out["note"] = ("no vehicle voltage at the adapter: not plugged into the car or "
                           "ignition off")
        out["port_held"] = False
        return _stamp(sess, out)


#: Legislated OBD-II responders: 7E8-7EF, the 11-bit reply IDs for ECU 0-7.
_OBD_FUNCTIONAL_REPLIES = {format(0x7E8 + i, "X") for i in range(8)}


def _active_probe_0100(lk: AdapterLink, b: Bus, port: str, baud: int,
                       allow_while_mes_connected: bool) -> dict[str, Any]:
    """One legislated Mode 01 PID 00 request, the last resort for CAN-C only.

    2018+ Giorgio cars put the OBD diagnostic pair (6/14) behind the Security
    Gateway Module: CAN-C carries no broadcast traffic at all, so a passive
    listen is 0 frames on a perfectly healthy car (MES has read this same car
    for weeks over the same pins). The gateway still answers any legislated
    OBD-II request -- every emissions-legal vehicle must -- so one read-only
    ``0100`` on the 11-bit functional address 7DF, at 500k (STP 33), is the
    only traffic that can prove the bus alive here. No reply means genuinely
    silent (ignition off, HS/MS switch, a half-seated plug), not a false
    negative from the gateway's silence.

    Never called for can_ch or can_ihs (cable routes never transmit on silence).
    Uses ``_bypass_silence_guard`` because this request is what *establishes*
    verification -- it cannot itself be gated on being verified already.
    """
    # The adapter's own auto-detect on this car reports "ISO 15765 500K/29B":
    # Giorgio answers legislated requests on 29-bit addressing (functional
    # 18DB33F1, replies 18DAF1xx), so that route is probed first; the 11-bit
    # pair (7DF / 7E8-7EF) second. Either reply proves the bus alive.
    plans = []
    for r in routes_for(b, lk.cable):
        if r.stn_protocol == "34":
            plans.append((r, ["ATCAF1", "ATCP18", "ATSHDB33F1"]))
    for r in routes_for(b, lk.cable):
        if r.stn_protocol == "33":
            plans.append((r, ["ATCAF1", "ATSH7DF"]))
    if not plans:
        return {"ok": False, "responders": [], "raw": None, "error": None,
                "note": "no CAN-C route for cable " + repr(lk.cable)}
    last: dict[str, Any] = {"raw": None, "error": None}
    for route, setup in plans:
        with lk.session("active_probe_0100", bus=b, port=port, baud=baud, passive=False,
                        allow_while_mes_connected=allow_while_mes_connected, route=route,
                        _bypass_silence_guard=True) as sess:
            for c in setup:
                sess.cmd(c, 2)
            # The adapter answers "NO DATA" from its own reply timer (default
            # ~200 ms, adaptive); give it the full ~1 s window and ask twice.
            sess.cmd("ATAT0", 2)
            sess.cmd("ATSTFF", 2)
            q = sess.query("0100", "41", timeout=1.5)
            if not q.get("ecus"):
                q = sess.query("0100", "41", timeout=1.5)
            responders = sorted(h.upper() for h in q["all_ecus"] if _is_obd_reply(h))
            ok = bool(responders) and bool(q["ecus"])
            audit.record("active_probe", bus=b.key, request="0100", ok=ok,
                         stn_protocol=route.stn_protocol, reply_ecus=responders, raw=q["raw"])
            last = q
            if ok:
                return {"ok": True, "responders": responders, "raw": q["raw"],
                        "error": q["error"], "stn_protocol": route.stn_protocol}
    return {"ok": False, "responders": [], "raw": last.get("raw"), "error": last.get("error"),
            "note": "active probe 0100 got no reply"}


# _active_probe_3e00 was removed 2026-10-23: its "silence -> send one functional 3E 00 at
# 125k" fallback transmitted at the wrong rate after the blue A5 cable was pulled (CAN
# ERROR on CAN-C, 00:50). On cable routes silence is never a reason to transmit.


def _is_obd_reply(header: str) -> bool:
    """A legislated OBD-II reply id: 7E8-7EF (11-bit) or 18DAF1xx (29-bit)."""
    h = (header or "").upper()
    return h in _OBD_FUNCTIONAL_REPLIES or (len(h) == 8 and h.startswith("18DAF1"))


def _judge_awake(attempts: list[dict[str, Any]]) -> tuple[Optional[bool], Optional[str]]:
    """Are the modules awake? ``(True|False|None, note)``, judged from the
    11-bit route. CAN-CH 2026-10-15: the 29-bit route hears only 1E3xxxxx
    keep-alive (~12/s) awake or asleep; awake = 11-bit route hears ~400 frames/s
    over ~30 ids, asleep = 11-bit route silent."""
    short = [a for a in attempts if a["header_bits"] == 11 and not a.get("active_probe")]
    if any(a["frames"] >= 50 or len(a["ids"]) >= 15 for a in short):
        return True, None
    wide = [a for a in attempts if a["header_bits"] != 11 and a["frames"] > 0]
    if (short and all(a["frames"] < 10 for a in short) and wide
            and all(str(i).upper().startswith("1E3") for a in wide for i in a["ids"])):
        n = max(a["frames"] for a in wide)
        return False, (f"only network-management frames at 10 Hz ({n} in the window) and "
                       "nothing on the 11-bit route: modules asleep -- cycle the ignition "
                       "(or start the engine) and retry")
    return None, None


def _detect_cable_removal(lk: AdapterLink, b: Bus, port: str, baud: int,
                          allow_while_mes_connected: bool) -> Optional[dict[str, Any]]:
    """Passive listens only. The declared cable's rate heard nothing; does the
    adapter's default 500k (STP 34 then 33) hear CAN-C traffic? Then the cable
    was pulled and the adapter is on CAN-C: auto-declare 'none' (clears every
    verification) and return the mismatch record. Never transmits."""
    declared = lk.cable
    if declared == "none" or declared_rate(b, declared) == 500000:
        return None   # same rate either way: a 500k listen proves nothing
    heard = 0
    try:
        for proto in ("34", "33"):
            route = Route(declared, proto, 500000, "untested",
                          "cable-removal check: passive listen at the adapter default 500k")
            with lk.session("cable_removal_check", bus=b, port=port, baud=baud, passive=True,
                            allow_while_mes_connected=allow_while_mes_connected,
                            route=route) as s2:
                cap = capture_mod.listen(s2, seconds=1.0, max_frames=50)
            heard = max(heard, cap["count"])
            if heard >= HEARD_MIN_FRAMES:
                return lk.auto_declare_none(declared, b, heard)
    except Exception as exc:  # noqa: BLE001 -- detection is advisory, never fails the verify
        tlog.warning("cable-removal check failed: %s", exc)
    return None


def verify_bus(bus: str, seconds: float = 2.0, port: str = "", baud: int = 0,
               allow_while_mes_connected: bool = False) -> dict[str, Any]:
    """Passive listen; marks the bus verified under the current cable if traffic is seen.

    A bus can be reachable under more than one adapter protocol -- CAN-C
    carries both 29-bit UDS and the 11-bit legislated pair, and a monitor
    opened for one ID width hears nothing of the other. Every route the
    declared cable allows is tried before reporting silence, because a healthy
    bus reported as dead is the worst answer this tool can give.

    On ``can_c`` only, hearing nothing on every route is still not the end of
    the story: 2018+ Giorgio cars gateway-isolate that bus (see
    :func:`_active_probe_0100`) so a car behind the Security Gateway Module
    is silent even when perfectly healthy. One active Mode 01 PID 00 probe is
    tried before reporting silence. Cable routes and non-500k buses (can_ihs,
    can_ch) get NO active probe: they are verified only by at least
    ``HEARD_MIN_FRAMES`` frames heard at the declared rate, else verified=False
    "no traffic heard at <rate>; refusing to transmit". If the declared cable
    hears nothing but a 500k listen hears CAN-C, the cable was pulled:
    :func:`_detect_cable_removal` auto-declares 'none'.
    """
    b = _bus(bus)
    lk = link()
    candidates: list[Any] = list(routes_for(b, lk.cable)) or [None]
    risky = is_risky_route(b, lk.cable)
    attempts: list[dict[str, Any]] = []
    sess = None
    first_ok: Optional[dict[str, Any]] = None
    for route in candidates:
        with lk.session("verify_bus", bus=b, port=port, baud=baud, passive=True,
                        allow_while_mes_connected=allow_while_mes_connected,
                        route=route) as sess:
            cap = capture_mod.listen(sess, seconds=seconds, max_frames=200)
            # "DATA ERROR" is the adapter's per-frame annotation for one frame
            # whose payload did not validate; with parsed frames beside it the
            # bus is demonstrably alive, so it is reported but does not veto.
            fatal = cap["error"] and not (cap["error"] == "DATA ERROR" and cap["count"] > 0)
            # Cable routes / non-500k buses: a stray frame or two is not proof.
            ok = cap["count"] >= (HEARD_MIN_FRAMES if risky else 1) and not fatal
            attempts.append({"stn_protocol": sess.route.stn_protocol,
                             "header_bits": sess.header_bits,
                             "frames": cap["count"], "error": cap["error"],
                             "ids": cap["ids"]})
            if ok and first_ok is None:
                first_ok = {"sess": sess, "cap": cap}
    if first_ok is not None:
        cap, fsess = first_ok["cap"], first_ok["sess"]
        awake, awake_note = _judge_awake(attempts)
        extra: dict[str, Any] = {}
        note: Optional[str] = None
        if b.key == "can_c" and lk.cable == "none":
            # Hearing keep-alive frames (STMA hears ~24 on STP 34) proves the
            # bus alive but NOT which addressing the ECM answers legislated
            # Mode 01/03/07/0A/06/09 on: this Stelvio answers on the 29-bit
            # functional route some days and the 11-bit one on others. Always
            # probe, so legislated reads start on the route that works.
            try:
                probe = _active_probe_0100(lk, b, port, baud, allow_while_mes_connected)
            except Exception as exc:  # noqa: BLE001 -- the listen already verified the bus
                probe = {"ok": False, "responders": [], "raw": None, "error": str(exc),
                         "note": f"active probe 0100 failed: {exc}"}
            attempts.append({"stn_protocol": probe.get("stn_protocol") or "33",
                             "header_bits": 29 if probe.get("stn_protocol") == "34" else 11,
                             "frames": 0, "error": probe.get("error"), "ids": {},
                             "active_probe": True,
                             "responders": probe.get("responders", [])})
            extra = {"probe_ok": bool(probe["ok"]),
                     "probe_stn_protocol": probe.get("stn_protocol") if probe["ok"] else None,
                     "responders": probe.get("responders", []) if probe["ok"] else []}
            if not probe["ok"]:
                note = ("legislated route unknown: the passive listen verified the bus but "
                        "the active Mode 01 PID 00 probe got no reply on either route; "
                        "legislated reads will try the 29-bit route, then the 11-bit one")
        lk.mark_verified(b, cap["count"], awake=awake, awake_note=awake_note,
                         **({"probe_stn_protocol": extra["probe_stn_protocol"],
                             "responders": extra["responders"]} if extra else {}))
        return _stamp(fsess, {"verified": True, "frames": cap["count"],
                              "rate_hz": cap["rate_hz"], "ids": cap["ids"],
                              "error": cap["error"],
                              "stn_protocol": fsess.route.stn_protocol,
                              "header_bits": fsess.header_bits,
                              "attempts": attempts, "verified_by": "passive_listen",
                              "awake": awake, "awake_note": awake_note,
                              "note": note, **extra})
    declared_cable = lk.cable
    tried = ", ".join(f"STP {a['stn_protocol']} ({a['header_bits']}-bit)" for a in attempts)
    base_note = (f"no traffic on {b.key} with cable {lk.cable!r} on any route "
                 f"tried ({tried}); check the cable, ignition, and the route "
                 f"note: {sess.route.note}")
    if b.key == "can_c" and lk.cable == "none":
        probe = _active_probe_0100(lk, b, port, baud, allow_while_mes_connected)
        attempts.append({"stn_protocol": "33", "header_bits": 11, "frames": 0,
                         "error": probe.get("error"), "ids": {}, "active_probe": True,
                         "responders": probe.get("responders", [])})
        if probe["ok"]:
            lk.mark_verified(b, 0, verified_by="active_probe_0100",
                             probe_stn_protocol=probe.get("stn_protocol"),
                             responders=probe["responders"])
            return _stamp(sess, {"verified": True, "frames": 0, "rate_hz": 0.0, "ids": {},
                                 "error": None, "attempts": attempts,
                                 "verified_by": "active_probe_0100", "awake": True, "awake_note": None,
                                 "responders": probe["responders"],
                                 "note": ("CAN-C carries no broadcast traffic behind the "
                                          "Security Gateway Module on this platform; verified "
                                          "instead by a reply from " +
                                          ", ".join(probe["responders"]) +
                                          " to a single legislated Mode 01 PID 00 request")})
        base_note += "; " + probe["note"]
    if risky:
        # Silence on a cable route / non-500k bus: refuse, never probe. If the cable
        # was pulled the adapter is now on CAN-C at 500k -- look (passively) for that.
        mismatch = _detect_cable_removal(lk, b, port, baud, allow_while_mes_connected)
        base_note = silence_reason(declared_rate(b, declared_cable)) + "; " + base_note
        if mismatch:
            base_note = (f"CABLE REMOVED? {mismatch['note']} " + base_note)
        tlog.info("transmit decision: purpose=verify_bus bus=%s rate=%s frames_heard=0 -> "
                  "REFUSED (%s)", b.key, rate_label(declared_rate(b, declared_cable)),
                  silence_reason(declared_rate(b, declared_cable)))
        out = _stamp(sess, {"verified": False, "frames": 0, "rate_hz": 0.0, "ids": {},
                            "error": attempts[-1]["error"] if attempts else None,
                            "attempts": attempts, "verified_by": None, "awake": None,
                            "awake_note": None, "note": base_note,
                            "reason": silence_reason(declared_rate(b, declared_cable))})
        if mismatch:
            out["cable_mismatch"] = mismatch
        return out
    return _stamp(sess, {"verified": False, "frames": 0, "rate_hz": 0.0, "ids": {},
                         "error": attempts[-1]["error"] if attempts else None,
                         "attempts": attempts, "verified_by": None, "awake": None,
                         "awake_note": None, "note": base_note})


def capture(bus: str, seconds: float = 2.0, max_frames: int = 500,
            filters: Optional[list[str]] = None, include_frames: bool = True,
            allow_while_mes_connected: bool = False) -> dict[str, Any]:
    b = _bus(bus)
    with link().session("capture", bus=b, passive=True,
                        allow_while_mes_connected=allow_while_mes_connected) as sess:
        cap = capture_mod.listen(sess, seconds=seconds, max_frames=max_frames, filters=filters)
        if not include_frames:
            cap["frames"] = cap["frames"][:20]
            cap["frames_truncated"] = True
        return _stamp(sess, cap)


# --- legislated OBD on CAN-C -------------------------------------------------

def _legislated_routes_in_order(ver: Optional[dict[str, Any]] = None) -> list[Any]:
    """The CAN-C routes legislated OBD can use, preferred first (29-bit/11-bit).

    Giorgio ECMs answer legislated Modes 01/03/07/0A/06/09 on EITHER the
    29-bit functional pair (18DB33F1 -> 18DAF110/118, STP 34) or the 11-bit
    one (7DF -> 7E8-7EF, STP 33), and which one varies by day (11-bit only on
    2026-09-25, 29-bit only on 2026-10-13, both flavours seen since). The
    route ``verify_bus``'s active probe proved is preferred whenever it is
    recorded, however the bus was verified (a passive listen proves the bus
    alive, not the legislated route); with no probe result the 29-bit route
    goes first and the 11-bit one second. Callers retry once on the other
    route when the preferred one is silent (:func:`_obd_read`).
    """
    lk = link()
    if ver is None:
        ver = (getattr(lk, "verified", {}) or {}).get(CAN_C.key) or {}
    want = ver.get("probe_stn_protocol")
    available = routes_for(CAN_C, lk.cable)
    order: list[Any] = []
    for proto in dict.fromkeys([p for p in (want, "34", "33") if p]):
        for route in available:
            if route.stn_protocol == proto and route not in order:
                order.append(route)
                break
    return order


def _obd_route() -> Any:
    """The preferred legislated route on CAN-C (see :func:`_legislated_routes_in_order`)."""
    order = _legislated_routes_in_order()
    return order[0] if order else None


_legislated_route = _obd_route


def _obd_session(purpose: str, **kw: Any):
    kw.setdefault("route", _obd_route())
    return link().session(purpose, bus=CAN_C, **kw)


def _obd_read(purpose: str, body: Callable[[Session], dict[str, Any]],
              answered: Callable[[dict[str, Any]], bool], **kw: Any) -> dict[str, Any]:
    """Run a legislated read on the preferred route; if no ECU answered it,
    retry ONCE on the other route.

    ``body(sess)`` does the read and returns its result; ``answered(result)``
    says whether any ECU gave a positive answer. A route that answers is
    remembered on the link's CAN-C verification so the next read starts there.
    When neither route answers, the preferred route's result is returned (its
    diagnostics are the ones the caller expects) with ``route_fallback``
    added, so the second attempt is visible. A caller-supplied ``route`` pins
    the read to that route with no retry.
    """
    if kw.get("route") is not None:
        with link().session(purpose, bus=CAN_C, **kw) as sess:
            return body(sess)
    kw.pop("route", None)
    order = _legislated_routes_in_order()[:2] or [None]
    first: Optional[dict[str, Any]] = None
    for i, route in enumerate(order):
        with link().session(purpose, bus=CAN_C, route=route, **kw) as sess:
            out = body(sess)
        if answered(out):
            if i:
                out["route_fallback"] = {"tried": [r.stn_protocol for r in order[:i + 1]],
                                         "answered_on": route.stn_protocol}
                ver = (getattr(link(), "verified", {}) or {}).get(CAN_C.key)
                if isinstance(ver, dict):
                    ver["probe_stn_protocol"] = route.stn_protocol
            return out
        if first is None:
            first = out
    if len(order) > 1 and first is not None:
        first["route_fallback"] = {"tried": [r.stn_protocol for r in order], "answered_on": None}
    return first if first is not None else {}


def _negative_responses(q: dict[str, Any]) -> list[str]:
    """Human-readable NRC lines for every ECU that answered 7F."""
    from .uds import NRC_TEXT as NRC  # local: keep the OBD path free of the UDS client
    lines: list[str] = []
    for hdr, data in (q.get("all_ecus") or {}).items():
        if len(data) >= 3 and data[0].upper() == "7F":
            nrc = int(data[2], 16)
            lines.append(f"ECU {hdr} answered NRC 0x{nrc:02X} "
                         f"({NRC.get(nrc, 'unknown')}) to service {data[1]}")
    return lines


def _silence_reason(sess: Session) -> str:
    """Why no ECU answered, judged from the voltage at the OBD port.

    "With the ignition off this is expected" was printed on 2026-09-25 while
    the port read 14.1 V with the engine running; the real cause was the
    adapter's bus access. Charging voltage rules the ignition out.
    """
    try:
        raw = sess.cmd("ATRV", 2)
    except Exception:  # noqa: BLE001 -- the explanation must never fail the read
        raw = ""
    m = re.search(r"(\d+\.\d+)V", raw or "")
    if not m:
        return ("no vehicle voltage at the adapter: it is not plugged into the car, or the "
                "car is fully off")
    v = float(m.group(1))
    if v >= 13.3:
        return (f"the port reads {v:.1f} V, so the engine is running: the ignition does NOT "
                f"explain the silence. Check the adapter's bus access: HS/MS switch on HS, "
                f"plug fully seated, no coloured cable fitted for CAN-C")
    if v < 11.0:
        return f"the port reads {v:.1f} V: the battery is low enough for modules to drop out"
    return (f"the port reads {v:.1f} V: the ignition may be off. Turn it ON and retry; if it "
            f"is already on, check the HS/MS switch and that the plug is fully seated")


def _dtc_read(sess: Session, mode: str, response_byte: str, label: str) -> dict[str, Any]:
    sess.untarget()
    q = sess.query(mode, response_byte)
    out: dict[str, Any] = {"kind": label, "raw": q["raw"]}
    if q["error"]:
        out["error"] = (f"ADAPTER/BUS ERROR: {q['error']}. This is NOT 'no codes'; the read did "
                        f"not complete.")
        return _stamp(sess, out)
    per_ecu = {hdr: decode_obd_dtcs(data) for hdr, data in q["ecus"].items()}
    out["dtcs"] = sorted({c for codes in per_ecu.values() for c in codes})
    out["by_ecu"] = per_ecu
    if not q["ecus"]:
        neg = _negative_responses(q)
        if neg:
            out["warning"] = ("negative response, not silence: " + "; ".join(neg) +
                              ". The service is refused on this route/session, so the "
                              "read did NOT complete.")
        else:
            out["warning"] = ("no ECU answered" + (" (NO DATA)" if no_data(q["raw"]) else "") +
                              "; " + _silence_reason(sess))
    if label == "stored" and not out["dtcs"]:
        out["note"] = _MODE03_NOTE
    return _observe(sess, "obd_dtcs", out)


_KINDS = {"stored": ("03", "43"), "pending": ("07", "47"), "permanent": ("0A", "4A")}


def obd_dtcs(kind: str = "stored", **kw: Any) -> dict[str, Any]:
    if kind not in _KINDS:
        raise BadCommand(f"kind must be one of {list(_KINDS)}")
    mode, resp = _KINDS[kind]
    return _obd_read(f"read_{kind}_dtcs", lambda sess: _dtc_read(sess, mode, resp, kind),
                     _dtc_answered, **kw)


def _dtc_answered(r: dict[str, Any]) -> bool:
    return "warning" not in r and "error" not in r


def obd_all_dtcs(**kw: Any) -> dict[str, Any]:
    return _obd_read(
        "read_all_dtcs",
        lambda sess: _stamp(sess, {k: _dtc_read(sess, m, r, k) for k, (m, r) in _KINDS.items()}),
        lambda r: any(_dtc_answered(r[k]) for k in _KINDS if isinstance(r.get(k), dict)), **kw)


def obd_pid(pid: str, **kw: Any) -> dict[str, Any]:
    hex_pid, spec = resolve_pid(pid)

    def body(sess: Session) -> dict[str, Any]:
        sess.untarget()
        q = sess.query(f"01{hex_pid}", "41")
        out: dict[str, Any] = {"pid": hex_pid, "name": spec.name if spec else None, "raw": q["raw"]}
        if q["error"]:
            out["error"] = f"ADAPTER/BUS ERROR: {q['error']}; the read did not complete"
            return _stamp(sess, out)
        readings = {hdr: decode_pid(hex_pid, spec, data[2:])
                    for hdr, data in q["ecus"].items() if len(data) >= 2 and data[1] == hex_pid}
        out["by_ecu"] = readings
        first = next(iter(readings.values()), None)
        if first is not None:
            out["value"], out["unit"] = first.get("value"), first.get("unit")
        else:
            out["warning"] = "no ECU answered this PID; " + _silence_reason(sess)
        return _stamp(sess, out)

    return _obd_read("read_pid", body, lambda r: bool(r.get("by_ecu")), **kw)


def obd_pids_snapshot(pids: list[str], **kw: Any) -> dict[str, Any]:
    """Every Mode 01 PID in ``pids`` inside ONE held adapter session, via
    :meth:`~cuore.live.transport.Session.query_pids` (<=6 PIDs per request,
    per-ECU split, automatic per-PID fallback) -- the batched replacement
    for calling :func:`obd_pid` once per PID, each of which pays its own
    session open/close. See
    docs/research/OBD_CONNECTIVITY_REVIEW_2026-10-14.md for the before/
    after session-count estimate this removes.
    """
    def body(sess: Session) -> dict[str, Any]:
        sess.untarget()
        q = sess.query_pids(pids)
        by_ecu: dict[str, dict[str, Any]] = {}
        for hdr, pid_data in q["by_ecu"].items():
            readings: dict[str, Any] = {}
            for pid, data in pid_data.items():
                spec = PIDS_BY_HEX.get(pid)
                dec = decode_pid(pid, spec, data)
                readings[pid] = {"name": spec.name if spec else None,
                                 "value": dec.get("value"), "unit": dec.get("unit")}
            by_ecu[hdr] = readings
        out = {"by_ecu": by_ecu, "requests_sent": q["requests_sent"],
              "multi_pid_used": q["multi_pid_used"]}
        return _observe(sess, "pids_snapshot", out)

    return _obd_read("read_pids_snapshot", body, lambda r: bool(r.get("by_ecu")), **kw)


def obd_freeze_frames(pids: list[str], **kw: Any) -> dict[str, Any]:
    """Every freeze-frame PID in ``pids`` (Mode 02, frame 0) inside ONE held
    adapter session -- the batched replacement for calling
    :func:`obd_freeze_frame` once per PID. PID "02" (the stored DTC itself)
    is decoded as a DTC, exactly as :func:`obd_freeze_frame` does; every
    other PID is decoded with :func:`~cuore.live.obd.decode_pid`. Mode 02
    has no J1979 multi-PID batching the way Mode 01 does (one PID per
    request, each naming its own frame number), so the saving here is the
    held session, not fewer requests.
    """
    with _obd_session("read_freeze_frame_set", **kw) as sess:
        sess.untarget()
        by_ecu: dict[str, dict[str, Any]] = {}
        requests = 0
        for pid in dict.fromkeys(pids):
            hex_pid, spec = resolve_pid(pid) if pid.strip() else ("02", None)
            q = sess.query(f"02{hex_pid}00", "42")
            requests += 1
            if q["error"]:
                continue
            for hdr, data in q["ecus"].items():
                if len(data) < 3 or data[1] != hex_pid:
                    continue
                payload = data[3:]
                if hex_pid == "02":
                    code = dtc_from_two_bytes(payload[0], payload[1]) if len(payload) >= 2 else None
                    by_ecu.setdefault(hdr, {})[hex_pid] = {"name": spec.name if spec else None,
                                                           "dtc": code, "bytes": payload}
                else:
                    dec = decode_pid(hex_pid, spec, payload)
                    by_ecu.setdefault(hdr, {})[hex_pid] = {"name": spec.name if spec else None,
                                                           "value": dec.get("value"),
                                                           "unit": dec.get("unit")}
        out = {"by_ecu": by_ecu, "requests_sent": requests}
        return _observe(sess, "freeze_frame_set", out)


def obd_voltage(**kw: Any) -> dict[str, Any]:
    with link().session("read_voltage", bus=CAN_C, passive=True, **kw) as sess:
        r = sess.cmd("ATRV", 2)
        m = re.search(r"(\d+\.\d+)V", r)
        return _stamp(sess, {"raw": r, "volts": float(m.group(1)) if m else None,
                             "vehicle_power_detected": bool(m)})


def obd_supported_pids(**kw: Any) -> dict[str, Any]:
    def body(sess: Session) -> dict[str, Any]:
        sess.untarget()
        out: dict[str, Any] = {"by_ecu": {}, "raw": {}}
        for base in ("00", "20", "40", "60", "80", "A0", "C0"):
            q = sess.query(f"01{base}", "41")
            out["raw"][base] = q["raw"]
            if q["error"]:
                out.setdefault("errors", {})[base] = q["error"]
                break
            any_next = False
            for hdr, data in q["ecus"].items():
                if len(data) < 6 or data[1] != base:
                    continue
                supported, more = decode_supported_pids(base, data[2:6])
                out["by_ecu"].setdefault(hdr, []).extend(supported)
                any_next = any_next or more
            if not any_next:
                break
        for hdr, lst in out["by_ecu"].items():
            out["by_ecu"][hdr] = {"count": len(lst), "pids": lst,
                                  "known_names": [PIDS_BY_HEX[p].name for p in lst if p in PIDS_BY_HEX]}
        return _stamp(sess, out)

    return _obd_read("read_supported_pids", body, lambda r: bool(r.get("by_ecu")), **kw)


def obd_freeze_frame(pid: str = "", **kw: Any) -> dict[str, Any]:
    hex_pid, spec = resolve_pid(pid) if pid.strip() else ("02", None)
    with _obd_session("read_freeze_frame", **kw) as sess:
        sess.untarget()
        q = sess.query(f"02{hex_pid}00", "42")
        out: dict[str, Any] = {"pid": hex_pid, "name": spec.name if spec else None, "raw": q["raw"]}
        if q["error"]:
            out["error"] = f"ADAPTER/BUS ERROR: {q['error']}; the read did not complete"
            return _stamp(sess, out)
        by_ecu: dict[str, Any] = {}
        for hdr, data in q["ecus"].items():
            if len(data) < 3 or data[1] != hex_pid:
                continue
            payload = data[3:]
            if hex_pid == "02":
                code = dtc_from_two_bytes(payload[0], payload[1]) if len(payload) >= 2 else None
                by_ecu[hdr] = {"dtc": code, "bytes": payload}
            else:
                by_ecu[hdr] = decode_pid(hex_pid, spec, payload)
        out["by_ecu"] = by_ecu
        if not by_ecu:
            out["warning"] = "no ECU returned a freeze frame (none stored, or ignition off)"
        return _observe(sess, "freeze_frame", out)


def obd_vin(**kw: Any) -> dict[str, Any]:
    def body(sess: Session) -> dict[str, Any]:
        sess.untarget()
        q = sess.query("0902", "49", 6)
        out: dict[str, Any] = {"raw": q["raw"]}
        if q["error"]:
            out["error"] = f"ADAPTER/BUS ERROR: {q['error']}; the read did not complete"
            return _stamp(sess, out)
        for hdr, data in q["ecus"].items():
            if len(data) >= 3 and data[1] == "02":
                vin = "".join(chr(int(b, 16)) for b in data[3:] if 32 <= int(b, 16) < 127)
                out.update({"vin": vin, "ecu": hdr, "length_ok": len(vin) == 17})
                if len(vin) == 17:
                    sess.link.vin = vin
                break
        if "vin" not in out:
            out["warning"] = "no ECU answered Mode 09 PID 02; " + _silence_reason(sess)
        return _stamp(sess, out)

    return _obd_read("read_vin", body, lambda r: "vin" in r, **kw)


def readiness_in(sess: Session) -> dict[str, Any]:
    sess.untarget()
    out: dict[str, Any] = {}
    for pid, label in (("01", "since_clear"), ("41", "this_drive_cycle")):
        q = sess.query(f"01{pid}", "41")
        if q["error"]:
            out[label] = {"error": q["error"], "raw": q["raw"]}
            continue
        decoded = None
        for hdr, data in q["ecus"].items():
            decoded = decode_readiness(data, "41")
            if decoded:
                decoded["ecu"] = hdr
                break
        neg = _negative_responses(q) if not decoded else []
        out[label] = decoded or {"error": ("negative response: " + "; ".join(neg)) if neg
                                 else "could not decode readiness response", "raw": q["raw"]}
        if not decoded and not neg and no_data(q["raw"]):
            out[label]["why"] = _silence_reason(sess)
    verdict = evap_verdict(out.get("since_clear") or {})
    if verdict:
        out["evap_verdict"] = verdict
    counters: dict[str, Any] = {}
    for name, hex_pid in (("warmups_since_clear", "30"), ("distance_since_clear", "31")):
        q = sess.query(f"01{hex_pid}", "41")
        if q["error"]:
            continue
        for _hdr, data in q["ecus"].items():
            if len(data) >= 3 and data[1] == hex_pid:
                dec = decode_pid(hex_pid, PIDS_BY_HEX[hex_pid], data[2:])
                if "value" in dec:
                    counters[name] = dec["value"]
                break
    if counters:
        out["drive_cycle_counters"] = counters
    return _observe(sess, "readiness", out)


def obd_readiness(**kw: Any) -> dict[str, Any]:
    return _obd_read("read_readiness", readiness_in,
                     lambda r: any(isinstance(r.get(k), dict) and r[k].get("ecu")
                                   for k in ("since_clear", "this_drive_cycle")), **kw)


# --- UDS on any bus ----------------------------------------------------------

def _compact_dtc_result(mod: dict[str, Any]) -> dict[str, Any]:
    """Summarise one module's UDS DTC read for ``detail=False`` callers.

    A UDS 0x19 02 reply lists every code the module TRACKS, not every code
    that is failing -- the ECM alone tracks 278 and reports all of them. Most
    callers only need what is wrong now, so this keeps the status/metadata
    fields and collapses the ``dtcs`` list to active/history counts plus the
    full records for the active codes only. :func:`coverage.classify_records`
    already does the status-byte classification for the coverage sweep; it is
    reused here rather than re-implemented so the two summaries never drift
    out of sync with what the status bits mean.
    """
    from . import coverage
    out = {k: mod[k] for k in
           ("ecu", "bus", "mask", "error", "nrc", "warning", "note", "skipped")
           if k in mod}
    if "dtcs" not in mod:
        return out
    records = mod.get("dtcs") or []
    cls = coverage.classify_records(records)
    active_set = set(cls["active"])
    out["active"] = cls["active"]
    out["history"] = cls["history"]
    out["tracked"] = cls["tracked"]
    out["not_run_since_clear"] = cls["not_run_since_clear"]
    out["active_records"] = [r for r in records if r.get("code") in active_set]
    return out


def module_dtcs(code: str, vin: str = "", mask: int = 0xFF, confirm: bool = False,
                detail: bool = True, **kw: Any) -> dict[str, Any]:
    """UDS 0x19 02 on one module. ``detail=False`` summarises the DTC list --
    see :func:`_compact_dtc_result`. The FULL result is always what gets
    recorded as the observation; only the returned value is ever summarised.
    """
    ecu = uds_mod.resolve_module(code, vin or None)
    with link().session(f"module_dtcs {ecu.code}", bus=_bus(ecu.bus_key), confirm=confirm,
                        **kw) as sess:
        full = _observe(sess, "module_dtcs", uds_mod.read_dtcs(sess, ecu, mask), vin)
        return full if detail else _compact_dtc_result(full)


def module_identity(code: str, vin: str = "", confirm: bool = False, **kw: Any) -> dict[str, Any]:
    ecu = uds_mod.resolve_module(code, vin or None)
    with link().session(f"module_identity {ecu.code}", bus=_bus(ecu.bus_key), confirm=confirm,
                        **kw) as sess:
        out = uds_mod.identity(sess, ecu)
        f190 = (out.get("fields") or {}).get("F190") or {}
        if f190.get("ascii") and len(f190["ascii"]) == 17:
            sess.link.vin = f190["ascii"]
        return _observe(sess, "identity", out, vin)


def module_did(code: str, did: str, vin: str = "", confirm: bool = False, **kw: Any
               ) -> dict[str, Any]:
    ecu = uds_mod.resolve_module(code, vin or None)
    try:
        did_int = int(did, 16)
    except ValueError:
        raise BadCommand(f"did must be hex, got {did!r}")
    if not 0 <= did_int <= 0xFFFF:
        raise BadCommand("did must be 0000..FFFF")
    with link().session(f"module_did {ecu.code} {did_int:04X}", bus=_bus(ecu.bus_key),
                        confirm=confirm, **kw) as sess:
        return _observe(sess, "did", uds_mod.read_did(sess, ecu, did_int), vin)


def module_did_sweep(code: str, dids: list[str], vin: str = "", per_did_timeout: float = 0.3,
                     confirm: bool = False, **kw: Any) -> dict[str, Any]:
    """Read-only 0x22 sweep of a caller-given candidate DID list against
    one module, in one adapter session for the whole list (contrast
    :func:`module_did`, one session per call). For a short, documented-
    candidates-only discovery sweep (:mod:`cuore.live.fullscan`'s TCM DID
    discovery is the first caller) -- never a blind scan of DID-space (see
    :func:`module_discover_dids` for that, a different tool for a
    different, broader job). Returns ``{"ecu", "bus", "tried", "hits":
    [{"did", "bytes"}, ...]}``; a DID that times out or answers negative
    is simply not a hit, never an error that stops the sweep.
    """
    ecu = uds_mod.resolve_module(code, vin or None)
    with link().session(f"module_did_sweep {ecu.code}", bus=_bus(ecu.bus_key),
                        confirm=confirm, **kw) as sess:
        hits: list[dict[str, Any]] = []
        tried = 0
        for did in dids:
            try:
                did_int = int(did, 16)
            except (TypeError, ValueError):
                continue
            tried += 1
            r = uds_mod.read_did(sess, ecu, did_int, timeout=per_did_timeout)
            if r.get("bytes"):
                hits.append({"did": f"{did_int:04X}", "bytes": r["bytes"]})
        result = {"ecu": ecu.code, "bus": sess.bus.key, "tried": tried, "hits": hits}
        return _observe(sess, "did_discovery", result, vin)


def scan_modules(bus: str = "can_c", vin: str = "", mask: int = 0xFF, confirm: bool = False,
                 detail: bool = True, **kw: Any) -> dict[str, Any]:
    """UDS DTC sweep over every confirmed module on a bus. ``detail=False``
    summarises each module's DTC list -- see :func:`_compact_dtc_result`. The
    FULL scan, and the FULL per-module result, are what get recorded as
    observations; only the returned value is ever summarised.
    """
    b = _bus(bus)
    with link().session(f"scan_modules {b.key}", bus=b, confirm=confirm, **kw) as sess:
        out = _observe(sess, "scan", uds_mod.scan_bus(sess, b, vin or None, mask), vin)
        for mod in out.get("modules", []):
            if "codes" in mod:
                store.record_observation("module_dtcs", mod,
                                         vin=vin or getattr(sess.link, "vin", ""),
                                         bus=b.key, cable=sess.link.cable,
                                         stream=sess.stream.describe)
        if not detail:
            out = {**out, "modules": [_compact_dtc_result(m) for m in out.get("modules", [])]}
        return out


def sweep_bus_full(bus: str = "can_c", vin: str = "", mask: int = 0xFF, confirm: bool = False,
                   known_did: Optional[Callable[[str], Optional[int]]] = None,
                   **kw: Any) -> dict[str, Any]:
    """DTCs, identity, and (when ``known_did`` names one) one DID per module
    on ``bus`` -- all inside the ONE adapter session this opens, via
    :func:`cuore.live.uds.sweep_bus_full`. The held-session replacement for
    a full-vehicle scan's old per-module pattern of :func:`scan_modules`
    (one open) then :func:`module_identity` (one open per module) then
    :func:`module_did` (one open per module with a known DID) -- see
    docs/research/OBD_CONNECTIVITY_REVIEW_2026-10-14.md for the timed
    before/after. ``known_did`` is an optional ``code -> Optional[int]``
    callable (e.g. ``fullscan._known_did`` bound to one car's VIN) naming
    the one DID to also read per module.

    Every module's ``dtcs``/``identity``/``did`` sub-result is recorded as
    its own observation here too (``module_dtcs``, ``module_identity``,
    ``did``) for a direct call to this function; a caller that monkeypatches
    this whole function (as the fullscan test suite does, by design -- see
    ``cuore.live.fullscan``'s own docstring) skips that silently and records
    from the returned dict itself instead, which is harmless duplication,
    never a gap.
    """
    b = _bus(bus)
    with link().session(f"sweep_bus_full {b.key}", bus=b, confirm=confirm, **kw) as sess:
        out = uds_mod.sweep_bus_full(sess, b, vin=vin or None, mask=mask, known_did=known_did)
        v = vin or getattr(sess.link, "vin", "") or ""
        for mod in out.get("modules", []):
            if "codes" in mod:
                store.record_observation("module_dtcs", mod, vin=v, bus=b.key,
                                         cable=sess.link.cable, stream=sess.stream.describe)
            if mod.get("identity") is not None:
                store.record_observation("module_identity", mod["identity"], vin=v, bus=b.key,
                                         cable=sess.link.cable, stream=sess.stream.describe)
            if mod.get("did") is not None:
                store.record_observation("did", mod["did"], vin=v, bus=b.key,
                                         cable=sess.link.cable, stream=sess.stream.describe)
        return _stamp(sess, out)


def discover(bus: str = "can_c", vin: str = "", confirm: bool = False,
             candidates: Optional[list[str]] = None, per_target_timeout: float = 0.25,
             stop_after: Optional[int] = None,
             probe_dids: Optional[list[str]] = None, deadline_s: float = 60.0,
             max_targets: Optional[int] = None, **kw: Any) -> dict[str, Any]:
    b = _bus(bus)
    cands = None
    if candidates:
        try:
            cands = [int(c, 16) for c in candidates]
        except ValueError:
            raise BadCommand("candidates must be hex target bytes")
    pdids = tuple(d.upper() for d in probe_dids) if probe_dids else ("F190",)
    if not all(len(d) == 4 and all(c in "0123456789ABCDEF" for c in d) for d in pdids):
        raise BadCommand("probe_dids must be 4-hex-digit DIDs")
    with link().session(f"discover {b.key}", bus=b, confirm=confirm, **kw) as sess:
        return _stamp(sess, uds_mod.discover(sess, b, vin_expected=vin or None,
                                             candidates=cands,
                                             per_target_timeout=per_target_timeout,
                                             stop_after=stop_after, probe_dids=pdids,
                                             deadline_s=max(5.0, min(float(deadline_s), 170.0)),
                                             max_targets=max_targets))


def discover_11bit(bus: str = "can_ch", vin: str = "", confirm: bool = False,
                   candidates: Optional[list[str]] = None, per_target_timeout: float = 0.25,
                   stop_after: Optional[int] = None, rx_mode: str = "plus8",
                   **kw: Any) -> dict[str, Any]:
    """Read-only 11-bit physical UDS sweep (3E 00 then identity), nothing persisted."""
    from . import discover11
    b = _bus(bus)
    r11 = [r for r in routes_for(b, link().cable) if r.stn_protocol == "33"]
    if not r11:
        raise BadCommand(f"bus {b.key} has no 11-bit (STP 33) route for cable {link().cable!r}")
    cands = None
    if candidates:
        try:
            cands = [int(c, 16) for c in candidates]
        except ValueError:
            raise BadCommand("candidates must be hex 11-bit request ids")
    with link().session(f"discover_11bit {b.key}", bus=b, confirm=confirm,
                        route=r11[0], **kw) as sess:
        return _stamp(sess, discover11.discover_11bit(
            sess, b, candidates=cands, per_target_timeout=per_target_timeout,
            stop_after=stop_after, rx_mode=rx_mode))


def observations(n: int = 50, vin: str = "", kind: str = "") -> dict[str, Any]:
    return {"path": str(store.observations_path()),
            "entries": store.recent_observations(n, vin=vin, kind=kind)}


# --- repair verification --------------------------------------------------------

def repair_status(codes: list[str], module: str = "ECM", vin: str = "",
                  read: bool = True, confirm: bool = False) -> dict[str, Any]:
    """Has each named test re-run since the clear, and did it pass?

    ``read=True`` reads the module now (0x19 02 FF); either way the answer
    carries a timeline from every earlier real read of this module for this
    VIN, so progress is visible drive by drive.
    """
    from datetime import datetime
    from . import repair
    if not [c for c in codes if c.strip()]:
        raise BadCommand("name at least one code, e.g. P0455,P0456,P0440")
    out: dict[str, Any] = {"module": module.upper(), "vin": vin or None}
    if read:
        now = module_dtcs(module, vin=vin, confirm=confirm)
        answered = not now.get("error") and now.get("codes") is not None
        out["read_at"] = datetime.now().isoformat(timespec="seconds")
        out["read_problem"] = now.get("error") or now.get("warning") or None
        out.update(repair.assess(codes, now.get("dtcs") or [], answered))
    history = ([o for o in store.recent_observations(1000, vin=vin, kind="module_dtcs")
                if store.is_from_car(o)] if vin else [])
    out["timeline"] = repair.timeline(codes, history, module)
    if not vin:
        out["timeline_note"] = "pass vin to see earlier reads of this car"
    return out


# --- deeper reads: Mode $06, DTC detail -----------------------------------------

def obd_mode06(mids: Optional[list[str]] = None, **kw: Any) -> dict[str, Any]:
    """OBD Mode $06 on-board test results, with the EVAP tests summarised."""
    from . import mode06
    def body(sess: Session) -> dict[str, Any]:
        out = mode06.read_mode06(sess, mids=[m.upper() for m in mids] if mids else None)
        out["evap_summary"] = mode06.evap_summary(out)
        return _observe(sess, "mode06", out)

    def answered(r: dict[str, Any]) -> bool:
        discovered = {h: v for h, v in (r.get("supported") or {}).items() if h != "requested"}
        return bool(discovered) or any(e.get("by_ecu") for e in (r.get("results") or {}).values())

    return _obd_read("read_mode06", body, answered, **kw)


def module_dtc_detail(code: str, dtc: str, vin: str = "", confirm: bool = False,
                      **kw: Any) -> dict[str, Any]:
    """Status, snapshot records and extended data (counters) for one code on one module."""
    from . import dtc_detail
    ecu = uds_mod.resolve_module(code, vin or None)
    with link().session(f"dtc_detail {ecu.code} {dtc}", bus=_bus(ecu.bus_key), confirm=confirm,
                        **kw) as sess:
        return _observe(sess, "dtc_detail", dtc_detail.dtc_detail(sess, ecu, dtc), vin)


def module_dtc_count(code: str, vin: str = "", mask: int = 0xFF, confirm: bool = False,
                     **kw: Any) -> dict[str, Any]:
    from . import dtc_detail
    ecu = uds_mod.resolve_module(code, vin or None)
    with link().session(f"dtc_count {ecu.code}", bus=_bus(ecu.bus_key), confirm=confirm,
                        **kw) as sess:
        return _stamp(sess, dtc_detail.dtc_count(sess, ecu, mask))


def module_read_all(code: str, vin: str = "", include_unverified: bool = True,
                    confirm: bool = False, **kw: Any) -> dict[str, Any]:
    """Identity plus every catalogued identifier for one module, decoded where known."""
    from . import readall
    ecu = uds_mod.resolve_module(code, vin or None)
    with link().session(f"read_all {ecu.code}", bus=_bus(ecu.bus_key), confirm=confirm,
                        **kw) as sess:
        return _observe(sess, "read_all", readall.read_all(sess, ecu, include_unverified), vin)


def module_discover_dids(code: str, vin: str = "", ranges: Optional[list[str]] = None,
                         max_dids: int = 2000, confirm: bool = False, **kw: Any
                         ) -> dict[str, Any]:
    """Read-only 0x22 sweep for identifiers the catalogue does not know.

    ``ranges`` like ["F180-F1FF", "1000-10FF"]; default is the module's conservative set.
    """
    from . import readall
    ecu = uds_mod.resolve_module(code, vin or None)
    rng = None
    if ranges:
        rng = []
        for r in ranges:
            a, _, b = r.partition("-")
            rng.append((int(a, 16), int(b or a, 16)))
    with link().session(f"discover_dids {ecu.code}", bus=_bus(ecu.bus_key), confirm=confirm,
                        **kw) as sess:
        args = {"max_dids": max_dids}
        if rng is not None:
            args["ranges"] = rng
        return _observe(sess, "did_discovery", readall.discover_dids(sess, ecu, **args), vin)


# --- clearing (the one write): per module, evidence first --------------------------

def clear_module_dtcs(code: str, consent: str, vin: str = "", confirm: bool = False,
                      group: str = "FFFFFF", override_speed_check: bool = False,
                      **kw: Any) -> dict[str, Any]:
    """Clear one module's DTCs after capturing evidence. Not exposed over HTTP.

    Refuses unless ``consent`` is exactly ``CLEAR <MODULE>``, the vehicle reads
    stationary (or ``override_speed_check`` is set because speed cannot be read),
    and, on CAN-CH, ``confirm`` is given.
    """
    from . import clear as clear_mod
    ecu = uds_mod.resolve_module(code, vin or None)
    clear_mod.assert_clear_allowed(ecu.code, consent, group)   # fail fast, before any traffic
    speed = None
    try:
        sp = obd_pid("0D", **kw)
        if sp.get("value") is not None:
            speed = float(sp["value"])
    except LiveError:
        speed = None
    if speed is None and not override_speed_check:
        raise Refused("could not read vehicle speed; refusing to clear. Pass "
                      "override_speed_check=True only if the car is stationary.")
    if speed:
        raise Refused(f"vehicle speed reads {speed:g} km/h; refusing to clear while moving")
    with link().session(f"clear {ecu.code}", bus=_bus(ecu.bus_key), confirm=confirm,
                        **kw) as sess:
        out = clear_mod.clear_module(sess, ecu, consent=consent, vin=vin, group=group,
                                     evidence_extra={"vehicle_speed_kmh": speed})
        return _stamp(sess, out)


# --- passive learning from a dealer tool ---------------------------------------------

def learn_capture(bus: str = "can_c", seconds: float = 20.0, max_frames: int = 20000
                  ) -> dict[str, Any]:
    """Passive capture while wiTECH reads; saves frames and the UDS transactions found."""
    import json as _json
    from . import learn
    from .config import state_dir
    cap = capture(bus, seconds=seconds, max_frames=max_frames, include_frames=True)
    frames = cap.get("frames") or []
    trans = learn.uds_transactions(frames)
    d = state_dir() / "captures"
    d.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{bus}.json"
    (d / name).write_text(_json.dumps({"bus": bus, "frames": frames, "transactions": trans},
                                      default=str), encoding="utf-8")
    dids = sorted({(t.get("target"), t.get("did")) for t in trans if t.get("did")})
    return {"capture": name, "frames": len(frames), "transactions": len(trans),
            "dids_seen": [{"target": a, "did": b} for a, b in dids],
            "error": cap.get("error")}


def learn_correlate(capture_name: str, marks: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank identifiers whose values track what the technician saw in wiTECH."""
    import json as _json
    from . import learn
    from .config import state_dir
    p = state_dir() / "captures" / Path(capture_name).name
    if not p.exists():
        raise BadCommand(f"no capture named {capture_name!r}")
    data = _json.loads(p.read_text(encoding="utf-8"))
    series = learn.did_series(data.get("transactions") or [])
    ranked = learn.correlate(series, marks)
    return {"capture": p.name, "candidates": ranked[:15]}


def learn_accept(vin: str, module_code: str, did: str, name: str, field: dict[str, Any],
                 scale: Optional[float] = None, offset: Optional[float] = None,
                 unit: Optional[str] = None, evidence: Optional[Any] = None) -> dict[str, Any]:
    from . import learned
    return learned.accept(vin, module_code, did, name, field, scale=scale, offset=offset,
                          unit=unit, evidence=evidence)


def learned_dids(vin: str = "") -> dict[str, Any]:
    from . import learned
    return {"learned": learned.learned(vin or None)}


# --- whole-vehicle coverage ---------------------------------------------------

def coverage_status() -> dict[str, Any]:
    from . import coverage
    return coverage.status()


def coverage_start(vin: str, engine_running: Optional[bool] = None) -> dict[str, Any]:
    from . import coverage
    return coverage.start(vin, engine_running=engine_running)


def coverage_run(key: str, confirm: bool = False, seconds: float = 3.0,
                 discover: Optional[bool] = None) -> dict[str, Any]:
    import sys
    from . import coverage
    return coverage.run_pass(key, ops=sys.modules[__name__], confirm=confirm,
                             seconds=seconds, discover=discover)


def coverage_skip(key: str, reason: str = "") -> dict[str, Any]:
    from . import coverage
    return coverage.skip_pass(key, reason)


def coverage_report() -> dict[str, Any]:
    from . import coverage
    return coverage.report()


def coverage_reset() -> dict[str, Any]:
    from . import coverage
    return coverage.reset()


# --- actuator tests: learned from a dealer tool, replayed under strict guards -----

def learn_actuator(capture_name: str, module: str, name: str, tool: str = "MES") -> dict[str, Any]:
    """Extract a replayable procedure for one module's actuator test from a saved capture.

    ``capture_name`` is a file :func:`learn_capture` wrote, under
    ``state_dir()/captures``. Pure offline parsing -- the adapter is never
    opened. The module's target byte is taken from this VIN's confirmed
    address if one is on record (``link().vin``), else the registry target.
    """
    import json as _json
    from . import actuate
    p = state_dir() / "captures" / Path(capture_name).name
    if not p.exists():
        raise BadCommand(f"no capture named {capture_name!r}")
    data = _json.loads(p.read_text(encoding="utf-8"))
    ecu = by_code(module.upper())
    if ecu is None:
        raise BadCommand(f"unknown module code {module!r}")
    vin = link().vin or ""
    target = store.confirmed_targets(vin).get(ecu.code) if vin else None
    if target is None:
        target = ecu.target
    if target is None:
        raise BadCommand(f"module {ecu.code} has no known address; run discovery first")
    procedure = actuate.extract_procedure(data.get("transactions") or [], f"{target:02X}")
    return actuate.save_actuator(vin, ecu.code, name, procedure, source=p.name, tool=tool)


def actuators(vin: str = "") -> dict[str, Any]:
    from . import actuate
    return {"actuators": actuate.list_actuators(vin or None)}


def run_actuator(vin: str, module: str, name: str, consent: str, max_seconds: float = 10.0,
                 confirm: bool = False, **kw: Any) -> dict[str, Any]:
    """Replay a learned actuator test (UDS 0x2F/0x31) on one module. Not exposed over HTTP.

    Refuses unless ``consent`` is exactly ``ACTUATE <MODULE> <NAME>``, the module is not
    safety-critical (:data:`safety.ACTUATION_BLOCKED_MODULES`, or anything on CAN-CH --
    use MultiEcuScan or wiTECH for those), the learned procedure is replayable (no
    SecurityAccess, no configuration/reflash/reset service), and the vehicle reads
    engine-off and stationary (PID 0C then 0D on the legislated route; unreadable refuses
    too). Bounded to ``max_seconds`` (hard cap 30 s); control is ALWAYS returned to the
    ECU afterwards, even if a step fails.
    """
    from . import actuate
    ecu = uds_mod.resolve_module(module, vin or None)
    procedure = actuate.get_actuator(vin, ecu.code, name)
    actuate.assert_actuate_allowed(ecu, procedure, consent, name)   # fail fast, before any traffic

    def _reading(pid: str) -> Optional[float]:
        try:
            r = obd_pid(pid, **kw)
        except LiveError:
            return None
        return float(r["value"]) if r.get("value") is not None else None

    rpm = _reading("0C")
    speed = _reading("0D")
    if rpm is None or speed is None:
        raise Refused("could not read engine RPM and vehicle speed; refusing to actuate")
    if rpm > 0:
        raise Refused(f"engine is running ({rpm:g} rpm); refusing to actuate")
    if speed > 0:
        raise Refused(f"vehicle speed reads {speed:g} km/h; refusing to actuate")

    with link().session(f"actuate {ecu.code} {name}", bus=_bus(ecu.bus_key), confirm=confirm,
                        **kw) as sess:
        out = actuate.run_actuator(sess, ecu, procedure, consent=consent, max_seconds=max_seconds)
        return _stamp(sess, out)


__all__ = ["observations", "status", "ports", "mes_settings", "set_cable", "cable_state", "buses", "modules",
           "probe", "verify_bus", "capture", "obd_dtcs", "obd_all_dtcs", "obd_pid",
           "obd_pids_snapshot", "obd_voltage", "obd_supported_pids", "obd_freeze_frame",
           "obd_freeze_frames", "obd_vin",
           "readiness_in", "obd_readiness", "module_dtcs", "module_identity", "module_did",
           "module_did_sweep", "sweep_bus_full",
           "scan_modules", "discover", "coverage_status", "coverage_start", "coverage_run",
           "coverage_skip", "coverage_report", "coverage_reset", "repair_status",
           "obd_mode06", "module_dtc_detail", "module_dtc_count", "clear_module_dtcs",
           "module_read_all", "module_discover_dids",
           "learn_capture", "learn_correlate", "learn_accept", "learned_dids",
           "learn_actuator", "actuators", "run_actuator",
           "AdapterLink", "link", "DEFAULT_TIMEOUT"]


# --- live-data engine: channel registry, poll sessions, alarms, recording -------
#
# Backend for a future dashboard UI. The poller (cuore.live.poller) owns one
# adapter session for the whole run; everything here is a thin wrapper so the
# HTTP routes and MCP tools share the same entry points as every other
# operation in this file.

def live_channels() -> dict[str, Any]:
    """The channel registry (every PID/DID/computed/battery channel) and presets."""
    from . import channels as channels_mod
    return {"channels": [c.to_dict() for c in channels_mod.available_channels()],
            "presets": channels_mod.presets()}


def live_session_start(channels: Optional[list[str]] = None, preset: str = "",
                       rates: Optional[dict[str, float]] = None, monitor_dtcs: bool = False,
                       dtc_interval_s: float = 10.0) -> dict[str, Any]:
    """Start the live-data poll session on the given channels and/or preset.

    Read-only (Mode 01, UDS 0x22, ATRV only) but holds the adapter for the
    whole session: other live operations refuse while this runs (see the
    guard below), and this itself refuses while MultiEcuScan is connected.

    ``monitor_dtcs`` (MES's "Monitor DTCs" convention): every
    ``dtc_interval_s`` seconds (minimum 5), the poller also reads Mode 03/07
    between channel reads and reports any change -- see
    :meth:`cuore.live.poller.LivePoller._poll_dtcs`.
    """
    from . import channels as channels_mod
    from . import poller as poller_mod
    chans = channels_mod.resolve_channels(channels, preset)
    return poller_mod.poller().start(chans, rates=rates, monitor_dtcs=monitor_dtcs,
                                     dtc_interval_s=dtc_interval_s)


def live_session_stop() -> dict[str, Any]:
    """Stop the live-data poll session and release the adapter."""
    from . import poller as poller_mod
    return poller_mod.poller().stop()


def live_session_status() -> dict[str, Any]:
    """Live-data session status: channels, configured and achieved rates, alarms."""
    from . import poller as poller_mod
    return poller_mod.poller().status()


def live_snapshot() -> dict[str, Any]:
    """Latest value (and alarm state) of every channel in the running session."""
    from . import poller as poller_mod
    return poller_mod.poller().snapshot()


def live_record_start() -> dict[str, Any]:
    """Start mirroring the running live session to an MES-format CSV recording."""
    from . import poller as poller_mod
    return poller_mod.poller().start_recording()


def live_record_stop() -> dict[str, Any]:
    """Stop the live-session CSV recording."""
    from . import poller as poller_mod
    return poller_mod.poller().stop_recording()


def live_set_alarm(channel: str, warn: Optional[float] = None, alarm: Optional[float] = None,
                   direction: str = "above", hysteresis: float = 0.0) -> dict[str, Any]:
    """Set (or replace) a warn/alarm threshold on one channel of the live session."""
    from . import poller as poller_mod
    return poller_mod.poller().set_alarm(channel, warn=warn, alarm=alarm, direction=direction,
                                         hysteresis=hysteresis)


def live_load_step() -> dict[str, Any]:
    """The load-step voltage test: preset, owner script, channel availability."""
    from . import load_step
    return load_step.describe()


def live_load_step_start(label: str = "") -> dict[str, Any]:
    """Start the load-step voltage test as a named, tagged recording (read-only).

    Holds the adapter for the test's 3 minutes, like any poll session."""
    from . import load_step
    return load_step.start(label)


def live_load_step_stop() -> dict[str, Any]:
    from . import load_step
    return load_step.stop()


def live_load_step_status() -> dict[str, Any]:
    from . import load_step
    return load_step.status()


def live_load_step_analysis(recording: str = "") -> dict[str, Any]:
    """Per-step voltage drops from a saved load-step recording (newest by default)."""
    from . import load_step
    return load_step.analyze_recording(recording)


def live_purge_trim_start(label: str = "") -> dict[str, Any]:
    """Start the passive purge-trim EVAP test as a named recording (read-only, 4 min)."""
    from . import purge_trim
    return purge_trim.start(label)


def live_purge_trim_stop() -> dict[str, Any]:
    from . import purge_trim
    return purge_trim.stop()


def live_purge_trim_status() -> dict[str, Any]:
    from . import purge_trim
    return purge_trim.status()


def live_purge_trim_analysis(recording: str = "") -> dict[str, Any]:
    """Purge-off vs purge-on trims from a saved purge-trim recording (newest by default)."""
    from . import purge_trim
    return purge_trim.analyze_recording(recording)


def live_stream_subscribe() -> Any:
    """A queue of ``{t, channel, value, unit, alarm}`` messages for the SSE route."""
    from . import poller as poller_mod
    return poller_mod.poller().subscribe()


def live_stream_unsubscribe(q: Any) -> None:
    from . import poller as poller_mod
    poller_mod.poller().unsubscribe(q)


def live_stream_events(max_messages: Optional[int] = None):
    """Generator of live-session messages, or ``None`` as a keepalive placeholder.

    A plain Python generator -- deliberately independent of FastAPI/ASGI --
    so it is directly testable without an HTTP layer. The SSE route wraps
    each yielded item into one ``data: ...`` (or ``: keepalive``) line.
    ``max_messages`` bounds it for callers that want a finite read (tests);
    the HTTP route leaves it unbounded and relies on the client disconnecting
    to end iteration (handled by the ``finally`` unsubscribe below).
    """
    import queue as _queue
    from . import poller as poller_mod
    q = poller_mod.poller().subscribe()
    n = 0
    try:
        while max_messages is None or n < max_messages:
            try:
                yield q.get(timeout=15.0)
                n += 1
            except _queue.Empty:
                yield None
    finally:
        poller_mod.poller().unsubscribe(q)


def _poller_active_guard() -> None:
    """Refuse with a clear message if the live-data poller holds the adapter.

    A poll session holds one :class:`~cuore.live.transport.Session` open for
    its whole run, so any of the ordinary per-call operations below would
    otherwise just block waiting for the adapter lock instead of failing
    fast. Checked before the operation opens its own session.
    """
    from . import poller as poller_mod
    if poller_mod.poller().holds_adapter():
        raise Refused("a live-data poll session is running and holds the adapter; stop it "
                      "first (live_session_stop / POST /api/live/session/stop)")


#: Every operation here that opens its own adapter session, guarded against
#: running while the live-data poller holds the port. Wrapping is applied
#: below by name rather than editing each function in place.
_POLLER_GUARDED = (
    "probe", "verify_bus", "capture", "obd_dtcs", "obd_all_dtcs", "obd_pid", "obd_voltage",
    "obd_supported_pids", "obd_freeze_frame", "obd_vin", "obd_readiness", "module_dtcs",
    "module_identity", "module_did", "scan_modules", "discover", "obd_mode06",
    "module_dtc_detail", "module_dtc_count", "module_read_all", "module_discover_dids",
    "clear_module_dtcs", "run_actuator",
)


def _guard_against_poller(fn):
    def _wrapped(*args, **kwargs):
        _poller_active_guard()
        return fn(*args, **kwargs)
    _wrapped.__name__ = getattr(fn, "__name__", "wrapped")
    _wrapped.__doc__ = getattr(fn, "__doc__", None)
    _wrapped.__wrapped__ = fn
    return _wrapped


for _name in _POLLER_GUARDED:
    globals()[_name] = _guard_against_poller(globals()[_name])
del _name


__all__ += ["live_channels", "live_session_start", "live_session_stop", "live_session_status",
           "live_snapshot", "live_record_start", "live_record_stop", "live_set_alarm",
           "live_load_step", "live_load_step_start", "live_load_step_stop",
           "live_load_step_status", "live_load_step_analysis",
           "live_purge_trim_start", "live_purge_trim_stop", "live_purge_trim_status",
           "live_purge_trim_analysis",
           "live_stream_subscribe", "live_stream_unsubscribe", "live_stream_events"]
