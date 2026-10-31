"""Per-platform fault-code text that MES itself printed in its scan logs.

Naming only, never a source for writes. A code gets text here only if a plain
MES SCAN log printed text beside that exact code (and failure type). Nothing is
generalised across failure types or invented. MES's encrypted database is never
touched; only the logs CUORE already parses through ``mes_bridge``.

Stored at ``<state_dir>/knowledge/<platform>/dtc_text.json`` (vendor-derived,
so it stays out of git). Precedence: manufacturer > mes_display > forum
(docs/design/KNOWLEDGE_LIBRARY.md).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from ..live.config import state_dir

PRECEDENCE = {"manufacturer": 3, "mes_display": 2, "forum": 1}
SOURCE_TAG = {"manufacturer": "Manufacturer", "mes_display": "MES display", "forum": "Forum"}
_VIN_PLATFORM = (("ZASF", "949"),)  # Alfa Romeo Stelvio
_CODE = re.compile(r"^([PBCU][0-9A-F]{4})(?:-([0-9A-F]{2}))?$")


def platform_of(vin: str) -> str:
    v = (vin or "").upper()
    for pre, plat in _VIN_PLATFORM:
        if v.startswith(pre):
            return plat
    return ""


def path_for(platform: str = "949") -> Path:
    return state_dir() / "knowledge" / platform / "dtc_text.json"


def load(platform: str = "949") -> list[dict[str, Any]]:
    try:
        d = json.loads(path_for(platform).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _better(new: dict, old: Optional[dict]) -> bool:
    return old is None or PRECEDENCE.get(new["source_kind"], 0) > PRECEDENCE.get(old["source_kind"], 0)


def merge(rows: list[dict[str, Any]], platform: str = "949") -> list[dict[str, Any]]:
    """Merge rows by (code, ftb, module). Higher source precedence replaces text;
    equal precedence keeps the first text and widens first/last seen."""
    idx = {(r["code"], r["failure_type"], r["module"]): r for r in load(platform)}
    for r in rows:
        k = (r["code"], r["failure_type"], r["module"])
        old = idx.get(k)
        if old is None or PRECEDENCE.get(r["source_kind"], 0) > PRECEDENCE.get(old["source_kind"], 0):
            idx[k] = dict(r)
        elif r["source_kind"] == old["source_kind"] and r["text"] == old["text"]:
            old["first_seen"] = min(old["first_seen"], r["first_seen"])
            if r["last_seen"] >= old["last_seen"]:
                old["last_seen"], old["source_log"] = r["last_seen"], r["source_log"]
    return sorted(idx.values(), key=lambda r: (r["code"], r["failure_type"], r["module"]))


def rows_from_scan_text(text: str, name: str, timestamp: str) -> list[dict[str, Any]]:
    """Rows for every code the scan text printed text beside. Pure; used by the builder and tests."""
    from . import mes_bridge
    log = mes_bridge.scan.parse_scan_text(text, name=name, timestamp=timestamp)
    out = []
    for e in log.entries:
        for d in e.dtcs:
            if not d.description.strip():
                continue
            out.append({"code": d.code, "failure_type": d.ftb or "", "module": e.name,
                        "text": d.description.strip(), "first_seen": timestamp, "last_seen": timestamp,
                        "source_log": name, "source_kind": "mes_display"})
    return out


def build(platform: str = "949") -> dict[str, Any]:
    """Scan every real (non-simulated, MES-root) SCAN log for this platform; write dtc_text.json."""
    from . import mes_bridge
    seen, rows, logs = set(), [], 0
    for e in mes_bridge.CATALOG.select(kind="scan", limit=None):
        if e.simulation or e.provenance:
            continue
        try:
            text = mes_bridge.encoding.read_log_text(e.path).text
            parsed = mes_bridge.scan.parse_scan_text(text, name=e.name, timestamp=e.timestamp)
            vin = parsed.vin
            log_rows = rows_from_scan_text(text, e.name, e.timestamp)
            log_seen = {d.code for en in parsed.entries for d in en.dtcs}
        except Exception:  # noqa: BLE001
            continue
        if platform_of(vin or e.vin) != platform:
            continue
        logs += 1
        rows += log_rows
        seen |= log_seen
    merged = merge(rows, platform)
    p = path_for(platform)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(merged, indent=1, ensure_ascii=False), encoding="utf-8")
    return coverage(platform) | {"logs_used": logs, "distinct_codes_seen": len(seen),
                                 "codes_seen_without_text": sorted(seen - {r["code"] for r in merged})}


def lookup(code: str, module: str = "", platform: str = "949") -> Optional[dict[str, Any]]:
    """Text MES printed for exactly this code (full code-FTB, or bare code: the rows' failure types
    are only used when one text is shared by all of them). None when MES never printed text."""
    m = _CODE.match((code or "").strip().upper())
    if not m:
        return None
    base, ftb = m.group(1), m.group(2)
    rows = [r for r in load(platform) if r["code"] == base and (not ftb or r["failure_type"] == ftb)]
    if module:
        mm = [r for r in rows if module.lower() in r["module"].lower()]
        rows = mm or rows
    if not rows:
        return None
    best = max(PRECEDENCE.get(r["source_kind"], 0) for r in rows)
    rows = [r for r in rows if PRECEDENCE.get(r["source_kind"], 0) == best]
    texts = {r["text"] for r in rows}
    if len(texts) != 1:  # bare code with differing failure-type texts: do not pick one
        return None
    r = sorted(rows, key=lambda r: r["last_seen"])[-1]
    return {"description": r["text"], "source_kind": r["source_kind"],
            "source_tag": SOURCE_TAG.get(r["source_kind"], r["source_kind"]),
            "source_log": r["source_log"], "last_seen": r["last_seen"]}


def coverage(platform: str = "949") -> dict[str, Any]:
    rows = load(platform)
    codes = {r["code"] for r in rows}
    return {"platform": platform, "entries": len(rows), "codes_with_text": len(codes)}
