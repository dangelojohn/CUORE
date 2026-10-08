"""``GET /v/{vin}/systems``: the cross-system dependency view -- which
systems may sit upstream of a given code's family, and where this
vehicle's own history corroborates that (or merely guesses at it).

Same posture as :mod:`cuore.web.timeline_routes`/:mod:`cuore.web.
parts_routes` (both built the same way, concurrently with other agents):
a separate router, reusing ``_dossier``/``_page``/``_set_active_vehicle``/
``_vehicle_bar`` from :mod:`cuore.web.routes` by import rather than
duplicating that plumbing.

The data contract lives in ``cuore.services.systems_bridge``
(``systems()``, ``systems_for_code(code, description="")``,
``correlate(vin)``), built in parallel by another agent and not
necessarily present yet. Every call into it is wrapped and falls back to
a fixture built to the exact shape the contract specifies, so this page --
and the ``_system_badge.html`` chips on ``code.html``/``vehicle.html``/
``report.html`` -- are developable and testable before that module lands.
Once it exists, nothing here needs to change -- the lazy import just
starts succeeding.

Registers two Jinja globals the same way :mod:`cuore.web.timeline_routes`
registers ``code_feel`` and :mod:`cuore.web.parts_routes` registers
``parts_for`` -- on both ``Jinja2Templates`` instances this feature's
pages use (``cuore.web.routes``'s, for ``code.html``/``vehicle.html``/
``report.html``, and ``cuore.web.service_routes``'s, the same
two-environments wrinkle :mod:`cuore.web.experience_globals` already
documents and works around):

* ``systems_for_code(code, description="")`` -- the badge list for one code.
* ``system_label(key)`` -- a system key's display label, for anywhere a
  badge or table only has the bare key (falls back to a title-cased key
  for one this page has never seen).

Not registered on the app here -- ``app.py`` is owned by another agent
while this was built. The two lines needed there (next to the other
``web`` router imports/includes):

    ``from .web import systems_routes``
    ``app.include_router(systems_routes.router)``
"""

from __future__ import annotations

import importlib
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import known_good_bridge, parts_bridge
from . import systems_svg
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar
from .routes import templates as _shared_templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

#: depends_on confidence -> edge line style, the same three buckets
#: systems_svg.py draws (solid covers both CONFIRMED and CORROBORATED).
CONFIDENCE_STYLE: dict[str, str] = {
    "CONFIRMED": "solid", "CORROBORATED": "solid",
    "SINGLE-SOURCE": "dashed", "UNKNOWN": "dotted",
}
#: role/confidence combinations the badge treats as "not yet nailed down" --
#: these get a trailing "?" on the badge rather than a second colour.
_LOW_CONFIDENCE = {"SINGLE-SOURCE", "UNKNOWN"}

STATUS_LABEL = systems_svg.STATUS_TEXT
#: status -> the existing status-chip CSS class (cuore.css already defines
#: .chip.status-active/.status-cleared_unverified/.status-stale and the
#: plain .chip.ok -- no new classes needed here). Vocabulary matches
#: mes.systems.correlate() exactly: active/cleared_unverified/clean/stale.
STATUS_CHIP_CLASS = {"active": "status-active", "cleared_unverified": "status-cleared_unverified",
                     "clean": "ok", "stale": "status-stale"}


# --- fixture: the exact shape cuore.services.systems_bridge returns, built
# directly against the real ``mes.systems`` contract (same keys, same
# vocabulary -- "electrical_supply" not "electrical", status one of
# active/cleared_unverified/clean/stale, live_channels/parts as plain known
# good/parts keys, not inline dicts) so this fixture and the real module
# are interchangeable to every consumer below. ----------------------------

def _fixture_systems() -> list[dict[str, Any]]:
    return [
        {"key": "electrical_supply", "label": "Electrical supply",
         "components": ["12V battery", "alternator", "chassis/engine grounds", "fuses"],
         "live_channels": ["battery_voltage"],
         "maintenance_items": ["battery_12v"], "parts": ["battery_12v"], "depends_on": []},
        {"key": "network", "label": "Network / CAN buses",
         "components": ["CAN-C", "CAN-IHS", "gateway modules", "BCM"],
         "live_channels": [], "maintenance_items": [], "parts": [],
         "depends_on": [{"system": "electrical_supply",
                          "why": "BCM power feeds and chassis grounds are a documented root cause "
                                "of multi-module U-code cascades, not per-module bus faults.",
                          "confidence": "CONFIRMED", "source": "mes.knowledge bulletins"}]},
        {"key": "evap", "label": "EVAP (evaporative emissions)",
         "components": ["purge valve", "vent valve", "fuel cap", "NVLD"],
         "live_channels": [], "maintenance_items": [], "parts": ["evap_purge_valve"],
         "depends_on": [{"system": "electrical_supply",
                          "why": "the purge valve solenoid is an ECM-commanded, power-fed actuator",
                          "confidence": "SINGLE-SOURCE", "source": "mes.parts esim/purge_valve"},
                         {"system": "fuel",
                          "why": "EVAP shares the tank, fuel cap and fuel-level/pressure signal path "
                                "with the fuel system",
                          "confidence": "CORROBORATED", "source": "mes.code_feel EVAP section"}]},
        {"key": "fuel", "label": "Fuel", "components": ["fuel pump", "fuel level sensor"],
         "live_channels": [], "maintenance_items": [], "parts": [], "depends_on": []},
        {"key": "brakes_abs", "label": "Brakes / ABS", "components": ["ABS module", "wheel speed sensors"],
         "live_channels": [], "maintenance_items": [], "parts": [],
         "depends_on": [{"system": "electrical_supply", "why": "speculative -- not yet corroborated on this car",
                          "confidence": "UNKNOWN", "source": "none yet"}]},
    ]


def _fixture_systems_for_code(code: str, description: str = "") -> list[dict[str, Any]]:
    c = (code or "").upper()
    if c.startswith("P04"):
        return [{"system": "evap", "role": "primary", "confidence": "CONFIRMED", "source": "DTC prefix table"},
                {"system": "electrical_supply", "role": "upstream", "confidence": "SINGLE-SOURCE",
                 "source": "systems depends_on graph"},
                {"system": "fuel", "role": "upstream", "confidence": "CORROBORATED",
                 "source": "systems depends_on graph"}]
    if c.startswith("U0"):
        return [{"system": "network", "role": "primary", "confidence": "CORROBORATED", "source": "DTC prefix table"},
                {"system": "electrical_supply", "role": "upstream", "confidence": "CONFIRMED",
                 "source": "systems depends_on graph"}]
    if c.startswith("C"):
        return [{"system": "brakes_abs", "role": "primary", "confidence": "CONFIRMED", "source": "DTC prefix table"},
                {"system": "electrical_supply", "role": "upstream", "confidence": "UNKNOWN",
                 "source": "systems depends_on graph"}]
    return []


def _fixture_correlate(vin: str) -> dict[str, Any]:
    return {
        "by_system": [
            {"system": "evap", "codes": ["P0440", "P0455", "P0456"], "sessions": 11,
             "first": "2025-09-24", "last": "2026-08-27", "status": "cleared_unverified"},
            {"system": "network", "codes": ["U0100"], "sessions": 2,
             "first": "2026-01-15", "last": "2026-01-15", "status": "stale"},
            {"system": "electrical_supply", "codes": [], "sessions": 0, "first": None, "last": None,
             "status": "clean"},
            {"system": "fuel", "codes": [], "sessions": 0, "first": None, "last": None, "status": "clean"},
            {"system": "brakes_abs", "codes": [], "sessions": 0, "first": None, "last": None, "status": "stale"},
        ],
        "co_occurrence": [
            {"a": "evap", "b": "electrical_supply", "sessions_together": 0, "sessions_a": 11, "sessions_b": 0,
             "lift": 1.0, "reading": "no electrical-supply session on file yet to corroborate against"},
        ],
        "chains": [
            {"issue": "EVAP leak codes (P0440/P0455/P0456) will not verify clean",
             "possible_upstream": [
                 {"system": "electrical_supply", "why": "purge valve solenoid control circuit",
                  "evidence": "TSB 18-030-17 (ECM calibration) is the leading verdict for this car; "
                              "no electrical fault has been corroborated on it yet"},
             ]},
        ],
        "findings": [
            "EVAP is the only system with an active/cleared-unverified code on this car -- every "
            "other system is stale (no live or session data) rather than confirmed clean.",
        ],
    }


def _bridge():
    """``cuore.services.systems_bridge``, or ``None`` if it has not landed."""
    try:
        from ..services import systems_bridge
        return systems_bridge
    except ImportError:
        return None


def _systems() -> list[dict[str, Any]]:
    """Normalises to a list either way: ``mes.systems.systems()`` actually
    returns an ordered ``{key: record}`` dict ("every vehicle system in
    the graph, in reading order" -- a Python dict preserves that just as
    well as a list), while this fixture (and the contract as first
    specified) uses a plain list. Every consumer below only ever wants
    the list of records, so that's what this always hands back."""
    bridge = _bridge()
    if bridge is None:
        return _fixture_systems()
    try:
        raw = bridge.systems()
    except Exception:  # noqa: BLE001 -- a knowledge-table miss must never 500 a page
        return _fixture_systems()
    if isinstance(raw, dict):
        return list(raw.values())
    return list(raw or [])


def _systems_for_code(code: str, description: str = "") -> list[dict[str, Any]]:
    bridge = _bridge()
    if bridge is None:
        return _fixture_systems_for_code(code, description)
    try:
        return bridge.systems_for_code(code, description) or []
    except Exception:  # noqa: BLE001
        return []


def _correlate(vin: str) -> dict[str, Any]:
    bridge = _bridge()
    if bridge is None:
        return _fixture_correlate(vin)
    try:
        return bridge.correlate(vin) or {}
    except Exception:  # noqa: BLE001
        return _fixture_correlate(vin)


def _live_channel_info(channel_id: str) -> dict[str, Any]:
    """One system's ``live_channels`` entry (a bare known-good channel key,
    e.g. ``"battery_voltage"``) resolved to a display name and its
    known-good band note, via :mod:`cuore.services.known_good_bridge` --
    the same source ``cuore.live.layouts``' gauges read. Never raises: an
    unresolvable or UNKNOWN-confidence channel still shows (by its id) with
    a plain "no sourced band yet" note rather than vanishing or 500ing."""
    row, band = None, None
    try:
        row = known_good_bridge.known_good_for(channel_id)
    except Exception:  # noqa: BLE001
        pass
    try:
        band = known_good_bridge.sourced_band(channel_id)
    except Exception:  # noqa: BLE001
        pass
    name = (row or {}).get("name") or channel_id.replace("_", " ").title()
    note = (band or {}).get("note") or "no sourced band yet"
    return {"name": name, "band": note}


def _system_parts(part_keys: list[str]) -> list[dict[str, Any]]:
    """One system's ``parts`` entry (a list of bare part keys, e.g.
    ``"battery_12v"``) resolved to full part dicts via
    :mod:`cuore.services.parts_bridge`, ready for ``_part_card.html``. A key
    with nothing on file is dropped, not shown as an empty card."""
    out = []
    for key in part_keys or []:
        try:
            p = parts_bridge.part(key)
        except Exception:  # noqa: BLE001
            p = None
        if p:
            out.append(p)
    return out


def _system_label(key: str) -> str:
    for s in _systems():
        if s.get("key") == key:
            return s.get("label") or key
    return (key or "").replace("_", " ").title()


_shared_templates.env.globals["systems_for_code"] = _systems_for_code
_shared_templates.env.globals["system_label"] = _system_label

for _module_name in ("service_routes", "drivetrain_routes", "timeline_routes"):
    try:
        _mod = importlib.import_module(f".{_module_name}", __package__)
        _tmpl = getattr(_mod, "templates", None) or getattr(_mod, "_shared_templates", None)
        if _tmpl is not None and _tmpl is not _shared_templates:
            _tmpl.env.globals["systems_for_code"] = _systems_for_code
            _tmpl.env.globals["system_label"] = _system_label
    except Exception:  # noqa: BLE001 -- import-time side effect, must never raise
        pass


# --- the page's view model --------------------------------------------------

def _build_view(vin: str, show_all: bool = True) -> dict[str, Any]:
    systems = _systems()
    corr = _correlate(vin)
    by_system = {r.get("system"): r for r in (corr.get("by_system") or [])}
    labels = {s.get("key"): s.get("label") or s.get("key") for s in systems}

    nodes, cards = [], []
    for s in systems:
        key = s.get("key")
        row = by_system.get(key) or {}
        status = row.get("status") or "stale"
        codes = row.get("codes") or []
        nodes.append({"key": key, "label": s.get("label") or key,
                     "status": status, "code_count": len(codes)})
        cards.append({
            "key": key, "label": s.get("label") or key,
            "status": status, "status_label": STATUS_LABEL.get(status, status),
            "status_chip_class": STATUS_CHIP_CLASS.get(status, "status-stale"),
            "codes": codes, "sessions": row.get("sessions"),
            "first": row.get("first"), "last": row.get("last"),
            "components": s.get("components") or [],
            "live_channels": [_live_channel_info(ch) for ch in (s.get("live_channels") or [])],
            "maintenance_items": [m.replace("_", " ") for m in (s.get("maintenance_items") or [])],
            "parts": _system_parts(s.get("parts") or []),
            "depends_on": [
                {**dep, "confidence": (dep.get("confidence") or "UNKNOWN").upper(),
                 "system_label": labels.get(dep.get("system"), dep.get("system"))}
                for dep in (s.get("depends_on") or [])
            ],
            "technical": s.get("technical") or {},
        })

    edges = []
    for s in systems:
        for dep in s.get("depends_on") or []:
            conf = (dep.get("confidence") or "UNKNOWN").upper()
            edges.append({"a": s.get("key"), "b": dep.get("system"), "confidence": conf,
                         "style": CONFIDENCE_STYLE.get(conf, "dotted"),
                         "why": dep.get("why"), "source": dep.get("source"),
                         "a_label": labels.get(s.get("key"), s.get("key")),
                         "b_label": labels.get(dep.get("system"), dep.get("system")),
                         "technical": dep.get("technical") or {}})

    co_occurrence = [
        {**row, "a_label": labels.get(row.get("a"), row.get("a")),
         "b_label": labels.get(row.get("b"), row.get("b"))}
        for row in (corr.get("co_occurrence") or [])
    ]

    chains = []
    for ch in corr.get("chains") or []:
        upstream = [{**u, "system_label": labels.get(u.get("system"), u.get("system"))}
                   for u in (ch.get("possible_upstream") or [])]
        chains.append({**ch, "possible_upstream": upstream})

    # Mechanic-UX review point 7: the graph defaults to this car's own
    # footprint -- the systems that actually have a code on it, plus
    # whatever those directly depend on -- not the full 25-system
    # taxonomy. ``?all=1`` (``show_all``) still shows everything, and the
    # per-system card list below the graph is filtered the same way so
    # the two never disagree about what's "on this car" right now.
    keep_keys = {n["key"] for n in nodes}
    if not show_all:
        with_codes = {n["key"] for n in nodes if n["code_count"]}
        upstream_keys: set[str] = set()
        for s in systems:
            if s.get("key") in with_codes:
                for dep in s.get("depends_on") or []:
                    upstream_keys.add(dep.get("system"))
        narrowed = with_codes | upstream_keys
        # Never show an empty graph -- a car with no codes on file yet
        # still gets the full map rather than a blank page.
        if narrowed:
            keep_keys = narrowed

    nodes = [n for n in nodes if n["key"] in keep_keys]
    cards = [c for c in cards if c["key"] in keep_keys]
    edges = [e for e in edges if e["a"] in keep_keys and e["b"] in keep_keys]

    return {
        "nodes": nodes, "edges": edges, "cards": cards,
        "co_occurrence": co_occurrence, "chains": chains,
        "findings": corr.get("findings") or [],
        "show_all": show_all, "total_systems": len(systems),
        "visible_systems": len(nodes),
    }


# --- the page ---------------------------------------------------------------


@router.get("/v/{vin}/systems", response_class=HTMLResponse)
def systems_page(request: Request, vin: str, all: bool = False) -> HTMLResponse:
    """The dependency graph: which systems may sit upstream of which codes,
    and what this vehicle's own history does and does not corroborate.

    ``?all=1`` shows the full systems taxonomy; by default the graph (and
    the card list under it) only shows what this car's own codes touch."""
    dossier = _dossier(vin)
    view = _build_view(vin, show_all=all)
    svg = systems_svg.render(view["nodes"], view["edges"])
    response = _page(request, "systems.html", vin=vin, bar=_vehicle_bar(vin, dossier),
                     tab="systems", view=view, svg=svg)
    _set_active_vehicle(response, vin)
    return response


__all__ = ["router"]
