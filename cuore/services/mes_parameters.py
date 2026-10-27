"""MES parameter inventory: what each module of this car reports, from MultiEcuScan's own logs.

MultiEcuScan writes a ``READING PARAMETERS:`` block to its FES session log while
its Parameters tab is open. Every real (non-simulation) FES log of this car is
read here and every parameter name it logged is listed under its module, with
the units and values MES printed. That list is the car's own answer to "what
sensors and values does this module have" -- no outside source is used.

Read-only: it never talks to the car. A module counts as captured once one real
log holds a parameter block for it; the checklist says which modules still need
a MES session and which cable MES needs for them.

Simulation logs (MES's practice data) are always excluded.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live.addressing import MODULES

from mes import catalog, fes  # noqa: E402  -- must follow the bootstrap import

#: Cable MES needs per bus on this car (from the module table's bus keys).
CABLE = {"can_c": "adapter alone", "can_ch": "grey A6 cable", "can_ihs": "blue A5 cable"}

_cache: dict[str, Any] = {"key": None, "logs": []}


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _module_for(ecu: str) -> str:
    """Module code whose table name matches MES's ECU description, else ''."""
    want = _norm(ecu)
    for m in MODULES:
        if _norm(m.name) == want:
            return m.code
    for m in MODULES:
        name = _norm(m.name).split(" (")[0]
        if name and (name in want or want in name):
            return m.code
    return ""


def _real_fes(vin: str) -> list[Any]:
    """Real FES logs carrying this VIN, plus real logs with NO VIN in them whose
    filename vehicle matches one of those (MES omits the VIN in some service
    functions); the latter are flagged ``vin_in_log=False`` on the page."""
    mine = [e for e in catalog.CATALOG.select(kind="fes", vin=vin) if not e.simulation]
    models = {e.vehicle for e in mine if e.vehicle}
    extra = [e for e in catalog.CATALOG.select(kind="fes")
             if not e.simulation and not e.vin and e.vehicle in models]
    return sorted(mine + extra, key=lambda e: e.sort_key)


def _parsed(vin: str) -> list[dict[str, Any]]:
    """One record per real FES log with parameter samples (cached by file set + mtimes)."""
    entries = _real_fes(vin)
    key = tuple((e.name, e.mtime) for e in entries)
    if _cache["key"] == (vin, key):
        return _cache["logs"]
    logs: list[dict[str, Any]] = []
    for e in entries:
        try:
            log = fes.load_fes(e.path, timestamp=e.timestamp)
        except Exception:  # noqa: BLE001 -- one unreadable log must not hide the rest
            continue
        if log.simulation or not log.samples:
            continue
        logs.append({"file": e.name, "at": e.timestamp, "ecu": log.ecu_description or "", "vin_in_log": bool(e.vin),
                     "samples": [[(v.name, v.raw, v.unit) for v in s.values] for s in log.samples]})
    _cache.update(key=(vin, key), logs=logs)
    return logs


def inventory(vin: str) -> dict[str, Any]:
    """{"modules": [...one row per module of the car...], "other": [...MES functions/ECUs not in the table...]}

    Each row: code, name, bus, cable, present, captured, sessions, parameters
    [{name, units, last, samples, first_at, last_at, files}].
    """
    per: dict[str, dict[str, Any]] = {}
    for lg in _parsed(vin):
        code = _module_for(lg["ecu"]) or ("ecu:" + lg["ecu"])
        slot = per.setdefault(code, {"ecu": lg["ecu"], "sessions": [], "params": {}})
        slot["sessions"].append({"file": lg["file"], "at": lg["at"], "vin_in_log": lg["vin_in_log"]})
        for sample in lg["samples"]:
            for name, raw, unit in sample:
                p = slot["params"].setdefault(name, {"name": name, "units": [], "last": "", "samples": 0,
                                                     "first_at": lg["at"], "last_at": lg["at"], "files": []})
                if unit and unit not in p["units"]:
                    p["units"].append(unit)
                p["last"], p["samples"] = raw, p["samples"] + 1
                p["first_at"], p["last_at"] = min(p["first_at"], lg["at"]), max(p["last_at"], lg["at"])
                if lg["file"] not in p["files"]:
                    p["files"].append(lg["file"])

    def row(code: str, name: str, bus: str, present: str) -> dict[str, Any]:
        slot = per.get(code) or {}
        params = list((slot.get("params") or {}).values())
        sessions = sorted(slot.get("sessions") or [], key=lambda s: s["at"])
        return {"code": code, "name": name, "bus": bus, "cable": CABLE.get(bus, bus), "present": present,
                "captured": bool(params), "sessions": sessions, "parameters": params,
                "last_at": sessions[-1]["at"] if sessions else None}

    modules = [row(m.code, m.name, m.bus_key, m.present) for m in MODULES]
    known = {m.code for m in MODULES}
    other = [row(code, slot["ecu"], "", "") for code, slot in per.items() if code not in known]
    for o in other:
        o["note"] = "MES logged this under a name that is not a module in CUORE's table (often a MES service function)."
    return {"vin": vin, "modules": modules, "other": other,
            "captured": sum(1 for m in modules if m["captured"]),
            "total": len(modules),
            "parameter_count": sum(len(m["parameters"]) for m in modules + other)}


def to_csv(vin: str) -> str:
    inv = inventory(vin)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["module", "module_name", "bus", "parameter", "units", "last_value", "samples",
                "first_seen", "last_seen", "mes_logs"])
    for m in inv["modules"] + inv["other"]:
        for p in m["parameters"]:
            w.writerow([m["code"], m["name"], m["bus"], p["name"], " | ".join(p["units"]), p["last"],
                        p["samples"], p["first_at"], p["last_at"], " | ".join(p["files"])])
    return buf.getvalue()


__all__ = ["inventory", "to_csv", "CABLE"]


# --- service values on the cluster: read-only discovery (UDS 0x22 only) ---------------------

def _sd():
    from ..live import service_dids
    return service_dids


def service_dids_view(vin: str) -> dict[str, Any]:
    """Expected values, sweep plan and last results for the page. Never contacts the car."""
    out: dict[str, Any] = {"expected": {"values": [], "note": ""}, "plan": None,
                           "results": {"matches": [], "next_step": "", "ran_at": ""}, "error": ""}
    try:
        sd = _sd()
        out["expected"] = sd.expected_values(vin)
        out["plan"] = sd.plan(vin)
        out["results"] = sd.results(vin)
    except Exception as exc:  # noqa: BLE001 -- the page must render without the discovery module
        out["error"] = f"Service-value discovery is unavailable: {exc}"
    return out


def service_dids_run(vin: str, max_seconds: float = 180) -> dict[str, Any]:
    """Run the read-only sweep. Refusals (MES holds the adapter, live poll running) raise LiveError."""
    return _sd().run(vin, max_seconds=max_seconds)
