"""Data for the bench page: "what am I doing to this car, right now".

``cuore/web/routes.py``'s old ``/v/{vin}`` was the full dossier -- verdict,
every code, every bulletin, every freeze frame, all at once. That page still
exists (moved to ``/v/{vin}/dossier``); this module backs the thing a
mechanic actually wants the instant the car is on the lift: the verdict's
own next-action sentence, the three things to go do about it (with the
parts and tools each one needs already resolved), and a couple of jump-off
points (codes, the job, the full dossier) -- nothing that needs scrolling to
reach on a 400x800 screen.

``build_bench`` is the only entry point. It composes bridges that already
exist -- ``dossier_bridge.build_view`` for the verdict/open-work/codes,
``parts_bridge``/``tools_kb_bridge`` for what a step needs,
``shop_bridge.resolve_vehicle_name``/``current_visit_for_vin`` for the
header line and the complaint, ``cases_bridge.prefill`` for the one-line
case hint -- and invents no new diagnosis of its own.
"""

from __future__ import annotations

from typing import Any

from . import cache, dossier_bridge, mes_bridge, parts_bridge, tools_kb_bridge
from .errors import BadRequest

try:
    from . import cases_bridge
except Exception:  # noqa: BLE001 -- the bench must still render without it
    cases_bridge = None

try:
    from . import shop_bridge
except Exception:  # noqa: BLE001
    shop_bridge = None


#: Capped the same way the spec caps each bench card: 3 next actions, each
#: with at most 3 parts and 4 tools.
_MAX_ACTIONS = 3
_MAX_PARTS = 3
_MAX_TOOLS = 4
_MAX_SHORTCUTS = 6

#: Family key (lowercased, as ``dossier_bridge.FAMILY_STEPS``/the generic
#: SAE-range rules spell it) -> icon registry key, for the bench card's own
#: pictogram. Anything not listed here falls back to a generic glyph --
#: never a 500 for a family this table doesn't know about yet.
FAMILY_ICON: dict[str, str] = {
    "evap": "sys_evap", "network": "sys_network", "misfire": "sys_ignition",
    "fuel_trim": "sys_fuel", "cooling": "sys_cooling",
    "engine_management": "sys_engine_management",
    "transmission_driveline": "sys_transmission_driveline", "adas": "sys_adas_sensors",
    "chassis": "sys_suspension", "body": "sys_body_comfort",
    "powertrain_other": "sys_engine_management",
}


def _vehicle_name(vin: str, dossier: dict[str, Any]) -> str:
    """Never "(unnamed vehicle)" -- ``shop_bridge.resolve_vehicle_name``
    already guarantees that (corpus name, then dossier identity, then a WMI
    decode, then the VIN itself); if that bridge is unavailable for any
    reason, fall back to the dossier's own identity field, then the VIN."""
    if shop_bridge is not None:
        try:
            name = shop_bridge.resolve_vehicle_name(vin)
            if name:
                return name
        except Exception:  # noqa: BLE001
            pass
    return (dossier.get("identity") or {}).get("vehicle") or vin


def _complaint(vin: str) -> str | None:
    if shop_bridge is None:
        return None
    try:
        visit = shop_bridge.current_visit_for_vin(vin)
    except Exception:  # noqa: BLE001
        return None
    return (visit or {}).get("complaint") or None


def _case_hint(vin: str, open_codes: list[str]) -> str | None:
    """One line from ``cases_bridge.prefill`` -- only when a prior case
    actually matched; the honest "no prior case on file" summary
    ``mes.cases.prefill`` returns otherwise is not a hint worth a mechanic's
    attention."""
    if cases_bridge is None:
        return None
    try:
        prefill = cases_bridge.prefill(vin, open_codes)
    except Exception:  # noqa: BLE001
        return None
    if not prefill.get("matched_case"):
        return None
    return prefill.get("summary")


def _family_parts(vin: str, codes: list[str]) -> list[dict[str, Any]]:
    """Up to :data:`_MAX_PARTS` parts for a family's codes, deduplicated by
    part key, each shaped ``{name, number, confidence}``. ``number`` and
    ``confidence`` come off the first OEM row a part carries, falling back
    to the first aftermarket row -- never invented when neither exists."""
    seen: dict[str, dict[str, Any]] = {}
    for code in codes:
        if len(seen) >= _MAX_PARTS:
            break
        try:
            rows = parts_bridge.parts_for_code(code, vin=vin)
        except Exception:  # noqa: BLE001
            rows = []
        for p in rows:
            key = p.get("key")
            if not key or key in seen:
                continue
            oem = p.get("oem") or []
            aftermarket = p.get("aftermarket") or []
            src = oem[0] if oem else (aftermarket[0] if aftermarket else {})
            seen[key] = {"name": p.get("name"), "number": src.get("number"),
                        "confidence": src.get("confidence", "UNKNOWN")}
            if len(seen) >= _MAX_PARTS:
                break
    return list(seen.values())


def _family_tools(family: str) -> list[dict[str, Any]]:
    """Up to :data:`_MAX_TOOLS` tools for this family, shaped
    ``{name, have}`` -- ``tools_kb_bridge.recommend`` already resolves
    ``have`` against the shop's own inventory. ``[]`` for a family
    ``mes.tools_kb`` has no job-tools table for yet (most of the generic
    families) -- never a guess at what tool a car needs."""
    try:
        rows = tools_kb_bridge.recommend((family or "").lower())
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in rows[:_MAX_TOOLS]:
        info = r.get("tool_info") or {}
        out.append({"name": info.get("name") or info.get("key"), "have": r.get("have")})
    return out


def _next_actions(vin: str, open_work: list[dict[str, Any]],
                  codes_by_base: dict[str, str]) -> list[dict[str, Any]]:
    """The top :data:`_MAX_ACTIONS` unchecked open-work steps across every
    family, ACTIVE families first (any of that family's codes currently
    ACTIVE in the code table), then in the same order
    ``dossier_bridge._build_open_work`` already put the cards in (curated
    families, then the generic ones) -- a stable sort preserves that
    ordering within each of the two groups."""
    def is_active(card: dict[str, Any]) -> bool:
        return any(codes_by_base.get(c) == "ACTIVE" for c in card.get("codes") or [])

    ordered = sorted(open_work, key=lambda c: 0 if is_active(c) else 1)

    actions: list[dict[str, Any]] = []
    for card in ordered:
        family = card.get("family") or ""
        for step in card.get("steps") or []:
            if step.get("done"):
                continue
            ref = step.get("ref")
            actions.append({
                "step_id": step["id"], "family": family, "text": step["text"],
                "bulletin": ({"id": ref, "href": step.get("ref_href")} if ref else None),
                "parts": _family_parts(vin, card.get("codes") or []),
                "tools": _family_tools(family),
                "done": False,
                "href_tick": f"/v/{vin}/checklist",
                "icon": FAMILY_ICON.get(family.lower(), "tools"),
            })
            if len(actions) >= _MAX_ACTIONS:
                return actions
    return actions


def _shortcuts(vin: str, codes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Up to :data:`_MAX_SHORTCUTS` code-page links, active codes and
    cleared-but-unverified codes only -- a stale code is not worth a tap
    target on a screen this small."""
    out = []
    for row in codes:
        if row.get("status") not in ("ACTIVE", "CLEARED_UNVERIFIED"):
            continue
        out.append({"code": row["code"], "href": row["href"], "status": row["status"]})
        if len(out) >= _MAX_SHORTCUTS:
            break
    return out


def build_bench(vin: str) -> dict[str, Any]:
    """Everything ``bench.html`` needs, computed once.

    ``live_status`` is passed as ``None`` into ``dossier_bridge.build_view``
    -- the same choice ``flow_bridge.flow_state`` and
    ``shop_bridge._dossier_verdict`` already make from the service layer:
    it only affects whether the verdict's own action buttons render as
    enabled, never the verdict state itself (that comes from recorded
    observations), and the bench page does not render those buttons anyway.
    """
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")

    dossier = cache.get_or_build(
        ("workup", vin, mes_bridge.newest_mtime(vin)),
        lambda: mes_bridge.workup(vin=vin),
    )
    view = dossier_bridge.build_view(vin, dossier, None)
    identity = dossier.get("identity") or {}

    verdict_raw = view.get("verdict") or {}
    verdict = {
        "state": verdict_raw.get("state"),
        "label": verdict_raw.get("label"),
        "sentence": verdict_raw.get("summary"),
        "next_action": verdict_raw.get("next_action"),
        "blocker": verdict_raw.get("blocker"),
    }

    codes = view.get("codes") or []
    codes_by_base = {row["code"]: row["status"] for row in codes}
    next_actions = _next_actions(vin, view.get("open_work") or [], codes_by_base)

    latest = view.get("latest") or {}
    last_read = latest.get("session_short") or latest.get("scan_short")

    try:
        open_codes = mes_bridge.open_codes_for(dossier)
    except Exception:  # noqa: BLE001
        open_codes = []

    return {
        "vin": vin,
        "vehicle": _vehicle_name(vin, dossier),
        "vin_tail": vin[-6:] if len(vin) >= 6 else vin,
        "km": identity.get("odometer_last_km"),
        "complaint": _complaint(vin),
        "verdict": verdict,
        "next_actions": next_actions,
        "open_codes_count": (view.get("code_counts") or {}).get("active", 0),
        "last_read": last_read,
        "shortcuts": _shortcuts(vin, codes),
        "case_hint": _case_hint(vin, open_codes),
    }


__all__ = ["build_bench", "FAMILY_ICON"]
