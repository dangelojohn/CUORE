"""Sensor health: one colour per physical sensor, from evidence already on disk.

green  answered, no current code, value in range (or no range to judge by)
orange a current code names it, a channel errored, or a value is outside its range
red    its module does not answer, every channel returned no data, or a current
       code of an open / short / no-signal / circuit type names it
grey   never read, or not readable with the current cable / no CUORE channel

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
from . import element_locations
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
    return {c.id: {"name": c.name, "unit": c.unit} for c in available_channels()}


# --- registry -----------------------------------------------------------------

_CONF_TO_RANK = {"SOURCED": "single-source", "INFERRED": "inferred", "UNKNOWN": ""}


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
                ev.append({"at": s.get("at") or "", "channel": ch, "value": v["value"],
                           "unit": v.get("unit", ""), "error": None, "src": "snapshot"})
    for c in _read_jsonl(CHECKS_FILE):
        if c.get("vin") and vin and str(c["vin"]).upper() != vin.upper():
            continue
        at = c.get("at") or ""
        for ch, v in (c.get("values") or {}).items():
            if v is not None:
                ev.append({"at": at, "channel": ch, "value": v, "unit": "", "error": None, "src": "check"})
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
            if (last.get("at") or "") >= (out.get(m, {}).get("at") or ""):
                out[m] = {"state": "answered" if ok else "no_answer",
                          "why": "" if ok else "every channel read from it failed",
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


def _scan_evidence() -> list[dict[str, Any]]:
    """Later-evidence source (a): every MES SCAN log, parsed with the mes
    package's own parser -> [{"at","label","modules": {abbrev: {full codes}}}]."""
    out: list[dict[str, Any]] = []
    try:
        from . import mes_bridge
        from mes import scan as scan_mod
        for entry in mes_bridge.CATALOG.select(kind="scan"):
            if entry.parse_error:
                continue
            try:
                log = scan_mod.load_scan(entry.path, timestamp=entry.timestamp)
            except Exception:  # noqa: BLE001
                continue
            mods: dict[str, set[str]] = {}
            for e in log.modules:
                mods.setdefault(e.abbrev, set()).update(d.full for d in e.dtcs)
            out.append({"at": str(entry.timestamp or "").replace(" ", "T"),
                        "label": Path(str(entry.path)).stem, "modules": mods})
    except Exception:  # noqa: BLE001 - no MES logs: no evidence from them
        pass
    return out


def _uds_evidence() -> list[dict[str, Any]]:
    """Source (c): CUORE UDS module-DTC reads recorded in observations.jsonl
    that answered (no error) and list the module's codes."""
    out: list[dict[str, Any]] = []
    for o in _read_jsonl("observations.jsonl"):
        d = o.get("data") or {}
        if o.get("kind") != "module_dtcs" or d.get("error") or not d.get("ecu")                 or not isinstance(d.get("codes"), list):
            continue
        out.append({"at": str(o.get("at") or ""), "label": "a CUORE module DTC read",
                    "modules": {str(d["ecu"]): set(d["codes"])}})
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
    evidence = _scan_evidence() + _uds_evidence()
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
    hist = _history_ranges(events)
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
                errored.append(f"{ch} ({e['error']})")
                continue
            rng = None
            t = tech.get((r["id"], ch))
            if t:
                rng = {"min": t.get("min"), "max": t.get("max"), "unit": t.get("unit", ""),
                       "source": f"{t['source']} (entered by {t.get('by') or 'unknown'}, {str(t.get('at') or '')[:10]})",
                       "kind": "technician"}
            elif ch in hist:
                rng = {**hist[ch], "unit": e["unit"] or meta.get(ch, {}).get("unit", "")}
            inr: Optional[bool] = None
            if rng is not None and _is_num(e["value"]):
                inr = not ((rng["min"] is not None and e["value"] < rng["min"])
                           or (rng["max"] is not None and e["value"] > rng["max"]))
            values.append({"channel": ch, "label": meta.get(ch, {}).get("name", ch), "value": e["value"],
                           "unit": e["unit"] or meta.get(ch, {}).get("unit", ""), "read_at": e["at"] or None,
                           "range": rng, "in_range": inr})
        last_read = max((v["read_at"] for v in values if v["read_at"]), default=None)

        status = "grey"
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
            elif not values and chans and len(errored) == len(chans):
                reasons.append("Every channel returned no data: " + "; ".join(errored) + ".")
                status = "red"
            elif not values:
                reasons.append("Never read: no value for any of its channels is on record yet.")
            else:
                status = "green"
                if errored:
                    reasons.append("Some channels returned no data: " + "; ".join(errored) + ".")
                    status = "orange"
                for v in values:
                    if v["in_range"] is False:
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
        out_rows.append({**r, "status": status, "stale": stale, "reasons": reasons, "last_read": last_read,
                         "values": values, "codes": sensor_codes})

    checked_at = max((c.get("at") for c in checks if c.get("at")), default=None)
    return {"vin": vin, "checked_at": checked_at, "sensors": out_rows, "counts": counts,
            "unplaced": [r["id"] for r in out_rows if not r.get("zone")]}


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
    return {"ok": True, "refused": False, **rec}


__all__ = ["registry", "health", "add_range", "check_all"]
