"""Adapter capability verdicts. Pure: never opens the adapter. Input is an identity dict that
transport/ops already hold (``ops.status()["adapter_identity"]`` or an ``ops.probe`` result)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

DATA = Path(__file__).resolve().parents[1] / "data" / "supported_hardware.json"
LOW_VOLTS = 11.5


def load_hardware() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def match_entry(identity: dict[str, Any], hw: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    hw = hw or load_hardware()
    text = " ".join(str(v) for v in (identity or {}).values()).lower()
    for it in hw["items"]:
        if any(m in text for m in it.get("match", [])):
            return it
    return None


def check_adapter(identity: Optional[dict[str, Any]], voltage: Optional[float] = None,
                  bus_test: Optional[dict[str, Any]] = None,
                  hw: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Return {"adapter", "chip", "matched", "verdicts": {function: {"verdict", "reason"}}, "labels"}.
    verdict is one of pass / limited / fail / not tested. bus_test is {"ok": bool, "note": str}."""
    hw = hw or load_hardware()
    funcs = list(hw["functions"])
    ident = identity or {}
    v: dict[str, dict[str, str]] = {}

    def put(f: str, verdict: str, reason: str) -> None:
        v[f] = {"verdict": verdict, "reason": reason}

    if not ident:
        for f in funcs:
            put(f, "not tested", "The adapter has not been probed yet. Press the probe button with the adapter plugged in.")
        return {"adapter": None, "chip": "unknown", "matched": None, "verdicts": v, "labels": hw["functions"]}

    is_stn = "STI" in ident
    entry = match_entry(ident, hw)
    tested = bool(entry and entry.get("tested_on"))
    name = ident.get("STDI") or ident.get("ATI") or "unknown adapter"
    if is_stn and tested:
        for f in funcs:
            put(f, "pass", "STN adapter that CUORE session records show working on the reference car.")
        put("bypass_buses", "pass", "STN adapter tested with the blue A5 and grey A6 cables; declare the cable and verify the bus.")
    elif is_stn:
        for f in funcs:
            put(f, "not tested", "STN chip, which CUORE supports, but this model has no CUORE session record.")
    elif "ATI" in ident:
        put("basic_obd", "pass", "ELM327-type adapter: basic OBD reads work on these.")
        put("uds_can_c", "limited", "ELM clone: small buffers and slow multi-frame replies; long module reads may fail.")
        put("bypass_buses", "not tested", "No STN commands; bypass-bus routes were only tested on an STN adapter.")
        put("listen_only", "limited", "ELM clone: small buffers, frames may be lost.")
    else:
        for f in funcs:
            put(f, "not tested", "The adapter did not identify itself as STN or ELM327.")

    if voltage is not None and voltage < LOW_VOLTS:
        for f in funcs:
            if v[f]["verdict"] in ("pass", "limited"):
                v[f] = {"verdict": "limited",
                        "reason": f"Vehicle voltage {voltage:.1f} V is low (below {LOW_VOLTS} V); reads may be unreliable. " + v[f]["reason"]}
    if bus_test is not None:
        if bus_test.get("ok"):
            put("bypass_buses", "pass", "Bus test passed: " + str(bus_test.get("note", "frames heard")))
        else:
            put("bypass_buses", "fail", "Bus test failed: " + str(bus_test.get("note", "no frames heard")))
    return {"adapter": name, "chip": "STN" if is_stn else ("ELM327 clone" if "ATI" in ident else "unknown"),
            "matched": entry["id"] if entry else None, "verdicts": v, "labels": hw["functions"]}
