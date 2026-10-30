"""Passive, listen-only recording of the manufacturer's tool (wiTECH) on CAN-C.

Owner decision 2026-10-30 (docs/project/DECISIONS.md): CUORE may passively record wiTECH
working on the reference car and use the decoded, read-back-verified traffic as the source of a
write procedure (source kind "witech_observed"). Recording MES / AlfaOBD / Launch for writes
stays prohibited; nothing here has a MES path.

Setup: wiTECH's pod sits in the OBD port; an OBD Y-splitter puts CUORE's adapter on the same
CAN-C pins (500 kbps). The splitter is declared with declare_splitter() (cable
"witech_splitter"). Under it CAN-C is reachable ONLY for passive sessions at CAN-C's confirmed
bitrate; cuore.live.transport refuses any transmitting session.

There is NO transmit path in this module: every session is passive=True (built on
cuore.live.buscapture), and there is no 0x27 / 0x2E / 0x31 sending code.

* start / stop / save -- record, tagged with the wiTECH function.
* transcript -- ordered decode (time, module, service, request, response, NRC); every 0x27
  SecurityAccess exchange is flagged (the seed changes every time; a recording does not give the
  algorithm).
* make_draft -- a DRAFT procedure under <state>/procedure_drafts/ (never in
  cuore/data/procedures and never loadable by cuore.live.procedure_sources), with the
  procedure_capture.gate result stored in it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from . import actuate, buscapture, interlock, replay, store
from . import procedure_capture as pc
from .addressing import MODULES
from .buses import BUSES, route_for
from .channels import Channel
from .config import state_dir
from .errors import BadCommand, Refused
from .learn import uds_transactions
from .poller import CsvRecorder
from .transport import link

CABLE = "witech_splitter"
BUS_KEY = "can_c"
KIND = "witech_recording"
DRAFT_STATUS = "draft from wiTECH recording"
UNLOCK_FLAG = "unlock: seed changes every time; recording does not give the algorithm"

NRC_NAMES = {
    "10": "generalReject", "11": "serviceNotSupported", "12": "subFunctionNotSupported",
    "13": "incorrectMessageLength", "22": "conditionsNotCorrect", "24": "requestSequenceError",
    "31": "requestOutOfRange", "33": "securityAccessDenied", "35": "invalidKey",
    "36": "exceededNumberOfAttempts", "37": "requiredTimeDelayNotExpired",
    "72": "generalProgrammingFailure", "78": "responsePending",
    "7E": "subFunctionNotSupportedInActiveSession", "7F": "serviceNotSupportedInActiveSession",
}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


# --------------------------------------------------------------------------- storage
def recordings_dir():
    d = state_dir() / "witech_recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def drafts_dir():
    d = state_dir() / "procedure_drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- recording
def declare_splitter() -> dict[str, Any]:
    """Declare that the OBD Y-splitter (wiTECH pod + this adapter) is fitted."""
    return buscapture.set_cable(CABLE)


def _check_ready() -> None:
    bus = BUSES[BUS_KEY]
    lk = link()
    if lk.cable != CABLE:
        raise Refused(f"CAN-C may be recorded for wiTECH only with the {CABLE!r} cable declared; "
                      f"the declared cable is {lk.cable!r}. Fit the Y-splitter and declare it first.")
    route = route_for(bus, lk.cable)
    rate = route.bitrate_override if route is not None and route.bitrate_override else bus.bitrate
    if route is None or bus.bitrate_confidence != "confirmed" or rate != bus.bitrate:
        raise Refused(f"{BUS_KEY} bitrate is not the confirmed {bus.bitrate}; refusing to listen")
    held = interlock.blocked_by()
    if held:
        raise Refused(f"adapter is held: {held}")


def start(function: str) -> dict[str, Any]:
    """Start a passive CAN-C recording tagged with the wiTECH function being run."""
    function = (function or "").strip()
    if not function:
        raise BadCommand("name the wiTECH function the technician is about to run "
                         "(e.g. 'Oil service reset')")
    _check_ready()
    return buscapture._start(BUS_KEY, "witech", function)   # passive=True inside buscapture._run


def status() -> dict[str, Any]:
    return buscapture.capture_status(BUS_KEY)


def stop() -> dict[str, Any]:
    return buscapture._stop(BUS_KEY)


def save(vin: str = "") -> dict[str, Any]:
    """Write the stopped recording as CSV (as bus captures are) plus a raw-frames JSON."""
    state = buscapture._get(BUS_KEY)
    if state["purpose"] != "witech":
        raise BadCommand("the last CAN-C session was not a wiTECH recording")
    if state["status"] == "running":
        raise BadCommand("this recording is still running; stop it first")
    if state.get("saved_name"):
        return {**buscapture._public(state), "id": state["saved_name"].rsplit(".", 1)[0],
                "already_saved": True}
    bus = BUSES[BUS_KEY]
    channels = [Channel(id=f"raw_{h}", name=f"CAN {h}", unit="hex", kind="broadcast", bus=BUS_KEY,
                        confidence="raw_capture", default_rate_hz=0.0)
                for h in sorted(state["ids"])]
    rid = f"witech_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    csv_path = replay.cuore_recordings_dir() / f"{rid}.csv"
    frames = sorted(state["frames"], key=lambda x: x["t"])
    rec = CsvRecorder(csv_path, channels)
    rec.start()
    for f in frames:
        rec.update(f"raw_{f['id']}", f["data"])
        rec.write_row()
    rec.stop()
    doc = {"id": rid, "kind": KIND, "function": state["action"], "vin": vin, "bus": BUS_KEY,
           "bitrate": bus.bitrate, "cable": state["cable"], "passive": True,
           "started_at": state["started_at"], "finished_at": state["finished_at"],
           "csv": str(csv_path), "frame_count": len(frames), "frames": frames}
    (recordings_dir() / f"{rid}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    state["saved_path"] = str(csv_path)
    state["saved_name"] = csv_path.name
    store.record_observation(
        KIND, {"recording": rid, "function": state["action"], "csv": str(csv_path),
               "frame_count": len(frames), "bitrate": bus.bitrate},
        vin=vin, bus=BUS_KEY, cable=state["cable"], stream=state["stream"] or "")
    return {**buscapture._public(state), "id": rid, "already_saved": False}


def list_recordings() -> list[dict[str, Any]]:
    out = []
    for p in sorted(recordings_dir().glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({k: d.get(k) for k in ("id", "function", "started_at", "frame_count", "bitrate")})
    return out


def load_recording(rid: str) -> dict[str, Any]:
    if not _ID_RE.match(rid or ""):
        raise BadCommand("bad recording id")
    p = recordings_dir() / f"{rid}.json"
    if not p.exists():
        raise BadCommand(f"no recording {rid!r}")
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- decoder
def _module_code(target_hex: str) -> str:
    t = int(target_hex, 16)
    m = next((m for m in MODULES if m.target == t), None)
    return m.code if m else f"unknown (0x{target_hex})"


def transcript(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordered rows: time, module, service name, request, response, NRC, unlock flag."""
    rows = []
    for tr in uds_transactions(rec.get("frames") or []):
        svc = tr["service"]
        resp = tr["response"]
        if resp is None:
            kind = "no response seen"
        elif resp[0].upper() == "7F":
            kind = "negative"
        else:
            kind = "positive"
        nrc = tr.get("nrc")
        rows.append({
            "t": tr["t_req"], "module": _module_code(tr["target"]), "target": tr["target"],
            "service": svc, "service_name": pc.SERVICE_NAMES.get(svc, f"service 0x{svc}"),
            "request": "".join(tr["request"]).upper(),
            "response": "".join(resp).upper() if resp else "", "result": kind,
            "nrc": nrc, "nrc_name": NRC_NAMES.get(nrc, "") if nrc else "",
            "flag": UNLOCK_FLAG if svc == "27" else "",
        })
    return rows


# --------------------------------------------------------------------------- draft procedure
def make_draft(rid: str) -> list[dict[str, Any]]:
    """One draft per module the tester talked to. Saved only under procedure_drafts/."""
    rec = load_recording(rid)
    txs = uds_transactions(rec.get("frames") or [])
    out = []
    for target in sorted({t["target"] for t in txs}):
        proc = actuate.extract_procedure(txs, target)
        code = _module_code(target)
        steps, behind = [], False
        for st in proc["steps"]:
            if st["service"] == "27":
                behind = True
            steps.append({
                "request": "".join(st["request"]), "response": "".join(st["response"] or []),
                "nrc": st["nrc"], "needs_algorithm": behind,
                **({"note": UNLOCK_FLAG} if st["service"] == "27" else {}),
            })
        name = re.sub(r"[^A-Za-z0-9_-]", "", f"{rid}__{code}".replace(" ", "_"))
        gate = pc.gate(proc, listen_bitrate=rec.get("bitrate"), name=name)
        draft = {
            "schema": 1, "name": name, "module": code, "target": target,
            "title": f"{rec.get('function')} (observed in wiTECH)",
            "intent": f"Steps wiTECH sent to {code} while the technician ran: {rec.get('function')}. "
                      "Observed, not documented; not executable.",
            "status": DRAFT_STATUS, "accepted_by_owner": False, "executable": False,
            "session": {"bus": rec.get("bus"), "bitrate": rec.get("bitrate"),
                        "diagnostic_session": proc.get("session_sub")},
            "steps": steps,
            "needs_algorithm": any(s["needs_algorithm"] for s in steps),
            "read_back": {"status": "unknown", "label": "Must be proven with a CUORE read before and "
                          "after (see the Dealer session checklist).", "checks": []},
            "preconditions": {"engine_state": None, "voltage_v": None, "label": "unknown"},
            "postconditions": {"engine_state": None, "voltage_v": None, "label": "unknown"},
            "verification_rule": "Unknown until a CUORE read-back before and after is recorded.",
            "source": {"kind": "witech_observed", "recording": rid, "function": rec.get("function"),
                       "confidence": "observed, unverified"},
            "gate": gate,
        }
        (drafts_dir() / f"{name}.json").write_text(json.dumps(draft, indent=1), encoding="utf-8")
        out.append(draft)
    return out


def list_drafts(rid: str) -> list[dict[str, Any]]:
    out = []
    for p in sorted(drafts_dir().glob(f"{rid}__*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


CHECKLIST: list[dict[str, str]] = [
    {"function": "Oil / service reset",
     "tech": "In wiTECH select the engine-oil / service-interval reset and run it.",
     "before": "CUORE read: service-interval / oil-life values if the module exposes them (read-only 0x22); battery voltage.",
     "after": "Read the same values again; the reset is proven only if they changed as expected."},
    {"function": "Battery registration",
     "tech": "In wiTECH run the battery replacement / registration routine.",
     "before": "CUORE read: battery voltage and any battery-sensor values the module exposes.",
     "after": "Read them again; confirm no new DTCs in the battery-sensor module."},
    {"function": "Paddle-shifter market + PROXI alignment",
     "tech": "In wiTECH change the paddle-shifter market setting in the BCM, then run PROXI alignment.",
     "before": "CUORE read: the PROXI block (Configuration page), byte 156 bits 4-5, and module DTCs.",
     "after": "Read the PROXI block again after alignment: the bits changed and no module reports a mismatch."},
    {"function": "Key learning (last)",
     "tech": "In wiTECH run key learning last, after the other functions. Expect 0x27 SecurityAccess.",
     "before": "CUORE read: number of keys known if exposed, and module DTCs.",
     "after": "Read again; every key starts the car. The recording shows the exchange, not the unlock algorithm."},
]

__all__ = ["declare_splitter", "start", "status", "stop", "save", "list_recordings",
           "load_recording", "transcript", "make_draft", "list_drafts", "CHECKLIST"]
