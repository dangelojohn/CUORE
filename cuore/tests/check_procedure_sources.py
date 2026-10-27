"""Checks for cuore.live.procedure_sources (documented procedures; offline, fakes only).

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_procedure_sources.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-procsrc-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import procedure_capture as pc, procedure_dry_run as dr, procedure_sources as ps  # noqa: E402

failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def override(name, **kw):
    p = Path(_TMP, "procedures", f"{name}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(kw), encoding="utf-8")


# 1. both shipped definitions load + validate with empty steps
names = [d["name"] for d in ps.list()]
check("both listed", {"service_interval_reset", "engine_oil_reset"} <= set(names), str(names))
for n, mod in (("service_interval_reset", "IPC"), ("engine_oil_reset", "ECM")):
    d = ps.load(n)
    v = ps.validate(d)
    check(f"{n} module", d["module"] == mod)
    check(f"{n} valid", v["ok"], str(v["errors"]))
    check(f"{n} awaiting", d["status"] == "awaiting source" and v["status"] == "awaiting source")
    check(f"{n} not accepted", d["accepted_by_owner"] is False and d["source"]["kind"] == "documented")
    r = ps.ready(n)
    check(f"{n} not ready", not r["dry_run_ok"] and not r["accepted"] and not r["read_back_known"]
          and any("awaiting source" in b for b in r["blockers"]), str(r["blockers"]))
    try:
        ps.accept(n, "owner", "x")
        check(f"{n} accept refused when empty", False)
    except ValueError:
        check(f"{n} accept refused when empty", True)
check("oil precondition engine running", ps.load("engine_oil_reset")["preconditions"]["engine_state"] == "running")

# 2. filled synthetic override passes the gate; dry run WORKED (synthetic bytes, tmp dir only)
SYN = ["1003", "22F190", "3101AA55", "3102AA55", "1001"]
override("service_interval_reset", steps=SYN,
         source={"kind": "documented", "citation": "SYNTHETIC TEST ONLY", "confidence": "test"})
PRE = {"engine_state": "off", "voltage_v": 12.6}
POST = {"engine_state": "off", "voltage_v": 12.5}
d = ps.load("service_interval_reset")
check("status filled", d["status"] != "awaiting source" and d["accepted_by_owner"] is False)
v = ps.validate(d, pre=PRE, post=POST)
check("synthetic validates + gate passes", v["ok"] and v["gate"] and v["gate"]["passed"], str(v))
check("gate tagged documented", v["gate"]["source"] == "documented")
rep = pc.review(d)
check("review tagged documented", rep["source"] == "documented" and rep["modules"][0]["source"] == "documented")
dry = dr.dry_run(pc.documented_procedure(d), pre=PRE, post=POST)
check("dry run WORKED", dry["verdict"] == dr.WORKED, dry["verdict_line"])
r = ps.ready("service_interval_reset", pre=PRE, post=POST)
check("ready: dry ok, gate ok, blockers = acceptance + read-back",
      r["dry_run_ok"] and r["gate"]["passed"] and not r["accepted"]
      and len(r["blockers"]) == 2, str(r["blockers"]))

# 3. refused steps
for bad in (["1003", "2701"], ["1003", "2EF19000", "3101AA55", "3102AA55"], ["3401"], ["11 01"], ["8582"], ["2802"]):
    dd = ps.load("service_interval_reset")
    dd["steps"] = bad
    vv = ps.validate(dd, pre=PRE, post=POST)
    check(f"refused {bad}", not vv["ok"] and any("step" in e for e in vv["errors"]), str(vv))

# 4. accept -> is_accepted; changing the steps voids it
rec = ps.accept("service_interval_reset", "owner", "test")
check("record names procedure+source+hash", rec["procedure"] == "service_interval_reset"
      and rec["citation"] == "SYNTHETIC TEST ONLY" and len(rec["steps_sha256"]) == 64)
a = ps.is_accepted("service_interval_reset")
check("accepted", a["accepted"] and ps.load("service_interval_reset")["accepted_by_owner"])
r = ps.ready("service_interval_reset", pre=PRE, post=POST)
check("ready accepted, only read-back blocks", r["accepted"] and len(r["blockers"]) == 1, str(r["blockers"]))
override("service_interval_reset", steps=SYN[:-1] + ["22F191", "1001"],
         source={"kind": "documented", "citation": "SYNTHETIC TEST ONLY", "confidence": "test"})
a = ps.is_accepted("service_interval_reset")
check("steps changed voids acceptance", not a["accepted"] and "void" in a["reason"], str(a))
lines = Path(_TMP, "procedure_acceptances.jsonl").read_text().splitlines()
check("log append-only (1 record kept)", len(lines) == 1)
check("other procedure untouched", not ps.is_accepted("engine_oil_reset")["accepted"])

print(f"{checks} checks, {len(failures)} failure(s)")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
