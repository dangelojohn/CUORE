"""What the last car session actually read: a factual block for the Bay sheet.

Only recorded from-car observations (live/store) are used; nothing is computed
or filled in. A module that did not answer is listed under NOT READ, never as
clean. "Session" = every from-car observation on the calendar day of the newest
one. No adapter, no network.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..live import read_state, store

MAX_SNAP = 8


def _s(x: Any) -> str:
    return str(x or "").strip()


def _obs(vin: str, kind: str) -> list[dict[str, Any]]:
    try:
        return [o for o in store.recent_observations(5000, vin=vin, kind=kind) if store.is_from_car(o)]
    except Exception:  # noqa: BLE001
        return []


def _state(flags: dict) -> str:
    if flags.get("testFailed"):
        return "active now"
    if flags.get("confirmedDTC") or flags.get("pendingDTC") or flags.get("testFailedSinceLastClear"):
        return "history / pending"
    return ""


def build(vin: str, who: str = "") -> dict[str, Any]:
    vin = _s(vin).upper()
    kinds = ("module_dtcs", "module_identity", "dtc_detail", "adapter_identity", "freeze_frame")
    allobs = {k: _obs(vin, k) for k in kinds}
    stamps = [o["at"] for v in allobs.values() for o in v if o.get("at")]
    if not stamps:
        return {"has": False, "who": _s(who)}
    day = max(stamps)[:10]
    today = {k: [o for o in v if _s(o.get("at"))[:10] == day] for k, v in allobs.items()}
    all_at = sorted(o["at"] for v in today.values() for o in v)

    # newest answered/unanswered read per module
    newest: dict[str, dict] = {}
    for o in sorted(today["module_dtcs"], key=lambda x: x["at"]):
        newest[_s((o.get("data") or {}).get("ecu")).upper()] = o
    details: dict[tuple[str, str], dict] = {}
    for o in today["dtc_detail"]:
        d = o.get("data") or {}
        details[(_s(d.get("ecu")).upper(), _s(d.get("dtc")).upper())] = o
    modules, codes = [], []
    for ecu, o in sorted(newest.items()):
        d = o.get("data") or {}
        if not read_state.is_read(d):
            continue
        n = 0
        for r in d.get("dtcs") or []:
            st = _state(r.get("flags") or {})
            if not st:
                continue
            n += 1
            code = _s(r.get("code"))
            det = details.get((ecu, code.upper()))
            snap = []
            if det:
                for rec in ((det["data"].get("snapshot") or {}).get("records") or []):
                    for i in rec.get("identifiers") or []:
                        snap.append({"name": _s(i.get("name")) or _s(i.get("did")), "value": i.get("value"),
                                     "unit": _s(i.get("unit")), "confidence": _s(i.get("confidence")) or "not stated"})
            codes.append({"ecu": ecu, "code": code, "state": st, "at": _s(o["at"])[11:16],
                          "snap": snap[:MAX_SNAP], "snap_more": max(0, len(snap) - MAX_SNAP),
                          "snap_read": det is not None})
        modules.append({"ecu": ecu, "codes": n, "at": _s(o["at"])[11:16]})

    not_read = [{"ecu": m["ecu"], "why": m["why"], "last_good": _s(m["last_good"])[:10]}
                for m in read_state.unread_modules(today["module_dtcs"])]

    ident: dict[str, dict] = {}
    for o in sorted(today["module_identity"], key=lambda x: x["at"]):
        d = o.get("data") or {}
        ident[_s(d.get("ecu")).upper()] = d
    identity = []
    for ecu, d in sorted(ident.items()):
        fields = d.get("fields") or {}
        s = read_state.identity_summary(fields)
        vals = [f"{_s(f.get('name'))} {_s(f.get('ascii'))}" for f in fields.values()
                if read_state.field_status(f) == read_state.ANSWERED and _s(f.get("ascii"))]
        identity.append({"ecu": ecu, "state": s["state"], "line": s["line"], "found": vals})
        if s["state"] == read_state.NOT_READ:
            not_read.append({"ecu": ecu, "why": "identity " + s["line"], "last_good": ""})

    volt = None
    for o in sorted(today["adapter_identity"], key=lambda x: x["at"]):
        p = (o.get("data") or {}).get("probe") or {}
        if p.get("battery_voltage") is not None:
            volt = {"volts": p["battery_voltage"], "at": _s(o["at"])[11:16]}

    return {"has": True, "day": day, "first": all_at[0][11:16], "last": all_at[-1][11:16],
            "who": _s(who), "printed": datetime.now().strftime("%Y-%m-%d %H:%M"), "modules": modules, "codes": codes, "not_read": not_read,
            "identity": identity, "voltage": volt,
            "freeze": [{"name": _s((o["data"]).get("name")), "value": v.get("value"), "unit": _s(v.get("unit"))}
                       for o in today["freeze_frame"] for v in ((o["data"].get("by_ecu") or {}).values())][:MAX_SNAP]}
