"""Car-session checklist: the Bench "Next connection" plan mapped to the parity rows it can close.

Read-only. Nothing here contacts the car, writes parity state or marks a row done. ``ready`` lists the
car_session rows whose step is finished and says what side-by-side MES read is still needed; a person confirms
on the parity page. Minutes are ESTIMATES (no recorded duration exists for most steps) unless a code cap is named.
Steps flagged ``added`` are defined here (the shipped plan file is left alone).
"""
from __future__ import annotations

from typing import Any

from . import next_session, parity

GROUPS = [
    ("off", "1. Engine off, ignition on, plain adapter on CAN-C (no cable)"),
    ("run", "2. Engine running / warm"),
    ("cable", "3. Cable swaps: grey A6 (CAN-CH) then blue A5 (CAN-IHS)"),
]

# g group, q order in group, m minutes (ESTIMATE), rows = car_session rows it can close, supports = rows it feeds
S: dict[str, dict[str, Any]] = {
    "rfhub-first": dict(g="off", q=1, m=5, rows=["module-scan"], note="Cold, before any other traffic.",
                        mes="MES module list for the same ignition cycle."),
    "evap-cold-soak": dict(g="off", q=2, m=10, rows=["mode06-layout"], note="3A/3C records; no clears.",
                           mes="MES Mode 06 screen, same monitors."),
    "discover-responders": dict(g="off", q=3, m=25, long=True, rows=["module-scan", "module-identity", "mod-dtcm-esm-dasm"],
                                mes="MES module list and each module's identity screen (part number, software) to match the F1xx values."),
    "proxi-discover-read": dict(g="off", q=4, m=10, added=True, long=True, rows=[], supports=["proxi-alignment"],
                                title="PROXI discovery and read (BCM, read-only 0x22)",
                                why="Configuration page: Discover (code cap 25 min), owner accepts the candidate, then Read.",
                                mes="MES CAN Setup screen names for the same bytes (names form on the Configuration page)."),
    "radio-etm-identity": dict(g="off", q=5, m=8, added=True, rows=[], supports=["mod-hvac-etm"],
                               title="Radio / ETM identity (address unverified)",
                               why="Existing discovery path only, 0x22 identity DIDs. No guessed address; name it only if identity matches a MES log line.",
                               mes="MES module list entry for the radio/ETM with its part number."),
    "module-round-canc": dict(g="off", q=6, m=15, rows=["dtc-status-19-02", "freeze-ipc-tcm"],
                              mes="MES fault list and snapshot for IPC and TCM, same ignition cycle."),
    "named-module-rounds": dict(g="off", q=7, m=15, added=True, rows=[], supports=["dtc-status-19-02"],
                                title="Code round with snapshots on every newly accepted module",
                                why="After discovery acceptance: /api/live/round?bus=can_c&modules=<accepted codes>. Unconfirmed addresses are skipped, not guessed.",
                                mes="MES fault list for each accepted module."),
    "service-dids": dict(g="off", q=8, m=15, rows=[], supports=["ibs-battery-read"], mes="MES service-value screens (read only)."),
    "shudder-misfire": dict(g="run", q=1, m=25, rows=["mode06-layout"], note="Includes the 40-60 km/h drive (estimate).",
                            mes="MES Mode 06 screen with the A1-A5 counters."),
    "decode-confirm-running": dict(g="run", q=2, m=20, rows=["live-decode-confirm"], mes="MES CSV with tags 3-4 for the same channels."),
    "confirm-decodings": dict(g="run", q=3, m=20, rows=["live-decode-confirm"], note="Engine off, warm: stop the engine after the running half.",
                              mes="MES CSV with tags 1-2 for the same channels."),
    "can-captures": dict(g="run", q=4, m=15, rows=[], mes="none"),
    "g003a-ground": dict(g="run", q=5, m=15, rows=[], mes="none (meter readings)"),
    "battery-label": dict(g="run", q=6, m=5, rows=[], mes="MES PROXI byte 63 only"),
    "abs-round": dict(g="cable", q=1, m=15, long=True, rows=["dtc-read-can-ch", "mod-abs", "bus-can-ch"],
                      mes="MES ABS fault list and module screen on the grey cable."),
    "abs-binding": dict(g="cable", q=2, m=20, rows=["freeze-abs"], mes="MES ABS freeze-frame screen: the seven fields."),
    "ihs-round": dict(g="cable", q=3, m=25, added=True, long=True, rows=["dtc-read-can-ihs", "bus-can-ihs"], supports=["mod-afls-half-pam"],
                      title="Blue cable: discovery on CAN-IHS, name responders, code round",
                      why="Declare the blue A5 cable, discover on can_ihs, name and accept (IHS62/IHS65 unnamed today), then the round. Confirmed bitrates only.",
                      mes="MES fault list for the IHS modules on the blue cable."),
}


def build(vin: str) -> dict[str, Any]:
    nv = next_session.view(vin) or {"steps": []}
    plan = {s["id"]: s for s in nv["steps"]}
    rows = {i["id"]: i for i in parity.load().get("items", [])}
    cs = {k for k, r in rows.items() if r.get("state") == "car_session"}
    covered_before = {r for sid, d in S.items() if sid in plan and not d.get("added") for r in d["rows"]}

    def ref(ids: list[str]) -> list[dict[str, str]]:
        return [{"id": r, "function": rows[r]["function"], "state": rows[r]["state"]} for r in ids if r in rows]

    steps: list[dict[str, Any]] = []
    for sid, d in S.items():
        p = plan.get(sid, {})
        closes = ref(d["rows"])
        n = sum(1 for c in closes if c["state"] == "car_session")
        steps.append({"id": sid, "group": d["g"], "seq": d["q"], "minutes": d["m"], "added": bool(d.get("added")),
                      "title": d.get("title") or p.get("title") or sid, "why": d.get("why") or p.get("why", ""),
                      "pre": p.get("preconditions") or "", "long": bool(d.get("long")), "done": bool(p.get("done")),
                      "closes": closes, "supports": ref(d.get("supports", [])), "mes": d["mes"], "note": d.get("note", ""),
                      "n_close": n, "per_hour": round(60 * n / d["m"], 1)})
    order = [g for g, _ in GROUPS]
    steps.sort(key=lambda s: (order.index(s["group"]), s["seq"]))
    groups = []
    for g, label in GROUPS:
        ss = [s for s in steps if s["group"] == g]
        groups.append({"key": g, "label": label, "steps": ss, "minutes": sum(s["minutes"] for s in ss)})
    covered = {c["id"] for s in steps for c in s["closes"]}
    ready: dict[str, dict[str, Any]] = {}
    for s in steps:
        if not s["done"]:
            continue
        for c in s["closes"]:
            if c["state"] == "car_session":
                e = ready.setdefault(c["id"], {"id": c["id"], "function": c["function"], "steps": [], "mes": []})
                e["steps"].append(s["title"])
                e["mes"].append(s["mes"])
    total = sum(s["minutes"] for s in steps)
    return {"vin": vin, "groups": groups, "steps": steps, "total_minutes": total, "hours": round(total / 60, 1),
            "n_rows": len(cs), "rows_covered": sorted(cs & covered), "rows_uncovered_before": sorted(cs - covered_before),
            "rows_uncovered": sorted(cs - covered), "ready": list(ready.values()),
            "missing_from_plan": [k for k, d in S.items() if not d.get("added") and k not in plan]}
