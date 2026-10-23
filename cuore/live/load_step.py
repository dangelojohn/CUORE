"""Load-step voltage test: start it as a named recording, and analyse the result.

READ-ONLY. It uses the ordinary live poller (ATRV, Mode 01 PID 42, UDS 0x22
on the BCM) and a CSV recording; it writes nothing to the car. The owner
switches loads (headlights, rear defrost, ...) by hand to a timed on-screen
script; every CSV row carries the current step in its TAG column, and a
``.json`` sidecar next to the CSV records the script and column order.

What the analysis does, and does not, claim
-------------------------------------------
For each load: the voltage each channel read while the load was ON (median
after a short settle) minus what it read in the seconds just before the load
was switched on. That is the channel's *drop* for that load. The adapter's
ATRV reading is measured at the OBD port. A module whose drop exceeds the
adapter's drop by more than ``excess_drop_limit_v`` (0.3 V) lost that extra
voltage somewhere between the battery/charging system and the module --
INFERENCE: resistance in that module's feed or ground path. It is a lead that
a multimeter voltage-drop test (docs/maintenance/GROUND_VOLTAGE_DROP_TEST.md)
should confirm, not a measurement of the wiring.

Limits worth knowing:
* the BCM DID 1004 has 0.1 V resolution (A/10): one count is a third of the limit;
* PID 42 is answered by several ECUs on this car (ECM 14.312 V and TCM
  14.062 V on 2026-10-23); the poller keeps the first reply, i.e. the ECM;
* with the engine running the alternator regulator reacts to load, so the
  absolute drop can be zero or negative -- the *difference to the adapter* is
  what is compared, which cancels most of that;
* only 6.5 s of data per ON window: a single flagged step is "repeat it",
  two or more flagged steps on one module is a pattern.

Reference for the 0.2-0.5 V voltage-drop limits (general automotive, not
Alfa-specific): https://www.fluke.com/en-us/learn/blog/digital-multimeters/how-to-check-starter-circuit-voltage-drop-with-a-multimeter
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

PRESET = "load_step_voltage"
ADAPTER_CHANNEL = "battery_voltage"
#: channel id -> what it measures (for the report)
MODULE_CHANNELS = {
    "control_module_voltage": {"module": "ECM", "via": "Mode 01 PID 42 (first ECU to answer)",
                               "resolution_v": 0.001},
    "bcm_1004": {"module": "BCM", "via": "UDS 22 1004, A/10 (formula unverified)",
                 "resolution_v": 0.1},
}
REFERENCE_URL = ("https://www.fluke.com/en-us/learn/blog/digital-multimeters/"
                 "how-to-check-starter-circuit-voltage-drop-with-a-multimeter")

_LOCK = threading.RLock()
_RUN: dict[str, Any] = {}


def spec() -> dict[str, Any]:
    return channels_mod.recording_presets()[PRESET]


def describe() -> dict[str, Any]:
    """The preset, its script, and which channels are really in the registry."""
    sp = spec()
    reg = channels_mod.registry()
    sp["channel_detail"] = [reg[c].to_dict() for c in sp["channels"] if c in reg]
    sp["missing_channels"] = [c for c in sp["channels"] if c not in reg]
    sp["module_channels"] = MODULE_CHANNELS
    sp["reference_url"] = REFERENCE_URL
    return sp


# --- run ---------------------------------------------------------------------

def _step_at(script: list[dict[str, Any]], t: float) -> Optional[dict[str, Any]]:
    for s in script:
        if s["t0"] <= t < s["t1"]:
            return s
    return None


def _tag_for(step: dict[str, Any]) -> str:
    return f"{step['state'].upper()} {step['load'] or '-'}"


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
            rec = pol.stop_recording()
            rows = rec.get("rows")
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
    side = Path(csv_path).with_suffix(".json")
    try:
        side.write_text(json.dumps({
            "test": PRESET, "csv": Path(csv_path).name, "label": _RUN.get("label", ""),
            "started": _RUN.get("started"), "ended": _RUN.get("ended"),
            "aborted": _RUN.get("aborted"), "rows": _RUN.get("rows"),
            "columns": _RUN.get("columns"), "script": _RUN.get("script"),
            "duration_s": _RUN.get("duration_s"), "requested_rate_hz": _RUN.get("rate_hz"),
            "settle_s": _RUN.get("settle_s"), "reference_window_s": _RUN.get("reference_window_s"),
            "excess_drop_limit_v": _RUN.get("limit_v"),
            "note": "read-only recording; TAG column = script step; Time = seconds since recorder start",
        }, indent=2), encoding="utf-8")
    except OSError:
        pass


def start(label: str = "") -> dict[str, Any]:
    """Start the poll session on the preset's channels at the requested rate and
    record it under a name. Refuses (BadCommand/Refused/LinkUnavailable) exactly
    when an ordinary ``live_session_start`` would. NOT called by anything at
    import time: the owner starts it, from the page or the API."""
    with _LOCK:
        if _RUN and not _RUN.get("ended") and poller_mod.poller().is_active():
            raise Refused("a load-step test is already running")
    sp = spec()
    chans = channels_mod.resolve_channels(preset=PRESET)
    rates = {c.id: float(sp["rate_hz"]) for c in chans}
    pol = poller_mod.poller()
    pol.start(chans, rates=rates)
    try:
        rec = pol.start_recording(name=f"load-step-voltage_{label}" if label else "load-step-voltage")
    except Exception:
        pol.stop()
        raise
    stop = threading.Event()
    with _LOCK:
        _RUN.clear()
        _RUN.update({
            "csv": rec["recording"], "columns": rec.get("columns"), "label": label,
            "started": datetime.now().isoformat(timespec="seconds"), "script": sp["script"],
            "duration_s": sp["duration_s"], "rate_hz": sp["rate_hz"], "settle_s": sp["settle_s"],
            "reference_window_s": sp["reference_window_s"], "limit_v": sp["excess_drop_limit_v"],
            "stop": stop, "ended": None,
        })
        _write_sidecar()
    threading.Thread(target=_script_thread, args=(float(sp["duration_s"]), sp["script"], stop),
                     name="cuore-load-step", daemon=True).start()
    return {"started": True, "recording": rec["recording"], "duration_s": sp["duration_s"],
            "requested_rate_hz": sp["rate_hz"], "channels": [c.id for c in chans]}


def stop() -> dict[str, Any]:
    with _LOCK:
        ev = _RUN.get("stop")
    if ev is None or _RUN.get("ended"):
        return {"stopped": False, "note": "no load-step test running"}
    ev.set()
    return {"stopped": True}


def status() -> dict[str, Any]:
    """Where the script is now: elapsed (the recorder's own clock), current and next step."""
    with _LOCK:
        run = dict(_RUN)
    if not run:
        return {"running": False, "note": "no load-step test has been started in this server session"}
    pol = poller_mod.poller()
    el = pol.recording_elapsed()
    running = el is not None and not run.get("ended")
    script = run["script"]
    out: dict[str, Any] = {
        "running": running, "recording": run["csv"], "label": run.get("label", ""),
        "duration_s": run["duration_s"], "ended": run.get("ended"), "aborted": run.get("aborted"),
        "elapsed_s": round(el, 1) if el is not None else None,
    }
    if running:
        cur = _step_at(script, el)
        out["step"] = cur
        out["step_remaining_s"] = round(cur["t1"] - el, 1) if cur else None
        out["next_step"] = next((s for s in script if cur and s["t0"] >= cur["t1"]), None)
        snap = pol.snapshot()["channels"]
        out["values"] = {k: v.get("value") for k, v in snap.items()}
        out["achieved_hz"] = pol.status().get("achieved_hz")
    return out


# --- analysis ------------------------------------------------------------------

def read_recording(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rows ``{t, tag, <channel_id>: float|None}`` from a CUORE recording CSV,
    and its sidecar (``{}`` when absent -- the preset's channel order is then used)."""
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


def _median(rows: list[dict[str, Any]], cid: str, t0: float, t1: float) -> tuple[Optional[float], int]:
    vals = [r[cid] for r in rows if t0 <= r["t"] < t1 and r.get(cid) is not None]
    return (statistics.median(vals), len(vals)) if vals else (None, 0)


def analyze(rows: list[dict[str, Any]], script: Optional[list[dict[str, Any]]] = None, *,
            limit_v: Optional[float] = None, settle_s: Optional[float] = None,
            ref_s: Optional[float] = None) -> dict[str, Any]:
    """Per load-step drops and the excess of each module's drop over the adapter's.

    ``rows`` = ``[{t, battery_voltage, control_module_voltage, bcm_1004, ...}]``.
    """
    sp = spec()
    script = script or sp["script"]
    limit_v = sp["excess_drop_limit_v"] if limit_v is None else limit_v
    settle_s = sp["settle_s"] if settle_s is None else settle_s
    ref_s = sp["reference_window_s"] if ref_s is None else ref_s
    present = [c for c in (ADAPTER_CHANNEL, *MODULE_CHANNELS) if any(r.get(c) is not None for r in rows)]

    steps: list[dict[str, Any]] = []
    for s in script:
        if s["state"] != "on":
            continue
        ref0, ref1 = s["t0"] - ref_s, s["t0"] - 0.5
        on0, on1 = s["t0"] + settle_s, s["t1"] - 0.25
        entry: dict[str, Any] = {"load": s["load"], "label": s["label"], "t0": s["t0"], "t1": s["t1"],
                                 "ref_v": {}, "on_v": {}, "drop_v": {}, "samples": {}}
        for c in present:
            rv, rn = _median(rows, c, ref0, ref1)
            ov, on = _median(rows, c, on0, on1)
            entry["samples"][c] = {"ref": rn, "on": on}
            if rv is not None and ov is not None and rn >= 3 and on >= 3:
                entry["ref_v"][c], entry["on_v"][c] = round(rv, 3), round(ov, 3)
                entry["drop_v"][c] = round(rv - ov, 3)
        ad = entry["drop_v"].get(ADAPTER_CHANNEL)
        entry["adapter_drop_v"] = ad
        entry["excess_v"] = {}
        entry["flagged"] = []
        if ad is not None:
            for c in MODULE_CHANNELS:
                if c in entry["drop_v"]:
                    ex = round(entry["drop_v"][c] - ad, 3)
                    entry["excess_v"][c] = ex
                    if ex > limit_v:
                        entry["flagged"].append(c)
        steps.append(entry)

    modules = []
    for c, meta in MODULE_CHANNELS.items():
        ex = [st["excess_v"][c] for st in steps if c in st["excess_v"]]
        flagged = [st["label"] for st in steps if c in st["flagged"]]
        if not ex:
            verdict = "no usable data (channel missing or too few samples in the windows)"
        elif len(flagged) >= 2:
            verdict = (f"INFERENCE: drops more than {limit_v} V beyond the adapter in {len(flagged)} steps -- "
                       "points at resistance in this module's feed or ground; confirm with the multimeter "
                       "voltage-drop test")
        elif len(flagged) == 1:
            verdict = "one step over the limit -- repeat the test before reading anything into it"
        else:
            verdict = f"no step more than {limit_v} V beyond the adapter -- no sign of extra resistance in its feed/ground"
        if ex and meta["resolution_v"] >= 0.1:
            verdict += f" (resolution {meta['resolution_v']} V: one count is a third of the limit)"
        modules.append({"channel": c, **meta, "steps_evaluated": len(ex), "flagged_steps": flagged,
                        "max_excess_v": max(ex) if ex else None,
                        "median_excess_v": round(statistics.median(ex), 3) if ex else None,
                        "verdict": verdict})

    ad_drops = [st["adapter_drop_v"] for st in steps if st["adapter_drop_v"] is not None]
    return {
        "test": PRESET, "limit_v": limit_v, "settle_s": settle_s, "reference_window_s": ref_s,
        "channels_present": present, "rows": len(rows),
        "adapter": {"channel": ADAPTER_CHANNEL,
                    "max_drop_v": max(ad_drops) if ad_drops else None,
                    "note": "ATRV is read at the OBD port; a drop there is shared by every module "
                            "and says nothing about any one module's own wiring"},
        "steps": steps, "modules": modules,
        "caveats": [
            "Drops are medians over short windows; the alternator regulator also reacts to load.",
            "A module's excess drop is an INFERENCE of extra resistance, not a measurement of it.",
            "PID 42 is the first ECU to answer (ECM); the TCM also answers it but is not kept.",
            "A fault in the adapter's own lead/DLC pins would look like the adapter dropping LESS than modules.",
        ],
        "reference": REFERENCE_URL,
    }


def recordings_dir() -> Path:
    return state_dir() / "recordings"


def latest_recording() -> Optional[Path]:
    files = sorted(recordings_dir().glob("live_load-step-voltage*.csv"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def analyze_recording(name: str = "") -> dict[str, Any]:
    """Analyse a saved load-step CSV by file name (default: the newest)."""
    if name:
        p = recordings_dir() / Path(name).name          # no path traversal
        if not p.is_file() or p.suffix.lower() != ".csv":
            raise BadCommand(f"no such recording {name!r} in the recordings folder")
    else:
        p = latest_recording()
        if p is None:
            raise BadCommand("no load-step recording exists yet; run the test first")
    rows, side = read_recording(p)
    out = analyze(rows, side.get("script") or None, limit_v=side.get("excess_drop_limit_v"),
                  settle_s=side.get("settle_s"), ref_s=side.get("reference_window_s"))
    out["recording"] = p.name
    out["complete"] = bool(side) and not side.get("aborted") and side.get("ended") is not None
    if side.get("aborted"):
        out["caveats"].append("The run was stopped early; steps after the stop have no data.")
    return out


__all__ = ["PRESET", "describe", "start", "stop", "status", "analyze", "analyze_recording",
           "read_recording", "spec"]
