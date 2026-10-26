"""Drift and trend tracking across visits (days and weeks, not within one session).

Question answered: "is a value moving toward its limit before a code sets?"

Pipeline, all read-only (nothing here opens the adapter or writes a file):

1. **Collect** readings from what CUORE already stored: observations.jsonl (through
   :func:`cuore.services.cache.recent_observations`, which parses the file once per file
   state), live snapshots and sensor checks, real MES FES logs (through
   :mod:`cuore.services.mes_parameters`, which already drops simulated logs and other VINs),
   load-step recordings and CUORE recordings. Which sources feed which quantity is data, in
   ``cuore/data/trend_metrics.json``.
2. **Clean**. A reading that is not a reading never reaches a trend: the ``invalid_reason``
   and ``suspect_reason`` rules of :mod:`cuore.services.sensor_health` are applied, and a
   snapshot or check value for ``ecm_195a`` / ``ecm_1956`` stored before the 2026-10-25
   formula fix is re-decoded with ``sensor_health.redecode`` (the same read-time rule the
   rest of CUORE uses) so old and new decodings are never compared as if alike. DID bytes
   are decoded with the CURRENT ``did_catalog`` formula, never the stored one.
3. **Select comparable readings** per metric (same condition: engine off and rested for
   resting voltage; warm idle for trims; ...). A reading that fails the condition is kept
   in an "excluded" list with its reason, never silently dropped.
4. **One point per day** per source stream (median), because two different instruments
   (BCM DID versus adapter ATRV) have different offsets and must not be mixed in one line.
5. **Explainable statistics**: least-squares slope with the sample count, a half-versus-half
   check, and a textbook CUSUM shift flag. No confidence percentages are invented. A
   "reaches the limit in about N days" line appears only with enough samples and span;
   otherwise the wording is "not enough data (N samples)".
"""

from __future__ import annotations

import bisect
import json
import math
import statistics
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from . import cache

CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "trend_metrics.json"
DEFAULT_VIN = "ZASFAKPN5J7B88115"

#: Status -> (label, chip class, symbol). Colour is never the only carrier: label and symbol too.
STATUS = {
    "past_limit":       ("past its limit",         "returned", "▲"),
    "heading_to_limit": ("heading toward limit",   "chronic",  "◆"),
    "shifted":          ("shifted",                "chronic",  "■"),
    "drifting":         ("drifting",               "cleared",  "●"),
    "moving_away":      ("moving away from limit", "cleared",  "◇"),
    "steady":           ("steady",                 "ok",       "✓"),
    "not_enough_data":  ("not enough data",        "plain",    "○"),
    "no_data":          ("no readings",            "plain",    "○"),
}
_PRIORITY = {"past_limit": 6, "heading_to_limit": 5, "shifted": 4, "drifting": 3, "moving_away": 2.5, "steady": 2,
             "not_enough_data": 1, "no_data": 0}

_cfg_cache: dict[str, Any] = {"stamp": None, "cfg": None}


def load_config() -> dict[str, Any]:
    st = CONFIG_PATH.stat()
    stamp = (st.st_mtime_ns, st.st_size)
    if _cfg_cache["stamp"] != stamp:
        _cfg_cache["cfg"] = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        _cfg_cache["stamp"] = stamp
    return _cfg_cache["cfg"]


# --- small helpers -------------------------------------------------------------------

def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _dt(s: Any) -> Optional[datetime]:
    if isinstance(s, datetime):
        return s
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).strip().replace(" ", "T")[:19])
    except ValueError:
        return None


def _fmt(v: Optional[float], decimals: int) -> str:
    if v is None:
        return "?"
    return f"{v:.{decimals}f}"


def _reading(at: Optional[datetime], q: str, value: Any, unit: str, stream: str, *,
             inline: Optional[dict[str, Any]] = None, excluded: str = "", **extra: Any) -> dict[str, Any]:
    return {"at": at, "q": q, "value": float(value) if _is_num(value) else None, "unit": unit,
            "stream": stream, "inline": inline or {}, "excluded": excluded, **extra}


# --- cleaning: the sensor_health rules -----------------------------------------------

def clean_channel(channel: str, value: Any, at: str, unit: str = "", formula: str = "",
                  plausibility_unit: Optional[str] = None) -> tuple[Optional[float], str, str]:
    """(value, unit, excluded_reason) for one stored channel value.

    Re-decodes the old ecm_195a / ecm_1956 numbers, then excludes anything sensor_health calls
    invalid (a 'not available' marker, an impossible value) or suspect (unconfirmed decoding).
    """
    from . import sensor_health
    if not _is_num(value):
        return None, unit, "not a number"
    v = float(value)
    rd = sensor_health.redecode(channel, v, at or "", unit)
    if rd:
        v, unit = rd[0], rd[1]
    chk_unit = unit if plausibility_unit is None else plausibility_unit
    bad = sensor_health.invalid_reason(channel, v, chk_unit, formula)
    if bad:
        return None, unit, f"invalid reading: {bad}"
    sus = sensor_health.suspect_reason(channel, v, {})
    if sus:
        return None, unit, f"suspect reading: {sus}"
    return v, unit, ""


# --- collection ----------------------------------------------------------------------

def _file_stamp(p: Path) -> Any:
    try:
        st = p.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _decode_did(ecu: str, did_hex: str, data_bytes: list[str], stored_formula: str) -> tuple[Optional[float], str, str, str]:
    """(value, unit, formula, error) using the CURRENT catalog formula (stored one only as a fallback)."""
    from ..live import channels, did_catalog
    spec = None
    try:
        want = int(did_hex, 16)
        spec = next((s for s in did_catalog.all_dids(ecu) if s.did == want), None)
    except (ValueError, KeyError):
        spec = None
    formula = (spec.formula if spec else "") or stored_formula or ""
    unit = (spec.unit if spec else "") or ""
    if not formula:
        return None, unit, "", "no decoding formula for this DID"
    try:
        vals = {chr(ord("A") + i): int(b, 16) for i, b in enumerate(data_bytes[:8])}
        return float(channels.eval_expr(formula, vals)), unit, formula, ""
    except Exception as exc:  # noqa: BLE001 -- a malformed record must not sink the page
        return None, unit, formula, f"could not decode: {exc}"


def _collect_observations(vin: str, cfg: dict[str, Any], out: list[dict[str, Any]],
                          activity: list[datetime]) -> None:
    rows = cache.recent_observations(n=10 ** 9, vin="")
    vins = {str(o.get("vin") or "").upper() for o in rows} - {""}
    untagged_ok = vins <= {vin.upper()}
    mine: list[dict[str, Any]] = []
    for o in rows:
        v = str(o.get("vin") or "").upper()
        if v == vin.upper() or (not v and untagged_ok):
            mine.append(o)
    quantities = cfg["quantities"]
    seen: set[tuple] = set()
    for o in mine:
        at = _dt(o.get("at"))
        if at is None:
            continue
        activity.append(at)
        kind = o.get("kind")
        data = o.get("data") or {}
        tag = "" if str(o.get("vin") or "") else " (stored without a VIN; accepted because only this VIN is on record)"
        for q, qd in quantities.items():
            for src in qd["sources"]:
                t = src.get("type")
                if t == "obs_did" and kind == "did":
                    if str(data.get("ecu")) != src["ecu"] or str(data.get("did", "")).upper() != src["did"].upper():
                        continue
                    if data.get("error") or not data.get("bytes"):
                        continue
                    val, unit, formula, err = _decode_did(src["ecu"], src["did"], data["bytes"], data.get("formula") or "")
                    reason = err
                    if not reason:
                        ch = f"{src['ecu'].lower()}_{src['did'].lower()}"
                        val, unit2, reason = clean_channel(ch, val, o.get("at") or "", unit or qd["unit"], formula,
                                                           qd.get("plausibility_unit"))
                    key = (q, src["label"], at, val)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(_reading(at, q, val, qd["unit"], src["label"] + tag, excluded=reason))
                elif t == "obs_pid" and kind == "pids_snapshot":
                    for ecu_key, pids in (data.get("by_ecu") or {}).items():
                        p = pids.get(src["pid"]) if isinstance(pids, dict) else None
                        if not isinstance(p, dict) or not _is_num(p.get("value")):
                            continue
                        inline = _pid_ctx(pids, cfg)
                        val, _u, reason = clean_channel(f"pid_{src['pid'].lower()}", p["value"], o.get("at") or "",
                                                        qd["unit"], "", qd.get("plausibility_unit"))
                        key = (q, src["label"], at, val, ecu_key)
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append(_reading(at, q, val, qd["unit"], src["label"] + tag, inline=inline, excluded=reason))
                elif t == "obs_probe_voltage" and kind == "adapter_identity":
                    probe = data.get("probe") or {}
                    bv = probe.get("battery_voltage") if isinstance(probe, dict) else None
                    if _is_num(bv):
                        val, _u, reason = clean_channel("battery_voltage", bv, o.get("at") or "", "V", "", None)
                        key = (q, src["label"], at, val)
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append(_reading(at, q, val, qd["unit"], src["label"] + tag, excluded=reason))


def _pid_ctx(pids: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Same-snapshot context (rpm, speed, coolant, battery) from the PIDs of one reply."""
    m = {"rpm": "0C", "speed": "0D", "coolant": "05", "battery_v": "42"}
    ctx = {}
    for k, pid in m.items():
        p = pids.get(pid)
        if isinstance(p, dict) and _is_num(p.get("value")):
            ctx[k] = float(p["value"])
    return ctx


_SNAP_CTX = {"rpm": ("engine_rpm", "ecm_1000"), "speed": ("vehicle_speed", "ecm_1002"),
             "coolant": ("engine_coolant_temp",), "oil_temp": ("ecm_1302",),
             "battery_v": ("battery_voltage", "bcm_1004")}


def _snapshot_value(v: Any) -> Any:
    if isinstance(v, dict):
        return v.get("value") if "value" in v else None
    return v


def _collect_snapshots(vin: str, cfg: dict[str, Any], out: list[dict[str, Any]], activity: list[datetime]) -> None:
    from ..live import config as live_config
    sd = Path(live_config.state_dir())
    quantities = cfg["quantities"]
    seen: set[tuple] = set()
    for fname in ("live_snapshots.jsonl", "sensor_checks.jsonl"):
        try:
            lines = (sd / fname).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                s = json.loads(line)
            except ValueError:
                continue
            if not isinstance(s, dict):
                continue
            if s.get("vin") and str(s["vin"]).upper() != vin.upper():
                continue
            at = _dt(s.get("at"))
            if at is None:
                continue
            activity.append(at)
            values = s.get("values") or {}
            inline: dict[str, Any] = {}
            for k, chans in _SNAP_CTX.items():
                for ch in chans:
                    sv = _snapshot_value(values.get(ch))
                    if _is_num(sv):
                        inline[k] = float(sv)
                        break
            for q, qd in quantities.items():
                for src in qd["sources"]:
                    if src.get("type") != "snapshot":
                        continue
                    ch = src["channel"]
                    raw = values.get(ch)
                    unit = (raw.get("unit") if isinstance(raw, dict) else "") or qd["unit"]
                    sv = _snapshot_value(raw)
                    if not _is_num(sv):
                        continue
                    key = (q, ch, at, sv, fname)
                    if key in seen:
                        continue
                    seen.add(key)
                    val, _u, reason = clean_channel(ch, sv, s.get("at") or "", unit, "", qd.get("plausibility_unit"))
                    out.append(_reading(at, q, val, qd["unit"], src["label"], inline=inline, excluded=reason))


def _collect_mes(vin: str, cfg: dict[str, Any], out: list[dict[str, Any]], activity: list[datetime]) -> None:
    try:
        from .. import bootstrap  # noqa: F401  -- puts `mes` on sys.path
        from mes import params as mes_params
        from . import mes_parameters
        logs = mes_parameters._parsed(vin)           # real FES logs only (simulated and other VINs dropped)
    except Exception:  # noqa: BLE001 -- MES side unavailable: trends just have fewer sources
        return
    ctx_names = {"rpm": ("Engine speed",), "speed": ("Vehicle speed",), "coolant": ("Engine temperature",),
                 "oil_temp": ("Engine oil temperature",), "battery_v": ("Battery voltage",)}
    wanted: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for q, qd in cfg["quantities"].items():
        for src in qd["sources"]:
            if src.get("type") == "mes_param":
                wanted.append((q, qd, src))
    for lg in logs:
        at = _dt(lg.get("at"))
        if at is None:
            continue
        activity.append(at)
        ecu = str(lg.get("ecu") or "")[:40]
        for sample in lg["samples"]:
            nums: dict[str, float] = {}
            for name, raw, unit in sample:
                pv = mes_params.parse_value(name, raw)
                if pv.number is not None:
                    nums.setdefault(name, float(pv.number))
            inline: dict[str, Any] = {}
            for k, names in ctx_names.items():
                for n in names:
                    if n in nums:
                        inline[k] = nums[n]
                        break
            for q, qd, src in wanted:
                if src["name"] in nums:
                    val, _u, reason = clean_channel("mes_" + src["name"], nums[src["name"]], lg.get("at") or "",
                                                    qd["unit"], "", qd.get("plausibility_unit"))
                    out.append(_reading(at, q, val, qd["unit"], f"{src['label']} in {ecu} log", inline=inline,
                                        excluded=reason))


def _collect_recordings(vin: str, cfg: dict[str, Any], out: list[dict[str, Any]], activity: list[datetime]) -> None:
    quantities = cfg["quantities"]
    for q, qd in quantities.items():
        for src in qd["sources"]:
            t = src.get("type")
            if t == "recording_load_step":
                try:
                    from ..live import load_step
                    rdir = load_step.recordings_dir()
                    files = sorted(Path(rdir).glob("live_load-step*.csv"))
                except Exception:  # noqa: BLE001
                    continue
                for f in files:
                    try:
                        rows, side = load_step.read_recording(f)
                    except Exception:  # noqa: BLE001
                        continue
                    at = _dt(side.get("started"))
                    base = [r[src["channel"]] for r in rows
                            if str(r.get("tag", "")).upper().startswith("BASELINE") and _is_num(r.get(src["channel"]))]
                    if at is None or not base:
                        continue
                    activity.append(at)
                    out.append(_reading(at, q, statistics.median(base), qd["unit"], src["label"],
                                        inline={"engine_state": ("running", "load-step script baseline: owner told to idle the engine")}))
            elif t == "recording_warmup":
                try:
                    from . import recordings
                    recs = recordings.list_recordings(vin)
                except Exception:  # noqa: BLE001 -- bad VIN string / no directory
                    continue
                for r in recs:
                    try:
                        full = recordings.load(vin, r.get("id", ""))
                    except Exception:  # noqa: BLE001
                        continue
                    if not full:
                        continue
                    pts = [(row.get("t"), (row.get("v") or {}).get(src["channel"])) for row in full.get("rows", [])]
                    pts = [(t0, v) for t0, v in pts if _is_num(t0) and _is_num(v)]
                    if not pts or pts[0][1] > src["cold_max_c"]:
                        continue
                    hit = next((t1 for t1, v in pts if v >= src["target_c"]), None)
                    at = _dt(full.get("start"))
                    if hit is None or at is None:
                        continue
                    activity.append(at)
                    out.append(_reading(at, q, (hit - pts[0][0]) / 60.0, qd["unit"], src["label"]))


def _collect_mode06(vin: str, cfg: dict[str, Any], out: list[dict[str, Any]]) -> None:
    m6 = cfg.get("mode06") or {}
    if not m6.get("enabled"):
        return
    rows = cache.recent_observations(n=10 ** 9, vin="", kind="mode06")
    vins = {str(o.get("vin") or "").upper() for o in cache.recent_observations(n=10 ** 9, vin="")} - {""}
    untagged_ok = vins <= {vin.upper()}
    sent = m6.get("no_limit_sentinels") or {}
    seen: set[tuple] = set()
    for o in rows:
        v = str(o.get("vin") or "").upper()
        if not (v == vin.upper() or (not v and untagged_ok)):
            continue
        at = _dt(o.get("at"))
        if at is None:
            continue
        for mid, entry in ((o.get("data") or {}).get("results") or {}).items():
            if str(mid).upper() not in [x.upper() for x in m6.get("mids", [])]:
                continue
            for ecu, recs in ((entry or {}).get("by_ecu") or {}).items():
                for rec in recs or []:
                    tid = str(rec.get("tid"))
                    q = f"m06:{str(mid).upper()}:{tid}"
                    key = (q, at, ecu, rec.get("value"))
                    if key in seen:
                        continue
                    seen.add(key)
                    raw = rec.get("raw") or {}
                    reason = ""
                    if m6.get("require_known_scaling", True) and raw.get("scaling") != "known":
                        reason = (f"unit-and-scaling ID 0x{rec.get('uasid')} is not decoded by CUORE, so the number "
                                  "is not a measurement in a known unit")
                    elif not _is_num(rec.get("value")):
                        reason = "no numeric value"
                    elif raw.get("value") == 0 and raw.get("min") == 0 and raw.get("max") == 0:
                        reason = "placeholder reply (value, minimum and maximum all 0): the monitor had not run"
                    lo, hi = rec.get("min"), rec.get("max")
                    lo = None if (not _is_num(lo) or lo in sent.get("min", [])) else float(lo)
                    hi = None if (not _is_num(hi) or hi in sent.get("max", [])) else float(hi)
                    out.append(_reading(at, q, rec.get("value"), rec.get("unit") or "", f"Mode 06 reply from {ecu}",
                                        excluded=reason, lo=lo, hi=hi, mid=str(mid).upper(), tid=tid,
                                        mid_name=rec.get("mid_name") or "", uasid=rec.get("uasid")))


def collect(vin: str, cfg: Optional[dict[str, Any]] = None) -> tuple[list[dict[str, Any]], list[datetime]]:
    """Every reading from every stored source, plus the timestamps of all CUORE/MES activity."""
    cfg = cfg or load_config()
    out: list[dict[str, Any]] = []
    activity: list[datetime] = []
    for fn in (_collect_observations, _collect_snapshots, _collect_mes, _collect_recordings):
        try:
            fn(vin, cfg, out, activity)
        except Exception:  # noqa: BLE001 -- one broken source must not hide the others
            continue
    try:
        _collect_mode06(vin, cfg, out)
    except Exception:  # noqa: BLE001
        pass
    activity = sorted(set(activity))
    return out, activity


# --- comparable-sample selection -------------------------------------------------------

class _Ctx:
    """Nearest-in-time context readings (rpm, speed, coolant, oil temp, battery volts)."""

    KEYS = ("rpm", "speed", "coolant", "oil_temp", "battery_v")

    def __init__(self, readings: list[dict[str, Any]], window_s: float) -> None:
        self.window = timedelta(seconds=window_s)
        self.idx: dict[str, list[tuple[datetime, float]]] = {k: [] for k in self.KEYS}
        for r in readings:
            if r["q"] in self.idx and not r["excluded"] and r["value"] is not None and r["at"]:
                self.idx[r["q"]].append((r["at"], r["value"]))
        for k in self.idx:
            self.idx[k].sort()

    def nearest(self, key: str, at: datetime) -> Optional[tuple[float, datetime]]:
        arr = self.idx.get(key) or []
        if not arr:
            return None
        i = bisect.bisect_left(arr, (at,))
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(arr):
                d = abs(arr[j][0] - at)
                if d <= self.window and (best is None or d < best[0]):
                    best = (d, arr[j])
        return (best[1][1], best[1][0]) if best else None

    def get(self, key: str, r: dict[str, Any]) -> Optional[float]:
        if key in r["inline"] and _is_num(r["inline"][key]):
            return float(r["inline"][key])
        if r["q"] == key and r["value"] is not None:
            return r["value"]
        n = self.nearest(key, r["at"]) if r["at"] else None
        return n[0] if n else None


def _engine_state(r: dict[str, Any], ctx: _Ctx, d: dict[str, Any]) -> tuple[str, str]:
    if "engine_state" in r["inline"]:
        st, basis = r["inline"]["engine_state"]
        return st, basis
    rpm = ctx.get("rpm", r)
    if rpm is not None:
        if rpm == 0:
            return "off", "RPM 0 at the same time"
        if rpm >= d["engine_rpm_running_min"]:
            return "running", f"RPM {rpm:g} at the same time"
    v = ctx.get("battery_v", r)
    if v is not None:
        if v <= d["engine_voltage_off_max_v"]:
            return "off", f"inferred from battery voltage {v:g} V (not charging)"
        if v >= d["engine_voltage_running_min_v"]:
            return "running", f"inferred from battery voltage {v:g} V (charging)"
    return "unknown", ""


def _rest_ok(r: dict[str, Any], activity: list[datetime], hours: float, d: dict[str, Any]) -> tuple[bool, str]:
    at = r["at"]
    cut = at - timedelta(minutes=d["rest_window_min"])
    i = bisect.bisect_right(activity, cut)
    if i == 0:
        return False, "no earlier CUORE or MES activity on record, so there is no proof the car had rested"
    prev = activity[i - 1]
    gap_h = (at - prev).total_seconds() / 3600.0
    if gap_h < hours:
        return False, (f"not rested: other activity {gap_h:.1f} h before this reading "
                       f"(need {hours:g} h quiet, reading in the first {d['rest_window_min']} min of a visit)")
    return True, ""


def check_condition(r: dict[str, Any], cond: dict[str, Any], ctx: _Ctx, activity: list[datetime],
                    d: dict[str, Any]) -> str:
    """"" when the reading satisfies the metric's condition, else the reason it is not comparable."""
    if cond.get("engine"):
        st, basis = _engine_state(r, ctx, d)
        if st == "unknown":
            return "engine state not known (no RPM, and no battery voltage in the reading window to infer it)"
        if st != cond["engine"]:
            return f"engine {st} ({basis}); this metric needs the engine {cond['engine']}"
    if cond.get("quiet_hours"):
        ok, why = _rest_ok(r, activity, float(cond["quiet_hours"]), d)
        if not ok:
            return why
    if cond.get("not_rest"):
        ok, _ = _rest_ok(r, activity, 2.0, d)
        if ok:
            return "this is a rested reading; it is counted under battery voltage at rest"
    for key, ckey, op, label in (("rpm_min", "rpm", ">=", "RPM"), ("rpm_max", "rpm", "<=", "RPM"),
                                 ("speed_max", "speed", "<=", "speed"), ("coolant_min", "coolant", ">=", "coolant"),
                                 ("oil_temp_max", "oil_temp", "<=", "oil temperature")):
        if key in cond:
            v = ctx.get(ckey, r)
            if v is None:
                return f"{label} not recorded within {int(d['context_window_s'])} s, so the condition cannot be shown"
            if (op == ">=" and v < cond[key]) or (op == "<=" and v > cond[key]):
                return f"{label} {v:g} is outside the condition ({key.replace('_', ' ')} {cond[key]:g})"
    return ""


# --- statistics ------------------------------------------------------------------------

def _ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return b, my - b * mx


def cusum_shift(ys: list[float], min_change: float, noise_floor: float, cfg_cusum: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Two-sided CUSUM against the first points. Returns the shift (index it began at, size) or None."""
    nb = int(cfg_cusum.get("baseline_points", 3))
    if len(ys) <= nb:
        return None
    base = ys[:nb]
    m0 = sum(base) / nb
    sd0 = max(statistics.pstdev(base) if nb > 1 else 0.0, noise_floor)
    k, h = cfg_cusum.get("slack_sd", 0.5) * sd0, cfg_cusum.get("threshold_sd", 4.0) * sd0
    sp = sm = 0.0
    start_p = start_m = nb
    for i in range(nb, len(ys)):
        d = ys[i] - m0
        sp = max(0.0, sp + d - k)
        sm = max(0.0, sm - d - k)
        if sp == 0.0:
            start_p = i + 1
        if sm == 0.0:
            start_m = i + 1
        for s, start, sign in ((sp, start_p, 1), (sm, start_m, -1)):
            if s > h and start <= i:
                size = sum(ys[start:i + 1]) / (i + 1 - start) - m0
                if abs(size) >= min_change:
                    return {"direction": "up" if sign > 0 else "down", "since_index": start, "baseline": m0,
                            "recent": m0 + size, "size": size}
    return None


def analyze_series(points: list[tuple[date, float, int]], spec: dict[str, Any],
                   defaults: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Trend statistics for one stream of per-day points ``[(day, value, readings_that_day)]``.

    ``spec``: min_change, noise_floor, decimals, unit, label, lo/hi (limit or None), min_points override.
    """
    d = defaults or load_config()["defaults"]
    pts = sorted(points, key=lambda p: p[0])
    n = len(pts)
    dec = int(spec.get("decimals", 2))
    unit = spec.get("unit", "")
    lo, hi = spec.get("lo"), spec.get("hi")
    min_points = int(spec.get("min_points") or d["min_points"])
    out: dict[str, Any] = {
        "n": n, "min_points": min_points, "unit": unit, "limit": {"lo": lo, "hi": hi},
        "points": [{"date": p[0].isoformat(), "value": round(p[1], 6), "readings": p[2]} for p in pts],
        "slope_per_day": None, "span_days": 0, "change": None, "direction": None, "cusum": None,
        "projection": None, "margin": None, "first": None, "last": None,
    }
    if n == 0:
        out.update(status="no_data", detail="no comparable readings")
        return out
    days0 = pts[0][0]
    xs = [float((p[0] - days0).days) for p in pts]
    ys = [p[1] for p in pts]
    span = xs[-1] - xs[0]
    out.update(span_days=int(span), first=ys[0], last=ys[-1],
               first_date=pts[0][0].isoformat(), last_date=pts[-1][0].isoformat())
    # Margin to the nearest limit (always shown, even with few points: it is a fact about the latest value).
    margins = []
    if lo is not None:
        margins.append((ys[-1] - lo, "above lower limit", lo))
    if hi is not None:
        margins.append((hi - ys[-1], "below upper limit", hi))
    if margins:
        m = min(margins, key=lambda t: t[0])
        out["margin"] = {"value": m[0], "side": m[1], "limit": m[2],
                         "text": f"{_fmt(abs(m[0]), dec)} {unit} {'inside' if m[0] >= 0 else 'outside'} the limit "
                                 f"{_fmt(m[2], dec)} ({m[1] if m[0] >= 0 else 'past it'})"}
    if n < min_points:
        out.update(status="not_enough_data",
                   detail=f"not enough data ({n} sample{'s' if n != 1 else ''}; at least {min_points} needed)")
        return out
    b, a = _ols(xs, ys)
    out["slope_per_day"] = b
    change = b * span
    out["change"] = change
    out["direction"] = "rising" if b > 0 else ("falling" if b < 0 else "flat")
    half = n // 2
    split = (sum(ys[n - half:]) / half) - (sum(ys[:half]) / half) if half else 0.0
    mc = float(spec.get("min_change", 0))
    material = abs(change) >= mc and (split * change > 0) and span > 0
    out["half_split_change"] = split
    out["material"] = material
    nf = float(spec.get("noise_floor", 0))
    cs = cusum_shift(ys, mc, nf, d.get("cusum", {}))
    if cs:
        cs["since"] = pts[cs["since_index"]][0].isoformat()
        out["cusum"] = cs
    last_val = ys[-1]
    past = (lo is not None and last_val < lo) or (hi is not None and last_val > hi)
    heading = (b > 0 and hi is not None) or (b < 0 and lo is not None)
    proj = None
    why_no_proj = ""
    if material and heading and not past:
        if n >= d["projection_min_points"] and span >= d["projection_min_span_days"]:
            limit = hi if b > 0 else lo
            fitted_last = a + b * xs[-1]
            days = (limit - fitted_last) / b
            days = max(days, 0.0)
            if days > d["max_projection_days"]:
                proj = {"days": None, "text": (f"no limit crossing within {d['max_projection_days'] // 365} years "
                                               f"at this slope ({n} samples over {int(span)} days)")}
            else:
                when = pts[-1][0] + timedelta(days=days)
                proj = {"days": round(days), "date": when.isoformat(), "limit": limit,
                        "text": (f"projected to reach {_fmt(limit, dec)} {unit} in about {round(days)} days "
                                 f"(around {when.isoformat()}); straight-line extrapolation from {n} samples over "
                                 f"{int(span)} days")}
        else:
            why_no_proj = (f"no projection yet: needs at least {d['projection_min_points']} samples over "
                           f"{d['projection_min_span_days']} days (have {n} over {int(span)} days)")
    out["projection"] = proj
    out["projection_note"] = why_no_proj
    no_limit = lo is None and hi is None
    cs_toward = bool(cs) and (no_limit or (cs["direction"] == "up" and hi is not None)
                              or (cs["direction"] == "down" and lo is not None))
    if cs:
        cs["toward_limit"] = cs_toward
    if past:
        status = "past_limit"
    elif proj and proj.get("days") is not None:
        status = "heading_to_limit"
    elif cs_toward:
        status = "shifted"
    elif material and (heading or no_limit):
        status = "drifting"
    elif cs or material:
        status = "moving_away"
    else:
        status = "steady"
    out["status"] = status
    out["detail"] = f"{n} samples over {int(span)} days"
    return out


# --- per-metric assembly ---------------------------------------------------------------

def _daily_points(rs: list[dict[str, Any]]) -> list[tuple[date, float, int]]:
    by_day: dict[date, list[float]] = {}
    for r in rs:
        by_day.setdefault(r["at"].date(), []).append(r["value"])
    return [(day, statistics.median(v), len(v)) for day, v in sorted(by_day.items())]


def _limit_for(metric: dict[str, Any]) -> dict[str, Any]:
    lim = dict(metric.get("limit") or {})
    if lim.get("kind") == "oil_min_mark":
        try:
            from .. import bootstrap  # noqa: F401
            from mes import oil_level
            lim["lo"] = round(float(oil_level.CAPACITY_L) - float(oil_level.dipstick_range_l()), 3)
        except Exception:  # noqa: BLE001
            lim["lo"] = None
    return lim


def _series_for(stream: str, kept: list[dict[str, Any]], excluded: list[tuple[dict[str, Any], str]],
                spec: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    pts = _daily_points(kept)
    s = analyze_series(pts, spec, d)
    reasons = Counter(why for _r, why in excluded)
    s["stream"] = stream
    s["readings_used"] = len(kept)
    s["excluded"] = {
        "count": len(excluded),
        "reasons": [{"reason": k, "count": v} for k, v in reasons.most_common()],
        "examples": [{"at": r["at"].isoformat(sep=" ") if r["at"] else "", "value": r["value"], "reason": why}
                     for r, why in excluded[:5]],
    }
    return s


def _metric_from(metric: dict[str, Any], readings: list[dict[str, Any]], ctx: _Ctx, activity: list[datetime],
                 d: dict[str, Any], limit: dict[str, Any]) -> dict[str, Any]:
    dec = int(metric.get("decimals", 2))
    spec = {"min_change": metric.get("min_change", 0), "noise_floor": metric.get("noise_floor", 0),
            "decimals": dec, "unit": metric["unit"], "lo": limit.get("lo"), "hi": limit.get("hi")}
    by_stream: dict[str, tuple[list, list]] = {}
    for r in readings:
        kept, exc = by_stream.setdefault(r["stream"], ([], []))
        if r["at"] is None:
            exc.append((r, "no timestamp"))
            continue
        why = r["excluded"] or check_condition(r, metric.get("condition") or {}, ctx, activity, d)
        (exc if why else kept).append((r, why) if why else r)
    series = [_series_for(st, kept, exc, spec, d) for st, (kept, exc) in by_stream.items()]
    series.sort(key=lambda s: (-_PRIORITY[s["status"]], -s["n"], s["stream"]))
    primary = series[0] if series else None
    status = primary["status"] if primary else "no_data"
    label, chip, sym = STATUS[status]
    return {
        "id": metric["id"], "label": metric["label"], "unit": metric["unit"], "decimals": dec,
        "why": metric.get("why", ""), "condition_text": metric.get("condition_text", ""),
        "limit": {"lo": limit.get("lo"), "hi": limit.get("hi"), "text": limit.get("text", ""),
                  "kind": limit.get("kind", "")},
        "status": status, "status_label": label, "chip": chip, "symbol": sym,
        "series": series,
        "n": primary["n"] if primary else 0,
        "detail": (primary["detail"] if primary else "no readings from any source yet"),
        "sentence": _sentence(metric, primary, dec) if primary else "",
    }


def _sentence(metric: dict[str, Any], s: dict[str, Any], dec: int) -> str:
    label, unit, st = metric["label"], metric["unit"], s["status"]
    if st in ("no_data",):
        return ""
    if st == "not_enough_data":
        return f"{label}: {s['detail']}"
    first, last = _fmt(s["first"], dec), _fmt(s["last"], dec)
    if st == "past_limit":
        return f"{label} is past its limit: {last} {unit} (limit {s['margin']['limit']:g})"
    base = f"{label} {s['direction']}: {first} → {last} {unit} over {s['n']} visits"
    if st == "heading_to_limit":
        return f"{base}; {s['projection']['text']}"
    if st == "shifted":
        c = s["cusum"]
        return (f"{label} shifted {c['direction']} since {c['since']}: {_fmt(c['baseline'], dec)} → "
                f"{_fmt(c['recent'], dec)} {unit} ({s['n']} visits)")
    if st == "drifting":
        return base
    if st == "moving_away":
        c = s.get("cusum")
        if c:
            return (f"{label} shifted {c['direction']} since {c['since']}: {_fmt(c['baseline'], dec)} → "
                    f"{_fmt(c['recent'], dec)} {unit} ({s['n']} visits), away from its limit")
        return f"{base}, away from its limit"
    return f"{label} steady: {first} → {last} {unit} over {s['n']} visits"


def _lim_pair(lo: Optional[float], hi: Optional[float]) -> str:
    parts = ([f"min {lo:g}"] if lo is not None else []) + ([f"max {hi:g}"] if hi is not None else [])
    return " ".join(parts) or "none"


def compute(readings: list[dict[str, Any]], activity: list[datetime], cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Pure: readings in, trends out. (Tests feed synthetic readings here.)"""
    cfg = cfg or load_config()
    d = cfg["defaults"]
    ctx = _Ctx(readings, d["context_window_s"])
    metrics: list[dict[str, Any]] = []
    for m in cfg["metrics"]:
        rs = [r for r in readings if r["q"] == m["quantity"]]
        metrics.append(_metric_from(m, rs, ctx, activity, d, _limit_for(m)))
    not_trendable: list[dict[str, Any]] = []
    m6 = cfg.get("mode06") or {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in readings:
        if r["q"].startswith("m06:"):
            groups.setdefault(r["q"], []).append(r)
    for q, rs in sorted(groups.items()):
        usable = [r for r in rs if not r["excluded"]]
        r0 = rs[0]
        label = f"Mode 06 {r0.get('mid')} {r0.get('mid_name') or ''} (test {r0.get('tid')})".replace("  ", " ")
        if not usable:
            why = Counter(r["excluded"] for r in rs).most_common(1)[0][0]
            not_trendable.append({"label": label, "reason": why, "readings": len(rs)})
            continue
        latest = max(usable, key=lambda r: r["at"])
        unit = latest["unit"] or ""
        ref = [x for x in (latest["lo"], latest["hi"]) if x is not None]
        scale = max([abs(latest["value"])] + [abs(x) for x in ref]) or 1.0
        mc = float(m6.get("min_change_fraction_of_range", 0.05)) * scale
        if latest["lo"] is not None and latest["hi"] is not None:
            lim_txt = (f"the test's own Mode 06 limits {latest['lo']:g} to {latest['hi']:g} {unit} "
                       "(latest stored reply)")
        elif latest["hi"] is not None:
            lim_txt = f"the test's own Mode 06 maximum {latest['hi']:g} {unit} (latest stored reply; no minimum set)"
        elif latest["lo"] is not None:
            lim_txt = f"the test's own Mode 06 minimum {latest['lo']:g} {unit} (latest stored reply; no maximum set)"
        else:
            lim_txt = "no usable limit in the reply (placeholders ignored): drift only"
        varies = sorted({(r["lo"], r["hi"]) for r in usable}, key=str)
        if len(varies) > 1:
            lim_txt += (f"; the ECM reported different limits on different days "
                        f"({'; '.join(_lim_pair(*v) for v in varies)}), the latest is used")
        mm = {"id": q.replace(":", "_"), "label": label, "unit": unit, "quantity": q,
              "decimals": int(m6.get("decimals", 0)),
              "why": "The ECM's own monitor result against the limits it reports; the margin shrinking visit by visit warns before the monitor fails.",
              "condition_text": "Any stored Mode 06 reply that carried a numeric value in a known unit.",
              "min_change": mc, "noise_floor": mc / 5.0}
        lim = {"lo": latest["lo"], "hi": latest["hi"], "kind": "data", "text": lim_txt}
        metrics.append(_metric_from(mm, usable, ctx, activity, d, lim))
        ex = [r for r in rs if r["excluded"]]
        if ex and metrics[-1]["series"]:
            metrics[-1]["series"][0]["excluded"]["count"] += len(ex)
    flagged = [m for m in metrics if _PRIORITY[m["status"]] >= _PRIORITY["drifting"]]
    flagged.sort(key=lambda m: (-_PRIORITY[m["status"]],
                                (m["series"][0].get("projection") or {}).get("days") or 10 ** 9))
    enough = [m for m in metrics if m["status"] not in ("no_data", "not_enough_data")]
    most = max((m["n"] for m in metrics), default=0)
    if flagged:
        top = flagged[0]
        headline = {"text": top["sentence"], "level": top["status"], "metric_id": top["id"]}
    elif enough:
        headline = {"text": f"No drift flagged. {len(enough)} of {len(metrics)} trends have enough data and none is moving "
                            "toward its limit.", "level": "steady", "metric_id": ""}
    else:
        headline = {"text": f"Not enough data yet to call any trend: the most samples any one trend has is {most} "
                            f"(each needs at least {d['min_points']}, one per visit day).", "level": "not_enough_data",
                    "metric_id": ""}
    label, chip, sym = STATUS[headline["level"]]
    headline.update(status_label=label, chip=chip, symbol=sym)
    return {"headline": headline, "metrics": metrics, "not_trendable": not_trendable,
            "counts": {"metrics": len(metrics), "flagged": len(flagged), "with_enough_data": len(enough),
                       "most_samples": most},
            "method": {
                "aggregate": d["aggregate"],
                "slope": "least-squares line through the daily points; the change is slope times the span",
                "drift_flag": "flagged only when the line's change is at least the metric's min_change and the second half of the points sits on the same side of the first half",
                "shift_flag": "two-sided CUSUM against the first points (slack 0.5 sd, decision limit 4 sd, noise floor per metric)",
                "projection": (f"shown only with at least {d['projection_min_points']} samples spanning "
                               f"{d['projection_min_span_days']} days and a slope heading toward a limit; "
                               "straight-line extrapolation, not a promise"),
                "untagged_vin_rule": d["untagged_vin_rule"],
            }}


def _stamp(vin: str) -> tuple:
    from ..live import config as live_config
    from ..live import store
    sd = Path(live_config.state_dir())
    try:
        from . import mes_bridge
        mes = mes_bridge.newest_mtime(vin)
    except Exception:  # noqa: BLE001
        mes = None
    try:
        from ..live import load_step
        rd = Path(load_step.recordings_dir())
        rec = sorted((p.name, _file_stamp(p)) for p in rd.glob("live_load-step*")) if rd.is_dir() else []
    except Exception:  # noqa: BLE001
        rec = []
    return (vin, _file_stamp(Path(store.observations_path())), _file_stamp(sd / "live_snapshots.jsonl"),
            _file_stamp(sd / "sensor_checks.jsonl"), mes, tuple(rec), _file_stamp(CONFIG_PATH),
            str(sd / "recordings" / vin))


def panel(vin: str) -> dict[str, Any]:
    """Trends for one VIN, memoised on the stored files' state (never re-reads the 2+ MB file per request)."""
    def build() -> dict[str, Any]:
        cfg = load_config()
        readings, activity = collect(vin, cfg)
        result = compute(readings, activity, cfg)
        result["vin"] = vin
        result["generated_at"] = datetime.now().isoformat(timespec="seconds")
        result["sources_note"] = ("observations.jsonl, live snapshots, sensor checks, real MES FES logs, load-step and "
                                  "CUORE recordings. Simulated MES logs and other VINs are not used.")
        return result
    return cache.get_or_build(("trends", _stamp(vin)), build)


__all__ = ["panel", "compute", "collect", "analyze_series", "cusum_shift", "check_condition", "clean_channel",
           "load_config", "STATUS"]
