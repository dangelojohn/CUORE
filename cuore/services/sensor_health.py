"""Sensor health: one colour per physical sensor, from evidence already on disk.

green  answered, no current code, value in range (or no range to judge by)
orange a current code names it, or a value is outside its range
red    the last full scan says its module does not answer, or a current code
       of an open / short / no-signal / circuit type names it
grey   never read, no channel answered this time, the car gives no data for its
       channels, or not readable with the current cable / no CUORE channel

A channel that fails is a fact about the READ, not the sensor: "no data" means
the car does not offer that value, a timeout means it was not answered this
time. Neither colours a sensor orange or red; both are listed as reasons.

Read-only for the car except :func:`check_all`, which runs one sweep through the
EXISTING live layer (``cuore.live.ops.live_session_*``) and so inherits its
guards (refuses while MultiEcuScan is connected or another session holds the
adapter; only CAN-C channels; never clears anything).

Ranges come from exactly two places, each labelled with its source:
  1. technician-entered ``sensor_ranges.jsonl`` (source text required);
  2. this car's own history (2nd-98th percentile, >= 30 numeric samples).
Nothing else is ever used as a range.
"""

from __future__ import annotations

import json
import math
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..live import config as _config
from . import cache, element_locations
from .errors import BadRequest

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "sensors_stelvio_2018.json"
CHECKS_FILE = "sensor_checks.jsonl"
RANGES_FILE = "sensor_ranges.jsonl"
SNAPSHOTS_FILE = "live_snapshots.jsonl"
FULLSCAN_FILE = "fullscan_last.json"
DEFAULT_VIN = "ZASFAKPN5J7B88115"
MIN_HISTORY_SAMPLES = 30
#: A newest read older than this is not "current health": grey, not green.
STALE_AFTER_DAYS = 7
RANK = {"grey": 0, "green": 1, "orange": 2, "red": 3}

#: Failure-type descriptions (mes.dtc FAILURE_TYPES text) that mean the sensor
#: circuit itself is open / shorted / silent.
_RED_PHRASES = ("open circuit", "short circuit", "short to", "no signal", "general electrical failure",
                "circuit resistance", "circuit low", "circuit high", "circuit intermittent")
_MODULE_TOKENS = re.compile(r"\b(ECM|TCM|BCM|IPC|RFHUB|DASM|HALF|ABS|DTCM|EPS|ORC|ESM|ETM|AFLS|PAM)\b")
_MODULE_PREFIX = (("Magneti Marelli IAW", "ECM"), ("Continental ABS", "ABS"))


# --- small file helpers -------------------------------------------------------

def _sd() -> Path:
    return _config.state_dir()


def _read_jsonl(name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for line in (_sd() / name).read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict):
                out.append(o)
    except OSError:
        pass
    return out


def _append(name: str, rec: dict[str, Any]) -> None:
    p = _sd() / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _channel_meta() -> dict[str, dict[str, str]]:
    from ..live.channels import available_channels
    return {c.id: {"name": c.name, "unit": c.unit, "formula": getattr(c, "formula", "") or ""}
            for c in available_channels()}


# Physical plausibility by unit: a decoded value outside this cannot be a real reading.
_PLAUSIBLE = {"bar": (-2.0, 3000.0), "mbar": (0.0, 6000.0), "kpa": (-100.0, 100000.0), "v": (-1.0, 60.0),
              "c": (-60.0, 400.0), "°c": (-60.0, 400.0), "%": (-1.0, 101.0)}
NA_MARK = "raw -32768 = 'not available' marker"


SUSPECT = "suspect - check decoding"


def suspect_reason(channel: str, value: Any, lv: dict[str, Any]) -> str:
    """Cross-check failures on a number that is not a marker: "" when nothing disagrees. ``lv``: latest value
    of every channel. Never changes data or formulas; it only says the number cannot be trusted as decoded."""
    if not _is_num(value):
        return ""
    if channel == "ecm_195b" and value < 0.1:
        return f"raw sensor voltage {value:g} V is under 0.1 V while the module answers"
    if channel in ("ecm_1925", "ecm_1926"):
        # Not percent (the throttle-position cross-check is invalid): shown as an unconfirmed decoding.
        raw = value * (655.35 if channel == "ecm_1925" else 245.76)
        n = int(round(raw))
        return (f"decoding unconfirmed (likely degrees: raw {n} -> {n / 100:.2f} deg); not comparable with "
                "throttle position in %")
    return ""


def invalid_reason(channel: str, value: Any, unit: str = "", formula: str = "") -> str:
    """Why a decoded number is NOT a reading ("" when it may be one).

    The module answers a signed/unsigned 16-bit "not available" marker (signed 0x8000 = -32768, unsigned 0xFFFF)
    when it has no value; after the channel's own scaling that shows up as e.g. -32.767 bar. Also catches values
    no physical quantity of that unit can have (e.g. -31764 mbar). Only plain numbers are judged here.
    """
    if not _is_num(value):
        return ""
    v = float(value)
    f = (formula or "").replace(" ", "")
    if "A*256" in f or "256*A" in f:
        m = re.search(r"/\(?(\d+(?:\.\d+)?)\)?", f)
        d = float(m.group(1)) if m else 1.0
        k = re.search(r"\)-(\d+(?:\.\d+)?)$", f)
        off = float(k.group(1)) if k else 0.0
        tol = 1.5 / d + 1e-9
        for cand in (-32768 / d, 65535 / d, 65535 / d - off):
            if abs(v - cand) <= tol or abs(v + off - cand) <= tol:
                return NA_MARK if cand < 0 else "raw 0xFFFF = 'not available' marker"
    elif v in (-32768.0, -32767.0):
        return NA_MARK
    lo_hi = _PLAUSIBLE.get(str(unit or "").strip().lower())
    if lo_hi and not lo_hi[0] <= v <= lo_hi[1]:
        return f"{v:g} {unit} is not a possible value for this quantity (likely a wrong decode)"
    return ""


# --- read-time re-decode of readings stored before the 2026-10-25 formula fix ------------------------
# ecm_195a / ecm_1956 used to be decoded with a wrong -32768 offset. Stored files are never rewritten; the
# old stored value is inverted to the raw integer (or taken from the matching audit.jsonl reply) and the
# corrected unsigned-mbar formula applied.
FORMULA_FIX_AT = "2026-10-25T23:34:00"
REDECODE_NOTE = "re-decoded from the stored value with the corrected formula"
_REDECODE = {"ecm_195a": ("22195A", lambda v: round((v + 1) * 1000 + 32768)),
             "ecm_1956": ("221956", lambda v: round(v + 32768))}
_audit_cache: dict[str, Any] = {}


def _audit_raws(req: str) -> list[tuple[float, int]]:
    """[(epoch, raw_int)] of successful UDS replies for ``req`` in audit.jsonl (cached by file stat)."""
    p = _sd() / "audit.jsonl"
    try:
        st = p.stat()
        key = f"{p}:{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return []
    if _audit_cache.get("key") != key:
        _audit_cache.clear()
        _audit_cache["key"] = key
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                r = o.get("req")
                raw = str(o.get("raw") or "")
                if o.get("event") != "uds" or o.get("error") or not isinstance(o.get("ts"), (int, float)):
                    continue
                if r not in ("22195A", "221956"):
                    continue
                i = raw.upper().find("62" + r[2:])
                if i < 0 or len(raw) < i + 10:
                    continue
                try:
                    _audit_cache.setdefault(r, []).append((float(o["ts"]), int(raw[i + 6:i + 10], 16)))
                except ValueError:
                    continue
        except OSError:
            pass
    return _audit_cache.get(req, [])


def redecode(channel: str, value: Any, at: str, unit: str = "") -> Optional[tuple[float, str, str]]:
    """(new_value, new_unit, note) for an old stored ecm_195a/ecm_1956 number, else None.

    Only records strictly older than the fix are converted. The raw integer comes from the audit.jsonl reply
    within 10 s of the record when it agrees with the inverted value; otherwise from the inverted value."""
    spec = _REDECODE.get(channel)
    if not spec or not _is_num(value) or not at or at >= FORMULA_FIX_AT:
        return None
    raw = spec[1](float(value))
    src = "stored value"
    try:
        t = datetime.fromisoformat(at)
        t = t.astimezone() if t.tzinfo else t
        t0 = t.timestamp()
        near = [(abs(ts - t0), rw) for ts, rw in _audit_raws(spec[0]) if abs(ts - t0) <= 10 and rw == raw]
        if near:
            src = "raw bytes in audit.jsonl"
    except ValueError:
        pass
    return float(raw), "mbar", f"{REDECODE_NOTE} ({src}, raw {raw})"


# --- registry -----------------------------------------------------------------

_CONF_TO_RANK = {"SOURCED": "single-source", "INFERRED": "inferred", "GENERAL": "", "UNKNOWN": ""}


def _load_rows() -> list[dict[str, Any]]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return [dict(r) for r in data.get("sensors", [])]


def registry(vin: str = DEFAULT_VIN) -> list[dict[str, Any]]:
    """Registry rows, with technician element locations merged in.

    A technician entry for an element only applies when exactly one registry
    row links to that element (a shared element such as the O2 sensors cannot
    say which sensor it meant), and it follows ``element_locations``' own
    outranking rules: it replaces an unknown or lower-confidence location only.
    """
    from ..web.electrical_svg import resolve_zone
    rows = _load_rows()
    try:
        entries = element_locations.latest_for_model(vin)
    except Exception:  # noqa: BLE001 - location overlay is optional
        entries = {}
    per_element: dict[str, int] = {}
    for r in rows:
        if r.get("element_id"):
            per_element[r["element_id"]] = per_element.get(r["element_id"], 0) + 1
    for r in rows:
        eid = r.get("element_id")
        ent = entries.get(eid) if eid else None
        if not ent or per_element.get(eid, 0) != 1:
            continue
        current = {"zone": r.get("zone") or "", "description": r.get("location_source") or "",
                   "source": r.get("location_source") if r.get("zone") else "",
                   "confidence": _CONF_TO_RANK.get(r.get("location_confidence", "UNKNOWN"), "")}
        loc, _prop = element_locations.overlay_location(ent, vin, current, resolve_zone)
        if loc.get("tech_entry"):
            zone = resolve_zone(loc.get("zone"))
            if zone != "other":
                r["zone"] = zone
                r["location_confidence"] = "SOURCED"
                r["location_source"] = (f"technician entry by {loc.get('entered_by') or 'unknown'}: "
                                        f"{loc.get('source') or ''}").strip()
    return rows


# --- technician ranges --------------------------------------------------------

def _model(model_or_vin: str) -> str:
    m = (model_or_vin or "").strip()
    return element_locations.model_key(m) if len(m) == 17 else m


def add_range(model: str, sensor_id: str, channel: str, min: Optional[float], max: Optional[float],
              unit: str, source: str, by: str = "") -> dict[str, Any]:
    """Append a technician-entered range. ``source`` is required."""
    src = (source or "").strip()
    if not src:
        raise BadRequest("a range needs a source (where the numbers came from)")
    if len(src) > 300:
        raise BadRequest("source text is limited to 300 characters")
    row = next((r for r in _load_rows() if r["id"] == sensor_id), None)
    if row is None:
        raise BadRequest(f"unknown sensor {sensor_id!r}")
    if channel not in row.get("channels", []):
        raise BadRequest(f"channel {channel!r} does not belong to sensor {sensor_id!r}")
    for nm, v in (("min", min), ("max", max)):
        if v is not None and not _is_num(v):
            raise BadRequest(f"{nm} must be a finite number")
    if min is None and max is None:
        raise BadRequest("give a min, a max, or both")
    if min is not None and max is not None and min > max:
        raise BadRequest("min is greater than max")
    rec = {"id": uuid.uuid4().hex[:10], "at": _now(), "model_key": _model(model), "sensor_id": sensor_id,
           "channel": channel, "min": min, "max": max, "unit": (unit or "").strip(),
           "source": src, "by": (by or "").strip()[:60]}
    _append(RANGES_FILE, rec)
    return rec


def _tech_ranges(model: str) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for r in _read_jsonl(RANGES_FILE):
        if r.get("model_key") == model and r.get("sensor_id") and r.get("channel"):
            out[(r["sensor_id"], r["channel"])] = r        # later lines win
    return out


# --- history ------------------------------------------------------------------

def _percentile(sorted_vals: list[float], p: float) -> float:
    k = (len(sorted_vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _events(vin: str) -> list[dict[str, Any]]:
    """Every per-channel observation on disk, oldest first:
    {"at","channel","value"|None,"unit","error"|None,"src"}."""
    ev: list[dict[str, Any]] = []
    for s in _read_jsonl(SNAPSHOTS_FILE):
        if s.get("vin") and vin and str(s["vin"]).upper() != vin.upper():
            continue
        for ch, v in (s.get("values") or {}).items():
            if isinstance(v, dict) and v.get("value") is not None:
                e = {"at": s.get("at") or "", "channel": ch, "value": v["value"],
                     "unit": v.get("unit", ""), "error": None, "src": "snapshot", "note": ""}
                rd = redecode(ch, e["value"], e["at"])
                if rd:
                    e["value"], e["unit"], e["note"] = rd
                ev.append(e)
    for c in _read_jsonl(CHECKS_FILE):
        if c.get("vin") and vin and str(c["vin"]).upper() != vin.upper():
            continue
        at = c.get("at") or ""
        for ch, v in (c.get("values") or {}).items():
            if v is not None:
                e = {"at": at, "channel": ch, "value": v, "unit": "", "error": None, "src": "check", "note": ""}
                rd = redecode(ch, v, at)
                if rd:
                    e["value"], e["unit"], e["note"] = rd
                ev.append(e)
        for ch, msg in (c.get("errors") or {}).items():
            ev.append({"at": at, "channel": ch, "value": None, "unit": "", "error": str(msg), "src": "check"})
    ev.sort(key=lambda e: e["at"])
    return ev


def _history_ranges(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    per: dict[str, list[tuple[str, float]]] = {}
    for e in events:
        if e["error"] is None and _is_num(e["value"]):
            per.setdefault(e["channel"], []).append((e["at"], float(e["value"])))
    out: dict[str, dict[str, Any]] = {}
    for ch, pts in per.items():
        if len(pts) < MIN_HISTORY_SAMPLES:
            continue
        vals = sorted(v for _, v in pts)
        dates = sorted(a[:10] for a, _ in pts if a)
        span = f"{dates[0]} to {dates[-1]}" if dates else "dates unknown"
        out[ch] = {"min": _percentile(vals, 0.02), "max": _percentile(vals, 0.98), "unit": "",
                   "source": f"this car's own history (2nd-98th percentile, {len(pts)} samples, {span})",
                   "kind": "history"}
    return out


# --- modules / codes ----------------------------------------------------------

def _fullscan() -> tuple[Optional[str], dict[str, dict[str, Any]]]:
    """(scan time iso or None, {module: {"state","why","active"}})."""
    p = _sd() / FULLSCAN_FILE
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, {}
    at = None
    m = re.search(r"(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$", str(d.get("scan_id") or ""))
    if m:
        yy, mo, dd, hh, mi = m.groups()
        at = f"20{yy}-{mo}-{dd}T{hh}:{mi}:00"
    else:
        try:
            at = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            pass
    mods: dict[str, dict[str, Any]] = {}
    for c in d.get("coverage") or []:
        mod, cat, why = c.get("module"), c.get("category"), c.get("why") or ""
        if not mod:
            continue
        if cat == "answered":
            st = "answered"
        elif cat == "not_reachable":
            st = "needs_cable" if "needs" in why and "cable" in why else "no_answer"
        else:
            st = "unknown"
        mods[mod] = {"state": st, "why": why, "active": c.get("active")}
    return at, mods


def _module_states(vin: str, checks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{module: {"state","why","at","src"}} -- the newer of the last full scan
    and the last sensor check wins, module by module."""
    fs_at, fs = _fullscan()
    out = {m: {"state": v["state"], "why": v["why"], "at": fs_at or "", "src": "the last full scan",
               "active": v.get("active"), "fs_state": v["state"], "fs_at": fs_at or ""}
           for m, v in fs.items()}
    last = None
    for c in checks:
        if c.get("vin") and vin and str(c["vin"]).upper() != vin.upper():
            continue
        last = c
    if last:
        for m, ok in (last.get("modules_answered") or {}).items():
            if not ok and m in out:
                continue                               # silence in a sweep is weaker than a full scan
            if (last.get("at") or "") >= (out.get(m, {}).get("at") or ""):
                out[m] = {"state": "answered" if ok else "not_answered",
                          "why": "" if ok else "every channel read from it failed this time",
                          "at": last.get("at") or "", "src": "the last sensor check",
                          "active": out.get(m, {}).get("active"), "fs_state": out.get(m, {}).get("fs_state"),
                          "fs_at": out.get(m, {}).get("fs_at", "")}
    return out


def _module_of(modules_text: str) -> str:
    t = modules_text or ""
    m = _MODULE_TOKENS.search(t)
    if m:
        return m.group(1)
    for pre, code in _MODULE_PREFIX:
        if pre.lower() in t.lower():
            return code
    return ""


def _load_dtcs(vin: str) -> list[dict[str, Any]]:
    from . import mes_bridge
    return mes_bridge.extract_dtcs(vin=vin).get("dtcs", [])


def _failure_text(code: str) -> str:
    ftb = code.split("-", 1)[1] if "-" in code else ""
    if not ftb:
        return ""
    try:
        from mes import dtc as dtc_mod
        ft = dtc_mod.failure_type(ftb)
        return (ft.text if ft is not None else "") or ""
    except Exception:  # noqa: BLE001
        return ""


#: (path, mtime) -> parsed record, so the 20-odd SCAN logs are parsed once, not on every page view.
_scan_ev_cache: dict[tuple[str, float], Optional[dict[str, Any]]] = {}


def _scan_evidence() -> list[dict[str, Any]]:
    """Later-evidence source (a): every MES SCAN log, parsed with the mes
    package's own parser -> [{"at","label","vin","modules": {abbrev: {full codes}}}].
    ``vin`` is the car the log says it came from ("" when it names none)."""
    out: list[dict[str, Any]] = []
    try:
        from . import mes_bridge
        from mes import scan as scan_mod
        for entry in mes_bridge.CATALOG.select(kind="scan"):
            if entry.parse_error:
                continue
            key = (str(entry.path), entry.mtime)
            if key not in _scan_ev_cache:
                try:
                    log = scan_mod.load_scan(entry.path, timestamp=entry.timestamp)
                except Exception:  # noqa: BLE001
                    _scan_ev_cache[key] = None
                    continue
                mods: dict[str, set[str]] = {}
                for e in log.modules:
                    mods.setdefault(e.abbrev, set()).update(d.full for d in e.dtcs)
                _scan_ev_cache[key] = {
                    "at": str(entry.timestamp or "").replace(" ", "T"),
                    "label": Path(str(entry.path)).stem, "vin": entry.vin or "", "modules": mods}
            if _scan_ev_cache[key] is not None:
                out.append(_scan_ev_cache[key])
    except Exception:  # noqa: BLE001 - no MES logs: no evidence from them
        pass
    return out


def _uds_evidence() -> list[dict[str, Any]]:
    """Source (c): CUORE UDS module-DTC reads recorded in observations.jsonl
    that answered (no error) and list the module's codes."""
    out: list[dict[str, Any]] = []
    for o in cache.recent_observations(10 ** 9, kind="module_dtcs"):
        d = o.get("data") or {}
        if d.get("error") or not d.get("ecu") or not isinstance(d.get("codes"), list):
            continue
        row = {"at": str(o.get("at") or ""), "label": "a CUORE module DTC read",
               "modules": {str(d["ecu"]): set(d["codes"])}}
        if o.get("vin"):                    # an untagged read was of whatever car was on the bench
            row["vin"] = str(o["vin"])
        out.append(row)
    return out


def _superseded_by(code: str, mod: str, last_seen: str, evidence: list[dict[str, Any]]) -> str:
    """Name the newest later evidence in which ``mod`` answered without ``code``."""
    best = None
    for ev in evidence:
        if ev["at"] > last_seen and mod in ev["modules"] and code not in ev["modules"][mod]:
            if best is None or ev["at"] > best["at"]:
                best = ev
    if best is None:
        return ""
    at = best["at"]
    return f"not present in {best['label']} at {at[11:16] or at} on {at[:10]}"


def _current_codes(vin: str, mods: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Codes whose newest occurrence is 'stored', minus those later evidence
    shows the module answered without: a later MES scan log, a CUORE UDS
    module read, or a later clean full scan (fullscan_last.json)."""
    try:
        dtcs = _load_dtcs(vin)
    except Exception:  # noqa: BLE001 - no MES logs / bridge unavailable: no code evidence
        return []
    # Only this car's own reads can show one of its codes gone: a SCAN log of another car (or one
    # naming no VIN), or a UDS read tagged with another VIN, answers for a different vehicle.
    # Entries with no "vin" key are untagged UDS reads.
    evidence = [e for e in _scan_evidence() + _uds_evidence()
                if "vin" not in e or str(e["vin"]).upper() == vin.upper()]
    out: list[dict[str, Any]] = []
    for r in dtcs:
        code = str(r.get("dtc") or "")
        occ = sorted(r.get("occurrences") or [], key=lambda o: str(o.get("timestamp") or ""))
        status = str(occ[-1].get("status") or "") if occ else (r.get("statuses_seen") or [""])[-1]
        last_seen = str(r.get("last_seen") or "").replace(" ", "T")
        modtxt = " ".join(r.get("modules") or [])
        mod = _module_of(modtxt)
        state = status or "unknown"
        by = ""
        if state == "stored" and mod:
            by = _superseded_by(code, mod, last_seen, evidence)
            ms = mods.get(mod)
            if not by and ms and ms.get("fs_state") == "answered" and ms.get("active") == 0                     and (ms.get("fs_at") or "") > last_seen:
                by = f"the full scan at {ms['fs_at'][11:16]} on {ms['fs_at'][:10]} found {mod} with no active codes"
            if by:
                state = "superseded"
        desc = (r.get("descriptions") or [""])[0]
        out.append({"code": code, "module": mod or modtxt, "description": desc, "state": state,
                    "last_seen": last_seen, "failure_type": _failure_text(code), "superseded_by": by})
    return out


def _is_red_code(c: dict[str, Any]) -> bool:
    t = (c.get("failure_type") or "").lower()
    return any(p in t for p in _RED_PHRASES)


def _match_codes(rows: list[dict[str, Any]], codes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {r["id"]: [] for r in rows}
    for c in codes:
        base = c["code"].split("-", 1)[0].upper()
        desc = (c.get("description") or "").lower()
        hit = []
        for r in rows:
            cm = r.get("code_match") or {}
            if base in [x.upper() for x in cm.get("codes", [])] or \
                    (desc and any(k.lower() in desc for k in cm.get("descriptions", []))):
                hit.append(r["id"])
        for sid in hit:
            out[sid].append({**c, "ambiguous_with": len(hit) - 1})
    return out


# --- health -------------------------------------------------------------------

def health(vin: str, now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or datetime.now()
    rows = registry(vin)
    meta = _channel_meta()
    events = _events(vin)
    checks = [c for c in _read_jsonl(CHECKS_FILE) if not c.get("vin") or str(c["vin"]).upper() == vin.upper()]
    mods = _module_states(vin, checks)
    codes = _current_codes(vin, mods)
    matched = _match_codes(rows, codes)
    fm = {ch: m.get("formula", "") for ch, m in meta.items()}
    hist = _history_ranges([e for e in events if e["error"] is not None or not invalid_reason(
        e["channel"], e["value"], e["unit"] or meta.get(e["channel"], {}).get("unit", ""), fm.get(e["channel"], ""))])
    tech = _tech_ranges(_model(vin))

    latest: dict[str, dict[str, Any]] = {}
    for e in events:
        latest[e["channel"]] = e                      # oldest first, so the last one wins

    out_rows: list[dict[str, Any]] = []
    counts = {"green": 0, "orange": 0, "red": 0, "grey": 0}
    for r in rows:
        reasons: list[str] = []
        values: list[dict[str, Any]] = []
        errored: list[str] = []
        chans = r.get("channels") or []
        for ch in chans:
            e = latest.get(ch)
            if e is None:
                continue
            if e["error"] is not None:
                errored.append((ch, str(e["error"])))
                continue
            rng = None
            t = tech.get((r["id"], ch))
            if t:
                rng = {"min": t.get("min"), "max": t.get("max"), "unit": t.get("unit", ""),
                       "source": f"{t['source']} (entered by {t.get('by') or 'unknown'}, {str(t.get('at') or '')[:10]})",
                       "kind": "technician"}
            elif ch in hist:
                rng = {**hist[ch], "unit": e["unit"] or meta.get(ch, {}).get("unit", "")}
            unit = e["unit"] or meta.get(ch, {}).get("unit", "")
            bad = invalid_reason(ch, e["value"], unit, fm.get(ch, ""))
            if bad:
                rng = None
            sus = suspect_reason(ch, e["value"], {c: x["value"] for c, x in latest.items() if x["error"] is None})
            if "wrong decode" in bad:
                sus = bad
            inr: Optional[bool] = None
            if rng is not None and _is_num(e["value"]):
                inr = not ((rng["min"] is not None and e["value"] < rng["min"])
                           or (rng["max"] is not None and e["value"] > rng["max"]))
            values.append({"channel": ch, "label": meta.get(ch, {}).get("name", ch), "value": e["value"],
                           "unit": e["unit"] or meta.get(ch, {}).get("unit", ""), "read_at": e["at"] or None,
                           "range": rng, "in_range": inr, "invalid": bad, "suspect": sus,
                           "redecoded": e.get("note") or ""})
        last_read = max((v["read_at"] for v in values if v["read_at"]), default=None)
        no_data = [f"{ch} ({err})" for ch, err in errored if "no data" in err.lower()]
        timed_out = [f"{ch} ({err})" for ch, err in errored if "no data" not in err.lower()]

        status = "grey"
        no_valid = suspect = False
        if not r.get("readable"):
            reasons.append("Not readable: " + (r.get("readable_note") or "no live channel"))
        else:
            ms = mods.get(r["module"])
            ms_state = ms["state"] if ms else "unknown"
            if ms_state == "no_answer" and last_read and last_read > (ms.get("at") or ""):
                ms_state = "answered"                  # read since the scan that said no
            if ms_state == "no_answer":
                why = f" ({ms['why']})" if ms.get("why") else ""
                reasons.append(f"Module {r['module']} did not answer in {ms['src']}{why}.")
                status = "red"
            elif not values:
                if ms_state == "not_answered":
                    reasons.append(f"Module {r['module']} answered none of its channels in "
                                   f"{ms['src']} ({(ms.get('at') or '')[:16]}).")
                if timed_out:
                    reasons.append("Did not answer this time: " + "; ".join(timed_out)
                                   + ". Run Check all sensors again.")
                if no_data:
                    reasons.append("The car gives no data for: " + "; ".join(no_data)
                                   + ". CUORE cannot read this sensor that way.")
                if not errored:
                    reasons.append("Never read: no value for any of its channels is on record yet.")
            elif (any(v["invalid"] and str(v["unit"]).strip().lower() != "v" for v in values)
                  or any(v["suspect"] for v in values)):
                # a primary channel (the sensor's own quantity, not a raw-voltage helper) is unusable, or a
                # cross-check disagrees: never green. Raw "V" channels that are only marked invalid fall through.
                prim = [v for v in values if v["invalid"] and str(v["unit"]).strip().lower() != "v"]
                no_valid = any("wrong decode" not in v["invalid"] for v in prim)
                suspect = not no_valid
                for v in prim:
                    word = "No valid reading for" if no_valid else "Suspect - check decoding:"
                    reasons.append(f"{word} {v['label']}: {v['invalid']}.")
                for v in values:
                    if v["suspect"] and v not in prim:
                        reasons.append(f"Suspect - check decoding: {v['label']}: {v['suspect']}.")
                        suspect = suspect or not no_valid
                ok_ch = [v["label"] for v in values if not v["invalid"] and not v["suspect"]]
                if ok_ch:
                    reasons.append("Other channels read but do not make the sensor OK: " + ", ".join(ok_ch) + ".")
            elif all(v["invalid"] for v in values):
                reasons.append("No valid reading: the module returned no value ("
                               + "; ".join(f"{v['label']}: {v['invalid']}" for v in values) + ").")
                no_valid = True
            else:
                status = "green"
                for v in values:
                    if v["invalid"]:
                        reasons.append(f"{v['label']}: no valid value ({v['invalid']}); not judged.")
                if no_data:
                    reasons.append("The car gives no data for: " + "; ".join(no_data)
                                   + " (not offered; other channels read).")
                if timed_out:
                    reasons.append("Did not answer this time: " + "; ".join(timed_out)
                                   + " (other channels read).")
                for v in values:
                    if v["in_range"] is False and not v["invalid"]:
                        rg = v["range"]
                        reasons.append(f"{v['label']} = {v['value']:g} {v['unit']} is outside "
                                       f"{rg['min']} to {rg['max']} ({rg['source']}).")
                        status = "orange"
                if status == "green":
                    reasons.append(f"Module {r['module']} answered and {len(values)} channel(s) read.")
                    judged = [v for v in values if v["in_range"] is True]
                    if judged:
                        reasons.append(f"{len(judged)} value(s) inside their range.")
                    else:
                        reasons.append("No range on record, so the values are not judged.")

        stale = False
        if r.get("readable") and status in ("green", "orange") and last_read:
            try:
                age = (now - datetime.fromisoformat(last_read)).days
            except ValueError:
                age = 0
            if age > STALE_AFTER_DAYS:
                stale, status = True, "grey"
                reasons = [f"Last read {last_read[:10]} ({age} days ago): it read OK then, but that is not "
                           "current health — run Check all sensors."]

        sensor_codes = []
        for c in matched.get(r["id"], []):
            sensor_codes.append({"code": c["code"], "module": c["module"], "description": c["description"],
                                 "state": c["state"],
                                 **({"superseded_by": c["superseded_by"]} if c.get("superseded_by") else {})})
            if c["state"] == "superseded":
                reasons.append(f"Code {c['code']} was stored earlier but is {c['superseded_by']}.")
            if c["state"] != "stored":
                continue                               # cleared / superseded: shown, not coloured
            red = _is_red_code(c)
            txt = f"Code {c['code']} ({c['description']}) is stored"
            if c.get("failure_type"):
                txt += f"; failure type: {c['failure_type']}"
            if c.get("ambiguous_with"):
                txt += (f"; its text matches {c['ambiguous_with'] + 1} sensors of this kind and does not say which")
            reasons.append(txt + ".")
            if RANK["red" if red else "orange"] > RANK[status]:
                status = "red" if red else "orange"
        counts[status] += 1
        out_rows.append({**r, "status": status, "stale": stale, "no_valid": no_valid, "suspect": suspect, "reasons": reasons,
                         "last_read": last_read,
                         "values": values, "codes": sensor_codes})

    checked_at = max((c.get("at") for c in checks if c.get("at")), default=None)
    return {"vin": vin, "checked_at": checked_at, "sensors": out_rows, "counts": counts,
            "unplaced": [r["id"] for r in out_rows if not r.get("zone")]}


# --- every saved reading, for comparing checks -----------------------------------

def _parts(value: Any) -> list[tuple[str, Any]]:
    """A multi-part value ({"lambda": .., "current_mA": ..}) becomes one entry per part."""
    if isinstance(value, dict):
        return [(str(k), v) for k, v in value.items()]
    return [("", value)]


def readings(vin: str) -> dict[str, Any]:
    """Every value and error from every saved sensor check, oldest check first.

    {"checks": [at, ...], "rows": [{"at","sensor_ids","sensors","channel","part","name",
    "unit","value","error"}, ...]} -- one row per channel part per check. Nothing is
    judged here: this is the raw record a mechanic compares and exports.
    """
    meta = _channel_meta()
    owners: dict[str, list[dict[str, Any]]] = {}
    for r in _load_rows():
        for ch in r.get("channels") or []:
            owners.setdefault(ch, []).append(r)
    checks = sorted((c for c in _read_jsonl(CHECKS_FILE)
                     if not c.get("vin") or str(c["vin"]).upper() == vin.upper()),
                    key=lambda c: c.get("at") or "")
    rows: list[dict[str, Any]] = []
    for c in checks:
        at = c.get("at") or ""
        items = [(ch, v, None) for ch, v in (c.get("values") or {}).items()]
        items += [(ch, None, str(msg)) for ch, msg in (c.get("errors") or {}).items()]
        for ch, v, err in items:
            own = owners.get(ch, [])
            base = {"at": at, "sensor_ids": [o["id"] for o in own], "sensors": [o.get("label") or o["id"] for o in own],
                    "channel": ch, "name": meta.get(ch, {}).get("name", ch), "unit": meta.get(ch, {}).get("unit", "")}
            if err is not None:
                rows.append({**base, "part": "", "value": None, "error": err})
                continue
            for part, pv in _parts(v):
                rd = redecode(ch, pv, at) if not part else None
                if rd:
                    rows.append({**base, "part": part, "value": rd[0], "unit": rd[1], "error": None, "redecoded": rd[2]})
                else:
                    rows.append({**base, "part": part, "value": pv, "error": None})
    return {"vin": vin, "checks": [c.get("at") or "" for c in checks], "rows": rows}


# --- one read-only sweep --------------------------------------------------------

def check_all(vin: str, timeout_s: float = 30.0, poll_s: float = 0.5) -> dict[str, Any]:
    """One read-only sweep of every readable sensor's channels via the live layer.

    Uses ``ops.live_session_start`` / ``live_snapshot`` / ``live_session_stop``.
    Those refuse (Refused / LinkUnavailable) while MultiEcuScan is connected or
    another live session holds the adapter; this function then returns
    ``{"ok": False, "refused": True, "error": ...}`` and writes nothing.
    Only CAN-C pid/did channels are requested; nothing is cleared or written.
    """
    from ..live import errors as live_errors
    from ..live import ops as live_ops
    from ..live.channels import available_channels

    rows = [r for r in _load_rows() if r.get("readable") and r.get("channels")]
    by_id = {c.id: c for c in available_channels()}
    wanted: list[str] = []
    for r in rows:
        for ch in r["channels"]:
            c = by_id.get(ch)
            if c is None or c.bus != "can_c" or c.kind not in ("pid", "did"):
                continue                               # never CAN-CH / probe / computed
            if ch not in wanted:
                wanted.append(ch)
    at = _now()
    try:
        live_ops.live_session_start(channels=wanted)
    except (live_errors.LiveError, OSError) as exc:
        return {"ok": False, "refused": True, "at": at, "vin": vin, "error": str(exc),
                "values": {}, "errors": {}, "modules_answered": {}}
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    try:
        deadline = time.monotonic() + max(1.0, timeout_s)
        snap: dict[str, Any] = {}
        while True:
            snap = (live_ops.live_snapshot() or {}).get("channels", {})
            if all(snap.get(ch, {}).get("value") is not None or snap.get(ch, {}).get("last_error")
                   for ch in wanted) or time.monotonic() >= deadline:
                break
            time.sleep(poll_s)
        for ch in wanted:
            s = snap.get(ch) or {}
            if s.get("value") is not None:
                values[ch] = s["value"]
            else:
                errors[ch] = str(s.get("last_error") or f"no reply within {timeout_s:g}s")
    finally:
        try:
            live_ops.live_session_stop()
        except Exception:  # noqa: BLE001 - never mask the sweep result
            pass
    answered: dict[str, bool] = {}
    for r in rows:
        got = [ch for ch in r["channels"] if ch in values]
        tried = [ch for ch in r["channels"] if ch in values or ch in errors]
        if got:
            answered[r["module"]] = True
        elif tried:
            answered.setdefault(r["module"], False)
    rec = {"at": at, "vin": vin, "values": values, "errors": errors, "modules_answered": answered}
    _append(CHECKS_FILE, rec)
    read = sum(1 for r in rows if any(ch in values for ch in r["channels"]))
    return {"ok": True, "refused": False, **rec, "checked": len(rows), "read": read}


__all__ = ["registry", "health", "readings", "add_range", "check_all"]
