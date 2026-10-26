"""Checks for the PROTOTYPE interactive-procedure screens (simulated car only).

Run:
    .venv/Scripts/python.exe cuore/tests/check_procedure_prototype.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_TMP = tempfile.mkdtemp(prefix="cuore_procproto_")
os.environ["CUORE_STATE_DIR"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import procedure_sim as sim  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


client = TestClient(create_app())
BASE = f"/v/{VIN}/procedures/prototype"
sim.open_job = lambda vin: None                      # generic WHY unless a test sets a job
now = [1000.0]
sim.CLOCK = lambda: now[0]
sim.TODAY = lambda: date(2026, 10, 26)


def fresh() -> None:
    sim.CAR.reset()
    sim._TOKENS.clear()
    sim.RUNS.clear()
    now[0] += 1000


def ready_esim() -> str:
    sim.answer("hood")
    return sim.mint_token("esim-vent")


def start_esim() -> sim.Run:
    run, why = sim.start("esim-vent", ready_esim())
    assert run, why
    return run


def text(html: str) -> str:
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", html)))


# -- banner on every page / state
fresh()
pages = [BASE, f"{BASE}/esim-vent", f"{BASE}/service-reset"]
for u in pages:
    r = client.get(u)
    check(r.status_code == 200 and "simulated car, nothing is sent to the Stelvio" in r.text and "PROTOTYPE" in r.text, f"banner on {u}")
run = start_esim()
tr = client.get(f"{BASE}/esim-vent?run={run.id}").text
check("simulated car, nothing is sent to the Stelvio" in tr and "RUNNING" in tr, "banner on the running view")
sim.stop(run.id)
ta = client.get(f"{BASE}/esim-vent?run={run.id}").text
check("simulated car, nothing is sent to the Stelvio" in ta, "banner on the after view")

# -- link in the More menu (not the visible row)
vt = client.get(f"/v/{VIN}/fuses").text
check(f'href="{BASE}"' in vt and "Prototype: interactive procedures" in vt, "More menu has the prototype link")
check(f'href="{BASE}"' not in vt.split("<details")[0], "link is not in the visible row")

# -- READY chips reflect the simulator; blockers name the unblock step
fresh()
t = client.get(f"{BASE}/esim-vent").text
check("Engine running, idle: 780 rpm" in text(t) and "Battery 12.5 V or more: 13.9 V" in text(t), "chips show live simulated readings")
for fault, label, step in (("mes_holding", "Adapter free", "Close MES"), ("cable_missing", "Cable fitted", "Fit the blue A5 cable"),
                           ("engine_stalls", "Engine running, idle", "Start the engine"), ("moving", "Stationary, in P", "Stop, select P"),
                           ("voltage_drops", "Battery 12.5 V or more", "Charge the battery"), ("ignition_off", "Ignition on", "Turn the ignition on")):
    fresh()
    sim.CAR.toggle(fault)
    h = text(client.get(f"{BASE}/esim-vent").text)
    check(f"{label} is blocking. {step}" in h, f"blocker {fault} names its unblock step")
    check("HOLD 2 s TO START - not ready" in h, f"no start control while {fault}")
fresh()
h = client.get(f"{BASE}/esim-vent").text
check("Hood open, hands clear of the fan?" in h and 'name="ask" value="hood"' in h, "unknown asked as a single Yes button")
check('name="token"' not in h, "no token while the question is unanswered")
client.post(f"{BASE}/esim-vent/recheck", data={"ask": "hood"})
h = client.get(f"{BASE}/esim-vent").text
check('name="token"' in h and "HOLD 2 s TO START" in h and 'id="pp-hold"' in h, "ready: token + hold button appear")
check("Hood open" in h and "pp-ok" in h, "answered question shows OK")

# -- WHY generic vs real job
check("No open job found" in h, "generic WHY without an open job")
sim.open_job = lambda vin: {"id": "76d3abcdef", "text": "EVAP codes P0440"}
h = client.get(f"{BASE}/esim-vent").text
check("76d3abcd" in h and "EVAP codes P0440" in h and f'href="/v/{VIN}/job"' in h, "WHY links the real open job")
sim.open_job = lambda vin: None

# -- tokens
fresh()
check(sim.mint_token("esim-vent") is None, "no token while the question is unanswered")
sim.answer("hood")
sim.CAR.toggle("mes_holding")
check(sim.mint_token("esim-vent") is None, "no token while blocked")
sim.CAR.toggle("mes_holding")
tok = sim.mint_token("esim-vent")
check(bool(tok), "token minted when READY passes")
r1, why1 = sim.start("esim-vent", tok)
check(r1 is not None, "start with a valid token runs")
sim.stop(r1.id)
sim.answer("hood")
r2, why2 = sim.start("esim-vent", tok)
check(r2 is None and "token" in why2, "second start with the same token refused")
r3, why3 = sim.start("esim-vent", "")
check(r3 is None, "start without a token refused")
n_runs = len(sim.RUNS)
resp = client.post(f"{BASE}/esim-vent/start", data={"token": "nope"}, follow_redirects=False)
check(resp.status_code == 303 and "refused" in resp.headers["location"].lower() and len(sim.RUNS) == n_runs, "POST start with a bad token refused, no run")
resp = client.post(f"{BASE}/esim-vent/start", data={}, follow_redirects=False)
check(resp.status_code == 303 and len(sim.RUNS) == n_runs, "POST start without a token refused")
# token goes stale if the car stops being ready before the hold finishes
fresh()
tok = ready_esim()
sim.CAR.toggle("engine_stalls")
r4, why4 = sim.start("esim-vent", tok)
check(r4 is None and "Engine running" in why4, "start re-checks READY and refuses, naming the blocker")
check(tok not in sim._TOKENS, "token consumed even when the start is refused")
# one controller
fresh()
run = start_esim()
sim.answer("hood")
other, why5 = sim.start("esim-vent", sim.mint_token("esim-vent") or "")
check(other is None, "second screen cannot start while one runs")
sim.stop(run.id)

# -- POST start -> run page; STOP POST stops
fresh()
tok = ready_esim()
resp = client.post(f"{BASE}/esim-vent/start", data={"token": tok}, follow_redirects=False)
loc = resp.headers["location"]
rid = loc.split("run=")[1]
check(resp.status_code == 303 and rid in sim.RUNS and sim.RUNS[rid].state == "running", "valid POST start begins a run")
page = client.get(loc).text
check("RUNNING" in page and ">STOP<" in page and f'action="{BASE}/esim-vent/stop"' in page, "running view: timer + STOP as a plain form POST")
check("EventSource" in page and "expected: falls" in text(page) and "(guard)" in page, "running view: live proof with expected direction + guards via EventSource")
check("pp-stop" in page and "min-height: 150px" in open(Path(__file__).resolve().parents[1] / "web/static/procedure_proto.css").read(), "STOP is the large control")
now[0] += 3
resp = client.post(f"{BASE}/esim-vent/stop", data={"run": rid}, follow_redirects=False)
check(sim.RUNS[rid].state == "done" and sim.RUNS[rid].stop_reason == "stop", "STOP POST stops the run")
after = client.get(f"{BASE}/esim-vent?run={rid}").text
check("Stopped with the STOP button" in after, "after view says it was stopped with STOP")

# -- guard breach
for fault, why in (("engine_stalls", "Engine stalled"), ("moving", "Car started moving"), ("voltage_drops", "Battery voltage dropped")):
    fresh()
    run = start_esim()
    now[0] += 2
    check(run.snapshot()["state"] == "running", f"{fault}: running before the breach")
    sim.CAR.toggle(fault)
    sn = run.snapshot()
    check(sn["state"] == "done" and run.stop_reason == "guard" and why in run.stop_text, f"guard breach {fault} stops with the reason")
    check(run.result["word"] == "UNCLEAR", f"{fault}: cut-short run is UNCLEAR")
    check(why in client.get(f"{BASE}/esim-vent?run={run.id}").text, f"{fault}: reason shown on the page")

# -- timeout
fresh()
run = start_esim()
now[0] += 29
check(run.snapshot()["state"] == "running", "still running at 29 s")
now[0] += 2
sim.reap()
check(run.state == "done" and run.stop_reason == "timeout" and "30 s" in run.stop_text, "max time (30 s) stops the run on the server")
check(run.result["word"] == "WORKED", "a full-length good run is WORKED")

# -- stream disconnect
fresh()
run = start_esim()


async def _drop():
    agen = sim.stream_events(run.id, interval=0.01)
    first = await agen.__anext__()
    await agen.aclose()
    return first


first = asyncio.run(_drop())
check(first.startswith("event: tick") and json.loads(first.split("data: ", 1)[1])["state"] == "running", "stream emits live ticks")
check(run.state == "done" and run.stop_reason == "disconnect", "stream disconnect stops the run")
fresh()
run = start_esim()


async def _finish():
    out = []
    async for ev in sim.stream_events(run.id, interval=0.0):
        out.append(ev)
        now[0] += 31
    return out


evs = asyncio.run(_finish())
check(evs[-1].startswith("event: done") and run.stop_reason == "timeout", "stream ends with a done event when the server stops the run")
fresh()
rr = client.get(f"{BASE}/esim-vent/stream?run=nope")
check(rr.status_code == 200 and "text/event-stream" in rr.headers["content-type"] and "event: done" in rr.text, "stream route serves SSE (unknown run -> done)")

# -- verdicts
for fault, word in ((None, "WORKED"), ("no_proof", "DIDN'T"), ("ambiguous_proof", "UNCLEAR")):
    fresh()
    if fault:
        sim.CAR.toggle(fault)
    run = start_esim()
    now[0] += 10
    sim.stop(run.id)
    check(run.result["word"] == word, f"proof {fault or 'present'} -> {word}")
    pg = text(client.get(f"{BASE}/esim-vent?run={run.id}").text)
    check(word in pg and "Before" in pg and "After" in pg and "Would be saved to" in pg, f"after view for {word}: word, table, evidence line")
fresh()
run = start_esim()
now[0] += 10
sim.stop(run.id)
pg = text(client.get(f"{BASE}/esim-vent?run={run.id}").text)
check("0.05 kPa" in pg and "-0.42 kPa" in pg and "evidence FOR" in pg, "WORKED shows 0.05 -> -0.42 kPa and evidence FOR")

# -- service reset
fresh()
sim.answer("oil")
run, why = sim.start("service-reset", sim.mint_token("service-reset"))
check(run is not None and run.state == "done" and run.result["word"] == "WORKED", "service reset completes and is WORKED")
b, a = dict(run.before), dict(run.after)
check(len(run.before) == 8 and len(run.after) == 8, "8 parameters")
check((b["Distance till next service"], a["Distance till next service"]) == ("10268.0 km", "16000.0 km"), "distance till next 10268 -> 16000 km")
check((b["Days till next service"], a["Days till next service"]) == ("324 days", "365 days"), "days till next 324 -> 365")
check((b["Distance after last service"], a["Distance after last service"]) == ("142475 km", "148207 km"), "distance after last service 142475 -> 148207")
check((b["Last service date"], a["Last service date"]) == ("09/12/2026", "10/26/2026"), "last service date -> today")
check(all(b[k] == a[k] for k in ("Odometer", "Number of services", "Service interval", "Service period")), "the other 4 values unchanged")
pg = text(client.get(f"{BASE}/service-reset?run={run.id}").text)
check("10268.0 km" in pg and "16000.0 km" in pg and "(changed)" in pg and "WORKED" in pg, "reset page shows before -> after table")
fresh()
sim.CAR.toggle("no_proof")
sim.answer("oil")
run, _ = sim.start("service-reset", sim.mint_token("service-reset"))
check(run.result["word"] == "DIDN'T", "reset with nothing changed on read-back -> DIDN'T")
fresh()
sim.CAR.toggle("ambiguous_proof")
sim.answer("oil")
run, _ = sim.start("service-reset", sim.mint_token("service-reset"))
check(run.result["word"] == "UNCLEAR", "reset with partial change -> UNCLEAR")
fresh()
sim.CAR.toggle("engine_stalls")           # reset does not need the engine running
sim.answer("oil")
check(bool(sim.mint_token("service-reset")), "service reset does not need the engine running")

# -- sim control route + prototype results file
fresh()
client.post(f"{BASE}/esim-vent/sim", data={"fault": "mes_holding"})
check("mes_holding" in sim.CAR.faults, "simulator page toggle works")
client.post(f"{BASE}/esim-vent/sim", data={"clear": "1"})
check(not sim.CAR.faults, "clear all faults")
lines = [json.loads(x) for x in (Path(_TMP) / "procedure_prototype.jsonl").read_text(encoding="utf-8").splitlines()]
check(len(lines) > 5 and all(x["prototype"] for x in lines), "results written to procedure_prototype.jsonl")
check(not (Path(_TMP) / "jobs").exists(), "nothing written to a job ledger")

# -- no contact with the car from the prototype modules
root = Path(__file__).resolve().parents[1]
FORBID = re.compile(r"cuore\.live|from\s+\.\.?live|import\s+live|\bobd2\b|serial|COM3|socket|send_raw|run_actuator|clear_dtcs|\.transport|\.ops\b", re.I)
for rel in ("services/procedure_sim.py", "web/procedure_proto_routes.py"):
    src = (root / rel).read_text(encoding="utf-8")
    imports = "\n".join(l for l in src.splitlines() if re.match(r"\s*(from|import)\s", l))
    check(not FORBID.search(imports), f"{rel}: no live/transport/ops import")
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    code = "\n".join(l for l in code.splitlines() if not l.strip().startswith("#"))
    check(not FORBID.search(code), f"{rel}: no call to a send function or adapter name")
loaded = [m for m in sys.modules if m.startswith("cuore.live") and m not in ("cuore.live",)]
import ast  # noqa: E402
mods = set()
for rel in ("services/procedure_sim.py", "web/procedure_proto_routes.py"):
    for n in ast.walk(ast.parse((root / rel).read_text(encoding="utf-8"))):
        if isinstance(n, ast.ImportFrom):
            mods.add(("." * n.level) + (n.module or ""))
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
check(not any("live" in m.split(".") for m in mods), f"AST: no import of a live module ({sorted(mods)})")

print(f"procedure_prototype checks: {passed} passed, {len(failures)} failed")
for f in failures:
    print("  FAIL:", f)
sys.exit(1 if failures else 0)
