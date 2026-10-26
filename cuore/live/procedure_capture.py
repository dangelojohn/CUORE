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


def review(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Reassemble the capture and report, per module the tester talked to."""
    txs = uds_transactions(frames)
    modules: list[dict[str, Any]] = []
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
            "procedure": proc,
        })
    rep: dict[str, Any] = {"transactions": len(txs), "modules": modules}
    rep["text"] = report_text(rep)
    return rep


def report_text(rep: dict[str, Any]) -> str:
    lines = [f"Procedure review: {rep['transactions']} UDS transaction(s), "
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
    return {"passed": not fails, "status": status,
            "reasons": fails or ["all gate checks passed"], "consent": consent,
            "interlock_conflicts": conflicts}
