"""Field-quality early warning (prototype): anonymised pattern rows from local cases.

Pure and offline: reads the local case store (one row per closed job), builds
categorical rows with no VIN, customer, plate, name or free text, applies the
minimum-cohort rule, and holds the consent flag. Nothing is ever sent; the only
output is the JSON the page offers for download. See docs/design/FIELD_QUALITY_FEED.md.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- puts `mes` on sys.path
from ..live import config as live_config

SCHEMA = "cuore.field_quality/1"
DEFAULT_MIN_COHORT = 3
COMEBACK_DAYS = 30
SETTINGS_FILE = "field_quality.json"

_PLATFORM = {"stelvio": "949", "giulia": "952"}   # platform codes on record in CUORE; else the model name
_YEAR = {c: 2010 + i for i, c in enumerate("ABCDEFGHJKLMNPRSTVWXY")}
_YEAR.update({str(d): 2030 + d - 1 for d in range(1, 10)})
_PART_RX = re.compile(r"^[A-Z0-9][A-Z0-9\-]{4,19}$")
_OUT = ("fail", "out of", "high", "low", "bad", "short", "open", "weak", "leak", "stuck")
_IN = ("pass", "ok", "good", "normal", "in range", "within")


# --- consent ---------------------------------------------------------------

def _path():
    return live_config.state_dir() / SETTINGS_FILE


def settings() -> dict[str, Any]:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            d = {}
    except (OSError, ValueError):
        d = {}
    try:
        mc = max(2, int(d.get("min_cohort", DEFAULT_MIN_COHORT)))
    except (TypeError, ValueError):
        mc = DEFAULT_MIN_COHORT
    return {"sharing": d.get("sharing") is True, "min_cohort": mc, "changed": d.get("changed", "")}


def set_sharing(on: bool) -> dict[str, Any]:
    s = settings()
    s.update(sharing=bool(on), changed=datetime.now().strftime("%Y-%m-%d"))
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return s


# --- helpers ----------------------------------------------------------------

def _dt(text: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(text)[:19])
    except (ValueError, TypeError):
        return None


def _split(code: str) -> tuple[str, str]:
    base, _, ft = code.strip().upper().partition("-")
    return base, ft or "-"


def _year(vin: str) -> str:
    v = (vin or "").upper()
    return str(_YEAR[v[9]]) if len(v) >= 10 and v[9] in _YEAR else "unknown"


def _signature(tests: list[dict[str, Any]]) -> str:
    out = inn = 0
    for t in tests or []:
        r = str((t or {}).get("result") or "").lower()
        if any(w in r for w in _OUT):
            out += 1
        elif any(w in r for w in _IN):
            inn += 1
    if not out and not inn:
        return "no readings categorised"
    return f"{out} out of band, {inn} in band"


def _fix(case: dict[str, Any]) -> str:
    if case.get("outcome") != "fixed":
        return "not fixed / unresolved"
    parts = sorted({str(p.get("part_no", "")).strip().upper()
                    for p in (case.get("parts_used") or []) + (case.get("parts_fitted") or [])
                    if isinstance(p, dict)})
    parts = [p for p in parts if _PART_RX.match(p)]
    return "part " + "+".join(parts) if parts else "fixed, part not recorded"


def _proven(case: dict[str, Any]) -> bool:
    return case.get("outcome") == "fixed" and (
        case.get("verification_state") == "verified clean" or bool(case.get("verified_by")))


def _comeback(case: dict[str, Any], all_cases: list[dict[str, Any]], now: datetime) -> str:
    if case.get("outcome") != "fixed":
        return "unknown"
    closed = _dt(case.get("closed"))
    if closed is None:
        return "unknown"
    mine = {_split(c)[0] for c in case.get("codes") or []}
    for o in all_cases:
        if o is case or o.get("vin") != case.get("vin"):
            continue
        opened = _dt(o.get("opened"))
        if opened and closed < opened <= closed + timedelta(days=COMEBACK_DAYS) \
                and mine & {_split(c)[0] for c in o.get("codes") or []}:
            return "yes"
    return "no" if now - closed > timedelta(days=COMEBACK_DAYS) else "unknown"


# --- rows -------------------------------------------------------------------

def build_rows(cases: list[dict[str, Any]], min_cohort: int = DEFAULT_MIN_COHORT,
               now: Optional[datetime] = None) -> dict[str, Any]:
    """Anonymised pattern rows. VINs are used only to count distinct cars and are never kept."""
    now = now or datetime.now()
    groups: dict[tuple, dict[str, Any]] = {}
    pool: set[str] = set()
    for c in cases:
        vin = str(c.get("vin") or "")
        pool.add(vin)
        model = str(c.get("model") or "").lower()
        platform = _PLATFORM.get(model, model if model and model != "unknown" else "unknown")
        sig, fix, proven, cb = _signature(c.get("tests") or []), _fix(c), _proven(c), _comeback(c, cases, now)
        for code in c.get("codes") or []:
            base, ft = _split(str(code))
            key = (platform, _year(vin), "unknown", base, ft, sig)
            g = groups.setdefault(key, {"vins": set(), "cases": 0, "proven": 0, "fixes": {},
                                        "cb": {"yes": 0, "no": 0, "unknown": 0}})
            g["vins"].add(vin)
            g["cases"] += 1
            g["proven"] += proven
            g["cb"][cb] += 1
            f = g["fixes"].setdefault(fix, {"fix": fix, "cases": 0, "proven": 0})
            f["cases"] += 1
            f["proven"] += proven
    rows = []
    for (platform, year, market, base, ft, sig), g in groups.items():
        cars = len(g["vins"])
        rows.append({
            "platform": platform, "model_year": year, "market": market, "dtc": base, "failure_type": ft,
            "readings_signature": sig, "cars": cars, "cases": g["cases"], "proven_fixes": g["proven"],
            "comebacks_30d": dict(g["cb"]),
            "fixes": sorted(g["fixes"].values(), key=lambda f: (-f["proven"], -f["cases"], f["fix"])),
            "is_pattern": cars >= min_cohort,
            "status": "pattern" if cars >= min_cohort else "single case, not a pattern yet" if cars == 1
                      else f"{cars} cars, below the minimum of {min_cohort}",
        })
    rows.sort(key=lambda r: (not r["is_pattern"], -r["proven_fixes"], -r["cars"], r["dtc"]))
    return {"rows": rows, "cars_in_pool": len(pool), "min_cohort": min_cohort,
            "patterns": sum(r["is_pattern"] for r in rows)}


def load_cases() -> list[dict[str, Any]]:
    from mes import cases as cases_mod
    return cases_mod.load()


def view() -> dict[str, Any]:
    s = settings()
    v = build_rows(load_cases(), s["min_cohort"])
    v["sharing"] = s["sharing"]
    return v


def export() -> dict[str, Any]:
    """The feed. Sharing off: no rows. Sharing on: pattern rows only (cars >= minimum cohort)."""
    s = settings()
    base = {"schema": SCHEMA, "generated": datetime.now().strftime("%Y-%m-%d"),
            "min_cohort": s["min_cohort"], "sharing": "on" if s["sharing"] else "off"}
    if not s["sharing"]:
        return {**base, "message": "sharing is off", "rows": []}
    v = build_rows(load_cases(), s["min_cohort"])
    rows = [{k: r[k] for k in ("platform", "model_year", "market", "dtc", "failure_type", "readings_signature",
                               "cars", "cases", "proven_fixes", "comebacks_30d", "fixes")}
            for r in v["rows"] if r["is_pattern"]]
    return {**base, "message": "", "rows": rows}
