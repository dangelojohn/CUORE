"""Derived view: where a catalogue part lives on this car.

Pure: takes the already-loaded catalogue dict and the explicit mapping tables
in ``cuore/data/parts_links_map.json`` (section slug prefixes and part-name
patterns only, no vendor data rows) and returns links to the system, sensor
and fuse pages. Nothing is stored and nothing is inferred beyond those tables;
a section or part no table names is counted as unmatched, never guessed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

MAP_FILE = Path(__file__).resolve().parents[1] / "data" / "parts_links_map.json"
_FUSE_SECTIONS = ("power-distribution-center", "battery-battery-tray")
_map: Optional[dict[str, Any]] = None


def load_map() -> dict[str, Any]:
    global _map
    if _map is None:
        raw = json.loads(MAP_FILE.read_text(encoding="utf-8"))
        raw["_name_sys"] = [(re.compile(r["name"], re.I), r["system"]) for r in raw.get("name_to_systems", [])]
        raw["_name_sen"] = [(re.compile(r["name"], re.I), r["sensors"]) for r in raw.get("name_to_sensors", [])]
        raw["_name_fuse"] = [re.compile(r["name"], re.I) for r in raw.get("name_to_fuses", [])]
        # longest prefix first so the most specific section wins
        raw["_sections"] = sorted(raw.get("sections_to_systems", {}).items(), key=lambda kv: -len(kv[0]))
        _map = raw
    return _map


def _section(slug: str) -> str:
    return (slug or "").split("--", 1)[-1]


def system_for_section(slug: str) -> Optional[str]:
    sec = _section(slug)
    for prefix, key in load_map()["_sections"]:
        if sec.startswith(prefix):
            return key
    return None


def row_links(slug: str, name: str) -> dict[str, Any]:
    """Keys for one catalogue row: ``systems`` (keys), ``sensors`` (ids), ``fuse`` (bool)."""
    m = load_map()
    systems: list[str] = []
    s = system_for_section(slug)
    if s:
        systems.append(s)
    for rx, key in m["_name_sys"]:
        if rx.search(name or "") and key not in systems:
            systems.append(key)
    sensors: list[str] = []
    for rx, ids in m["_name_sen"]:
        if rx.search(name or ""):
            sensors += [i for i in ids if i not in sensors]
    fuse = _section(slug).startswith(_FUSE_SECTIONS) and any(rx.search(name or "") for rx in m["_name_fuse"])
    return {"systems": systems, "sensors": sensors, "fuse": fuse}


def for_part(part: dict[str, Any], vin: str = "", labels: Optional[dict[str, str]] = None,
             sensor_labels: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Links for a part as returned by ``parts_catalog.part``. Hrefs are empty without a VIN."""
    labels, sensor_labels = labels or {}, sensor_labels or {}
    systems: dict[str, str] = {}
    sensors: list[str] = []
    fuse = False
    for a in part.get("appearances") or []:
        r = row_links(a["diagram"].get("slug", ""), a["row"].get("name", ""))
        for k in r["systems"]:
            systems.setdefault(k, a["diagram"].get("section", ""))
        sensors += [i for i in r["sensors"] if i not in sensors]
        fuse = fuse or r["fuse"]
    base = f"/v/{vin}" if vin else ""
    return {
        "systems": [{"key": k, "label": labels.get(k, k.replace("_", " ")), "why": f"catalogue section: {sec}",
                     "href": f"{base}/systems/{k}" if vin else ""} for k, sec in systems.items()],
        "sensors": [{"id": i, "label": sensor_labels.get(i, i), "why": "matched by part name (mapping table)",
                     "href": f"{base}/sensors#sensor-{i}" if vin else ""} for i in sensors],
        "fuses": ([{"label": "Fuses and relays", "why": "fuse or relay type in the power-distribution diagrams",
                    "href": f"{base}/fuses" if vin else ""}] if fuse else []),
    }


def sections_for_system(cat: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Catalogue sections mapped to a system key, with first diagram and part count."""
    out = []
    for sec in cat.get("sections") or []:
        if sec.get("excluded_reason") or system_for_section(sec["slug"]) != key:
            continue
        dids = [d for d in sec.get("diagrams") or [] if d in cat["diagrams"]]
        n = sum(len(cat["diagrams"][d]["parts"]) for d in dids)
        out.append({"slug": sec["slug"], "title": sec["title"], "group": sec.get("group", ""),
                    "diagram_id": dids[0] if dids else "", "diagrams": len(dids), "parts": n})
    return out


def coverage(cat: dict[str, Any]) -> dict[str, Any]:
    """Honest counts over every catalogue row (excluded sections left out)."""
    excl = {s["slug"] for s in cat.get("sections") or [] if s.get("excluded_reason")}
    total = sys_n = sen_n = fuse_n = any_n = 0
    by_sys: dict[str, int] = {}
    for d in cat.get("diagrams", {}).values():
        if d["slug"] in excl:
            continue
        for p in d["parts"]:
            total += 1
            r = row_links(d["slug"], p["name"])
            if r["systems"]:
                sys_n += 1
                for k in r["systems"]:
                    by_sys[k] = by_sys.get(k, 0) + 1
            sen_n += bool(r["sensors"])
            fuse_n += bool(r["fuse"])
            any_n += bool(r["systems"] or r["sensors"] or r["fuse"])
    return {"rows": total, "with_system": sys_n, "with_sensor": sen_n, "with_fuse": fuse_n,
            "with_any": any_n, "unmatched": total - any_n, "by_system": by_sys}
