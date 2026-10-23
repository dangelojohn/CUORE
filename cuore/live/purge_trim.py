"""Passive purge-trim EVAP test: record, then analyse. READ-ONLY.

What it is
----------
A 4-minute recording of Mode 01 values (commanded purge PID 2E, short/long fuel
trim PID 06/07, RPM 0C, MAP 0B, load 43, coolant 05, fuel level 2F, ambient 46)
while the engine idles warm and the owner touches nothing. The ECM opens and
closes the purge valve on its own schedule; the analysis looks at what the fuel
trims did when it opened. Nothing is written to the car: no Mode 08, no UDS
2F/31, no clearing. It uses the ordinary live poller and a CSV recording, like
:mod:`cuore.live.load_step` (same start/stop/status/analysis shape).

What the analysis does, and does not, claim
-------------------------------------------
* PID 2E is the ECM's COMMANDED purge percentage, not measured flow. This car's
  ESIM-based EVAP system has no vapour-pressure sensor, so there is no flow or
  pressure reading to cross-check it with.
* "Purge on" = commanded purge >= ``on_threshold_pct`` (1 %). "Purge off" = below.
* For every off -> on transition with a baseline: STFT baseline (median of the
  5 s before) versus the lowest STFT in the 10 s after. When the canister holds
  fuel vapour and the purge path flows, the extra fuel pulls the short-term trim
  NEGATIVE (the ECM removes injected fuel). A dip of at least ``dip_response_pct``
  (3 %) with steady RPM and MAP is read as "a response". That is INFERENCE.
* No response is NOT "purge dead": an empty or lightly loaded canister (a recent
  long drive, low vapour load) gives no trim response through a healthy valve.
* If PID 2E never leaves 0 % the ECM did not command purge in the window; that
  is "inconclusive", never "purge dead".
* If PID 2E is missing from the recording the analysis degrades to trims only
  (STFT excursions); nothing can then be attributed to purge.

General reference (not Alfa-specific, background only):
https://en.wikipedia.org/wiki/Evaporative_emissions_control
"""

from __future__ import annotations

import csv
import json
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import channels as channels_mod
from . import poller as poller_mod
from .config import state_dir
from .errors import BadCommand, Refused
from .load_step import _step_at, _tag_for

PRESET = "purge_trim"
PURGE = "commanded_evap_purge"
STFT = "short_fuel_trim_b1"
LTFT = "long_fuel_trim_b1"
RPM = "engine_rpm"
MAP = "intake_map"
LOAD = "absolute_load"
COOLANT = "engine_coolant_temp"
FUEL = "fuel_level"
AMBIENT = "ambient_air_temp"
REFERENCE_URL = "https://en.wikipedia.org/wiki/Evaporative_emissions_control"
NOT_COMMANDED = ("ECM did not command purge in this window (conditions not met: warm-up, "
                 "time since start, fuel level) -- inconclusive")
WARM_COOLANT_C = 75.0
STEADY_RPM = 150.0
STEADY_MAP_KPA = 5.0

_LOCK = threading.RLock()
_RUN: dict[str, Any] = {}


def spec() -> dict[str, Any]:
    return channels_mod.recording_presets()[PRESET]


def describe() -> dict[str, Any]:
    sp = spec()
    reg = channels_mod.registry()
    sp["channel_detail"] = [reg[c].to_dict() for c in sp["channels"] if c in reg]
    sp["missing_channels"] = [c for c in sp["channels"] if c not in reg]
    sp["reference_url"] = REFERENCE_URL
    sp["not_included"] = {"evap_vapor_pressure": "not supported: the FCA ESIM system has no pressure sensor",
                          "pid_04_calculated_load": "supported by the ECM but no decoder in cuore.live.obd; "
                                                    "PID 43 absolute_load is recorded instead"}
    return sp


# --- run -----------------------------------------------------------------------

def _script_thread(duration: float, script: list[dict[str, Any]], stop: threading.Event) -> None:
    pol = poller_mod.poller()
    last_tag = None
    aborted = False
    try:
        while True:
            el = pol.recording_elapsed()
            if el is None or not pol.is_active() or stop.is_set():
                aborted = el is None or stop.is_set() or el < duration
                break
            if el >= duration:
                break
            step = _step_at(script, el)
            tag = _tag_for(step) if step else ""
            if tag != last_tag:
                pol.set_recording_tag(tag)
                last_tag = tag
            time.sleep(0.1)
    finally:
        rows = None
        try:
            rows = pol.stop_recording().get("rows")
        except Exception:  # noqa: BLE001
            pass
        try:
            pol.stop()
        except Exception:  # noqa: BLE001
            pass
        with _LOCK:
            _RUN["ended"] = datetime.now().isoformat(timespec="seconds")
            _RUN["aborted"] = aborted
            _RUN["rows"] = rows
            _write_sidecar()


def _write_sidecar() -> None:
    csv_path = _RUN.get("csv")
    if not csv_path:
        return
    try:
        Path(csv_path).with_suffix(".json").write_text(json.dumps({
            "test": PRESET, "csv": Path(csv_path).name, "label": _RUN.get("label", ""),
            "started": _RUN.get("started"), "ended": _RUN.get("ended"),
            "aborted": _RUN.get("aborted"), "rows": _RUN.get("rows"),
            "columns": _RUN.get("columns"), "script": _RUN.get("script"),
            "duration_s": _RUN.get("duration_s"), "requested_rates_hz": _RUN.get("rates"),
            "on_threshold_pct": _RUN.get("on_threshold_pct"), "dip_window_s": _RUN.get("dip_window_s"),
            "dip_baseline_s": _RUN.get("dip_baseline_s"), "dip_response_pct": _RUN.get("dip_response_pct"),
            "note": "read-only passive recording; Mode 01 only; PID 2E is the COMMANDED purge %",
        }, indent=2), encoding="utf-8")
    except OSError:
        pass


def start(label: str = "") -> dict[str, Any]:
    """Start the poll session on the preset's channels and record it under a name.
    Read-only. NOT called at import time: the owner starts it, from the page or API."""
    with _LOCK:
        if _RUN and not _RUN.get("ended") and poller_mod.poller().is_active():
            raise Refused("a purge-trim test is already running")
    sp = spec()
    chans = channels_mod.resolve_channels(preset=PRESET)
    rates = {c.id: float(sp["rates_hz"].get(c.id, sp["rate_hz"])) for c in chans}
    pol = poller_mod.poller()
    pol.start(chans, rates=rates)
    try:
        rec = pol.start_recording(name=f"purge-trim_{label}" if label else "purge-trim")
    except Exception:
        pol.stop()
        raise
    stop_ev = threading.Event()
    with _LOCK:
        _RUN.clear()
        _RUN.update({
            "csv": rec["recording"], "columns": rec.get("columns"), "label": label,
            "started": datetime.now().isoformat(timespec="seconds"), "script": sp["script"],
            "duration_s": sp["duration_s"], "rates": rates,
            "on_threshold_pct": sp["on_threshold_pct"], "dip_window_s": sp["dip_window_s"],
            "dip_baseline_s": sp["dip_baseline_s"], "dip_response_pct": sp["dip_response_pct"],
            "stop": stop_ev, "ended": None,
        })
        _write_sidecar()
    threading.Thread(target=_script_thread, args=(float(sp["duration_s"]), sp["script"], stop_ev),
                     name="cuore-purge-trim", daemon=True).start()
    return {"started": True, "recording": rec["recording"], "duration_s": sp["duration_s"],
            "requested_rates_hz": rates, "channels": [c.id for c in chans]}


def stop() -> dict[str, Any]:
    with _LOCK:
        ev = _RUN.get("stop")
    if ev is None or _RUN.get("ended"):
        return {"stopped": False, "note": "no purge-trim test running"}
    ev.set()
    return {"stopped": True}


def status() -> dict[str, Any]:
    """Elapsed time (the recorder's clock), the step, and the live values."""
    with _LOCK:
        run = dict(_RUN)
    if not run:
        return {"running": False, "note": "no purge-trim test has been started in this server session"}
    pol = poller_mod.poller()
    el = pol.recording_elapsed()
    running = el is not None and not run.get("ended")
    out: dict[str, Any] = {
        "running": running, "recording": run["csv"], "label": run.get("label", ""),
        "duration_s": run["duration_s"], "ended": run.get("ended"), "aborted": run.get("aborted"),
        "elapsed_s": round(el, 1) if el is not None else None,
    }
    if running:
        cur = _step_at(run["script"], el)
        out["step"] = cur
        out["step_remaining_s"] = round(cur["t1"] - el, 1) if cur else None
        snap = pol.snapshot()["channels"]
        out["values"] = {k: v.get("value") for k, v in snap.items()}
        out["units"] = {k: v.get("unit") for k, v in snap.items()}
        out["achieved_hz"] = pol.status().get("achieved_hz")
    return out


# --- analysis ------------------------------------------------------------------

def read_recording(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rows ``{t, tag, <channel_id>: float|None}`` from a CUORE recording CSV and its sidecar."""
    side: dict[str, Any] = {}
    sp = path.with_suffix(".json")
    if sp.exists():
        try:
            side = json.loads(sp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            side = {}
    cols = side.get("columns") or list(channels_mod.PRESETS[PRESET])
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as f:
        rd = csv.reader(f, delimiter="\t")
        next(rd, None)   # names
        next(rd, None)   # units
        for r in rd:
            if not r:
                continue
            try:
                t = float(r[0])
            except ValueError:
                continue
            row: dict[str, Any] = {"t": t, "tag": r[-1].strip('"') if len(r) > len(cols) + 1 else ""}
            for i, cid in enumerate(cols, start=1):
                try:
                    row[cid] = float(r[i]) if i < len(r) and r[i] != "" else None
                except ValueError:
                    row[cid] = None
            rows.append(row)
    return rows, side


def _vals(rows: list[dict[str, Any]], cid: str) -> list[float]:
    return [r[cid] for r in rows if r.get(cid) is not None]


def _mean(rows: list[dict[str, Any]], cid: str) -> Optional[float]:
    v = _vals(rows, cid)
    return round(statistics.fmean(v), 3) if v else None


def _med(rows: list[dict[str, Any]], cid: str) -> Optional[float]:
    v = _vals(rows, cid)
    return round(statistics.median(v), 3) if v else None


def _seg(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean/median figures for one segment of rows."""
    t = rows[-1]["t"] - rows[0]["t"] if len(rows) > 1 else 0.0
    return {"rows": len(rows), "span_s": round(t, 1),
            "stft_mean": _mean(rows, STFT), "ltft_mean": _mean(rows, LTFT),
            "rpm_mean": _mean(rows, RPM), "map_mean": _mean(rows, MAP),
            "load_mean": _mean(rows, LOAD)}


def _events(rows: list[dict[str, Any]], thr: float, base_s: float, win_s: float,
            resp_pct: float) -> list[dict[str, Any]]:
    """Every off -> on transition of the commanded purge that has a baseline."""
    pr = [r for r in rows if r.get(PURGE) is not None]
    out: list[dict[str, Any]] = []
    for i in range(1, len(pr)):
        if not (pr[i - 1][PURGE] < thr <= pr[i][PURGE]):
            continue
        t0 = pr[i]["t"]
        before = [r for r in rows if t0 - base_s <= r["t"] < t0 and r.get(STFT) is not None
                  and (r.get(PURGE) is None or r[PURGE] < thr)]
        after = [r for r in rows if t0 <= r["t"] < t0 + win_s and r.get(STFT) is not None]
        ev: dict[str, Any] = {"t_open_s": round(t0, 1), "baseline_rows": len(before), "after_rows": len(after)}
        if len(before) < 3 or len(after) < 3:
            ev["usable"] = False
            ev["why"] = "too few STFT samples before/after the opening"
            out.append(ev)
            continue
        base = statistics.median(r[STFT] for r in before)
        low = min(after, key=lambda r: r[STFT])
        ev.update({
            "usable": True, "stft_baseline": round(base, 2), "stft_min_after": round(low[STFT], 2),
            "t_min_s": round(low["t"], 1), "lag_s": round(low["t"] - t0, 1),
            "dip_pct": round(low[STFT] - base, 2),
            "purge_peak_pct": round(max((r[PURGE] for r in rows if t0 <= r["t"] < t0 + win_s
                                         and r.get(PURGE) is not None), default=pr[i][PURGE]), 1),
        })
        rb, ra = _med(before, RPM), _med(after, RPM)
        mb, ma = _med(before, MAP), _med(after, MAP)
        ev["rpm_change"] = round(ra - rb, 1) if rb is not None and ra is not None else None
        ev["map_change_kpa"] = round(ma - mb, 1) if mb is not None and ma is not None else None
        ev["steady"] = (ev["rpm_change"] is not None and abs(ev["rpm_change"]) <= STEADY_RPM
                        and (ev["map_change_kpa"] is None or abs(ev["map_change_kpa"]) <= STEADY_MAP_KPA))
        ev["response"] = ev["dip_pct"] <= -resp_pct
        out.append(ev)
    return out


def _excursions(rows: list[dict[str, Any]], resp_pct: float) -> dict[str, Any]:
    v = _vals(rows, STFT)
    if not v:
        return {"median": None, "excursions": []}
    med = statistics.median(v)
    exc: list[dict[str, Any]] = []
    cur: Optional[dict[str, Any]] = None
    for r in rows:
        x = r.get(STFT)
        if x is None:
            continue
        if abs(x - med) >= resp_pct:
            if cur is None:
                cur = {"t0": round(r["t"], 1), "t1": round(r["t"], 1), "extreme": x}
            cur["t1"] = round(r["t"], 1)
            if abs(x - med) > abs(cur["extreme"] - med):
                cur["extreme"] = x
        elif cur is not None:
            exc.append(cur)
            cur = None
    if cur is not None:
        exc.append(cur)
    for e in exc:
        e["extreme"] = round(e["extreme"], 2)
    return {"median": round(med, 2), "excursions": exc}


def analyze(rows: list[dict[str, Any]], *, thr: Optional[float] = None, base_s: Optional[float] = None,
            win_s: Optional[float] = None, resp_pct: Optional[float] = None) -> dict[str, Any]:
    sp = spec()
    thr = sp["on_threshold_pct"] if thr is None else thr
    base_s = sp["dip_baseline_s"] if base_s is None else base_s
    win_s = sp["dip_window_s"] if win_s is None else win_s
    resp_pct = sp["dip_response_pct"] if resp_pct is None else resp_pct
    present = [c for c in channels_mod.PRESETS[PRESET] if any(r.get(c) is not None for r in rows)]
    out: dict[str, Any] = {
        "test": PRESET, "rows": len(rows), "channels_present": present,
        "span_s": round(rows[-1]["t"] - rows[0]["t"], 1) if len(rows) > 1 else 0.0,
        "on_threshold_pct": thr, "dip_response_pct": resp_pct,
        "dip_baseline_s": base_s, "dip_window_s": win_s,
        "overall": _seg(rows) if rows else {},
        "reference": REFERENCE_URL,
        "caveats": [
            "PID 2E is the ECM's COMMANDED purge %, not measured flow; this car has no EVAP pressure sensor to cross-check it.",
            "The trim response is INFERENCE from general EVAP behaviour (reference link), not a measurement of the purge path.",
            "No trim response is not proof of a dead purge path: an empty canister gives none through a healthy valve.",
            "STFT also moves with throttle, load and closed-loop state; events are only used when RPM and MAP stayed steady.",
        ],
    }
    ctx: dict[str, Any] = {"coolant_first_c": None, "coolant_last_c": None, "fuel_level_pct": _med(rows, FUEL),
                           "ambient_c": _med(rows, AMBIENT)}
    cv = _vals(rows, COOLANT)
    if cv:
        ctx["coolant_first_c"], ctx["coolant_last_c"] = round(cv[0], 1), round(cv[-1], 1)
    ctx["warm"] = (ctx["coolant_first_c"] is not None and ctx["coolant_first_c"] >= WARM_COOLANT_C)
    out["context"] = ctx
    if not rows or STFT not in present:
        out["mode"] = "no_data"
        out["verdict"] = "no usable short-term trim data in the recording -- inconclusive"
        return out

    if PURGE not in present:
        out["mode"] = "trims_only"
        out["excursions"] = _excursions(rows, resp_pct)
        out["verdict"] = ("PID 2E (commanded purge) is missing from this recording, so the test degraded to "
                          "trims only: STFT excursions are listed but cannot be attributed to purge -- inconclusive")
        return out

    pmax = max(_vals(rows, PURGE))
    out["purge_max_pct"] = round(pmax, 1)
    if pmax < thr:
        out["mode"] = "not_commanded"
        out["off"] = _seg(rows)
        out["verdict"] = NOT_COMMANDED
        if ctx["coolant_first_c"] is not None and not ctx["warm"]:
            out["verdict"] += f"; coolant was {ctx['coolant_first_c']} C at the start (below {WARM_COOLANT_C:.0f} C)"
        return out

    on_rows = [r for r in rows if r.get(PURGE) is not None and r[PURGE] >= thr]
    off_rows = [r for r in rows if r.get(PURGE) is not None and r[PURGE] < thr]
    out["mode"] = "purge_commanded"
    out["on"], out["off"] = _seg(on_rows), _seg(off_rows)
    out["on_fraction"] = round(len(on_rows) / max(1, len(on_rows) + len(off_rows)), 3)
    evs = _events(rows, thr, base_s, win_s, resp_pct)
    out["events"] = evs
    usable = [e for e in evs if e.get("usable")]
    steady = [e for e in usable if e["steady"]]
    resp = [e for e in steady if e["response"]]
    if not usable:
        out["verdict"] = ("purge was commanded but no off-to-on transition has a usable STFT baseline "
                          "(on from the start, or too few samples) -- inconclusive")
    elif resp:
        worst = min(resp, key=lambda e: e["dip_pct"])
        out["verdict"] = (f"INFERENCE: STFT dipped {worst['dip_pct']} % ({worst['stft_baseline']} -> "
                          f"{worst['stft_min_after']}) within {worst['lag_s']} s of purge opening at "
                          f"t={worst['t_open_s']} s with steady RPM/MAP, in {len(resp)} of {len(usable)} usable "
                          "openings -- consistent with a flowing purge path drawing vapour; it does not "
                          "test the ESIM seal or the leak monitor")
    elif steady:
        out["verdict"] = (f"purge was commanded ({len(steady)} steady opening(s)) but STFT showed no dip of "
                          f"{resp_pct} % or more -- consistent with a non-flowing purge path OR with a "
                          "canister holding little vapour; one passive run cannot separate them (inconclusive)")
    else:
        out["verdict"] = ("purge was commanded but RPM or MAP changed during every opening, so the trim "
                          "movement cannot be attributed to purge -- inconclusive")
    return out


def recordings_dir() -> Path:
    return state_dir() / "recordings"


def latest_recording() -> Optional[Path]:
    files = sorted(recordings_dir().glob("live_purge-trim*.csv"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def analyze_recording(name: str = "") -> dict[str, Any]:
    """Analyse a saved purge-trim CSV by file name (default: the newest)."""
    if name:
        p = recordings_dir() / Path(name).name          # no path traversal
        if not p.is_file() or p.suffix.lower() != ".csv":
            raise BadCommand(f"no such recording {name!r} in the recordings folder")
    else:
        p = latest_recording()
        if p is None:
            raise BadCommand("no purge-trim recording exists yet; run the test first")
    rows, side = read_recording(p)
    out = analyze(rows, thr=side.get("on_threshold_pct"), base_s=side.get("dip_baseline_s"),
                  win_s=side.get("dip_window_s"), resp_pct=side.get("dip_response_pct"))
    out["recording"] = p.name
    out["complete"] = bool(side) and not side.get("aborted") and side.get("ended") is not None
    if side.get("aborted"):
        out["caveats"].append("The run was stopped early; the rest of the window has no data.")
    return out


__all__ = ["PRESET", "describe", "start", "stop", "status", "analyze", "analyze_recording",
           "read_recording", "spec"]
