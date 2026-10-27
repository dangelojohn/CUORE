"""PROTOTYPE - simulated car and two simulated procedures for the interactive-procedure screen.

Nothing here talks to a car. No adapter, no live-transport module, no MCP tool is imported or called; the whole
"car" is a dict of readings plus a set of switchable faults, so every screen state can be shown on the tablet.

Procedures:  esim-vent    engine-running class, proof = EVAP vapour pressure must FALL, guards RPM / speed / voltage.
             service-reset  read-before / save / write / read-back with the 8 service parameters, values from the
                          real 2026-10-23 MES log (docs/vehicles/.../MES_MODULE_READS_2026-10-23.md).

Server-owned stop: STOP, max time (30 s), guard breach, stream disconnect. A one-time token is minted when READY
passes and consumed by the hold-start. Results go to <state dir>/procedure_prototype.jsonl (never the job ledger).
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any, Optional

from . import procedure_dry_bridge as dry_bridge

CLOCK = time.monotonic          # tests replace this
TODAY = date.today              # tests replace this
MAX_RUN = 30.0                  # seconds, server-enforced
PROOF_FALL_OK = 0.20            # kPa fall that counts as WORKED
PROOF_FALL_NONE = 0.05          # less than this = DIDN'T
BANNER = "PROTOTYPE - simulated car, nothing is sent to the Stelvio"

FAULTS = {
    "ignition_off": "Ignition off",
    "engine_stalls": "Engine stalls / is off",
    "moving": "Car moving (12 km/h)",
    "not_in_park": "Gear not in P",
    "voltage_drops": "Battery voltage drops",
    "mes_holding": "MES holding adapter",
    "cable_missing": "Cable not fitted",
    "no_proof": "No proof response",
    "ambiguous_proof": "Weak / ambiguous proof",
}

SERVICE_BEFORE = [
    ("Odometer", "148207.0 km"), ("Distance after last service", "142475 km"), ("Last service date", "09/12/2026"),
    ("Number of services", "0"), ("Service interval", "16000 km"), ("Service period", "365 days"),
    ("Distance till next service", "10268.0 km"), ("Days till next service", "324 days"),
]
SERVICE_CHANGES = {"Distance after last service", "Last service date", "Distance till next service",
                   "Days till next service"}

PROCS: dict[str, dict[str, Any]] = {
    "esim-vent": {
        "title": "ESIM vent test (simulated)", "module": "Engine ECM", "bus": "CAN-C", "kind": "run",
        "why_generic": "Proves the EVAP vent path: the vent valve is commanded and the vapour pressure must fall.",
        "serves": {"codes": ["P0440", "P0455", "P0456", "P1CEA"], "systems": ["evap"], "words": []},
        "hypothesis": "vent path OK", "proof": ("EVAP vapour pressure", "kPa", "falls"),
        "asks": [("hood", "Hood open, hands clear of the fan?")],
        "blurb": "Engine running, stationary in P. Watches vapour pressure fall. 30 s maximum.",
    },
    "service-reset": {
        "title": "Service interval reset (simulated)", "module": "Instrument cluster", "bus": "CAN-C", "kind": "reset",
        "why_generic": "Restarts the service counters after an oil and filter change.",
        "serves": {"codes": [], "systems": ["service", "maintenance"],
                   "words": ["oil change", "oil and filter", "service interval", "service reset", "service counter"]},
        "hypothesis": "service counters restarted", "proof": None,
        "asks": [("oil", "Oil and filter change done on this visit?")],
        "blurb": "Reads the 8 service values, saves them, writes the reset, reads them back.",
    },
}


class SimCar:
    def __init__(self) -> None:
        self.faults: set[str] = set()
        self.answers: set[str] = set()

    def toggle(self, fault: str) -> bool:
        if fault not in FAULTS:
            raise KeyError(fault)
        self.faults ^= {fault}
        return fault in self.faults

    def readings(self) -> dict[str, Any]:
        f = self.faults
        ign = "ignition_off" not in f
        running = ign and "engine_stalls" not in f
        volt = 11.2 if "voltage_drops" in f else (13.9 if running else (12.4 if ign else 12.5))
        return {"ignition": ign, "engine_running": running, "rpm": 780 if running else 0,
                "speed": 12 if "moving" in f else 0, "gear": "D" if "not_in_park" in f else "P",
                "voltage": volt, "mes_holding": "mes_holding" in f, "cable": "cable_missing" not in f}

    def reset(self) -> None:
        self.faults.clear()
        self.answers.clear()


CAR = SimCar()
_LOCK = threading.RLock()
_TOKENS: dict[str, str] = {}          # token -> proc
RUNS: dict[str, "Run"] = {}


#: Existing pages that help with an unblock step. Only real routes; anything else is instruction text + Re-check.
UNBLOCK_LINKS = {"cable": ("/live", "Open the Live page: pick the cable, then Verify")}


def _chip(key: str, label: str, ok: bool, value: str, unblock: str) -> dict[str, Any]:
    href, link_label = ("", "") if ok else UNBLOCK_LINKS.get(key, ("", ""))
    return {"key": key, "label": label, "state": "ok" if ok else "blocked", "value": value,
            "unblock": "" if ok else unblock, "href": href, "link_label": link_label}


def readiness(proc: str, car: Optional[SimCar] = None) -> dict[str, Any]:
    car = car or CAR
    r = car.readings()
    p = PROCS[proc]
    chips = [
        _chip("cable", "Cable fitted", r["cable"], "fitted" if r["cable"] else "not fitted", "Fit the blue A5 cable, then Verify"),
        _chip("mes", "Adapter free", not r["mes_holding"], "free" if not r["mes_holding"] else "MES holding adapter", "Close MES (exit MultiEcuScan fully, not just minimise), then Re-check"),
        _chip("ignition", "Ignition on", r["ignition"], "on" if r["ignition"] else "off", "Turn the ignition on"),
    ]
    if p["kind"] == "run":
        ok = r["engine_running"] and 600 <= r["rpm"] <= 1100
        chips.append(_chip("engine", "Engine running, idle", ok, f"{r['rpm']} rpm", "Start the engine and let it idle"))
        vmin = 12.5
    else:
        vmin = 12.0
    chips.append(_chip("park", "Stationary, in P", r["speed"] == 0 and r["gear"] == "P", f"{r['speed']} km/h, {r['gear']}",
                       "Stop, select P, set the parking brake"))
    chips.append(_chip("voltage", f"Battery {vmin:g} V or more", r["voltage"] >= vmin, f"{r['voltage']:.1f} V",
                       "Charge the battery or check the alternator"))
    asks = [{"key": k, "text": t, "answered": k in car.answers} for k, t in p["asks"]]
    blockers = [c for c in chips if c["state"] != "ok"]
    ready = not blockers and all(a["answered"] for a in asks)
    return {"chips": chips, "asks": asks, "blockers": blockers, "ready": ready}


def answer(key: str, yes: bool = True, car: Optional[SimCar] = None) -> None:
    car = car or CAR
    (car.answers.add if yes else car.answers.discard)(key)


def mint_token(proc: str, car: Optional[SimCar] = None) -> Optional[str]:
    """A one-time start token, only when READY passes. A new mint replaces the old one for that procedure."""
    if not readiness(proc, car)["ready"]:
        return None
    with _LOCK:
        for t in [t for t, p in _TOKENS.items() if p == proc]:
            _TOKENS.pop(t, None)
        tok = secrets.token_urlsafe(16)
        _TOKENS[tok] = proc
        return tok


def _short(t: str, n: int = 140) -> str:
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "..."


def _job_text(j: dict[str, Any]) -> str:
    c = str(j.get("complaint") or "").strip()
    if c:
        return _short(c)
    for h in j.get("hypotheses") or []:
        if not h.get("deleted") and h.get("text"):
            return _short(h["text"])
    return ""


def job_matches(proc: str, j: dict[str, Any]) -> int:
    """Relevance of one open job to a procedure: 0 = not relevant. Reads the job's complaint and its live
    hypotheses (text + system) only; the word EVAP alone in a complaint does not count (a "non-EVAP" job)."""
    sv = PROCS[proc].get("serves") or {}
    hyps = [h for h in (j.get("hypotheses") or []) if not h.get("deleted")]
    blob = " ".join([str(j.get("complaint") or "")] + [str(h.get("text") or "") for h in hyps]).lower()
    score = 0
    for h in hyps:
        if str(h.get("system") or "").lower() in sv.get("systems", []):
            score += 10
    score += sum(1 for c in sv.get("codes", []) if c.lower() in blob)
    score += sum(1 for w in sv.get("words", []) if w in blob)
    return score


def pick_job(proc: str, jobs_list: list[dict[str, Any]]) -> Optional[dict[str, str]]:
    best = max(jobs_list, key=lambda j: job_matches(proc, j), default=None)
    if best is None or job_matches(proc, best) <= 0:
        return None
    return {"id": str(best.get("id") or ""), "text": _job_text(best)}


def open_job(vin: str, proc: str = "") -> Optional[dict[str, str]]:
    """The open job this procedure serves (read-only), else None. Never raises."""
    try:
        try:
            from cuore import bootstrap
            bootstrap.ensure_paths()
        except Exception:  # noqa: BLE001
            pass
        from mes import jobs
        return pick_job(proc, list(jobs.open_jobs(vin) or [])) if proc in PROCS else None
    except Exception:  # noqa: BLE001
        return None


class Run:
    def __init__(self, proc: str, car: SimCar) -> None:
        self.id = secrets.token_hex(6)
        self.proc, self.car = proc, car
        self.t0 = CLOCK()
        self.state = "running"
        self.stop_reason = ""
        self.stop_text = ""
        self.elapsed_final = 0.0
        self.before: list[tuple[str, str]] = []
        self.after: list[tuple[str, str]] = []
        self.p_before = 0.05
        self.p_min = 0.05
        self.result: Optional[dict[str, Any]] = None
        self.dry: Optional[dict[str, Any]] = None   # procedure_dry_run report when a capture file exists

    def _proof_at(self, e: float) -> float:
        f = self.car.faults
        drop = 0.0 if "no_proof" in f else (0.10 if "ambiguous_proof" in f else 0.47)
        return round(self.p_before - drop * min(1.0, e / 6.0), 2)

    def guards(self) -> list[dict[str, Any]]:
        r = self.car.readings()
        return [
            {"label": "RPM", "value": f"{r['rpm']}", "ok": 600 <= r["rpm"] <= 1100,
             "why": "Engine stalled or stopped" if r["rpm"] < 600 else "RPM too high"},
            {"label": "Speed", "value": f"{r['speed']} km/h", "ok": r["speed"] == 0, "why": "Car started moving"},
            {"label": "Voltage", "value": f"{r['voltage']:.1f} V", "ok": r["voltage"] >= 12.5, "why": "Battery voltage dropped"},
        ]

    def elapsed(self) -> float:
        return self.elapsed_final if self.state != "running" else max(0.0, CLOCK() - self.t0)

    def snapshot(self) -> dict[str, Any]:
        """Advance the run: enforces max time and guard breaches on the server, whoever is watching."""
        with _LOCK:
            if self.state == "running":
                e = self.elapsed()
                self.p_min = min(self.p_min, self._proof_at(e))
                breach = [g for g in self.guards() if not g["ok"]]
                if breach:
                    self.finish("guard", f"Stopped by CUORE: {breach[0]['why']} ({breach[0]['label']} {breach[0]['value']})")
                elif e >= MAX_RUN:
                    self.finish("timeout", f"Stopped by CUORE: maximum time {MAX_RUN:.0f} s reached")
            e = self.elapsed()
            proof = None
            if PROCS[self.proc]["proof"]:
                lbl, unit, direction = PROCS[self.proc]["proof"]
                now = self._proof_at(e) if self.state == "running" else self.p_min
                proof = {"label": lbl, "unit": unit, "expected": direction, "before": self.p_before, "now": now}
            return {"run": self.id, "state": self.state, "elapsed": round(e, 1), "max": MAX_RUN, "proof": proof,
                    "guards": self.guards(), "stop_reason": self.stop_reason, "stop_text": self.stop_text}

    def finish(self, reason: str, text: str = "") -> None:
        with _LOCK:
            if self.state != "running":
                return
            self.elapsed_final = max(0.0, CLOCK() - self.t0)
            self.state, self.stop_reason = "done", reason
            self.stop_text = text or {"stop": "Stopped with the STOP button", "disconnect": "Stopped by CUORE: screen disconnected",
                                       "complete": "Finished"}.get(reason, reason)
            self.result = _judge(self)
            _save(self)


def _judge(run: Run) -> dict[str, Any]:
    if run.dry is not None:
        return {"word": run.dry["verdict"], "reason": run.dry["verdict_line"], "dry_run": True}
    if PROCS[run.proc]["kind"] == "reset":
        changed = {n for (n, b), (_, a) in zip(run.before, run.after) if b != a}
        want = changed & SERVICE_CHANGES
        if len(want) == len(SERVICE_CHANGES):
            return {"word": "WORKED", "reason": f"All {len(want)} counters moved to the new service point; the other 4 values did not change."}
        if not want:
            return {"word": "DIDN'T", "reason": "The module said it accepted the reset, but read-back shows no value changed."}
        return {"word": "UNCLEAR", "reason": f"Only {len(want)} of {len(SERVICE_CHANGES)} expected values changed on read-back."}
    drop = round(run.p_before - run.p_min, 2)
    if run.stop_reason in ("guard", "disconnect"):
        return {"word": "UNCLEAR", "reason": f"{run.stop_text}. Run cut short; vapour pressure fell {drop:.2f} kPa before it stopped."}
    if drop >= PROOF_FALL_OK:
        return {"word": "WORKED", "reason": f"Vapour pressure fell {drop:.2f} kPa while venting."}
    if drop < PROOF_FALL_NONE:
        return {"word": "DIDN'T", "reason": f"Vapour pressure did not move ({drop:.2f} kPa); the car did not respond."}
    return {"word": "UNCLEAR", "reason": f"Vapour pressure fell only {drop:.2f} kPa; not enough to call it."}


def state_dir() -> Path:
    for base in (os.environ.get("CUORE_STATE_DIR"),
                 os.path.join(os.environ["PROGRAMDATA"], "cuore") if os.environ.get("PROGRAMDATA") else None,
                 str(Path.home() / ".cuore")):
        if not base:
            continue
        try:
            Path(base).mkdir(parents=True, exist_ok=True)
            return Path(base)
        except OSError:
            continue
    return Path.cwd()


def _save(run: Run) -> None:
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "prototype": True, "run": run.id, "procedure": run.proc,
           "result": run.result, "dry_gate_passed": (run.dry or {}).get("gate", {}).get("passed"), "stop_reason": run.stop_reason, "elapsed_s": round(run.elapsed_final, 1),
           "before": run.before, "after": run.after, "p_before": run.p_before, "p_min": run.p_min}
    try:
        with (state_dir() / "procedure_prototype.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def active_run() -> Optional[Run]:
    with _LOCK:
        for r in RUNS.values():
            if r.state == "running":
                return r
    return None


def reap() -> None:
    """Enforce timeout / guards on every running run (called on each request)."""
    for r in list(RUNS.values()):
        if r.state == "running":
            r.snapshot()


def _service_after(car: SimCar) -> list[tuple[str, str]]:
    if "no_proof" in car.faults:
        return list(SERVICE_BEFORE)
    d = dict(SERVICE_BEFORE)
    d["Distance after last service"] = d["Odometer"].replace(".0", "")
    d["Distance till next service"] = "16000.0 km"
    d["Days till next service"] = "365 days"
    if "ambiguous_proof" not in car.faults:
        d["Last service date"] = TODAY().strftime("%m/%d/%Y")
    return [(n, d[n]) for n, _ in SERVICE_BEFORE]


def start(proc: str, token: str, car: Optional[SimCar] = None) -> tuple[Optional[Run], str]:
    """Consume the token and start. Returns (run, "") or (None, refusal line)."""
    car = car or CAR
    reap()
    with _LOCK:
        if not token or _TOKENS.get(token) != proc:
            return None, "Start refused: no valid one-time token. Re-check READY first."
        _TOKENS.pop(token, None)                      # single use, consumed even when refused below
        if active_run():
            return None, "Start refused: running on another screen. STOP it first."
        rd = readiness(proc, car)
        if not rd["ready"]:
            b = (rd["blockers"] or [{"label": "a question", "unblock": "Answer the question"}])[0]
            return None, f"Start refused: {b['label']} - {b['unblock']}."
        run = Run(proc, car)
        for old in [k for k, v in RUNS.items() if v.state != "running"][:-49]:
            RUNS.pop(old, None)                       # keep the newest finished runs only
        RUNS[run.id] = run
        car.answers.clear()                           # every run asks again
        run.dry = dry_bridge.report_for(proc, car.faults)
        if run.dry is not None:                       # a captured procedure exists: real gate + scripted replies
            run.finish("complete", "Dry run of the captured procedure (gate + fake transport)")
        elif PROCS[proc]["kind"] == "reset":
            run.before = list(SERVICE_BEFORE)
            run.after = _service_after(car)
            run.finish("complete", "Reset written and read back")
        else:
            run.before = [("EVAP vapour pressure", f"{run.p_before:.2f} kPa")]
        return run, ""


def stop(run_id: str, reason: str = "stop") -> Optional[Run]:
    run = RUNS.get(run_id)
    if run:
        run.snapshot()
        run.finish(reason)
    return run


async def stream_events(run_id: str, interval: float = 0.5):
    """Server-sent events for one run. If the consumer goes away while the run is live, the run is stopped."""
    import asyncio
    run = RUNS.get(run_id)
    try:
        while run is not None:
            snap = run.snapshot()
            yield f"event: tick\ndata: {json.dumps(snap)}\n\n"
            if snap["state"] != "running":
                yield f"event: done\ndata: {json.dumps(snap)}\n\n"
                return
            await asyncio.sleep(interval)
        yield "event: done\ndata: {}\n\n"
    finally:
        if run is not None and run.state == "running":
            run.finish("disconnect")
