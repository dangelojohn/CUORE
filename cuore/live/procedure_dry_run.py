"""Dry run of a captured MES procedure: the real gate and the real replay logic, no car.

OFFLINE. Nothing here opens an adapter, a serial port or a socket. A capture is loaded, passed through
:func:`procedure_capture.review` / :func:`procedure_capture.gate` exactly as the real path does, and if the
gate passes, every step is replayed by :func:`actuate.run_actuator` -- the unmodified replay function --
against :class:`FakeSession`, an in-memory stand-in whose replies are scripted by ``fake_replies``.
So the consent check, the per-request allowlist re-check, the stop / return-control handling, the
terminator synthesis, the session restore, the abort paths and the audit records are all exercised for real.

What is deliberately different from a real run (and reported in ``warnings``):
  * replies are SIMULATED. A WORKED verdict means "the protocol logic completes", never "the car did it".
  * the learned gaps between requests are skipped (bytes and order are unchanged).
  * the actuator-test observation is NOT written to the observation store (fake values are not evidence);
    the audit log gets the normal ``actuate`` record tagged ``dry_run=true`` plus a ``procedure_dry_run`` record.

``fake_replies`` maps a key to a reply spec (or a list of specs, consumed one per matching send, last repeats):
  key   int N          the N-th captured step (1-based)
        "2F123400"     any send of exactly that request (hex, no spaces; also matches terminators)
        "stop"         any stop request (2F <did> 00, 31 02 <id>) -- captured or synthesised
        "*"            everything not matched above
  spec  "ok" (default) | "nrc:31" or {"nrc": "31"} | "no_reply" | "pending" / "pending:N" (0x78 N times then ok)
        | "disconnect" (this send and every later one raise ConnectionError)

CLI:  .venv/Scripts/python.exe -X utf8 -m cuore.live.procedure_dry_run <capture.json|.jsonl> [--nrc STEP:CODE]
      [--drop-stop] [--disconnect STEP] [--name N] [--max-seconds S] [--pre k=v,..] [--post k=v,..] [--json]
"""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from . import actuate, audit, procedure_capture
from .errors import Refused

WORKED, DIDNT, UNCLEAR = "WORKED", "DIDN'T", "UNCLEAR"
DEFAULT_MAX_SECONDS = 10.0
_FAKE_HEADER = "18DAF110"
_LOCK = threading.Lock()

NRC_NAMES = {
    "10": "generalReject", "11": "serviceNotSupported", "12": "subFunctionNotSupported",
    "13": "incorrectMessageLength", "22": "conditionsNotCorrect", "24": "requestSequenceError",
    "31": "requestOutOfRange", "33": "securityAccessDenied", "35": "invalidKey",
    "72": "generalProgrammingFailure", "78": "responsePending",
    "7E": "subFunctionNotSupportedInActiveSession", "7F": "serviceNotSupportedInActiveSession",
}


# ===========================================================================
# Fake transport
# ===========================================================================

def _hex(bs) -> str:
    return "".join(f"{int(b, 16) if isinstance(b, str) else b:02X}" for b in bs)


def is_stop_request(request: list[str]) -> bool:
    """2F <did hi> <did lo> 00 (returnControlToECU) or 31 02 <routine> (stopRoutine)."""
    if not request:
        return False
    if request[0] == "2F":
        return len(request) > 3 and request[3] == "00"
    if request[0] == "31":
        return len(request) > 1 and request[1] == "02"
    return False


class FakeSession:
    """Quacks like ``transport.Session`` for ``actuate.run_actuator``; never touches a port."""

    def __init__(self, fake_replies: Optional[dict] = None, steps: Optional[list[dict]] = None) -> None:
        self.replies: dict[Any, Any] = {}
        for k, v in (fake_replies or {}).items():
            self.replies[k.upper() if isinstance(k, str) and k not in ("stop", "*") else k] = v
        self.steps = steps or []
        self.sent: list[dict[str, Any]] = []          # every transmit attempt, in order
        self.dead = False
        self._hits: dict[Any, int] = {}
        self.bus = SimpleNamespace(key="can_c")
        self.link = SimpleNamespace(cable="dry-run (no cable)")
        self.stream = SimpleNamespace(describe="DRY RUN: in-memory fake, no transport")

    def _spec(self, request: list[str]) -> Any:
        n = len(self.sent)                                # this send is index n (0-based)
        candidates: list[Any] = []
        if n < len(self.steps) and self.steps[n].get("request") == request:
            candidates.append(n + 1)
        candidates.append(_hex(request))
        if is_stop_request(request):
            candidates.append("stop")
        candidates.append("*")
        for key in candidates:
            if key in self.replies:
                val = self.replies[key]
                if isinstance(val, list):
                    i = self._hits.get(key, 0)
                    self._hits[key] = i + 1
                    return val[min(i, len(val) - 1)] if val else "ok"
                return val
        return "ok"

    def uds(self, ecu: Any, service: int, payload: bytes = b"", timeout: float = 3.0,
            retries_on_pending: int = 3) -> dict[str, Any]:
        request = [f"{service:02X}", *[f"{b:02X}" for b in payload]]
        spec = self._spec(request)
        rec = {"request": "".join(request), "spec": spec}
        self.sent.append(rec)
        if self.dead or spec == "disconnect":
            self.dead = True
            rec["outcome"] = "disconnected"
            raise ConnectionError("adapter disconnected (scripted)")
        base = {"request": rec["request"], "ecu": getattr(ecu, "code", ""), "bus": "can_c", "attempts": 1}
        svc = request[0]
        if isinstance(spec, dict):
            spec = f"nrc:{spec.get('nrc', '10')}"
        spec = str(spec or "ok")
        if spec == "no_reply":
            rec["outcome"] = "no reply"
            return {**base, "raw": "", "positive": {}, "nrc": {}, "error": "no response (timeout)"}
        if spec.startswith("nrc:"):
            code = spec.split(":", 1)[1].strip().upper().replace("0X", "").zfill(2)
            rec["outcome"] = f"NRC {code}"
            return {**base, "raw": f"7F{svc}{code}", "positive": {}, "nrc": {_FAKE_HEADER: int(code, 16)},
                    "error": None}
        if spec.startswith("pending"):
            want = int(spec.split(":", 1)[1]) if ":" in spec else 1
            tries = 0
            while tries < want:
                tries += 1
                if tries > retries_on_pending:       # the real Session gives up and returns the 0x78
                    rec["outcome"] = "NRC 78 (still pending, no retries left)"
                    return {**base, "raw": f"7F{svc}78", "positive": {}, "nrc": {_FAKE_HEADER: 0x78},
                            "error": None, "attempts": tries}
        raw = f"{(service + 0x40) & 0xFF:02X}" + "".join(request[1:])
        rec["outcome"] = "positive"
        return {**base, "raw": raw, "positive": {_FAKE_HEADER: raw}, "nrc": {}, "error": None}


class _DryAudit:
    """actuate's audit handle: the real audit log, every record tagged dry_run."""
    @staticmethod
    def record(event: str, **fields: Any) -> None:
        audit.record(event, dry_run=True, **fields)


class _NullStore:
    """Fake replies must never become observations about the car."""
    @staticmethod
    def record_observation(*a: Any, **k: Any) -> None:
        return None


# ===========================================================================
# Loading
# ===========================================================================

def load(capture: Any) -> dict[str, Any]:
    """Normalise a capture into ``{"source", "frames"|"procedure", "bitrate", "name", "pre", "post",
    "max_seconds", "mes_function", "vin", "format"}``. Accepts a path or a dict in any of the shapes
    mes_learn / procedure_capture produce: a ``.jsonl`` (header + frames), a dict with ``frames``,
    a stored ``*.review.json`` (its ``capture_file`` is loaded), or an extracted procedure (``steps``)."""
    src = "dict"
    if isinstance(capture, (str, Path)):
        src = str(capture)
        p = Path(capture)
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".jsonl":
            from . import mes_learn
            header, frames = mes_learn.load_capture(str(p))
            cap: dict[str, Any] = {**{k: v for k, v in header.items() if k != "type"}, "frames": frames,
                                   "format": "mes_learn .jsonl"}
        else:
            cap = json.loads(text)
            if not isinstance(cap, dict):
                raise ValueError("capture JSON must be an object")
    else:
        cap = dict(capture)
    if "frames" not in cap and "steps" not in cap and cap.get("capture_file"):
        from . import mes_learn
        header, frames = mes_learn.load_capture(cap["capture_file"])
        cap = {**{k: v for k, v in header.items() if k != "type"}, "frames": frames,
               "bitrate": cap.get("recorded_bitrate") or header.get("bitrate"),
               **{k: v for k, v in cap.items() if k in ("name", "pre", "post", "max_seconds", "mes_function")},
               "format": "stored review -> its capture file"}
    cap.setdefault("format", "frames" if "frames" in cap else "procedure")
    return {
        "source": src, "format": cap["format"], "frames": cap.get("frames"),
        "procedure": cap if "steps" in cap and "frames" not in cap else None,
        "bitrate": cap.get("bitrate") if cap.get("bitrate") is not None else cap.get("listen_bitrate"),
        "name": cap.get("name") or "", "pre": cap.get("pre"), "post": cap.get("post"),
        "max_seconds": cap.get("max_seconds"), "mes_function": cap.get("mes_function") or "",
        "vin": cap.get("vin") or "",
    }


# ===========================================================================
# Meaning
# ===========================================================================

def _meaning(step: dict[str, Any]) -> str:
    sent = step.get("sent") or []
    svc = sent[0] if sent else ""
    name = procedure_capture.SERVICE_NAMES.get(svc, f"service {svc}")
    if step.get("error") and "accepted" not in step:
        return f"{name}: NOT sent to completion, {step['error']}"
    if step.get("error"):
        return f"{name}: no usable reply ({step['error']})"
    if step.get("nrc"):
        return f"{name} REFUSED by the module: NRC {step['nrc']} {NRC_NAMES.get(step['nrc'], '')}".strip()
    if not step.get("accepted"):
        return f"{name}: not accepted"
    role = ""
    if is_stop_request(sent):
        role = " - control returned to the ECU" if svc == "2F" else " - routine stopped"
    elif svc == "2F":
        role = " - output commanded"
    elif svc == "31":
        role = " - routine started"
    elif svc == "10":
        role = " - session " + ("restored to default" if sent[1:2] == ["01"] else "changed")
    return f"{name} accepted{role}"


# ===========================================================================
# The run
# ===========================================================================

def _run_once(proc: dict[str, Any], ecu: Any, consent: str, fake_replies: Optional[dict],
              max_seconds: float, *, quiet: bool) -> tuple[dict[str, Any], FakeSession]:
    """actuate.run_actuator over a FakeSession. ``quiet`` swaps audit/store for no-ops (the clean
    preview pass must not leave records)."""
    fake = FakeSession(fake_replies, proc.get("steps"))
    with _LOCK:
        saved = (actuate.audit, actuate.store)
        actuate.audit = SimpleNamespace(record=lambda *a, **k: None) if quiet else _DryAudit
        actuate.store = _NullStore
        try:
            out = actuate.run_actuator(fake, ecu, proc, consent=consent, max_seconds=max_seconds)
        finally:
            actuate.audit, actuate.store = saved
    return out, fake


def _roles(proc: dict[str, Any], sent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = proc.get("steps") or []
    term = proc.get("synthesised_terminator")
    out = []
    for i, s in enumerate(sent):
        req = s["request"]
        if i < len(steps) and "".join(steps[i]["request"]) == req:
            role = "learned step %d" % (i + 1)
        elif term is not None and "".join(term["request"]) == req:
            role = "stop (synthesised: not in the capture)"
        elif req == "1001":
            role = "session restore (not in the capture)"
        else:
            role = "terminator (repeat of the last actuation)"
        out.append({"seq": i + 1, "bytes": req, "text": " ".join(req[j:j + 2] for j in range(0, len(req), 2)),
                    "role": role})
    return out


def _verdict(r: dict[str, Any]) -> tuple[str, str, Optional[str]]:
    """(word, one line, aborted_reason)"""
    log = r["steps"]
    learned = [s for s in log if s.get("label") == "learned"]
    aborted = next((s for s in log if s.get("label") in ("learned", "terminator failed") and s.get("error")
                    and "accepted" not in s), None)
    budget = next((s for s in log if s.get("label") == "budget"), None)
    reason = None
    if aborted:
        n = 1 + next((i for i, s in enumerate(learned) if s is aborted), len(learned))
        reason = (f"{'step %d' % n if aborted in learned else 'terminator'} failed to send: "
                  f"{aborted['error']}; return-control was still attempted")
    elif budget:
        reason = budget["note"]
    ret, rest = r["control_returned"], r["session_restored"]

    def is_start(s):
        q = s.get("sent") or []
        return bool(q) and ((q[0] == "2F" and not is_stop_request(q)) or (q[0] == "31" and not is_stop_request(q)))

    starts = [s for s in learned if is_start(s) and "accepted" in s]
    refused = [s for s in starts if not s["accepted"]]
    if not ret:
        tail = " Control NOT confirmed returned: switch the ignition OFF."
        if refused and not reason:
            s = refused[0]
            return (DIDNT, f"The module refused the actuation ({_meaning(s)}).{tail}", reason)
        why = reason or "the module did not acknowledge the stop / return-control request"
        return (UNCLEAR, f"Cannot call it: {why}.{tail}", reason)
    if reason:
        return (UNCLEAR, f"Run was cut short ({reason}); control did return to the module.", reason)
    if refused:
        return (DIDNT, f"The module refused the actuation ({_meaning(refused[0])}); control is returned.", None)
    if not rest:
        return (UNCLEAR, "Control returned, but the default session (10 01) was not confirmed restored.", None)
    bad = [s for s in learned if "accepted" in s and not s["accepted"] and not is_start(s)]
    if bad:
        return (UNCLEAR, f"Control returned, but a supporting step was not accepted ({_meaning(bad[0])}).", None)
    return (WORKED, "Every request was accepted, control returned to the ECU and the default session was "
                    "restored (protocol level, simulated replies: the physical effect is not observed).", None)


def dry_run(capture: Any, *, fake_replies: Optional[dict] = None, module: Optional[str] = None,
            name: Optional[str] = None, pre: Optional[dict] = None, post: Optional[dict] = None,
            max_seconds: Optional[float] = None, bitrate: Optional[int] = None, vin: str = "") -> dict[str, Any]:
    """Replay a capture against the gate and a fake transport. Never contacts hardware."""
    cap = load(capture)
    name = name or cap["name"]
    pre = pre if pre is not None else cap["pre"]
    post = post if post is not None else cap["post"]
    max_s = max_seconds if max_seconds is not None else cap["max_seconds"]
    bitrate = bitrate if bitrate is not None else cap["bitrate"]
    warnings = ["DRY RUN: replies are simulated, nothing was transmitted and the car was not contacted.",
                "A real run also sends adapter set-up, a CAN-C bus verification listen and PID 0C/0D "
                "reads (engine off, 0 km/h required); those are not shown in would_send."]
    rep: dict[str, Any] = {
        "source": cap["source"], "format": cap["format"], "dry_run": True, "name": name,
        "gate": {"passed": False, "status": "not run", "reasons": [], "consent": None},
        "procedures_found": [], "procedure_used": None, "steps": [], "control_returned": False,
        "session_restored": False, "aborted_reason": None, "verdict": UNCLEAR, "verdict_line": "",
        "would_send": [], "would_send_text": "", "warnings": warnings, "ran": False,
    }

    # --- review + gate, exactly as mes_learn._auto_review / the real path do ---
    if cap["frames"] is not None:
        review = procedure_capture.review(cap["frames"])
    else:
        p = cap["procedure"]
        mod = procedure_capture._module_for(p["target"])
        review = {"transactions": len(p["steps"]), "modules": [{
            "target": p["target"], "module": mod.code if mod else None, "procedure": p,
            "sequence": [s["service"] for s in p["steps"]]}]}
    mods = review["modules"]
    rep["procedures_found"] = [{"module": m["module"], "target": m["target"], "kind": m["procedure"]["kind"],
                               "sequence": m["sequence"]} for m in mods]
    if not mods:
        rep["gate"]["reasons"] = ["no UDS requests found in the capture"]
        rep["gate"]["status"] = "failed"
        return _finish(rep, None)
    chosen = next((m for m in mods if module and (m["module"] or "").upper() == module.upper()), None)
    if chosen is None:
        chosen = next((m for m in mods if m["procedure"]["kind"] in ("io_control", "routine_control")), mods[0])
    rep["procedure_used"] = {"module": chosen["module"], "target": chosen["target"]}
    if len(mods) > 1:
        warnings.append(f"Capture holds {len(mods)} module conversations "
                        f"({', '.join(str(m['module'] or m['target']) for m in mods)}); "
                        f"this report covers {chosen['module'] or chosen['target']} only. "
                        f"Pass module=... to pick another.")
    proc = copy.deepcopy(chosen["procedure"])
    proc["name"] = name or ""
    if vin or cap["vin"]:
        proc["vin"] = vin or cap["vin"]

    g = procedure_capture.gate(chosen, listen_bitrate=bitrate, pre=pre, post=post, max_seconds=max_s,
                               name=name or "", mes_function=cap["mes_function"])
    rep["gate"] = g
    if not g["passed"]:
        rep["verdict_line"] = "Not run: the safety gate refused this procedure (" + "; ".join(g["reasons"]) + \
                              "). Nothing would be sent."
        return _finish(rep, None)

    ecu = procedure_capture._module_for(chosen["target"])
    for st in proc["steps"]:        # learned gaps are timing only; skip them so the rehearsal is instant
        st["t_req"] = None
    budget = float(max_s) if max_s else DEFAULT_MAX_SECONDS
    try:
        # clean preview first: the exact bytes a real, fully-accepted run transmits
        clean, cfake = _run_once(proc, ecu, g["consent"], None, budget, quiet=True)
        rep["would_send"] = _roles(proc, cfake.sent)
        rep["would_send_text"] = "\n".join(f"{w['seq']:>2}. {w['text']:<24} {w['role']}" for w in rep["would_send"])
        out, fake = _run_once(proc, ecu, g["consent"], fake_replies, budget, quiet=False)
    except Refused as e:           # the replay gate refusing is the gate doing its job
        rep["gate"] = dict(g, passed=False, status="failed", reasons=[f"replay gate refused: {e}"])
        rep["verdict_line"] = f"Not run: replay gate refused ({e}). Nothing would be sent."
        rep["would_send"], rep["would_send_text"] = [], ""
        return _finish(rep, None)

    rep["ran"] = True
    rep["actually_sent_in_rehearsal"] = _roles(proc, fake.sent)
    for s in out["steps"]:
        if s.get("label") in ("budget",):
            continue
        sent = s.get("sent") or []
        rep["steps"].append({"label": s.get("label"), "request": "".join(sent), "reply": s.get("raw") or "",
                             "accepted": s.get("accepted"), "nrc": s.get("nrc"), "error": s.get("error"),
                             "meaning": _meaning(s)})
    rep["control_returned"], rep["session_restored"] = out["control_returned"], out["session_restored"]
    word, line, why = _verdict(out)
    rep["verdict"], rep["verdict_line"], rep["aborted_reason"] = word, line, why
    rep["outcome"] = out["outcome"]
    if fake_replies:
        warnings.append("Replies were SCRIPTED (fake_replies), not defaults: this rehearses a failure path.")
    return _finish(rep, out)


def _finish(rep: dict[str, Any], out: Optional[dict[str, Any]]) -> dict[str, Any]:
    audit.record("procedure_dry_run", source=rep["source"], name=rep["name"], gate_passed=rep["gate"]["passed"],
                 ran=rep["ran"], verdict=rep["verdict"], control_returned=rep["control_returned"],
                 session_restored=rep["session_restored"], aborted_reason=rep["aborted_reason"],
                 would_send=[w["bytes"] for w in rep["would_send"]], dry_run=True)
    return rep


# ===========================================================================
# Text + CLI
# ===========================================================================

def render_text(rep: dict[str, Any]) -> str:
    g = rep["gate"]
    L = [f"DRY RUN (no car, nothing transmitted): {rep['name'] or '(unnamed)'}  [{rep['source']}]"]
    pf = rep["procedures_found"]
    if pf:
        L.append("Procedures in capture: " + "; ".join(f"{p['module'] or p['target']} ({p['kind']})" for p in pf)
                 + f" -> using {(rep['procedure_used'] or {}).get('module')}")
    L.append(f"GATE: {'PASS' if g['passed'] else 'FAIL'} ({g['status']})")
    for r in g["reasons"]:
        L.append(f"  - {r}")
    if g.get("consent"):
        L.append(f"  consent phrase a real run needs: {g['consent']}")
    if rep["would_send"]:
        L.append("WOULD SEND TO THE CAR (in order):")
        L.extend("  " + ln for ln in rep["would_send_text"].splitlines())
    if rep["steps"]:
        L.append("REHEARSAL (scripted replies):")
        for s in rep["steps"]:
            L.append(f"  {s['request']:<12} -> {s['reply'] or '(none)':<12} {'ok ' if s['accepted'] else 'NO '} {s['meaning']}")
        L.append(f"control_returned={rep['control_returned']}  session_restored={rep['session_restored']}  "
                 f"aborted_reason={rep['aborted_reason']}")
    L.append(f"VERDICT: {rep['verdict']} - {rep['verdict_line']}")
    L.extend("WARNING: " + w for w in rep["warnings"])
    return "\n".join(L)


def _kv(s: Optional[str]) -> Optional[dict[str, Any]]:
    if not s:
        return None
    out: dict[str, Any] = {}
    for part in s.split(","):
        k, _, v = part.partition("=")
        try:
            out[k.strip()] = float(v) if k.strip() == "voltage_v" else v.strip()
        except ValueError:
            out[k.strip()] = v.strip()
    return out


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m cuore.live.procedure_dry_run", description=__doc__.split("\n")[0])
    ap.add_argument("capture")
    ap.add_argument("--nrc", action="append", default=[], metavar="STEP:CODE", help="module answers NRC CODE at step STEP (1-based)")
    ap.add_argument("--drop-stop", action="store_true", help="the stop / return-control request gets no acknowledgement")
    ap.add_argument("--disconnect", type=int, metavar="STEP", help="adapter drops at step STEP and stays down")
    ap.add_argument("--name"); ap.add_argument("--module"); ap.add_argument("--max-seconds", type=float)
    ap.add_argument("--bitrate", type=int); ap.add_argument("--pre"); ap.add_argument("--post")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    fr: dict[Any, Any] = {}
    for item in a.nrc:
        step, _, code = item.partition(":")
        fr[int(step)] = f"nrc:{code}"
    if a.drop_stop:
        fr["stop"] = "no_reply"
    if a.disconnect:
        fr[a.disconnect] = "disconnect"
    rep = dry_run(a.capture, fake_replies=fr or None, module=a.module, name=a.name, pre=_kv(a.pre),
                  post=_kv(a.post), max_seconds=a.max_seconds, bitrate=a.bitrate)
    print(json.dumps(rep, indent=1, default=str) if a.json else render_text(rep))
    return 0 if rep["verdict"] == WORKED else 2


if __name__ == "__main__":
    raise SystemExit(main())
