"""Sensor cross-checks (analytic redundancy): readings that must agree with each other.

Each rule in ``cuore/data/sensor_crosschecks.json`` names two or more channels that measure the
same thing (or physically must agree under a stated condition, e.g. MAP and barometric pressure
with the engine stopped). A pair that disagrees beyond its tolerance flags a suspect sensor or a
decoding error. Result per rule, one of:

  AGREE                 all sides read at the same moment, condition met, spread within tolerance
  DISAGREE              same, spread beyond tolerance (confirmed decodings on every side)
  UNCONFIRMED DECODING  a side's decoding is not confirmed (or is flagged suspect); the numbers
                        are shown with ``would_be`` AGREE/DISAGREE, never as a plain AGREE
  CONDITION NOT MET     the rule's condition (engine off, idle, cold soak) did not hold
  NOT RECORDED          a side or a condition channel was not read at the same moment, or a side
                        is an invalid reading, or the units differ. Never shown as 0 or OK.

Same moment: every reading carries its own time; the readings of one rule must lie within the
rule's ``max_skew_s`` of each other (default ``DEFAULT_MAX_SKEW_S``). A sweep saved in one
sensor_checks / live_snapshots record shares one time. The live cache has no per-channel times,
so a live snapshot is treated as one moment (now).

Read-only: never opens an adapter. The only live-layer touch is the poller's in-memory cache,
and only when a poller already exists and is active.
"""
from __future__ import annotations

import bisect
import json
import math
import re
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "sensor_crosschecks.json"
DEFAULT_MAX_SKEW_S = 5.0
MAX_ANCHORS = 400                   # newest readings of a rule's first side tried when looking for a paired moment
DISAGREE_SHARE = 0.25               # recording: this share of evaluated rows beyond tolerance -> DISAGREE

AGREE, DISAGREE = "AGREE", "DISAGREE"
UNCONFIRMED = "UNCONFIRMED DECODING"
NOT_MET = "CONDITION NOT MET"
NOT_REC = "NOT RECORDED"
ORDER = (DISAGREE, UNCONFIRMED, AGREE, NOT_MET, NOT_REC)
CONFIRMED_CONFIDENCE = {"confirmed", "legislated", "computed"}
MARK = {AGREE: "✓", DISAGREE: "✕", UNCONFIRMED: "?", NOT_MET: "–", NOT_REC: "∅"}
CSS = {AGREE: "agree", DISAGREE: "disagree", UNCONFIRMED: "unconfirmed", NOT_MET: "notmet", NOT_REC: "notrec"}


# --- small helpers ----------------------------------------------------------------

def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _unit_norm(u: Any) -> str:
    s = str(u or "").strip().lower().replace("°", "")
    return s


def _g(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".") if abs(x) < 1000 else f"{x:.0f}"


def _t_epoch(at: Any) -> Optional[float]:
    raw = str(at or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()   # naive = local, as CUORE writes it
    except ValueError:
        return None


def _t_text(t: Optional[float]) -> str:
    return "" if t is None else datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S")


def load_rules(path: Optional[Path] = None) -> dict[str, Any]:
    return json.loads((path or RULES_PATH).read_text(encoding="utf-8"))


class Reading:
    """One value of one channel key at one time."""
    __slots__ = ("t", "value", "unit", "src", "note", "key")

    def __init__(self, key: str, t: float, value: Any, unit: str = "", src: str = "", note: str = "") -> None:
        self.key, self.t, self.value, self.unit, self.src, self.note = key, t, value, unit, src, note


Series = dict[str, list[Reading]]


def _add(series: Series, key: str, t: float, value: Any, unit: str, src: str, note: str = "") -> None:
    """Add a value; a multi-part value (dict) becomes ``key.part`` entries."""
    if isinstance(value, dict):
        for part, pv in value.items():
            if _is_num(pv):
                series.setdefault(f"{key}.{part}", []).append(Reading(f"{key}.{part}", t, pv, unit, src, note))
        return
    if _is_num(value):
        series.setdefault(key, []).append(Reading(key, t, value, unit, src, note))


# --- channel knowledge (units, confidence, validity) ---------------------------------

def _registry() -> dict[str, Any]:
    try:
        from ..live import channels
        return channels.registry()
    except Exception:  # noqa: BLE001 -- the evaluator must work without the live layer
        return {}


def _base(key: str) -> str:
    return re.split(r"[@.]", key, 1)[0]


def _confidence(key: str, reg: dict[str, Any]) -> tuple[bool, str]:
    """(confirmed?, why not). Unknown channels are unconfirmed."""
    ch = reg.get(_base(key))
    if ch is None:
        return False, "channel not in the CUORE channel registry"
    if getattr(ch, "untrusted", False):
        return False, "channel is marked untrusted (decodes to junk on this car)"
    conf = str(getattr(ch, "confidence", "") or "")
    if conf in CONFIRMED_CONFIDENCE:
        return True, ""
    return False, f"decoding {conf or 'unknown'} (not confirmed on this car)"


def _invalid_and_suspect(key: str, value: float, unit: str, reg: dict[str, Any]) -> tuple[str, str]:
    try:
        from . import sensor_health
    except Exception:  # noqa: BLE001
        return "", ""
    base = _base(key)
    ch = reg.get(base)
    formula = getattr(ch, "formula", "") or ""
    inv = sensor_health.invalid_reason(base, value, unit, formula)
    sus = "" if inv else sensor_health.suspect_reason(base, value, {})
    return inv, sus


# --- loading saved readings ---------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict):
                out.append(o)
    except OSError:
        pass
    return out


def _redecode(ch: str, value: Any, at: str) -> tuple[Any, str, str]:
    try:
        from . import sensor_health
        rd = sensor_health.redecode(ch, value, at)
    except Exception:  # noqa: BLE001
        rd = None
    return (rd[0], rd[1], rd[2]) if rd else (value, "", "")


def _vin_ok(rec_vin: Any, vin: str) -> bool:
    return not rec_vin or not vin or str(rec_vin).upper() == vin.upper()


def load_saved(vin: str) -> Series:
    """Every numeric reading on disk for this car, per channel key, oldest first."""
    from ..live import config as live_config
    from . import cache
    sd = Path(live_config.state_dir())
    reg = _registry()
    series: Series = {}
    for rec in _read_jsonl(sd / "live_snapshots.jsonl"):
        t = _t_epoch(rec.get("at"))
        if t is None or not _vin_ok(rec.get("vin"), vin):
            continue
        for ch, v in (rec.get("values") or {}).items():
            if isinstance(v, dict) and "value" in v:
                val, unit = v["value"], v.get("unit", "")
                nv, nu, note = _redecode(ch, val, str(rec.get("at")))
                _add(series, ch, t, nv, nu or unit, "live snapshot", note)
    for rec in _read_jsonl(sd / "sensor_checks.jsonl"):
        t = _t_epoch(rec.get("at"))
        if t is None or not _vin_ok(rec.get("vin"), vin):
            continue
        for ch, val in (rec.get("values") or {}).items():
            nv, nu, note = _redecode(ch, val, str(rec.get("at")))
            unit = nu or getattr(reg.get(ch), "unit", "")
            _add(series, ch, t, nv, unit, "sensor check sweep", note)
    # observations: one DID per record, and per-module PID snapshots (both answers kept)
    try:
        from ..live import readall
        evaluate_formula = readall.eval_formula
    except Exception:  # noqa: BLE001
        evaluate_formula = None
    for o in cache.recent_observations(100000, vin=vin, kind="did"):
        if not str(o.get("stream") or "").startswith("serial"):
            continue
        d = o.get("data") or {}
        t = _t_epoch(o.get("at"))
        cid = f"{str(d.get('ecu') or '').lower()}_{str(d.get('did') or '').lower()}"
        ch = reg.get(cid)
        if t is None or ch is None or d.get("error") or d.get("nrc") or not evaluate_formula:
            continue
        formula = getattr(ch, "formula", "")
        try:
            val = evaluate_formula(formula, [int(b, 16) for b in d.get("bytes") or []])
        except Exception:  # noqa: BLE001 -- undecodable record: skipped, not guessed
            continue
        _add(series, cid, t, val, ch.unit, "saved DID read")
    for o in cache.recent_observations(100000, vin=vin, kind="pids_snapshot"):
        if not str(o.get("stream") or "").startswith("serial"):
            continue
        t = _t_epoch(o.get("at"))
        if t is None:
            continue
        for ecu, pids in ((o.get("data") or {}).get("by_ecu") or {}).items():
            for _pid, p in (pids or {}).items():
                name = (p or {}).get("name")
                if not name:
                    continue
                _add(series, f"{name}@{ecu}", t, p.get("value"), p.get("unit", ""), f"saved PID snapshot ({ecu})")
                if ecu == "18DAF110":                      # the ECM: what the live poller's plain channel is
                    _add(series, name, t, p.get("value"), p.get("unit", ""), "saved PID snapshot (ECM)")
    for lst in series.values():
        lst.sort(key=lambda r: r.t)
    return series


def add_live(series: Series, now: float) -> bool:
    """Append the running live session's cache as one moment at ``now``. False when none is running."""
    try:
        from ..live import poller as poller_mod
        if getattr(poller_mod, "_POLLER", None) is None:
            return False
        snap = poller_mod._POLLER.snapshot()
    except Exception:  # noqa: BLE001
        return False
    if not snap.get("active"):
        return False
    for ch, info in (snap.get("channels") or {}).items():
        if (info or {}).get("last_error"):
            continue                                       # stale value from a failed read
        _add(series, ch, now, (info or {}).get("value"), (info or {}).get("unit", ""), "live session")
    return True


def series_from_recording(rec: dict[str, Any]) -> list[tuple[float, dict[str, Reading]]]:
    """[(time, {key: Reading})] one entry per recorded row (all values of a row share its time)."""
    rows = []
    for row in rec.get("rows") or []:
        t = _t_epoch(row.get("at"))
        if t is None:
            continue
        s: Series = {}
        for ch, v in (row.get("v") or {}).items():
            _add(s, ch, t, v, (rec.get("units") or {}).get(ch, ""), "recording")
        rows.append((t, {k: lst[0] for k, lst in s.items()}))
    return rows


# --- judging one rule at one moment ---------------------------------------------------

def _pick(get, keys: list[str]) -> Optional[Reading]:
    for k in keys:
        r = get(k)
        if r is not None:
            return r
    return None


def _cond_keys(cond: dict[str, Any]) -> list[str]:
    return list(cond.get("channels") or [])


def _side_dict(side: dict[str, Any], r: Optional[Reading], reg: dict[str, Any]) -> dict[str, Any]:
    scale = float(side.get("scale", 1))
    confirmed, why = _confidence(side["key"], reg)
    d: dict[str, Any] = {"key": side["key"], "label": side.get("label") or side["key"], "unit": side.get("unit", ""),
                         "confirmed": confirmed, "note": why, "value": None, "raw_value": None, "at": "",
                         "source": "", "converted": scale != 1}
    if r is not None:
        d.update(raw_value=r.value, value=r.value * scale, at=_t_text(r.t), source=r.src)
        if r.note:
            d["note"] = (d["note"] + "; " if d["note"] else "") + r.note
    return d


def _tol_text(tol: dict[str, Any], unit: str) -> str:
    parts = []
    if tol.get("abs") is not None:
        parts.append(f"{_g(float(tol['abs']))} {unit}")
    if tol.get("rel_pct") is not None:
        parts.append(f"{_g(float(tol['rel_pct']))} %")
    return "within " + " + ".join(parts) if parts else "no tolerance set"


def _base_result(rule: dict[str, Any], status: str, reg: dict[str, Any], readings: list[Optional[Reading]],
                 reason: str = "") -> dict[str, Any]:
    tol = rule.get("tolerance") or {}
    sides = [_side_dict(s, r, reg) for s, r in zip(rule["sides"], readings)]
    ts = [r.t for r in readings if r is not None]
    return {
        "id": rule["id"], "title": rule["title"], "group": rule.get("group", ""), "status": status,
        "mark": MARK[status], "css": CSS[status], "reason": reason, "unit": rule.get("unit", ""),
        "sides": sides, "a": sides[0], "b": sides[1] if len(sides) > 1 else None,
        "diff": None, "spread": None, "would_be": "",
        "tolerance": {"abs": tol.get("abs"), "rel_pct": tol.get("rel_pct"), "unit": rule.get("unit", ""),
                      "text": _tol_text(tol, rule.get("unit", "")), "basis": rule.get("tolerance_basis", "")},
        "basis": rule.get("basis", ""),
        "condition_text": "; ".join(c.get("text", "") for c in rule.get("conditions") or []) or "none (always applies)",
        "max_skew_s": float(rule.get("max_skew_s", DEFAULT_MAX_SKEW_S)),
        "skew_s": round(max(ts) - min(ts), 3) if len(ts) > 1 else (0.0 if ts else None),
        "at": _t_text(min(ts)) if ts else "", "t": min(ts) if ts else None, "suspects": "",
    }


def _unpaired(res: dict[str, Any]) -> dict[str, Any]:
    res["unpaired"] = True          # no common moment: the saved-readings search tries an older anchor
    return res


def judge(rule: dict[str, Any], get, reg: dict[str, Any], soaked_h: Optional[float] = None) -> dict[str, Any]:
    """Judge one rule given ``get(key) -> Reading | None`` (already restricted to one moment)."""
    readings = [get(s["key"]) for s in rule["sides"]]
    skew_max = float(rule.get("max_skew_s", DEFAULT_MAX_SKEW_S))
    missing = [s.get("label") or s["key"] for s, r in zip(rule["sides"], readings) if r is None]
    if missing:
        return _unpaired(_base_result(rule, NOT_REC, reg, readings, "not read at the same moment: " + ", ".join(missing)))
    # condition channels
    unmet: list[str] = []
    cond_missing: list[str] = []
    cond_readings: list[Reading] = []
    for cond in rule.get("conditions") or []:
        if cond.get("type") == "soak":
            need = float(cond.get("hours", 0))
            if soaked_h is None:
                unmet.append(f"{cond.get('text')} - not stated; open this page with ?soaked_h=<hours> if the car sat that long")
            elif soaked_h < need:
                unmet.append(f"{cond.get('text')} - you stated {_g(soaked_h)} h")
            continue
        r = _pick(get, _cond_keys(cond))
        if r is None:
            cond_missing.append(cond.get("text") or "/".join(_cond_keys(cond)))
            continue
        cond_readings.append(r)
        if not (float(cond.get("min", -math.inf)) <= r.value <= float(cond.get("max", math.inf))):
            unmet.append(f"{cond.get('text')} - read {_g(r.value)} {r.unit}".rstrip() + f" ({r.key})")
    if cond_missing:
        return _unpaired(_base_result(rule, NOT_REC, reg, readings,
                            "cannot tell whether the condition holds, no reading at the same moment for: " + "; ".join(cond_missing)))
    allr = [r for r in readings if r is not None] + cond_readings
    spread_t = max(r.t for r in allr) - min(r.t for r in allr)
    if spread_t > skew_max + 1e-9:
        return _unpaired(_base_result(rule, NOT_REC, reg, readings,
                            f"readings are {_g(spread_t)} s apart; the limit is {_g(skew_max)} s"))
    if unmet:
        res = _base_result(rule, NOT_MET, reg, readings, "condition not met: " + "; ".join(unmet))
        res["skew_s"] = round(spread_t, 3)
        return res
    # validity and units
    bad: list[str] = []
    sus: list[str] = []
    for s, r in zip(rule["sides"], readings):
        want = _unit_norm(s.get("unit"))
        if r.unit and want and _unit_norm(r.unit) != want:
            bad.append(f"{s.get('label')}: unit {r.unit} is not the expected {s.get('unit')}")
            continue
        inv, su = _invalid_and_suspect(s["key"], r.value, s.get("unit", ""), reg)
        if inv:
            bad.append(f"{s.get('label')}: invalid reading ({inv})")
        if su:
            sus.append(f"{s.get('label')}: {su}")
    if bad:
        res = _base_result(rule, NOT_REC, reg, readings, "; ".join(bad))
        res["skew_s"] = round(spread_t, 3)
        return res
    vals = [r.value * float(s.get("scale", 1)) for s, r in zip(rule["sides"], readings)]
    spread = max(vals) - min(vals)
    tol = rule.get("tolerance") or {}
    limit = float(tol.get("abs") or 0) + float(tol.get("rel_pct") or 0) / 100.0 * max(abs(v) for v in vals)
    verdict = AGREE if spread <= limit + 1e-9 else DISAGREE
    unconf = [(s.get("label") or s["key"], _confidence(s["key"], reg)[1]) for s in rule["sides"]
              if not _confidence(s["key"], reg)[0]]
    res = _base_result(rule, verdict, reg, readings)
    res["skew_s"] = round(spread_t, 3)
    res["diff"] = res["spread"] = round(spread, 4)
    if unconf or sus:
        res["status"], res["mark"], res["css"] = UNCONFIRMED, MARK[UNCONFIRMED], CSS[UNCONFIRMED]
        res["would_be"] = verdict
        res["reason"] = ("; ".join(f"{n}: {w}" for n, w in unconf) + ("; " if unconf and sus else "")
                         + "; ".join(sus))
        res["reason"] += (" -- values agree, which supports the decoding but does not confirm it"
                          if verdict == AGREE else " -- values disagree: the sensor or its decoding is wrong")
    return res


# --- finding the moment: saved readings ----------------------------------------------------

def _nearest(lst: list[Reading], times: list[float], t: float, skew: float) -> Optional[Reading]:
    i = bisect.bisect_left(times, t)
    best: Optional[Reading] = None
    for j in (i - 1, i):
        if 0 <= j < len(lst) and abs(lst[j].t - t) <= skew and (best is None or abs(lst[j].t - t) < abs(best.t - t)):
            best = lst[j]
    return best


def evaluate_saved_rule(rule: dict[str, Any], series: Series, reg: dict[str, Any],
                        soaked_h: Optional[float] = None) -> dict[str, Any]:
    skew = float(rule.get("max_skew_s", DEFAULT_MAX_SKEW_S))
    times = {k: [r.t for r in lst] for k, lst in series.items()}
    first = rule["sides"][0]["key"]
    anchors = list(reversed(series.get(first, [])))[:MAX_ANCHORS]
    if not anchors:
        return judge(rule, lambda k: None, reg, soaked_h)
    newest: Optional[dict[str, Any]] = None
    for a in anchors:
        def get(k: str, _t=a.t) -> Optional[Reading]:
            return _nearest(series.get(k, []), times.get(k, []), _t, skew) if k in series else None
        res = judge(rule, get, reg, soaked_h)
        if res.get("unpaired"):
            if newest is None:
                newest = res
            continue                                       # no paired moment here: try an older anchor
        if res["status"] == NOT_MET:
            if newest is None or newest.get("unpaired"):
                newest = res
            continue                                       # look for an older moment where the condition held
        if newest is not None and newest["status"] == NOT_MET and res["status"] != NOT_MET:
            res["reason"] = (res["reason"] + " " if res["reason"] else "") + \
                "(latest moment at which the condition held; newer readings did not meet it)"
        return res
    return newest or judge(rule, lambda k: None, reg, soaked_h)


# --- recording: every row ------------------------------------------------------------------

def evaluate_recording_rule(rule: dict[str, Any], rows: list[tuple[float, dict[str, Reading]]],
                            reg: dict[str, Any], soaked_h: Optional[float] = None) -> dict[str, Any]:
    results = [judge(rule, lambda k, _r=r: _r.get(k), reg, soaked_h) for _t, r in rows]
    n = {s: sum(1 for x in results if x["status"] == s) for s in ORDER}
    judged = [x for x in results if x["status"] in (AGREE, DISAGREE, UNCONFIRMED)]
    counts = {"rows": len(results), "evaluated": len(judged), "agree": n[AGREE], "disagree": n[DISAGREE],
              "unconfirmed": n[UNCONFIRMED], "condition_not_met": n[NOT_MET], "not_recorded": n[NOT_REC]}
    if not judged:
        pick = NOT_MET if n[NOT_MET] else NOT_REC
        base = next((x for x in results if x["status"] == pick), None) or judge(rule, lambda k: None, reg, soaked_h)
        base = dict(base)
        if not results:
            base["reason"] = "the recording has no rows"
        else:
            base["reason"] = f"no row could be judged: {n[NOT_MET]} condition not met, {n[NOT_REC]} not recorded. " + base["reason"]
        base["rows"] = counts
        return base
    outs = [x["would_be"] if x["status"] == UNCONFIRMED else x["status"] for x in judged]
    bad_share = outs.count(DISAGREE) / len(outs)
    verdict = DISAGREE if bad_share >= DISAGREE_SHARE else AGREE
    if verdict == DISAGREE:
        rep = max((x for x, o in zip(judged, outs) if o == DISAGREE), key=lambda x: x["diff"])
    else:
        by = sorted(judged, key=lambda x: x["diff"])
        rep = by[len(by) // 2]
    res = dict(rep)
    med = statistics.median(x["diff"] for x in judged)
    unconf = any(x["status"] == UNCONFIRMED for x in judged)
    if unconf:
        res.update(status=UNCONFIRMED, mark=MARK[UNCONFIRMED], css=CSS[UNCONFIRMED], would_be=verdict)
    else:
        res.update(status=verdict, mark=MARK[verdict], css=CSS[verdict], would_be="")
    res["reason"] = (f"{counts['evaluated']} of {counts['rows']} rows judged; {outs.count(DISAGREE)} beyond tolerance "
                     f"({round(bad_share * 100)} %); median difference {_g(med)} {rule.get('unit', '')}; "
                     f"the pair shown is the {'worst' if verdict == DISAGREE else 'median'} row"
                     + (f". {rep['reason']}" if unconf and rep.get("reason") else ""))
    res["rows"] = counts
    return res


# --- suspect attribution, headline ----------------------------------------------------------

def _attribute(results: list[dict[str, Any]]) -> None:
    """Name the likelier culprit of a DISAGREE: a side that also AGREES with another channel is cleared."""
    cleared: dict[str, str] = {}
    for r in results:
        if r["status"] == AGREE:
            for s in r["sides"]:
                cleared.setdefault(_base(s["key"]), r["title"])
    for r in results:
        if r["status"] not in (DISAGREE, UNCONFIRMED) or (r["status"] == UNCONFIRMED and r["would_be"] != DISAGREE):
            continue
        keys = [(s["label"], _base(s["key"]), s["confirmed"]) for s in r["sides"]]
        free = [lab for lab, b, _c in keys if b not in cleared]
        clr = [(lab, cleared[b]) for lab, b, _c in keys if b in cleared]
        if clr and free and len(free) < len(keys):
            r["suspects"] = (f"suspect {' or '.join(free)}; {clr[0][0]} agrees elsewhere ({clr[0][1]})")
        else:
            r["suspects"] = "suspect " + " or ".join(lab for lab, _b, _c in keys) + " (or a decoding)"


def headline(results: list[dict[str, Any]]) -> str:
    dis = [r for r in results if r["status"] == DISAGREE]
    unc_bad = [r for r in results if r["status"] == UNCONFIRMED and r["would_be"] == DISAGREE]
    agree = [r for r in results if r["status"] == AGREE]
    unc_ok = [r for r in results if r["status"] == UNCONFIRMED and r["would_be"] == AGREE]
    ran = len(dis) + len(unc_bad) + len(agree) + len(unc_ok)
    idle = len(results) - ran

    def one(r: dict[str, Any]) -> str:
        return f"{r['title']} off by {_g(r['diff'])} {r['unit']} - {r['suspects']}"
    if dis:
        txt = f"{len(dis)} of {ran} checks disagree: " + "; ".join(one(r) for r in dis[:2])
        if len(dis) > 2:
            txt += f"; and {len(dis) - 2} more"
        if unc_bad:
            txt += f". {len(unc_bad)} more disagree where a decoding is unconfirmed"
        return txt + "."
    if unc_bad:
        return (f"No confirmed check disagrees, but {len(unc_bad)} of {ran} disagree where a decoding is unconfirmed: "
                + "; ".join(one(r) for r in unc_bad[:2]) + ".")
    if ran:
        return (f"{ran} checks could run and none disagree ({len(agree)} agree"
                + (f", {len(unc_ok)} agree on an unconfirmed decoding" if unc_ok else "") + f"); {idle} could not run.")
    return f"No cross-check could run: none of the {len(results)} has both values read at the same moment with its condition met."


# --- public API ----------------------------------------------------------------------------

def evaluate(vin: str, recording: Optional[str] = None, soaked_h: Optional[float] = None,
             rules_path: Optional[Path] = None, series: Optional[Series] = None,
             recording_data: Optional[dict[str, Any]] = None, now: Optional[float] = None) -> dict[str, Any]:
    """Evaluate every rule. ``series``/``recording_data`` let tests inject data; otherwise it is read from disk."""
    table = load_rules(rules_path)
    reg = _registry()
    now = time.time() if now is None else now
    out: dict[str, Any] = {"vin": vin, "recording": recording or "", "soaked_h": soaked_h,
                           "default_max_skew_s": DEFAULT_MAX_SKEW_S, "error": "", "live_used": False,
                           "generated_at": _t_text(now), "needs": table.get("needs") or []}
    results: list[dict[str, Any]] = []
    try:
        if recording:
            rec = recording_data
            if rec is None:
                from . import recordings
                rec = recordings.load(vin, recording)
            if rec is None:
                raise LookupError(f"no recording {recording!r} for this car")
            rows = series_from_recording(rec)
            out["recording_info"] = {"id": rec.get("id"), "label": rec.get("label", ""), "start": rec.get("start", ""),
                                     "rows": len(rows), "channels": len(rec.get("channels") or [])}
            results = [evaluate_recording_rule(r, rows, reg, soaked_h) for r in table["rules"]]
        else:
            if series is None:
                series = load_saved(vin)
                out["live_used"] = add_live(series, now)
                for lst in series.values():
                    lst.sort(key=lambda r: r.t)
            results = [evaluate_saved_rule(r, series, reg, soaked_h) for r in table["rules"]]
    except Exception as exc:  # noqa: BLE001 -- the page explains instead of failing
        out["error"] = f"{type(exc).__name__}: {exc}"
    _attribute(results)
    results.sort(key=lambda r: (ORDER.index(r["status"]), r["group"], r["title"]))
    for r in results:
        r["age_text"] = _age(now, r.get("t"))
    for r in results:
        r.pop("unpaired", None)
    out["results"] = results
    out["counts"] = {s: sum(1 for r in results if r["status"] == s) for s in ORDER}
    out["counts"]["total"] = len(results)
    out["call"] = headline(results) if results else (out["error"] or "No rules loaded.")
    out["tone"] = ("bad" if out["counts"][DISAGREE] else "warn" if any(
        r["status"] == UNCONFIRMED and r["would_be"] == DISAGREE for r in results) else "ok")
    return out


def _age(now: float, t: Optional[float]) -> str:
    if t is None:
        return ""
    d = max(0.0, now - t)
    if d < 90:
        return "just now"
    if d < 5400:
        return f"{round(d / 60)} min ago"
    if d < 172800:
        return f"{round(d / 3600)} h ago"
    return f"{round(d / 86400)} days ago"


def panel(vin: str, recording: Optional[str] = None, soaked_h: Optional[float] = None) -> dict[str, Any]:
    """Context for ``_crosscheck_panel.html``: ``{% include "_crosscheck_panel.html" %}`` needs ``cc`` and ``vin``."""
    try:
        return evaluate(vin, recording or None, soaked_h)
    except Exception as exc:  # noqa: BLE001
        return {"vin": vin, "recording": recording or "", "results": [], "needs": [], "counts": {"total": 0},
                "call": f"Cross-checks are not available: {exc}", "tone": "warn", "error": str(exc),
                "soaked_h": soaked_h, "live_used": False, "generated_at": "", "default_max_skew_s": DEFAULT_MAX_SKEW_S}
