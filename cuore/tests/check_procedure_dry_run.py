"""Checks for cuore.live.procedure_dry_run (gate + replay against a fake transport; no car).

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_procedure_dry_run.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-dryrun-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import audit, procedure_dry_run as dr  # noqa: E402
from cuore.live.buses import BUSES  # noqa: E402

failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def frame(t, can_id, bs):
    n = len(bs)
    return {"t": t, "id": can_id, "data": f"{n:02X}" + "".join(f"{b:02X}" for b in bs)}


def pair(t, req):
    return [frame(t, "18DA10F1", req), frame(t + 0.01, "18DAF110", [req[0] + 0x40, *req[1:]])]


PRE = {"engine_state": "off", "voltage_v": 12.6}
POST = {"engine_state": "off", "voltage_v": 12.5}
RATE = BUSES["can_c"].bitrate


def capture(frames, **kw):
    return {"frames": frames, "bitrate": RATE, "name": "Evap vent", "pre": PRE, "post": POST, **kw}


FULL = (pair(0.0, [0x10, 0x03]) + pair(1.0, [0x2F, 0x12, 0x34, 0x03, 0xAA])
        + pair(2.0, [0x2F, 0x12, 0x34, 0x00]) + pair(3.0, [0x10, 0x01]))
NOSTOP = pair(0.0, [0x10, 0x03]) + pair(1.0, [0x2F, 0x12, 0x34, 0x03, 0xAA])
WITH27 = pair(0.0, [0x10, 0x03]) + pair(1.0, [0x27, 0x01]) + pair(2.0, [0x2F, 0x12, 0x34, 0x03, 0xAA]) \
    + pair(3.0, [0x2F, 0x12, 0x34, 0x00])

# --- 1. clean pass: gate passes, WORKED, control returned ------------------
r = dr.dry_run(capture(FULL))
check("gate passes", r["gate"]["passed"], str(r["gate"]))
check("verdict WORKED", r["verdict"] == "WORKED", r["verdict_line"])
check("control returned + session restored", r["control_returned"] and r["session_restored"])
check("would_send is the captured bytes in order",
      [w["bytes"] for w in r["would_send"]] == ["1003", "2F12340 3AA".replace(" ", ""), "2F123400", "1001"],
      str(r["would_send"]))
check("steps carry request/reply/meaning", len(r["steps"]) == 4 and r["steps"][2]["meaning"].endswith(
    "control returned to the ECU") and r["steps"][1]["reply"] == "6F123403AA", str(r["steps"]))
check("states simulation", any("simulated" in w.lower() for w in r["warnings"]))

# --- 2. 0x27 present: gate refuses, nothing would be sent ------------------
r = dr.dry_run(capture(WITH27))
check("0x27: gate fails", not r["gate"]["passed"] and any("0x27" in x for x in r["gate"]["reasons"]),
      str(r["gate"]))
check("0x27: not run, nothing to send", not r["ran"] and r["would_send"] == [] and r["verdict"] == "UNCLEAR")

# --- 3. no captured stop: synthesised terminator in would_send; refused -----
r = dr.dry_run(capture(NOSTOP, max_seconds=10))
check("no-stop: gate passes with declared timeout", r["gate"]["passed"], str(r["gate"]))
ws = [w["bytes"] for w in r["would_send"]]
check("no-stop: synthesised terminator + restore in would_send", ws == ["1003", "2F12340 3AA".replace(" ", ""), "2F123400", "1001"], str(ws))
check("no-stop: terminator labelled synthesised", "synthesised" in r["would_send"][2]["role"])
r = dr.dry_run(capture(NOSTOP, max_seconds=10), fake_replies={"stop": "nrc:22"})
check("refused stop: control NOT returned", r["control_returned"] is False)
check("refused stop: DIDN'T/UNCLEAR", r["verdict"] in ("DIDN'T", "UNCLEAR"), r["verdict"])
check("refused stop: tells owner to switch ignition off", "ignition" in r["verdict_line"].lower())
check("refused stop: terminator shown still in would_send", "2F123400" in [w["bytes"] for w in r["would_send"]])
r2 = dr.dry_run(capture(FULL), fake_replies={"stop": "no_reply"})
check("missing stop ack: UNCLEAR, not returned", r2["verdict"] == "UNCLEAR" and not r2["control_returned"])
r3 = dr.dry_run(capture(FULL), fake_replies={2: "nrc:31"})
check("actuation refused: DIDN'T", r3["verdict"] == "DIDN'T" and r3["control_returned"], r3["verdict_line"])
r4 = dr.dry_run(capture(FULL), fake_replies={2: "pending"})
check("0x78 pending on a learned step is not accepted", r4["steps"][1]["nrc"] == "78" and r4["verdict"] == "DIDN'T",
      str(r4["steps"][1]))

# --- 4. disconnect mid-run: aborted, return-control attempted --------------
r = dr.dry_run(capture(FULL), fake_replies={2: "disconnect"})
check("disconnect: aborted_reason set", bool(r["aborted_reason"]) and "step 2" in r["aborted_reason"], str(r["aborted_reason"]))
check("disconnect: UNCLEAR, control not returned", r["verdict"] == "UNCLEAR" and not r["control_returned"])
sent = [s["bytes"] for s in r["actually_sent_in_rehearsal"]]
check("disconnect: return-control was still attempted", "2F123400" in sent, str(sent))
check("disconnect: failure recorded as terminator failed", any(s["label"] == "terminator failed" for s in r["steps"]),
      str(r["steps"]))

# --- 5. audit records in the temp state dir, flagged dry_run ----------------
lp = audit.log_path()
check("audit log is under the temp state dir", str(lp).startswith(_TMP), str(lp))
recs = [json.loads(x) for x in lp.read_text(encoding="utf-8").splitlines() if x.strip()]
ev = {x["event"] for x in recs}
check("audit: actuate + procedure_dry_run written", {"actuate", "procedure_dry_run"} <= ev, str(ev))
check("audit: every one tagged dry_run", all(x.get("dry_run") for x in recs if x["event"] in ("actuate", "procedure_dry_run")))
check("no observation store written", not (Path(_TMP) / "observations").exists()
      and not any("actuator_test" in p.read_text(errors="ignore") for p in Path(_TMP).rglob("*.json*") if "audit" not in p.name))

# --- 6. CLI -----------------------------------------------------------------
cap_file = Path(_TMP) / "cap.json"
cap_file.write_text(json.dumps(capture(FULL)), encoding="utf-8")
import io, contextlib  # noqa: E402
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = dr.main([str(cap_file), "--drop-stop"])
check("CLI prints verdict and would-send", "VERDICT: UNCLEAR" in buf.getvalue() and "WOULD SEND" in buf.getvalue() and rc == 2,
      buf.getvalue()[-400:])

# --- 7. prototype screen uses the dry run when a capture file exists ----------
from cuore.services import procedure_sim as sim  # noqa: E402
cdir = Path(_TMP) / "procedure_captures"
cdir.mkdir()
(cdir / "esim-vent.json").write_text(json.dumps(capture(FULL)), encoding="utf-8")
sim.CAR.reset(); sim.answer("hood")
run, why = sim.start("esim-vent", sim.mint_token("esim-vent"))
check("prototype: run started", run is not None, why)
check("prototype: result comes from the dry run", run.dry is not None and run.result["word"] == "WORKED"
      and run.result.get("dry_run") and run.dry["gate"]["passed"] and run.dry["would_send"], str(run.result))
sim.CAR.reset(); sim.CAR.toggle("ambiguous_proof"); sim.answer("hood")
run, _ = sim.start("esim-vent", sim.mint_token("esim-vent"))
check("prototype: fault scripts a missing stop ack", run.result["word"] == "UNCLEAR", str(run.result))
(cdir / "esim-vent.json").unlink()
sim.CAR.reset(); sim.answer("hood")
run, _ = sim.start("esim-vent", sim.mint_token("esim-vent"))
check("prototype: no capture -> hand-written simulator", run is not None and run.dry is None)

print(f"procedure_dry_run checks: {checks - len(failures)} passed, {len(failures)} failed")
for f in failures:
    print("  FAIL:", f)
sys.exit(1 if failures else 0)
