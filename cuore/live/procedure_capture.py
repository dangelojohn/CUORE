"""Procedure-capture dry run and safety gate for passively learned MES procedures.

Offline and pure: nothing here opens an adapter or transmits. Input is the
frame list the MES-learn listener records (``cuore.live.mes_learn`` state
``frames``): ``[{"t": float seconds, "id": "18DA10F1", "data": "0210030000..."}]``
(``data`` is the CAN payload as a hex string, no separators; this is also the
shape ``capture.listen`` returns). ISO-TP is reassembled by
:func:`cuore.live.learn.uds_transactions`; the ordered procedure is built by
:func:`cuore.live.actuate.extract_procedure`, so the replay rules are exactly
the ones ``actuate.py`` applies (never a second, drifting copy).

* :func:`review` -- per-module review report (services, 0x27, writes, replay verdict).
* :func:`gate` -- the checks a learned procedure must pass before CUORE may offer it.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from . import actuate
from .addressing import MODULES
from .buses import BUSES
from .learn import uds_transactions
from .safety import ACTUATION_BLOCKED_MODULES

SERVICE_NAMES: dict[str, str] = {
    "10": "DiagnosticSessionControl", "11": "ECUReset", "14": "ClearDiagnosticInformation",
    "19": "ReadDTCInformation", "22": "ReadDataByIdentifier", "27": "SecurityAccess",
    "28": "CommunicationControl", "2E": "WriteDataByIdentifier",
    "2F": "InputOutputControlByIdentifier", "31": "RoutineControl",
    "34": "RequestDownload", "36": "TransferData", "37": "RequestTransferExit",
    "3D": "WriteMemoryByAddress", "3E": "TesterPresent", "85": "ControlDTCSetting",
}
#: Write / reset / reflash style services (anything that changes stored state).
WRITE_RESET_SERVICES = frozenset({"11", "14", "28", "2E", "34", "35", "36", "37", "3D", "85"})


def _module_for(target_hex: str):
    t = int(target_hex, 16)
    return next((m for m in MODULES if m.target == t), None)


def _norm_request(raw: Any) -> list[str]:
    """A documented step's request as upper-case hex bytes (``"22F190"`` or ``["22","F1","90"]``)."""
    if isinstance(raw, dict):
        raw = raw.get("request")
    if isinstance(raw, str):
        h = re.sub(r"[^0-9A-Fa-f]", "", raw)
        if len(h) % 2:
            raise ValueError(f"odd-length hex request {raw!r}")
        return [h[i:i + 2].upper() for i in range(0, len(h), 2)]
    return [str(b).upper().zfill(2) for b in (raw or [])]


def documented_transactions(defn: dict[str, Any]) -> list[dict[str, Any]]:
    """A DOCUMENTED procedure definition (``steps`` = ordered requests, from published
    documentation / open-source code / a published trace) as ``uds_transactions``-shaped rows, so
    the very same :func:`actuate.extract_procedure` rules apply. Never invents anything: no
    ``steps`` means no transactions."""
    addr = next((m for m in MODULES if m.code == str(defn.get("module", "")).upper()), None)
    target = f"{addr.target:02X}" if addr else str(defn.get("target", "")).upper()
    return [{"target": target, "request": _norm_request(st), "response": None, "nrc": None,
             "t_req": float(i), "t_resp": None} for i, st in enumerate(defn.get("steps") or [])]


def review_documented(defn: dict[str, Any]) -> dict[str, Any]:
    """:func:`review` for a documented definition; the result is tagged ``source="documented"``."""
    return review(defn)


def documented_procedure(defn: dict[str, Any]) -> dict[str, Any]:
    """The ``extract_procedure`` dict for a documented definition, plus the fields
    ``procedure_dry_run.load`` / :func:`gate` read (name, pre, post, bitrate, max_seconds).
    ``source="documented"``; an empty ``steps`` yields a non-replayable, kind ``empty`` procedure."""
    txs = documented_transactions(defn)
    target = txs[0]["target"] if txs else (
        f"{next((m.target for m in MODULES if m.code == str(defn.get('module', '')).upper()), 0):02X}")
    proc = actuate.extract_procedure(txs, target)
    sess = defn.get("session") or {}
    pre = {k: v for k, v in (defn.get("preconditions") or {}).items() if k in ("engine_state", "voltage_v")}
    post = {k: v for k, v in (defn.get("postconditions") or {}).items() if k in ("engine_state", "voltage_v")}
    proc.update({
        "source": "documented", "name": defn.get("name", ""), "pre": pre, "post": post,
        "bitrate": sess.get("bitrate"), "max_seconds": defn.get("max_seconds"),
        "citation": (defn.get("source") or {}).get("citation"),
    })
    return proc


def review(frames: Any) -> dict[str, Any]:
    """Reassemble the capture and report, per module the tester talked to. ``frames`` is the
    MES-learn frame list, or a DOCUMENTED procedure definition (a dict with ``steps``), which
    goes through the same rules and is tagged ``source="documented"``."""
    documented = isinstance(frames, dict)
    txs = documented_transactions(frames) if documented else uds_transactions(frames)
    modules: list[dict[str, Any]] = []
    if documented and not txs:                  # awaiting source: report it, never invent steps
        addr = next((m for m in MODULES if m.code == str(frames.get("module", "")).upper()), None)
        txs = []
        proc = documented_procedure(frames)
        modules.append({
            "target": proc["target"], "module": addr.code if addr else None,
            "bus": addr.bus_key if addr else None, "sequence": [], "services": [],
            "has_security_access": False, "write_reset_services": [], "unanswered": 0,
            "negative_responses": [], "replay_allowed": False,
            "replay_reasons": proc["reasons"], "procedure": proc, "source": "documented"})
    for target in sorted({t["target"] for t in txs}):
        proc = actuate.extract_procedure(txs, target)
        seq = [s["service"] for s in proc["steps"]]
        addr = _module_for(target)
        modules.append({
            "target": target, "module": addr.code if addr else None,
            "bus": addr.bus_key if addr else None,
            "sequence": seq,
            "services": sorted(set(seq)),
            "has_security_access": "27" in seq,
            "write_reset_services": sorted({s for s in seq if s in WRITE_RESET_SERVICES}),
            "unanswered": sum(1 for s in proc["steps"] if s["response"] is None),
            "negative_responses": [s["nrc"] for s in proc["steps"] if s["nrc"]],
            "replay_allowed": bool(proc["replayable"]),
            "replay_reasons": proc["reasons"],
            "procedure": proc, "source": "documented" if documented else "captured",
        })
        if documented:
            proc.update({k: v for k, v in documented_procedure(frames).items()
                         if k in ("source", "name", "pre", "post", "bitrate", "max_seconds", "citation")})
    rep: dict[str, Any] = {"transactions": len(txs), "modules": modules,
                           "source": "documented" if documented else "captured"}
    rep["text"] = report_text(rep)
    return rep


def report_text(rep: dict[str, Any]) -> str:
    lines = [f"Procedure review [{rep.get('source', 'captured')}]: {rep['transactions']} UDS transaction(s), "
             f"{len(rep['modules'])} module(s)."]
    if not rep["modules"]:
        lines.append("No UDS requests found. Nothing to review (check the bitrate and splitter).")
    for m in rep["modules"]:
        name = f"{m['module'] or 'unknown module'} (target {m['target']})"
        seq = " -> ".join(f"{s} {SERVICE_NAMES.get(s, '?')}" for s in m["sequence"]) or "none"
        lines.append(f"{name}: {seq}")
        lines.append("  SecurityAccess 0x27: "
                     + ("PRESENT - cannot be replayed" if m["has_security_access"] else "none"))
        w = m["write_reset_services"]
        lines.append("  Write/reset/reflash services: "
                     + (", ".join(f"{s} {SERVICE_NAMES.get(s, '?')}" for s in w) if w else "none"))
        lines.append("  actuate.py would "
                     + ("ALLOW replay." if m["replay_allowed"]
                        else "REFUSE replay: " + "; ".join(m["replay_reasons"])))
        if m["unanswered"]:
            lines.append(f"  {m['unanswered']} request(s) had no response in the capture.")
        if m["negative_responses"]:
            lines.append("  Negative responses (NRC): " + ", ".join(m["negative_responses"]))
    return "\n".join(lines)


#: What ``ops.run_actuator`` requires before it will command anything.
RUN_ACTUATOR_INTERLOCK = "engine off (0 rpm) and vehicle stationary (0 km/h)"
INTERLOCK_CONFLICT_STATUS = "needs an owner decision: interlock conflict"
_ENGINE_ON_RE = re.compile(r"engine\s+(running|on)\b|purge\s+active|vehicle\s+(moving|driving)",
                           re.IGNORECASE)
_ENGINE_STATE_ON_RE = re.compile(r"\b(running|idle|idling|on)\b", re.IGNORECASE)
_ENGINE_STATE_OFF_RE = re.compile(r"\b(off|koeo|stopped)\b", re.IGNORECASE)


def interlock_conflicts(name: str = "", mes_function: str = "",
                        pre: Optional[dict[str, Any]] = None) -> list[str]:
    """Where the conditions MES runs this procedure under contradict CUORE's
    ``run_actuator`` interlock (engine off AND stationary). Sources: the
    ``mes_functions`` prerequisites for the named function, and the recorded
    ``pre`` engine_state. The interlock itself is never changed here."""
    out: list[str] = []
    fn = None
    try:
        from .. import bootstrap  # noqa: F401 -- side effect: mes on sys.path
        from mes import mes_functions
        fn = mes_functions.function(mes_function) if mes_function else None
        if fn is None and name:
            fn = next((f for f in mes_functions.search(name) if f.get("kind") == "actuator"), None)
    except Exception:  # noqa: BLE001 -- knowledge table is optional
        fn = None
    if fn:
        for req in fn.get("prerequisites", []):
            if _ENGINE_ON_RE.search(req):
                out.append(f"MES lists '{req}' as a prerequisite for '{fn.get('name')}', "
                           f"but run_actuator requires {RUN_ACTUATOR_INTERLOCK}")
    es = str((pre or {}).get("engine_state") or "").strip().lower()
    if es and _ENGINE_STATE_ON_RE.search(es) and not _ENGINE_STATE_OFF_RE.search(es):
        out.append(f"the procedure was captured with engine_state={es!r}, but run_actuator "
                   f"requires {RUN_ACTUATOR_INTERLOCK}")
    return out


def gate_report(rep: dict[str, Any], *, listen_bitrate: Optional[int], pre: Optional[dict] = None,
                post: Optional[dict] = None, name: str = "", max_seconds: Optional[float] = None,
                mes_function: str = "") -> list[dict[str, Any]]:
    """:func:`gate` for every module of a :func:`review` report, fed the RECORDED bitrate."""
    return [dict(gate(m, listen_bitrate=listen_bitrate, pre=pre, post=post, max_seconds=max_seconds,
                      name=name, mes_function=mes_function),
                 module=m["module"], target=m["target"]) for m in rep["modules"]]


def gate(proc_or_module: dict[str, Any], *, listen_bitrate: Optional[int] = None,
         pre: Optional[dict[str, Any]] = None, post: Optional[dict[str, Any]] = None,
         max_seconds: Optional[float] = None, name: str = "",
         mes_function: str = "") -> dict[str, Any]:
    """Pass/fail for offering a learned procedure. ``proc_or_module`` is a
    :func:`review` module entry or a bare ``extract_procedure`` result.

    ``pre``/``post`` are recorded conditions, each needing ``engine_state`` and
    ``voltage_v``. ``listen_bitrate`` is the bitrate the capture ran at.
    ``max_seconds`` is the declared replay timeout (needed when the stop step
    was not captured). Returns ``{"passed", "status", "reasons", "consent",
    "interlock_conflicts"}``. A conflict between MES's conditions and the
    ``run_actuator`` interlock sets status "needs an owner decision: interlock
    conflict" and never passes.
    """
    proc = proc_or_module.get("procedure", proc_or_module)
    addr = _module_for(proc["target"])
    fails: list[str] = []
    seq = [s["service"] for s in proc["steps"]]

    if "27" in seq or proc.get("requires_security_access"):
        fails.append("0x27 SecurityAccess present")
    bad = sorted({s for s in seq if int(s, 16) not in actuate.ACTUATION_SERVICES and s != "27"})
    if bad:
        fails.append("services outside the actuation allowlist: " + ", ".join(bad))
    if not proc.get("replayable") and not fails:
        fails.append("actuate.py marks it not replayable: "
                     + "; ".join(proc.get("reasons") or ["unknown"]))
    if proc.get("kind") not in ("io_control", "routine_control"):
        fails.append(f"not an actuator test (kind={proc.get('kind')})")

    if addr is None:
        fails.append(f"target {proc['target']} is not a known module")
    else:
        if addr.bus_key != "can_c":
            fails.append(f"{addr.code} is on {addr.bus_key}, not CAN-C")
        if addr.code in ACTUATION_BLOCKED_MODULES or addr.bus_key == "can_ch":
            fails.append(f"{addr.code} is a safety-critical module (blocked)")
        bus = BUSES.get(addr.bus_key)
        if bus is not None and bus.bitrate_confidence != "confirmed":
            fails.append(f"{addr.bus_key} bitrate is not confirmed")
        if bus is not None and listen_bitrate != bus.bitrate:
            fails.append(f"capture bitrate {listen_bitrate} != confirmed {bus.bitrate} "
                         f"for {addr.bus_key}")
        if not addr.usable:
            fails.append(f"{addr.code} address is not confirmed")

    if proc.get("ended_with_terminator"):
        pass  # captured returnControlToECU / stopRoutine
    elif (proc.get("synthesised_terminator") and max_seconds
          and 0 < max_seconds <= actuate.HARD_CAP_SECONDS):
        pass  # stop step is synthesised, but a bounded timeout is declared
    else:
        fails.append("no stop step (2F returnControlToECU / 31 02 stopRoutine) captured, and no "
                     f"timeout <= {actuate.HARD_CAP_SECONDS:.0f}s declared")

    for label, cond in (("pre", pre), ("post", post)):
        for key in ("engine_state", "voltage_v"):
            if not cond or cond.get(key) in (None, ""):
                fails.append(f"{label}-condition {key} not recorded")

    if not name:
        fails.append("no procedure name, so no consent phrase can be defined")
    consent = (actuate.consent_phrase(addr.code, name, routine=actuate.is_routine(proc))
               if addr and name else None)
    conflicts = interlock_conflicts(name, mes_function, pre)
    if conflicts:
        fails.append(INTERLOCK_CONFLICT_STATUS)
        fails.extend(conflicts)
    status = (INTERLOCK_CONFLICT_STATUS if conflicts
              else "passed" if not fails else "failed")
    src = proc_or_module.get("source") or proc.get("source") or "captured"
    return {"passed": not fails, "status": status, "source": src,
            "reasons": fails or ["all gate checks passed"], "consent": consent,
            "interlock_conflicts": conflicts}


# ===========================================================================
# automatic review of a SAVED capture (mes_learn.stop and serial-mirror saves)
# ===========================================================================

#: Gate reasons that only say "the owner has not filled in the replay form yet";
#: they say nothing about whether the capture itself is replayable.
_FORM_REASON_PREFIXES = ("pre-condition", "post-condition", "no procedure name")


def verdict_line(rep: dict[str, Any], gates: list[dict[str, Any]], path: str = "") -> str:
    """One line: is this capture replayable, and if not, the first blocker."""
    mods = rep.get("modules") or []
    if not mods:
        return "replayable: no - no UDS requests found in the capture (check bitrate and splitter)"
    for m, g in zip(mods, gates):
        seq = m["sequence"]
        reasons = [r for r in g.get("reasons", [])
                   if not r.startswith(_FORM_REASON_PREFIXES) and r != "all gate checks passed"]
        who = m["module"] or f"target {m['target']}"
        if "27" in seq:
            return (f"replayable: no - 0x27 SecurityAccess present at step {seq.index('27') + 1}"
                    f" ({who})")
        if reasons:
            return f"replayable: no - {reasons[0]} ({who})"
    m = mods[0]
    seq = m["sequence"]
    proc = m.get("procedure", {})
    stop = (f"stop step at {len(seq)}" if proc.get("ended_with_terminator")
            else "stop step synthesised")
    nxt = f"; dry-run next: python -m cuore.live.procedure_dry_run {path}" if path else ""
    return f"replayable: yes, {len(seq)} steps, {stop}{nxt}"


def review_frames(frames: list[dict[str, Any]], *, path: str = "",
                  listen_bitrate: Optional[int] = None, **gate_kw: Any) -> dict[str, Any]:
    """review + gate_report + verdict; writes ``<path stem>.review.json`` beside
    the capture when ``path`` is given. NEVER raises: a bad capture is reported
    in the returned dict (``verdict`` says so) and the capture is untouched."""
    import json
    from datetime import datetime
    from pathlib import Path
    try:
        rep = review(frames)
        rep["gates"] = gate_report(rep, listen_bitrate=listen_bitrate, **gate_kw)
        rep["recorded_bitrate"] = listen_bitrate
        rep["capture_file"] = path or None
        rep["verdict"] = verdict_line(rep, rep["gates"], path)
        rep["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
        rep["review_file"] = None
        if path:
            out = Path(path).with_suffix(".review.json")
            out.write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
            rep["review_file"] = str(out)
        return rep
    except Exception as e:  # noqa: BLE001
        return {"verdict": f"replayable: no - review failed: {e}", "error": str(e),
                "text": "", "gates": [], "modules": [], "review_file": None,
                "recorded_bitrate": listen_bitrate, "capture_file": path or None}


def review_file(path: str, **gate_kw: Any) -> dict[str, Any]:
    """:func:`review_frames` for a saved JSONL capture (mes_learn or
    ``serial_mirror.write_capture``); the gate gets the header's RECORDED bitrate."""
    import json
    header: dict[str, Any] = {}
    frames: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("type") == "header":
                    header = row
                elif "id" in row and "data" in row:
                    frames.append(row)
    except OSError as e:
        return {"verdict": f"replayable: no - cannot read capture: {e}", "error": str(e),
                "text": "", "gates": [], "modules": [], "review_file": None}
    return review_frames(frames, path=str(path), listen_bitrate=header.get("bitrate"), **gate_kw)
