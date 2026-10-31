"""One module workspace: everything a technician needs for one module, in one fixed order.

Pure composition over existing read-only services (``modules_bridge``, ``adjustments``,
``systems_bridge``, ``adapter_cables_bridge``, ``live.buses``). It opens no adapter, writes
nothing and adds no route that can. The order is the same for every module and every marque:

  answer -> connect (bus + cable) -> identity -> faults -> live values -> adjustments and tests
  -> not read -> go next (job, bulletins, wiring, bay sheet, proof)

Marque facts come from data (``live.buses``, ``data/adapter_cables.json``, the module registry);
no marque or model name is written here.
"""
from __future__ import annotations

from typing import Any, Optional

from ..live import buses
from ..live.config import default_cable
from . import adapter_cables_bridge, adjustments, modules_bridge, systems_bridge

SECTION_ORDER = ("answer", "connect", "identity", "faults", "live", "adjust", "notread", "next")

HONEST = {  # adjustment/test state -> (plain state, what the technician does)
    "awaiting source": ("Needs the manufacturer procedure",
                        "Use the manufacturer tool (wiTECH or equivalent). CUORE has no documented source for this and will not guess."),
    "documented": ("Documented, not accepted",
                   "Procedure is on file but the owner has not accepted it. Use the manufacturer tool until it is."),
    "accepted": ("Accepted, runs only in a gated session",
                 "Runs only through the gated session: dry run, gate, typed consent, read-back. Not from this page."),
    "performed_verified": ("Done and verified",
                           "A repeat goes through the gated session. Not from this page."),
}


def _cable_label(cable: str) -> str:
    row = adapter_cables_bridge.for_cable(cable)
    if row:
        return f"{row.get('colour', cable)} lead ({row.get('code', cable)})"
    if cable == "witech_splitter":
        return "OBD Y-splitter (listen-only, shared with the manufacturer pod)"
    return "no cable (plain OBD port)" if cable == "none" else cable


def connect_plan(bus_key: Optional[str], fitted: Optional[str] = None) -> dict[str, Any]:
    """Bus and cable needed before connecting, and the exact step if the wrong cable is fitted."""
    fitted = (fitted if fitted is not None else default_cable()) or "none"
    bus = buses.BUSES.get(bus_key or "")
    if bus is None:
        return {"known": False, "fitted": fitted, "fitted_label": _cable_label(fitted), "ok": False,
                "headline": "Bus unknown for this module: do not connect.",
                "step": "Do not guess a bus. Never open a bus at a rate other than its own. "
                        "Find the module's bus in the module registry first.", "needed": [], "rate": None,
                "warning": adapter_cables_bridge.WRONG_BITRATE_WARNING}
    needed: list[dict[str, str]] = []
    for r in bus.routes:
        if r.cable not in [n["cable"] for n in needed]:
            needed.append({"cable": r.cable, "label": _cable_label(r.cable), "status": r.status,
                           "switch": buses.adapter_switch(bus.key, r.cable)})
    ok = any(n["cable"] == fitted for n in needed)
    rate = f"{bus.bitrate // 1000}k"
    best = next((n for n in needed if n["status"] == "confirmed"), needed[0])
    step = ""
    if not ok:
        step = (f"Wrong cable. Fitted: {_cable_label(fitted)}. {bus.name} needs {best['label']}. "
                f"1) Disconnect the adapter from the OBD port. 2) Fit {best['label']} between the port and the adapter. "
                f"3) Set the cable to {best['cable']} in the CUORE session, adapter switch {best['switch']}. "
                f"4) Connect again. {bus.name} runs at {rate} only; never try another rate.")
    return {"known": True, "bus": bus.key, "bus_name": bus.name, "rate": rate, "needed": needed,
            "fitted": fitted, "fitted_label": _cable_label(fitted), "ok": ok, "step": step,
            "listen_only": fitted == "witech_splitter",
            "headline": (f"{bus.name} at {rate}. Cable fitted matches." if ok
                         else f"{bus.name} at {rate}. The fitted cable does not reach this bus."),
            "warning": adapter_cables_bridge.WRONG_BITRATE_WARNING}


def _answer(d: dict[str, Any]) -> str:
    if d.get("not_read"):
        return f"NOT READ. {d['not_read']} Do not treat this module as clean."
    e = d.get("errors") or {}
    if e.get("active"):
        return f"{e['active']} active fault{'s' if e['active'] != 1 else ''} on {d['code']}."
    if e.get("cleared_unverified"):
        return f"Codes were cleared on {d['code']} and not verified: prove the repair."
    if e.get("stale"):
        return f"Only older codes on {d['code']}; nothing active when last read."
    return f"{d['code']} read clean when last read."


def _why(d: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for c in d.get("errors_detail") or []:
        if c.get("status") not in ("active", "cleared_unverified"):
            continue
        for s in systems_bridge.systems_for_code((c["dtc"] or "").split("-")[0]):
            if s["system"] not in seen:
                seen.add(s["system"])
                out.append({"system": s["system"].replace("_", " "), "role": s.get("role", ""),
                            "code": c["dtc"]})
    return out[:6]


def _adjust_rows(vin: str, d: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for c in adjustments.cards():
        if (c.get("module") or "").upper() != d["code"]:
            continue
        state, todo = HONEST[c["status"]]
        rows.append({"kind": "procedure", "title": c["title"], "state": state, "status": c["status"],
                     "todo": todo, "source": c["source"]})
    for a in d.get("actuators_detail") or []:
        if a.get("blocked"):
            state, todo = "Blocked", a.get("blocked_reason") or "Blocked for this module."
        elif a.get("replayable"):
            state, todo = "Learned, replayable in a gated session", "Typed consent phrase in the gated session. Not from this page."
        else:
            state, todo = "Learned, not replayable", str(a.get("reasons") or "Not replayable yet.")
        rows.append({"kind": "test", "title": a["name"], "state": state, "status": "actuator", "todo": todo,
                     "source": a.get("tool") or a.get("source") or ""})
    return rows


def _not_read(d: dict[str, Any], adj: list[dict[str, Any]]) -> list[str]:
    n: list[str] = []
    if d.get("not_read"):
        n.append(d["not_read"])
    ident = d.get("identity") or {}
    if not ident.get("software") and not ident.get("hardware"):
        n.append("Identity: no SCAN identity on record.")
    params = d.get("parameters") or []
    unseen = [p["name"] for p in params if not p.get("last_value")]
    if params and unseen:
        n.append(f"Live values never observed: {len(unseen)} of {len(params)} catalogued "
                 f"({', '.join(unseen[:4])}{', ...' if len(unseen) > 4 else ''}).")
    if not params:
        n.append("Live values: no catalogued parameters for this module.")
    nof = [e["dtc"] for e in d.get("errors_detail") or [] if not e.get("freeze_frame")]
    if nof:
        n.append(f"No snapshot (freeze frame) stored for: {', '.join(nof[:6])}{', ...' if len(nof) > 6 else ''}.")
    pending = [a["title"] for a in adj if a["status"] == "awaiting source"]
    if pending:
        n.append(f"Adjustments with no documented procedure: {len(pending)}.")
    if not d.get("actuators_detail"):
        n.append("Actuator tests: none learned on this car.")
    return n


def _next(d: dict[str, Any], plan: dict[str, Any], vin: str) -> dict[str, str]:
    if not plan["ok"]:
        return {"text": "Fit the right cable (see Connect), then read this module.", "href": f"/v/{vin}/car-session"}
    if d.get("not_read"):
        return {"text": "Read this module again in a CUORE session before any conclusion.", "href": f"/v/{vin}/car-session"}
    e = d.get("errors") or {}
    if e.get("active"):
        return {"text": "Open the job for the active code and follow its plan.", "href": f"/v/{vin}/job"}
    if e.get("cleared_unverified"):
        return {"text": "Run the proof of repair for the cleared codes.", "href": f"/v/{vin}/bench/proof"}
    return {"text": "Nothing active. Read live values if a symptom remains.", "href": f"/v/{vin}/liveboard"}


def _value_groups(vin: str, code: str) -> list[dict[str, Any]]:
    """Value groups holding readings from this module, each linking to the whole group on the Live board."""
    try:
        from ..live import channels as channels_mod
        from . import value_groups
        reg = channels_mod.registry()
        labels = value_groups.doc().get("labels") or {}
        return [{"label": g["label"], "href": value_groups.href(vin, g["id"]),
                 "mine": [labels.get(c) or reg[c].name for c in g["mine"]], "others": g["others"]}
                for g in value_groups.groups_for_module(code)]
    except Exception:  # noqa: BLE001 -- the workspace renders without the groups
        return []


def build(vin: str, code: str, fitted_cable: Optional[str] = None) -> dict[str, Any]:
    d = modules_bridge.module_detail(vin, code)
    plan = connect_plan(d.get("bus"), fitted_cable)
    adj = _adjust_rows(vin, d)
    return {
        "order": list(SECTION_ORDER),
        "answer": _answer(d),
        "why": _why(d),
        "connect": plan,
        "adjust": adj,
        "not_read_list": _not_read(d, adj),
        "value_groups": _value_groups(vin, code),
        "next": _next(d, plan, vin),
        "links": [
            ("Job", f"/v/{vin}/job"), ("Bay sheet", f"/v/{vin}/bay-sheet"),
            ("Wiring", f"/v/{vin}/electrical"), ("Systems map", f"/v/{vin}/systems"),
            ("Live board", f"/v/{vin}/liveboard"), ("Proof of repair", f"/v/{vin}/bench/proof"),
        ],
    }


__all__ = ["build", "connect_plan", "SECTION_ORDER", "HONEST"]
