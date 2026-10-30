"""Arrive-ready job: what to prepare before the car arrives. Pure view-model.

No adapter, no network. Reads existing stores only: owner events, the job store, DTC history, the
bulletin cross-reference, the TSB catalogue, the parts bridge, shop visits and the bus table.
Owner words are attested, never readings; leads are things to test, never conclusions; nothing
here invents a recall status or a labour time.
"""
from __future__ import annotations

import re
from typing import Any

VERIFY = "Verify by VIN with the manufacturer: CUORE cannot confirm recall or campaign status."
FLASH_RE = re.compile(r"flash|reprogram|software|calibration|proxi|wi-?tech|programming", re.I)
BUS_CABLE = {"can_ihs": ("blue", "A5", "CAN-IHS"), "can_ch": ("grey", "A6", "CAN-CH")}


def _s(x: Any) -> str:
    return str(x or "").strip()


def _owner(vin: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from ..live import owner_events
        from . import owner_reports as orp
        for e in owner_events.load(vin):
            f = e.get("fields") or {}
            if e.get("kind") == orp.KIND and not e.get("deleted") and f.get("consent") is True:
                out.append({"id": e.get("id", ""), "at": _s(e.get("recorded_at"))[:16].replace("T", " "),
                            "text": orp.compose_text(f), "photo": bool(e.get("media_ids")),
                            "source": _s(f.get("source")) or "owner", "origin": "owner",
                            "label": "owner's words, not a reading"})
    except Exception:  # noqa: BLE001
        pass
    try:
        from mes import shop
        for v in shop.load(vin):
            t = _s(v.get("complaint"))
            if t:
                at = _s(v.get("in_at"))[:16].replace("T", " ")
                who = _s(v.get("technician")) or "unnamed technician"
                out.append({"id": _s(v.get("id")), "at": at, "text": t, "photo": False, "source": "intake",
                            "origin": "intake", "label": f"recorded at intake by {who}, {at[:10] or 'date unknown'}"})
    except Exception:  # noqa: BLE001
        pass
    try:
        from mes import symptoms
        for sy in symptoms.load(vin):
            t = _s(sy.get("text")) or ", ".join(_s(x).replace("_", " ") for x in sy.get("tags") or [])
            if t:
                at = _s(sy.get("at"))[:16].replace("T", " ")
                odo = sy.get("odometer_km")
                odo_s = f", {odo:g} km" if isinstance(odo, (int, float)) else ""
                out.append({"id": _s(sy.get("id")), "at": at, "text": t, "photo": False,
                            "source": _s(sy.get("reporter")) or "driver", "origin": "symptom",
                            "label": f"symptom record, {at[:10] or 'date unknown'}{odo_s}"})
    except Exception:  # noqa: BLE001
        pass
    out.sort(key=lambda r: r["at"], reverse=True)
    seen: set[str] = set()
    uniq = []
    for r in out:  # same words entered twice (any origin): keep the newest only
        k = re.sub(r"\W+", " ", r["text"].casefold()).strip()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


def _job(vin: str) -> dict[str, Any] | None:
    try:
        from mes import jobs
        return jobs.current(vin)
    except Exception:  # noqa: BLE001
        return None


def _leads(vin: str, job: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str], set[str]]:
    leads: list[dict[str, Any]] = []
    codes: list[str] = []
    modules: set[str] = set()
    for h in (job or {}).get("hypotheses") or []:
        if h.get("deleted") or h.get("status") == "refuted":
            continue
        leads.append({"kind": "Open job hypothesis", "text": _s(h.get("text")), "test": _s(h.get("next_test")),
                      "why": f"Recorded on the open job ({_s(h.get('system_text')) or 'no system'}); not yet proven."})
        if h.get("system_text"):
            modules.add(_s(h["system_text"]))
        codes.extend(_s(c).upper() for c in h.get("codes") or [])
    try:
        from . import tsb_xref_bridge as x
        for r in x._load_dtc_history(vin):
            c = _s(r.get("dtc")).upper()
            if not c:
                continue
            codes.append(c)
            modules.update(_s(m) for m in r.get("modules") or [])
            leads.append({"kind": "DTC history", "text": c, "test": "",
                          "why": f"Seen in {r.get('sessions', '?')} session(s), last {_s(r.get('last_seen'))[:10] or 'date unknown'}; "
                                 "history says it was stored, not that it is present now."})
        view = x.safe_xref(vin) if leads else None  # cross-reference only when the car has its own leads
        for b in (x.top(view, 5) if view else []):
            reasons = "; ".join(_s(r.get("reason")) for r in b.get("relations") or [])[:240]
            leads.append({"kind": "Bulletin cross-reference", "text": f"{b['number']}: {_s(b.get('title'))}",
                          "test": "", "why": reasons or "Linked by CUORE's cross-reference.", "href": b.get("href", "")})
    except Exception:  # noqa: BLE001
        pass
    return leads, list(dict.fromkeys(codes)), {m for m in modules if m}


def _bulletins() -> tuple[list[dict[str, Any]], str]:
    try:
        from ..data import load_tsb_catalogue
        cat = load_tsb_catalogue()
    except Exception:  # noqa: BLE001
        return [], ""
    v = cat.get("vehicle") or {}
    plat = " ".join(_s(v.get(k)) for k in ("year", "make", "model", "engine"))
    rows = [{"number": _s(i.get("number")), "kind": _s(i.get("kind")).upper(), "title": _s(i.get("title")),
             "applies": {"yes": "applies", "vin_check": "applicability unconfirmed, check by VIN"}.get(
                 i.get("applies"), _s(i.get("applies"))),
             "verified": bool(i.get("verified")), "repair": _s(i.get("repair_implied")),
             "href": "/tsb#tsb-row-" + re.sub(r"[^A-Za-z0-9]+", "-", _s(i.get("id"))).strip("-")}
            for i in cat.get("items") or []
            if i.get("vehicle_scope") != "sibling_engine" and i.get("applies") != "no"]
    return rows, plat


def _parts(vin: str, codes: list[str]) -> list[dict[str, Any]]:
    from . import parts_bridge
    out: dict[str, dict[str, Any]] = {}
    for c in codes:
        try:
            rows = parts_bridge.parts_for_code(c, vin)
        except Exception:  # noqa: BLE001
            rows = []
        for p in rows:
            k = _s(p.get("key") or p.get("name"))
            o = out.setdefault(k, {"name": _s(p.get("name")) or k, "key": k,
                                   "oem": [str(n) for n in (p.get("oem") or [])][:3], "codes": []})
            o["codes"].append(c)
    return list(out.values())


def _time(vin: str) -> list[dict[str, Any]]:
    try:
        from mes import shop
        vs = shop.load(vin)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for v in vs:
        mins = [s["minutes"] for s in v.get("step_times") or [] if isinstance(s.get("minutes"), (int, float))]
        if v.get("out_at") or mins:
            out.append({"in": _s(v.get("in_at"))[:16].replace("T", " "), "out": _s(v.get("out_at"))[:16].replace("T", " "),
                        "complaint": _s(v.get("complaint")), "step_minutes": round(sum(mins), 1) if mins else None})
    return out


def _equipment(vin: str, job: dict[str, Any] | None, leads: list[dict[str, Any]], modules: set[str],
               bulletins: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    for l in leads:
        if FLASH_RE.search(l["test"]) or (l["kind"] == "Open job hypothesis" and FLASH_RE.search(l["text"])):
            reasons.append(f"Lead mentions a flash/programming/configuration step: {l['text'][:80]}.")
    lead_nums = " ".join(l["text"] for l in leads if l["kind"] == "Bulletin cross-reference")
    for b in bulletins:
        if b["number"] and b["number"] in lead_nums and b["repair"] in ("flash", "software_update"):
            reasons.append(f"Linked bulletin {b['number']} implies a software update.")
    witech: list[dict[str, Any]] = []
    try:
        from ..web import handoff_routes as h
        from . import fault_board
        if job:
            ctx = fault_board.fault_board_context(vin, job.get("id"))
            cards = [c for g in ctx["groups"] for c in g["cards"]]
            witech = h._witech(job, cards, modules)
    except Exception:  # noqa: BLE001
        pass
    buses: list[dict[str, Any]] = []
    try:
        from ..live.buses import BUSES
        low = {m.lower() for m in modules}
        for key, (colour, tag, name) in BUS_CABLE.items():
            hit = sorted(m for m in BUSES[key].modules_seen if m.lower() in low)
            if hit:
                buses.append({"colour": colour, "tag": tag, "bus": name, "modules": hit})
    except Exception:  # noqa: BLE001
        pass
    return {"charger": reasons, "witech": witech, "bypass": buses}


def build(vin: str) -> dict[str, Any]:
    vin = _s(vin).upper()
    owner = _owner(vin)
    job = _job(vin)
    leads, codes, modules = _leads(vin, job)
    bulletins, platform = _bulletins()
    parts = _parts(vin, codes)
    eq = _equipment(vin, job, leads, modules, bulletins)
    if eq["charger"] or eq["witech"]:
        top = "Battery charger on the car (13.2-13.5 V) and wiTECH ready: " + (
            eq["charger"][0] if eq["charger"] else eq["witech"][0]["why"])
    elif leads:
        top = f"First lead to test: {leads[0]['text'][:140]} (a lead, not a conclusion)."
    elif owner:
        top = f"Read the complaint first: {owner[0]['text'][:140]} ({owner[0]['label']})."
    else:
        top = "Nothing on record for this car yet: arrive with the adapter checked and take a fresh reading."
    return {"vin": vin, "owner": owner, "job": job, "leads": leads, "codes": codes, "bulletins": bulletins,
            "platform": platform, "verify": VERIFY, "parts": parts, "equipment": eq, "times": _time(vin),
            "top": top,
            "counts": {"owner": len(owner), "leads": len(leads), "bulletins": len(bulletins), "parts": len(parts),
                       "equipment": 1 + len(eq["charger"]) + len(eq["witech"]) + len(eq["bypass"])}}
