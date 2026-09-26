"""The operations both surfaces call: HTTP routes and MCP tools are wrappers over these.

Every function returns a plain dict, opens the adapter for exactly its own
operation through :func:`link`, and names the bus and cable it used. Errors
are :class:`LiveError` subclasses; the surfaces decide how to render them.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import serial.tools.list_ports

from . import capture as capture_mod
from . import store
from . import uds as uds_mod
from .addressing import MODULES, by_code, on_bus
from .buses import BUSES, CAN_C, Bus, routes_for
from .config import mes_folders, mes_interfaces, mes_registry, resolve_port
from .errors import BadCommand
from .framing import adapter_error, no_data
from .obd import (decode_obd_dtcs, decode_pid, decode_readiness, decode_supported_pids,
                  dtc_from_two_bytes, evap_verdict, resolve_pid, PIDS_BY_HEX)
from .transport import DEFAULT_TIMEOUT, AdapterLink, Session, link

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


def verify_bus(bus: str, seconds: float = 2.0, port: str = "", baud: int = 0,
               allow_while_mes_connected: bool = False) -> dict[str, Any]:
    """Passive listen; marks the bus verified under the current cable if traffic is seen.

    A bus can be reachable under more than one adapter protocol -- CAN-C
    carries both 29-bit UDS and the 11-bit legislated pair, and a monitor
    opened for one ID width hears nothing of the other. Every route the
    declared cable allows is tried before reporting silence, because a healthy
    bus reported as dead is the worst answer this tool can give.
    """
    b = _bus(bus)
    lk = link()
    candidates: list[Any] = list(routes_for(b, lk.cable)) or [None]
    attempts: list[dict[str, Any]] = []
    sess = None
    for route in candidates:
        with lk.session("verify_bus", bus=b, port=port, baud=baud, passive=True,
                        allow_while_mes_connected=allow_while_mes_connected,
                        route=route) as sess:
            cap = capture_mod.listen(sess, seconds=seconds, max_frames=200)
            # "DATA ERROR" is the adapter's per-frame annotation for one frame
            # whose payload did not validate; with parsed frames beside it the
            # bus is demonstrably alive, so it is reported but does not veto.
            fatal = cap["error"] and not (cap["error"] == "DATA ERROR" and cap["count"] > 0)
            ok = cap["count"] > 0 and not fatal
            attempts.append({"stn_protocol": sess.route.stn_protocol,
                             "header_bits": sess.header_bits,
                             "frames": cap["count"], "error": cap["error"],
                             "ids": cap["ids"]})
            if ok:
                lk.mark_verified(b, cap["count"])
                return _stamp(sess, {"verified": True, "frames": cap["count"],
                                     "rate_hz": cap["rate_hz"], "ids": cap["ids"],
                                     "error": cap["error"],
                                     "stn_protocol": sess.route.stn_protocol,
                                     "header_bits": sess.header_bits,
                                     "attempts": attempts, "note": None})
    tried = ", ".join(f"STP {a['stn_protocol']} ({a['header_bits']}-bit)" for a in attempts)
    return _stamp(sess, {"verified": False, "frames": 0, "rate_hz": 0.0, "ids": {},
                         "error": attempts[-1]["error"] if attempts else None,
                         "attempts": attempts,
                         "note": (f"no traffic on {b.key} with cable {lk.cable!r} on any route "
                                  f"tried ({tried}); check the cable, ignition, and the route "
                                  f"note: {sess.route.note}")})


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

def _obd_route() -> Any:
    """The 11-bit legislated route on CAN-C, when the cable allows one.

    Giorgio ECMs serve Modes 01/03/07/0A only on the 11-bit 7DF/7E8 pair; the
    29-bit UDS address answers every legislated request with NRC 0x11
    (serviceNotSupported), which read as silence until 2026-09-25.
    """
    for route in routes_for(CAN_C, link().cable):
        if route.stn_protocol == "33":
            return route
    return None


def _obd_session(purpose: str, **kw: Any):
    kw.setdefault("route", _obd_route())
    return link().session(purpose, bus=CAN_C, **kw)


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
    with _obd_session(f"read_{kind}_dtcs", **kw) as sess:
        return _dtc_read(sess, mode, resp, kind)


def obd_all_dtcs(**kw: Any) -> dict[str, Any]:
    with _obd_session("read_all_dtcs", **kw) as sess:
        return _stamp(sess, {k: _dtc_read(sess, m, r, k) for k, (m, r) in _KINDS.items()})


def obd_pid(pid: str, **kw: Any) -> dict[str, Any]:
    hex_pid, spec = resolve_pid(pid)
    with _obd_session("read_pid", **kw) as sess:
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


def obd_voltage(**kw: Any) -> dict[str, Any]:
    with link().session("read_voltage", bus=CAN_C, passive=True, **kw) as sess:
        r = sess.cmd("ATRV", 2)
        m = re.search(r"(\d+\.\d+)V", r)
        return _stamp(sess, {"raw": r, "volts": float(m.group(1)) if m else None,
                             "vehicle_power_detected": bool(m)})


def obd_supported_pids(**kw: Any) -> dict[str, Any]:
    with _obd_session("read_supported_pids", **kw) as sess:
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
        return _stamp(sess, out)


def obd_vin(**kw: Any) -> dict[str, Any]:
    with _obd_session("read_vin", **kw) as sess:
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
    with _obd_session("read_readiness", **kw) as sess:
        return readiness_in(sess)


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


def discover(bus: str = "can_c", vin: str = "", confirm: bool = False,
             candidates: Optional[list[str]] = None, per_target_timeout: float = 0.25,
             stop_after: Optional[int] = None, **kw: Any) -> dict[str, Any]:
    b = _bus(bus)
    cands = None
    if candidates:
        try:
            cands = [int(c, 16) for c in candidates]
        except ValueError:
            raise BadCommand("candidates must be hex target bytes")
    with link().session(f"discover {b.key}", bus=b, confirm=confirm, **kw) as sess:
        return _stamp(sess, uds_mod.discover(sess, b, vin_expected=vin or None,
                                             candidates=cands,
                                             per_target_timeout=per_target_timeout,
                                             stop_after=stop_after))


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


__all__ = ["observations", "status", "ports", "mes_settings", "set_cable", "cable_state", "buses", "modules",
           "probe", "verify_bus", "capture", "obd_dtcs", "obd_all_dtcs", "obd_pid",
           "obd_voltage", "obd_supported_pids", "obd_freeze_frame", "obd_vin",
           "readiness_in", "obd_readiness", "module_dtcs", "module_identity", "module_did",
           "scan_modules", "discover", "coverage_status", "coverage_start", "coverage_run",
           "coverage_skip", "coverage_report", "coverage_reset", "repair_status",
           "AdapterLink", "link", "DEFAULT_TIMEOUT"]
