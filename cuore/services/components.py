"""Electrical components for the Fuses & relays page: switches, motors, actuators, gauges, lamps, modules...

Rows come from ``cuore/data/components_stelvio_2018.json`` (sourced inventory; no part numbers, and an ``area`` / ``side``
only when a source gives one). Nothing here contacts the car.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[1] / "data" / "components_stelvio_2018.json"

# category -> (label, plural, extra search words). Order = legend order.
CATS: dict[str, tuple[str, str, str]] = {
    "fuse": ("Fuse", "Fuses", "fuse"),
    "relay": ("Relay", "Relays", "relay"),
    "switch": ("Switch", "Switches", "switch button"),
    "motor": ("Motor", "Motors", "motor servo"),
    "actuator": ("Actuator", "Actuators", "actuator servo motor"),
    "solenoid_valve": ("Solenoid / valve", "Solenoids and valves", "solenoid valve"),
    "gauge_display": ("Gauge / display", "Gauges and displays", "gauge display cluster instrument screen"),
    "lamp": ("Lamp", "Lamps", "lamp light bulb"),
    "module": ("Control module", "Control modules", "module computer controller unit"),
    "connector": ("Connector", "Connectors", "connector plug socket"),
    "ground": ("Ground", "Grounds", "ground earth"),
    "pump": ("Pump", "Pumps", "pump"),
    "heater": ("Heater", "Heaters", "heater heating element"),
    "horn_speaker": ("Horn / speaker", "Horns and speakers", "horn speaker sound audio"),
    "antenna": ("Antenna", "Antennas", "antenna aerial"),
    "sensor": ("Sensor", "Sensors", "sensor"),
    "other": ("Other", "Other", "other"),
}
AREA_WORDS = {"engine_bay": "engine bay", "rear_left_wheel_well": "rear left wheel well", "underbody": "underbody"}
# area -> view area key used by the car drawing
AREA_VIEW = {"engine_bay": "engine", "rear_left_wheel_well": "rear", "underbody": "underbody"}
_SYN = {"servo": ("motor", "actuator"), "button": ("switch",), "bulb": ("lamp", "light"), "light": ("lamp",),
        "lights": ("lamp",), "gauge": ("gauge", "display", "cluster"), "display": ("gauge", "display"),
        "cluster": ("cluster", "instrument"), "lamps": ("lamp",), "motors": ("motor",), "switches": ("switch",)}


def load() -> list[dict[str, Any]]:
    try:
        rows = json.loads(DATA.read_text(encoding="utf-8")).get("rows") or []
    except (OSError, ValueError):
        return []
    return [r for r in rows if r.get("id") and r.get("name")]


def cat_of(r: dict[str, Any]) -> str:
    return r.get("category") if r.get("category") in CATS else "other"


def area_text(r: dict[str, Any]) -> str:
    a = AREA_WORDS.get(r.get("area") or "", str(r.get("area") or "").replace("_", " "))
    side = r.get("side")
    if a and side:
        return f"{a}, {side} side"
    return a or (f"{side} side (area not sourced)" if side else "")


def source_lines(r: dict[str, Any], plain) -> list[str]:
    out: list[str] = []
    for s in r.get("sources") or []:
        ref, text, kind = str(s.get("ref") or ""), str(s.get("text") or ""), s.get("kind")
        if kind == "mopar_diagram":
            diag = " - ".join(p.replace("-", " ") for p in ref.split("--")[:-1] if p) if "--" in ref else ref
            line = f"Mopar parts diagram: {diag} (part listed as \"{text}\")"
        elif kind == "mes_parameter":
            mod, _, par = ref.partition("/")
            line = (f"MultiEcuScan module list: {mod} is a module on this car" if par == "(module)"
                    else f"MultiEcuScan {mod} parameter: {par}")
        else:
            line = f"CUORE's own fuse and wiring data: {text or ref}"
        out.append(plain(line))
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _hay(r: dict[str, Any]) -> str:
    c = cat_of(r)
    bits = [r.get("name"), CATS[c][0], CATS[c][2], r.get("area") and AREA_WORDS.get(r["area"], r["area"]), r.get("module"),
            r.get("side"), *[s.get("text") for s in r.get("sources") or []], *[s.get("ref") for s in r.get("sources") or []]]
    return re.sub(r"[_\-/]+", " ", " ".join(str(b) for b in bits if b)).lower()


def search(q: str, rows: list[dict[str, Any]], extra_syn: dict[str, tuple[str, ...]] | None = None) -> list[dict[str, Any]]:
    words = [w for w in re.sub(r"\s+", " ", (q or "").strip().lower()).split(" ") if w]
    if not words:
        return []
    syn = {**(extra_syn or {}), **_SYN}
    out = []
    for r in rows:
        h = _hay(r)
        if all(w in h or any(s in h for s in syn.get(w, ())) for w in words):
            out.append(r)
    return out


def photo_terms(name: str) -> list[str]:
    """Words of the component's core name (before any bracket), minus filler words."""
    core = re.split(r"[(,]", name)[0].lower()
    stop = {"left", "right", "the", "of", "and", "unit", "module", "control", "named", "only", "by", "front", "rear"}
    return [w for w in re.findall(r"[a-z]{3,}", core) if w not in stop]


def photo_for(name: str, cache: dict[str, Any], exclude_placeholders: bool = False) -> Any:
    """A catalogue photo only when the catalogue part's NAME contains every core word of the component's name."""
    terms = photo_terms(name)
    key = " ".join(terms)
    if key not in cache:
        hit = None
        if len(terms) >= 1:
            try:
                from . import component_images
                for h in component_images.images_for(terms, limit=3, exclude_placeholders=exclude_placeholders):
                    if all(t in str(h.get("name") or "").lower() for t in terms):
                        hit = {"url": h["photo_url"], "href": h["part_url"], "name": h["name"]}
                        break
            except Exception:  # noqa: BLE001
                hit = None
        cache[key] = hit
    return cache[key]
