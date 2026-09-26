"""Actuator tests learned from a dealer tool, replayed under strict guards.

FCA does not publish InputOutputControl/RoutineControl identifiers, so cuore
never guesses them. A technician runs an actuator test once in MultiEcuScan
or wiTECH with cuore capturing passively (splitter cable, see :mod:`learn`);
this module extracts the exact request sequence the tester sent and can
replay it later, request for request, under the guards in :mod:`safety`.

Two halves:

* :func:`extract_procedure` -- pure, offline: turns the paired UDS
  transactions from one :func:`learn.uds_transactions` capture into an
  ordered procedure for one target address, classifies it ``replayable`` or
  not, and works out (or synthesises) the terminating request.
* :func:`run_actuator` -- the replay itself, over a live ``Session``. Every
  request is checked again by :func:`safety.assert_actuation_allowed`
  immediately before it is sent -- ``Session.uds`` sends any service, so
  this is the only gate standing between a learned procedure and the wire.
  The terminating request(s) are ALWAYS sent in a ``finally`` block, even if
  a mid-procedure response is negative or sending raises.

Persistence: ``<state_dir>/actuators.json``, ``{vin: {module: {name: entry}}}``
-- same JSON-file-beside-lock-file pattern as :mod:`learned`.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import audit, store
from .addressing import ECUAddress
from .config import state_dir
from .errors import BadCommand, Refused
from .safety import ACTUATION_UDS, assert_actuation_allowed, assert_actuation_module_allowed

#: The service IDs the actuation allowlist covers. Kept derived from
#: safety.ACTUATION_UDS so the learning-time classification below and the
#: replay-time gate in safety.py never drift apart.
ACTUATION_SERVICES: frozenset[int] = frozenset(ACTUATION_UDS)

#: Services that make a captured procedure unreplayable outright, with why.
#: All of these are already outside ACTUATION_SERVICES; this dict exists so
#: the reported reason names the actual hazard instead of a bare "not
#: allowed". 0x27 (SecurityAccess) is handled separately -- see
#: ``requires_security_access`` below -- because it is not a hazard so much
#: as something that structurally cannot be replayed (the seed is
#: per-session).
_EXPLICIT_BLOCKED: dict[int, str] = {
    0x2E: "WriteDataByIdentifier",
    0x34: "RequestDownload",
    0x35: "RequestUpload",
    0x36: "TransferData",
    0x37: "RequestTransferExit",
    0x3D: "WriteMemoryByAddress",
    0x11: "ECUReset",
    0x28: "CommunicationControl",
    0x85: "ControlDTCSetting",
    0x14: "ClearDiagnosticInformation",
}

#: Never held longer than this, however large ``max_seconds`` is asked for.
HARD_CAP_SECONDS = 30.0

_LOCK = threading.Lock()


def is_routine(procedure: Optional[dict[str, Any]]) -> bool:
    """True if the procedure starts a RoutineControl (31 01). Routine IDs are opaque:
    a learned one may be an adaptation reset rather than a harmless output test."""
    for st in (procedure or {}).get("steps") or []:
        if st.get("service") == "31" and (st.get("payload") or [None])[0] == "01":
            return True
    return False


def consent_phrase(module_code: str, name: str, routine: bool = False) -> str:
    verb = "RUN ROUTINE" if routine else "ACTUATE"
    return f"{verb} {module_code.upper()} {name.upper()}"


def _step_from_transaction(tr: dict[str, Any]) -> dict[str, Any]:
    req = [b.upper() for b in (tr.get("request") or [])]
    resp = tr.get("response")
    return {
        "t_req": tr.get("t_req"), "t_resp": tr.get("t_resp"),
        "service": req[0] if req else None,
        "payload": req[1:],
        "request": req,
        "response": [b.upper() for b in resp] if resp else None,
        "nrc": tr.get("nrc"),
        "synthesised": False,
    }


def extract_procedure(transactions: list[dict[str, Any]], target: str) -> dict[str, Any]:
    """The ordered procedure of requests one tester sent to ``target`` (hex byte string).

    ``transactions`` is :func:`learn.uds_transactions`' output. Only
    transactions whose ``target`` matches (case-insensitively) are kept, in
    time order. The procedure is classified ``replayable`` only when every
    request's service is on the actuation allowlist (0x10 sub 0x01/0x03,
    0x3E, 0x2F, 0x31, 0x22, 0x19) and no 0x27 SecurityAccess or
    configuration/reflash/reset service appears. A 0x27 sets
    ``requires_security_access`` and is reported separately, since the
    reason it cannot be replayed (a per-session seed/key exchange) is
    different from "this service is refused".

    Also records whether the capture already ended with the terminating
    request -- ``returnControlToECU`` (``2F <did> 00``) or routine stop
    (``31 02 <routine>``) -- or, when it did not, synthesises one from the
    learned DID/routine ID (``synthesised_terminator``, ``synthesised=True``).
    """
    target = (target or "").upper()
    steps = [_step_from_transaction(tr)
             for tr in sorted(transactions, key=lambda t: t["t_req"])
             if (tr.get("target") or "").upper() == target and tr.get("request")]

    reasons: list[str] = []
    requires_security_access = False
    blocked: list[str] = []
    for st in steps:
        svc = int(st["service"], 16)
        if svc == 0x27:
            requires_security_access = True
            continue
        if svc in _EXPLICIT_BLOCKED:
            blocked.append(f"{st['service']} ({_EXPLICIT_BLOCKED[svc]})")
            continue
        if svc not in ACTUATION_SERVICES:
            blocked.append(st["service"])
            continue
        if svc == 0x10:
            allowed = ACTUATION_UDS.get(0x10)
            sub = int(st["payload"][0], 16) if st["payload"] else None
            if sub is None or (allowed is not None and (sub & 0x7F) not in allowed):
                blocked.append(f"10 {st['payload'][0] if st['payload'] else '(none)'}")

    if not steps:
        reasons.append(f"no requests to target {target} found in this capture")
    if requires_security_access:
        reasons.append("procedure includes UDS 0x27 SecurityAccess; the seed/key exchange is "
                       "per-session and cannot be replayed")
    if blocked:
        reasons.append("procedure includes services outside the actuation allowlist: "
                       + ", ".join(blocked))
    replayable = bool(steps) and not requires_security_access and not blocked

    # --- the terminating request: present in the capture, or synthesised ---
    actuations = [st for st in steps if st["service"] in ("2F", "31")]
    ended_with_terminator = True
    synthesised_terminator: Optional[dict[str, Any]] = None
    if actuations:
        last = actuations[-1]
        if last["service"] == "2F":
            cp = last["payload"][2] if len(last["payload"]) > 2 else None
            ended_with_terminator = cp == "00"
            if not ended_with_terminator and len(last["payload"]) >= 2:
                did_hi, did_lo = last["payload"][0], last["payload"][1]
                synthesised_terminator = {
                    "service": "2F", "payload": [did_hi, did_lo, "00"],
                    "request": ["2F", did_hi, did_lo, "00"], "synthesised": True,
                    "note": f"returnControlToECU synthesised for DID {did_hi}{did_lo}",
                }
        else:  # "31"
            sub = last["payload"][0] if last["payload"] else None
            ended_with_terminator = sub == "02"
            if not ended_with_terminator and len(last["payload"]) >= 3:
                rid = last["payload"][1:3]
                synthesised_terminator = {
                    "service": "31", "payload": ["02", *rid],
                    "request": ["31", "02", *rid], "synthesised": True,
                    "note": f"routine stop synthesised for routine {''.join(rid)}",
                }
        if not ended_with_terminator and synthesised_terminator is None:
            # The last 2F/31 request was too short to read a DID/routine id
            # from -- nothing safe can be synthesised, so refuse replay
            # rather than leave the module unable to be returned to normal.
            replayable = False
            reasons.append("last actuation request did not carry a DID/routine id long enough "
                           "to synthesise a terminating request")

    used_tester_present = any(st["service"] == "3E" for st in steps)
    session_sub = next((st["payload"][0] for st in steps
                        if st["service"] == "10" and st["payload"]), None)
    kind = ("io_control" if any(st["service"] == "2F" for st in steps) else
            "routine_control" if any(st["service"] == "31" for st in steps) else
            "read_only" if steps else "empty")

    return {
        "target": target, "kind": kind, "steps": steps, "replayable": replayable,
        "requires_security_access": requires_security_access, "reasons": reasons,
        "ended_with_terminator": ended_with_terminator,
        "synthesised_terminator": synthesised_terminator,
        "used_tester_present": used_tester_present, "session_sub": session_sub,
    }


# ===========================================================================
# Persistence: <state_dir>/actuators.json
# ===========================================================================

def path() -> Path:
    return state_dir() / "actuators.json"


def _load() -> dict[str, Any]:
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict[str, Any]) -> None:
    try:
        path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def save_actuator(vin: str, module_code: str, name: str, procedure: dict[str, Any], *,
                  source: str, tool: str) -> dict[str, Any]:
    """Persist a learned procedure for ``vin``/``module_code``/``name``, replacing any prior one."""
    entry = {
        "vin": vin or "", "module": module_code.upper(), "name": name, "tool": tool,
        "source": source, "learned_at": datetime.now().isoformat(timespec="seconds"),
        **procedure,
    }
    with _LOCK:
        data = _load()
        data.setdefault(vin or "", {}).setdefault(module_code.upper(), {})[name] = entry
        _save(data)
    return entry


def get_actuator(vin: str, module_code: str, name: str) -> Optional[dict[str, Any]]:
    with _LOCK:
        data = _load()
    return (data.get(vin or "", {}) or {}).get(module_code.upper(), {}).get(name)


def list_actuators(vin: Optional[str] = None) -> dict[str, list[dict[str, Any]]]:
    """``{vin: [{module, name, tool, source, learned_at, replayable, reasons}, ...]}``."""
    with _LOCK:
        data = _load()
    if vin is not None:
        data = {vin: data.get(vin, {})}
    out: dict[str, list[dict[str, Any]]] = {}
    for v, by_module in data.items():
        rows = []
        for module_code, tests in (by_module or {}).items():
            for name, entry in tests.items():
                rows.append({
                    "module": module_code, "name": name, "tool": entry.get("tool"),
                    "source": entry.get("source"), "learned_at": entry.get("learned_at"),
                    "kind": entry.get("kind"), "replayable": entry.get("replayable"),
                    "reasons": entry.get("reasons"),
                    "requires_security_access": entry.get("requires_security_access"),
                })
        out[v] = rows
    return out


# ===========================================================================
# Replay
# ===========================================================================

def assert_actuate_allowed(ecu: ECUAddress, procedure: Optional[dict[str, Any]], consent: str,
                           name: str) -> dict[str, Any]:
    """The actuation gate: consent, module, and replayability. Raises before any traffic."""
    if procedure is None:
        raise BadCommand(f"no learned actuator test {name!r} for {ecu.code}; run learn_actuator "
                         f"first")
    routine = is_routine(procedure)
    phrase = consent_phrase(ecu.code, name, routine=routine)
    if (consent or "").strip().upper() != phrase:
        why = ("this procedure starts a module ROUTINE whose effect cuore cannot know (it may be "
               "an adaptation reset, not an output test)" if routine
               else "actuating it moves hardware")
        raise Refused(f"{ecu.code} {name!r}: {why}; type the consent phrase exactly: {phrase!r}")
    assert_actuation_module_allowed(ecu.code, ecu.bus_key)
    if not procedure.get("replayable"):
        raise Refused(f"the learned procedure for {ecu.code} {name!r} is not replayable: "
                      + "; ".join(procedure.get("reasons") or ["unknown reason"]))
    return procedure


def run_actuator(sess: Any, ecu: ECUAddress, procedure: dict[str, Any], *, consent: str,
                 max_seconds: float = 10.0) -> dict[str, Any]:
    """Replay a learned procedure on ``ecu``. ``sess`` must already target ``ecu``'s bus.

    Re-checks :func:`assert_actuate_allowed` (defence in depth: ``ops.run_actuator``
    checks it before opening the session too, but nothing here trusts that).
    Sends the learned requests in order, sleeping the learned gap between
    them (bounded so the whole replay never exceeds ``max_seconds``, hard
    capped at :data:`HARD_CAP_SECONDS`). Every request is re-checked by
    :func:`safety.assert_actuation_allowed` immediately before it is sent.
    The terminating request(s) -- learned or synthesised -- are ALWAYS
    ATTEMPTED in a ``finally`` block, and a return to the default session
    (``10 01``) is attempted if the procedure left it elsewhere, even when a
    mid-procedure response is negative or sending raises. They count only
    when the module accepts them: check ``control_returned`` /
    ``session_restored`` / ``outcome``; if either is False the result says to
    switch the ignition off.
    """
    name = procedure.get("name") or ""
    assert_actuate_allowed(ecu, procedure, consent, name)

    budget = max(0.0, min(float(max_seconds), HARD_CAP_SECONDS))
    steps: list[dict[str, Any]] = procedure.get("steps") or []
    log: list[dict[str, Any]] = []
    started = time.monotonic()
    control_returned = False
    session_sub = procedure.get("session_sub")
    session_restored = session_sub in (None, "01")

    def _remaining() -> float:
        return budget - (time.monotonic() - started)

    def _send(step: dict[str, Any], label: str, timeout: float = 3.0,
              retries: int = 3) -> dict[str, Any]:
        service = int(step["service"], 16)
        payload = bytes(int(b, 16) for b in (step.get("payload") or []))
        assert_actuation_allowed(service, payload)
        r = sess.uds(ecu, service, payload, timeout=timeout, retries_on_pending=retries)
        nrc = next(iter(r.get("nrc", {}).values()), None)
        rec = {"label": label, "sent": step.get("request"), "raw": r.get("raw"),
              "positive": r.get("positive"), "nrc": None if nrc is None else f"{nrc:02X}",
              "error": r.get("error")}
        rec["accepted"] = bool(r.get("positive")) and nrc is None and not r.get("error")
        log.append(rec)
        return rec

    try:
        prev_t: Optional[float] = None
        for step in steps:
            if _remaining() <= 0:
                log.append({"label": "budget", "sent": None,
                           "note": f"max_seconds ({budget:g}s) reached; stopping early, the "
                                   f"terminator is still sent"})
                break
            if prev_t is not None and step.get("t_req") is not None:
                gap = max(0.0, min(step["t_req"] - prev_t, _remaining()))
                time.sleep(gap)
                if _remaining() <= 0:
                    log.append({"label": "budget", "sent": None,
                                "note": f"max_seconds ({budget:g}s) reached during a learned gap; "
                                        f"stopping, the terminator is still sent"})
                    break
            prev_t = step.get("t_req")
            try:
                # Learned steps get no more than the time left, and no responsePending
                # retries: a slow module must not stretch an active actuation.
                _send(step, "learned", timeout=max(0.3, min(3.0, _remaining())), retries=0)
            except Exception as e:  # noqa: BLE001 -- surfaced in the report, not raised: the
                                    # terminator must still be sent in the finally block below
                log.append({"label": "learned", "sent": step.get("request"), "error": str(e)})
                break
            if step["service"] == "2F" and len(step.get("payload") or []) > 2 \
                    and step["payload"][2] == "00":
                control_returned = True
            elif step["service"] == "31" and (step.get("payload") or [None])[0] == "02":
                control_returned = True
            if step["service"] == "10":
                session_restored = (step.get("payload") or [None])[0] == "01"
    finally:
        try:
            term = procedure.get("synthesised_terminator")
            if not control_returned:
                if term is not None:
                    control_returned = _send(term, "terminator (synthesised)")["accepted"]
                else:
                    last_act = next((s for s in reversed(steps) if s["service"] in ("2F", "31")),
                                    None)
                    if last_act is not None:
                        control_returned = _send(last_act, "terminator (repeat)")["accepted"]
            if not session_restored:
                session_restored = _send({"service": "10", "payload": ["01"],
                                          "request": ["10", "01"]},
                                         "session restore")["accepted"]
        except Exception as e:  # noqa: BLE001 -- must not mask whatever failed above
            log.append({"label": "terminator failed", "error": str(e)})
        audit.record("actuate", module=ecu.code, name=name, steps=len(log),
                     control_returned=control_returned, session_restored=session_restored)
        try:
            store.record_observation(
                "actuator_test",
                {"ecu": ecu.code, "name": name, "steps": log,
                 "control_returned": control_returned, "session_restored": session_restored},
                vin=procedure.get("vin") or "", bus=sess.bus.key, cable=sess.link.cable,
                stream=sess.stream.describe)
        except Exception:  # noqa: BLE001 -- recording the observation must never mask a real error
            pass

    ok = control_returned and session_restored
    return {"ecu": ecu.code, "name": name, "bus": sess.bus.key,
            "outcome": ("control returned to the module" if ok else
                        "CONTROL NOT CONFIRMED RETURNED: switch the ignition OFF now. That ends the "
                        "module's diagnostic session and releases any output it is holding. Then "
                        "check the module for codes."),
            "control_returned": control_returned, "session_restored": session_restored,
            "routine": is_routine(procedure), "steps": log,
            "duration_s": round(time.monotonic() - started, 2)}


__all__ = [
    "ACTUATION_SERVICES", "HARD_CAP_SECONDS", "consent_phrase", "extract_procedure",
    "path", "save_actuator", "get_actuator", "list_actuators",
    "assert_actuate_allowed", "run_actuator", "is_routine",
]
