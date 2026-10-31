"""The shop-wide Bay board: one card per car now in the shop, every brand.

Read-only view-model from CUORE's own stores (visits, jobs, logs). It never touches the car or the adapter.
Reuses the landing page's car facts and verdict, and the Bay Service Sheet's status word and latest work, so a
card can never disagree with the pages it links to. A missing value is "" -- nothing is invented, and a repair
that is not proven clean is never called fixed (``status_word`` decides). No customer data is read.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from . import bay_service_sheet as sheet
from . import flow_bridge, landing_bridge, mes_bridge


def _s(x: Any) -> str:
    return str(x or "").strip()


def time_in_bay(in_at: str, now: Optional[datetime] = None) -> str:
    """"25 min", "3 h 20 min", "2 d 4 h" from the intake stamp; "" when it cannot be read."""
    try:
        t0 = datetime.fromisoformat(_s(in_at))
    except ValueError:
        return ""
    mins = int(((now or datetime.now()) - t0).total_seconds() // 60)
    if mins < 0:
        return ""
    if mins < 60:
        return f"{mins} min"
    if mins < 2880:
        h, m = divmod(mins, 60)
        return f"{h} h {m} min" if m else f"{h} h"
    d, rest = divmod(mins, 1440)
    return f"{d} d {rest // 60} h"


def _in_bay_visits() -> dict[str, dict[str, Any]]:
    """vin -> the newest visit that has not left."""
    out: dict[str, dict[str, Any]] = {}
    shop = flow_bridge._shop_mod()
    if shop is None:
        return out
    try:
        for v in shop.load():  # oldest first, so a later visit of the same car wins
            vin = _s(v.get("vin"))
            if not vin:
                continue
            if v.get("status") != "out":
                out[vin] = v
            else:
                out.pop(vin, None)
    except Exception:  # noqa: BLE001
        pass
    return out


def _job_for(vin: str, job_id: Any) -> Optional[dict[str, Any]]:
    try:
        from mes import jobs
        for j in jobs.load(vin):
            if job_id and j.get("id") == job_id:
                return j
    except Exception:  # noqa: BLE001
        pass
    return sheet._job(vin)


def _group(card: dict[str, Any]) -> int:
    """0 = open job with active faults, 1 = verifying, 2 = the rest."""
    if card["status"] == "Open" and card["state"] == "ACTIVE_FAULTS":
        return 0
    if card["status"] == "Verifying":
        return 1
    return 2


GROUP_TITLES = {0: "Needs attention", 1: "Verifying", 2: "In the bay"}


def build(now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or datetime.now()
    visits = _in_bay_visits()
    known = landing_bridge._gather() if visits else {}
    cards: list[dict[str, Any]] = []
    for vin, v in visits.items():
        info = known.get(vin) or {}
        verdict = landing_bridge._verdict(vin, (info.get("logs") or 0) > 0)
        job = _job_for(vin, v.get("job_id"))
        marque = mes_bridge.marque_for_vin(vin)
        b = landing_bridge.brand(marque) or {}
        work = sheet.latest_work(vin, 1)
        cards.append({
            "vin": vin, "vin8": vin[-8:], "marque": marque, "brand": b,
            "name": _s(v.get("vehicle")) or _s(info.get("name")),
            "reason": _s((job or {}).get("complaint")) or _s(v.get("complaint")),
            "tech": _s((job or {}).get("technician")) or _s(v.get("technician")),
            "in_at": _s(v.get("in_at")), "time": time_in_bay(v.get("in_at"), now),
            "status": sheet.status_word(job, verdict),
            "work": work[0] if work else None,
            "state": verdict["state"], "state_word": verdict["word"],
        })
    for c in cards:
        c["group"] = _group(c)
    cards.sort(key=lambda c: landing_bridge._neg(c["in_at"]))  # newest first
    cards.sort(key=lambda c: c["group"])                       # stable: attention first
    groups = [{"title": GROUP_TITLES[g], "cards": [c for c in cards if c["group"] == g]}
              for g in (0, 1, 2) if any(c["group"] == g for c in cards)]
    return {"groups": groups, "total": len(cards),
            "open": sum(c["status"] == "Open" for c in cards),
            "verifying": sum(c["status"] == "Verifying" for c in cards)}
