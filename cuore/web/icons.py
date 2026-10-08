"""Pictogram registry + the ``icon`` Jinja global.

CUORE's mechanics mostly don't read English (or the UI's current language)
as a first language, so the plan across the whole web app leans on small
line pictograms with a short label rather than paragraphs: see
``cuore/web/static/icons.svg`` for the sprite and ``icons.css`` for sizing.
This module is the registry that ties a short key (``"sys_fuel"``,
``"priority_p1"``, ...) to a symbol in that sprite and to the bilingual
label shown next to (or instead of) it.

The symbol id in icons.svg is always ``"i-" + key`` -- the registry key
IS the symbol suffix, so there is no separate mapping to keep in sync; see
``cuore/tests/check_icons_i18n.py`` for the check that the two files agree.

``icon(key, size="m", label=None)`` returns ready-to-use markup::

    <span class="ico ico-28"><svg role="img" aria-label="Fuel">
      <use href="/static/icons.svg#i-sys_fuel"></use></svg></span>

Registered as the Jinja global ``icon`` on every template environment that
already carries ``experience_links`` / ``flow_state_for`` -- same trick,
same four route modules, same defensive "must never 500 a page" posture;
see ``cuore/web/experience_globals.py``'s own docstring for why there are
exactly four. Importing this module is the side effect that does the
registration; nothing here is called directly. Wiring it in (so the global
actually exists at render time) is the same one-line
``from ..web import icons  # noqa: F401`` move used for the other
``*_globals`` modules -- left for the integration pass, not done here.
"""

from __future__ import annotations

import importlib
from html import escape
from typing import Any, Optional

try:  # pragma: no cover -- exercised indirectly; keep import optional
    from markupsafe import Markup
except Exception:  # noqa: BLE001 -- markupsafe ships with Jinja2, but don't 500 without it
    def Markup(s: str) -> str:  # type: ignore[no-redef]
        return s

from .static_version import static_url


#: key -> {"symbol": <icons.svg symbol suffix, == key>, "label_en": ..., "label_it": ...}
#: Grouped the same way icons.svg is grouped: flow steps, systems (keys taken
#: straight from mes-log-mcp/mes/systems.py's SYSTEMS dict), symptoms (keys
#: from mes-log-mcp/mes/symptoms.py's SYMPTOM_TAGS), statuses, priorities,
#: then the handful of misc glyphs (tools/parts/camera/...).
ICONS: dict[str, dict[str, str]] = {
    # -- 12 flow steps --------------------------------------------------
    "step_start":       {"symbol": "step_start",       "label_en": "Start",            "label_it": "Avvio"},
    "step_complaint":   {"symbol": "step_complaint",   "label_en": "Complaint",        "label_it": "Disturbo riferito"},
    "step_verdict":     {"symbol": "step_verdict",     "label_en": "Verdict",          "label_it": "Verdetto"},
    "step_scan":        {"symbol": "step_scan",        "label_en": "Scan",             "label_it": "Scansione"},
    "step_understand":  {"symbol": "step_understand",  "label_en": "Understand",       "label_it": "Comprendere"},
    "step_test":        {"symbol": "step_test",        "label_en": "Test",             "label_it": "Prova"},
    "step_hypothesis":  {"symbol": "step_hypothesis",  "label_en": "Hypothesis",       "label_it": "Ipotesi"},
    "step_plan":        {"symbol": "step_plan",        "label_en": "Plan",             "label_it": "Piano"},
    "step_repair":      {"symbol": "step_repair",      "label_en": "Repair",           "label_it": "Riparazione"},
    "step_verify":      {"symbol": "step_verify",      "label_en": "Verify",           "label_it": "Verifica"},
    "step_document":    {"symbol": "step_document",    "label_en": "Document",         "label_it": "Documentare"},
    "step_release":     {"symbol": "step_release",     "label_en": "Release",          "label_it": "Rilascio"},

    # -- 25 systems -------------------------------------------------------
    "sys_electrical_supply":      {"symbol": "sys_electrical_supply",      "label_en": "Electrical supply",      "label_it": "Impianto elettrico"},
    "sys_network":                {"symbol": "sys_network",                "label_en": "Network / CAN",          "label_it": "Rete / CAN"},
    "sys_ignition":                {"symbol": "sys_ignition",               "label_en": "Ignition",               "label_it": "Accensione"},
    "sys_fuel":                    {"symbol": "sys_fuel",                   "label_en": "Fuel",                   "label_it": "Alimentazione"},
    "sys_evap":                    {"symbol": "sys_evap",                   "label_en": "EVAP",                   "label_it": "Valvola di spurgo (EVAP)"},
    "sys_air_intake_boost":        {"symbol": "sys_air_intake_boost",       "label_en": "Air intake / boost",     "label_it": "Aspirazione / sovralimentazione"},
    "sys_cooling":                 {"symbol": "sys_cooling",                "label_en": "Cooling",                "label_it": "Raffreddamento"},
    "sys_lubrication":             {"symbol": "sys_lubrication",            "label_en": "Lubrication",             "label_it": "Lubrificazione"},
    "sys_exhaust_emissions":       {"symbol": "sys_exhaust_emissions",      "label_en": "Exhaust / emissions",    "label_it": "Scarico / emissioni"},
    "sys_transmission_driveline":  {"symbol": "sys_transmission_driveline", "label_en": "Transmission / driveline", "label_it": "Trasmissione"},
    "sys_brakes_abs":              {"symbol": "sys_brakes_abs",             "label_en": "Brakes / ABS",            "label_it": "Freni / ABS"},
    "sys_steering":                {"symbol": "sys_steering",               "label_en": "Steering",               "label_it": "Sterzo"},
    "sys_suspension":              {"symbol": "sys_suspension",             "label_en": "Suspension",             "label_it": "Sospensioni"},
    "sys_body_comfort":            {"symbol": "sys_body_comfort",           "label_en": "Body / comfort",         "label_it": "Carrozzeria / comfort"},
    "sys_adas_sensors":            {"symbol": "sys_adas_sensors",           "label_en": "ADAS sensors",           "label_it": "Sensori ADAS"},
    "sys_hvac":                    {"symbol": "sys_hvac",                   "label_en": "HVAC",                   "label_it": "Climatizzazione"},
    "sys_pcv":                     {"symbol": "sys_pcv",                    "label_en": "PCV / breather",         "label_it": "Sfiato (PCV)"},
    "sys_engine_management":       {"symbol": "sys_engine_management",      "label_en": "Engine management",      "label_it": "Centralina motore"},
    "sys_valve_control":           {"symbol": "sys_valve_control",          "label_en": "Valve control",          "label_it": "Distribuzione"},
    "sys_starting_charging":       {"symbol": "sys_starting_charging",      "label_en": "Starting / charging",    "label_it": "Avviamento / ricarica"},
    "sys_security_immobiliser":    {"symbol": "sys_security_immobiliser",   "label_en": "Security / immobiliser", "label_it": "Antifurto / immobilizzatore"},
    "sys_infotainment_cluster":    {"symbol": "sys_infotainment_cluster",   "label_en": "Infotainment / cluster", "label_it": "Infotainment / quadro"},
    "sys_lighting":                {"symbol": "sys_lighting",               "label_en": "Lighting",               "label_it": "Illuminazione"},
    "sys_wheels_tpms":             {"symbol": "sys_wheels_tpms",            "label_en": "Wheels / TPMS",          "label_it": "Ruote / TPMS"},
    "sys_restraints":              {"symbol": "sys_restraints",             "label_en": "Restraints",             "label_it": "Sistemi di ritenuta"},

    # -- 12 symptoms --------------------------------------------------
    "symptom_drives_normally": {"symbol": "symptom_drives_normally", "label_en": "Drives normally",  "label_it": "Guida normalmente"},
    "symptom_mil_on":          {"symbol": "symptom_mil_on",          "label_en": "Warning lamp on",   "label_it": "Spia accesa"},
    "symptom_fuel_smell":      {"symbol": "symptom_fuel_smell",      "label_en": "Fuel smell",        "label_it": "Odore di carburante"},
    "symptom_hard_start":      {"symbol": "symptom_hard_start",      "label_en": "Hard to start",      "label_it": "Difficoltà di avviamento"},
    "symptom_rough_idle":      {"symbol": "symptom_rough_idle",      "label_en": "Rough idle",         "label_it": "Minimo irregolare"},
    "symptom_hesitation":      {"symbol": "symptom_hesitation",      "label_en": "Hesitation",         "label_it": "Esitazione"},
    "symptom_loss_of_power":   {"symbol": "symptom_loss_of_power",   "label_en": "Loss of power",      "label_it": "Perdita di potenza"},
    "symptom_hard_to_refuel":  {"symbol": "symptom_hard_to_refuel",  "label_en": "Hard to refuel",     "label_it": "Difficoltà di rifornimento"},
    "symptom_noise":           {"symbol": "symptom_noise",           "label_en": "Noise",              "label_it": "Rumore"},
    "symptom_vibration":       {"symbol": "symptom_vibration",       "label_en": "Vibration",          "label_it": "Vibrazione"},
    "symptom_warning_message": {"symbol": "symptom_warning_message", "label_en": "Warning message",    "label_it": "Messaggio di avviso"},
    "symptom_other":           {"symbol": "symptom_other",           "label_en": "Other",              "label_it": "Altro"},

    # -- 5 statuses ------------------------------------------------------
    "status_active":              {"symbol": "status_active",              "label_en": "Active",               "label_it": "Attivo"},
    "status_cleared_unverified":  {"symbol": "status_cleared_unverified",  "label_en": "Cleared, unverified",  "label_it": "Azzerato, non verificato"},
    "status_verified":            {"symbol": "status_verified",            "label_en": "Verified",             "label_it": "Verificato"},
    "status_stale":                {"symbol": "status_stale",               "label_en": "Stale",                "label_it": "Obsoleto"},
    "status_unknown":              {"symbol": "status_unknown",             "label_en": "Unknown",              "label_it": "Sconosciuto"},

    # -- 3 priorities ------------------------------------------------------
    "priority_p1": {"symbol": "priority_p1", "label_en": "Priority 1", "label_it": "Priorità 1"},
    "priority_p2": {"symbol": "priority_p2", "label_en": "Priority 2", "label_it": "Priorità 2"},
    "priority_p3": {"symbol": "priority_p3", "label_en": "Priority 3", "label_it": "Priorità 3"},

    # -- misc ------------------------------------------------------------
    "tools":      {"symbol": "tools",      "label_en": "Tools",      "label_it": "Attrezzi"},
    "parts":      {"symbol": "parts",      "label_en": "Parts",      "label_it": "Ricambi"},
    "camera":     {"symbol": "camera",     "label_en": "Camera",     "label_it": "Fotocamera"},
    "microphone": {"symbol": "microphone", "label_en": "Microphone", "label_it": "Microfono"},
    "photo":      {"symbol": "photo",      "label_en": "Photo",      "label_it": "Foto"},
    "pdf":        {"symbol": "pdf",        "label_en": "PDF",        "label_it": "PDF"},
    "label":      {"symbol": "label",      "label_en": "Label",      "label_it": "Etichetta"},
}

#: The step/system/symptom/status/priority key *lists* above, exposed so
#: cuore/tests/check_icons_i18n.py (and anything else) can assert coverage
#: without re-deriving them from ICONS' insertion order.
STEP_KEYS: tuple[str, ...] = (
    "step_start", "step_complaint", "step_verdict", "step_scan",
    "step_understand", "step_test", "step_hypothesis", "step_plan",
    "step_repair", "step_verify", "step_document", "step_release",
)
STATUS_KEYS: tuple[str, ...] = (
    "status_active", "status_cleared_unverified", "status_verified",
    "status_stale", "status_unknown",
)
PRIORITY_KEYS: tuple[str, ...] = ("priority_p1", "priority_p2", "priority_p3")

_SIZE_PX = {"s": 20, "m": 28, "l": 40}


def icon(key: str, size: str = "m", label: Optional[str] = None) -> Any:
    """Render one pictogram as an inline ``<span class="ico ico-NN">``.

    Falls back to a bare, still-accessible span for an unknown key or size
    rather than raising -- this is a template global, and (per the house
    rule other ``*_globals`` modules follow) must never 500 a page.
    """
    px = _SIZE_PX.get(size, _SIZE_PX["m"])
    entry = ICONS.get(key)
    if entry is None:
        safe_label = escape(label or key)
        return Markup(
            f'<span class="ico ico-{px}" role="img" aria-label="{safe_label}"></span>'
        )
    symbol = entry["symbol"]
    text = label or entry.get("label_en") or key
    safe_label = escape(text)
    return Markup(
        f'<span class="ico ico-{px}">'
        f'<svg role="img" aria-label="{safe_label}">'
        f'<use href="{static_url("icons.svg")}#i-{symbol}"></use>'
        f'</svg></span>'
    )


def _register(templates: Any) -> None:
    templates.env.globals["icon"] = icon


for _module_name in ("routes", "service_routes", "drivetrain_routes", "timeline_routes"):
    try:
        _mod = importlib.import_module(f".{_module_name}", __package__)
        _tmpl = getattr(_mod, "templates", None) or getattr(_mod, "_shared_templates", None)
        if _tmpl is not None:
            _register(_tmpl)
    except Exception:  # noqa: BLE001 -- import-time side effect, must never raise
        pass


__all__ = ["ICONS", "STEP_KEYS", "STATUS_KEYS", "PRIORITY_KEYS", "icon"]
