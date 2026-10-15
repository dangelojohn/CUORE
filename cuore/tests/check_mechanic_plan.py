"""Checks for the mechanic-steps generator (cuore/services/mechanic_plan_bridge.py),
GET /api/jobs/{job}/hypotheses/{hyp}/plan, the job-page partial and the
"Save as next test" route.

Fake catalogue + fake DTC history are swapped in for ``tsb_xref_bridge``'s
loaders; ``CUORE_STATE_DIR`` points at a throwaway directory BEFORE cuore is
imported, so the job/hypothesis/actions below live in a temp job store.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_mechanic_plan.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-mplan-")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.data import load_tsb_catalogue  # noqa: E402
from cuore.services import jobs_bridge, mechanic_plan_bridge as M, tsb_xref_bridge as X  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

CAT = {"vehicle": {"make": "Alfa Romeo", "model": "Stelvio", "year": 2018, "vin": VIN},
       "updated": "2026-10-15", "items": [
    {"id": "tsb-flash", "number": "77-100-26", "kind": "tsb", "title": "Flash: ECM update",
     "systems": ["ECM", "EVAP"], "dtcs": ["P0440"], "applies": "yes",
     "remedy": "Reprogram the ECM.", "repair_implied": "flash", "components": ["ECM"]},
    {"id": "tsb-ruled", "number": "77-200-26", "kind": "tsb", "title": "Canister flooded",
     "systems": ["EVAP"], "applies": "yes", "remedy": "Replace the vapor canister.",
     "repair_implied": "replace:vapor canister"},
    {"id": "tsb-hoses", "number": "77-300-26", "kind": "tsb", "title": "Purge hoses",
     "systems": ["EVAP"], "applies": "yes", "remedy": "Inspect purge hoses for kinks.",
     "repair_implied": "inspect", "components": ["purge hoses"]},
    {"id": "tsb-slvt", "number": "77-400-26", "kind": "tsb", "title": "SLVT",
     "systems": ["EVAP"], "dtcs": ["P0456"], "applies": "yes",
     "remedy": "Run the wiTECH SLVT after the repair.", "repair_implied": "procedure:wiTECH SLVT"},
]}
HIST = [{"dtc": "P0440-00", "first_seen": "2026-08-01 10:00:00", "last_seen": "2026-10-10 09:00:00",
         "sessions": 5, "modules": ["Engine / ECM"],
         "occurrences": [{"timestamp": "2026-10-10 09:00:00", "status": "stored"}]}]

X._load_catalogue = lambda: load_tsb_catalogue(json.dumps(CAT))  # type: ignore[assignment]
X._load_dtc_history = lambda vin: [dict(r) for r in HIST]  # type: ignore[assignment]
X._load_live_active = lambda vin: {"P0440"}  # type: ignore[assignment]
X._load_identity = lambda vin: {}  # type: ignore[assignment]

HYP_TEXT = ("CLAIM: P0440 comes from the ECM calibration (77-100-26), not a leak. "
            "CONFIRM: drive until the EVAP monitor reports complete without clearing, then read "
            "ECM P0440 status bytes and Mode 06 EVAP test IDs via CUORE. If P0440 sets while Mode 06 "
            "passes, the hypothesis is confirmed. REFUTE: if Mode 06 shows a real leak-test failure, "
            "the hypothesis is refuted. Do not clear codes before then.")

job = jobs_bridge.open_job(VIN, complaint="EVAP codes")
hyp = jobs_bridge.add_hypothesis(job["id"], HYP_TEXT, system="evap")
jobs_bridge.add_action(job["id"], "inspection",
                       "2026-09-26: TSB 77-200-26 checked: no fuel in the canister, ruled out.")
jobs_bridge.add_action(job["id"], "inspection",
                       "2026-10-01: purge hoses inspected per TSB 77-300-26, found seated and unkinked.")
JOB, HYP = job["id"], hyp["id"]

failures: list[str] = []
checks = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" -- {detail}"))
    if not ok:
        failures.append(name)


p = M.plan(VIN, JOB, HYP)
steps = p["steps"]
by_title = {s["title"]: s for s in steps}

# 1. never-clear is step 0
check("never-clear is step 0", steps[0]["n"] == 0 and "clear" in steps[0]["title"].lower()
      and steps[0]["kind"] == "precondition", json.dumps(steps[0])[:200])

# 2. candidate flash bulletin -> VIN check + flash step
vin_steps = [s for s in steps if s["kind"] == "vin_check" and "77-100-26" in s["bulletins"]]
flash_steps = [s for s in steps if s["kind"] == "flash" and "77-100-26" in s["bulletins"]]
check("candidate flash -> VIN check + flash step", bool(vin_steps) and bool(flash_steps)
      and "77-100-26" in flash_steps[0]["source"], json.dumps([s["title"] for s in steps]))

# 3. ruled-out bulletin -> no step, listed in rationale
check("ruled_out bulletin: no step, in rationale",
      not any("77-200-26" in s["bulletins"] for s in steps)
      and "77-200-26" in p["rationale"] and "ruled out" in p["rationale"], p["rationale"][:300])

# 4. CONFIRM/REFUTE -> read + decide, drive cycle before the monitor-dependent read
kinds = [s["kind"] for s in steps if not s["done"]]
idx = {k: kinds.index(k) for k in ("drive_cycle", "read", "decide") if k in kinds}
reads = [s for s in steps if s["kind"] == "read" and "status bytes" in s["detail"]]
decide = [s for s in steps if s["kind"] == "decide"]
check("CONFIRM/REFUTE -> drive cycle, read, decide in order",
      len(idx) == 3 and bool(reads) and bool(decide)
      and kinds.index("drive_cycle") < [i for i, s in enumerate([x for x in steps if not x["done"]])
                                        if "status bytes" in s["detail"]][0] < kinds.index("decide")
      and "confirmed" in decide[0]["detail"] and "refuted" in decide[0]["detail"]
      and "CONFIRM" in reads[0]["source"], json.dumps(kinds))

# 5. done inspection action marks its step done with done_ref, after the record step
hose = [s for s in steps if "77-300-26" in s["bulletins"]]
rec_n = next(s["n"] for s in steps if s["kind"] == "record")
check("done inspection -> done=True with done_ref, moved under already done",
      bool(hose) and hose[0]["done"] and "inspection" in hose[0]["done_ref"]
      and hose[0]["n"] > rec_n, json.dumps(hose)[:300])

# 6. deterministic ordering + every step cites a source
p2 = M.plan(VIN, JOB, HYP)
order = {"precondition": 0, "vin_check": 1, "flash": 3, "test": 4, "drive_cycle": 5,
         "decide": 7, "inspect": 8, "record": 9}
open_kinds = [order.get(s["kind"]) for s in steps if not s["done"] and s["kind"] != "read"]
check("ordering is deterministic and staged",
      [s["title"] for s in p2["steps"]] == [s["title"] for s in steps]
      and open_kinds == sorted(open_kinds) and all(s["source"] for s in steps)
      and steps[[s["kind"] for s in steps].index("record")]["n"] == max(s["n"] for s in steps if not s["done"]),
      json.dumps([(s["n"], s["kind"]) for s in steps]))

# 7. API 200 + page renders the partial + Save as next test writes next_test
client = TestClient(create_app())
r = client.get(f"/api/jobs/{JOB}/hypotheses/{HYP}/plan", params={"vin": VIN})
r404 = client.get(f"/api/jobs/{JOB}/hypotheses/nope/plan", params={"vin": VIN})
check("API returns 200 with steps (404 for unknown hypothesis)",
      r.status_code == 200 and r.json()["steps"][0]["n"] == 0 and r404.status_code == 404,
      f"{r.status_code} {r.text[:200]} / {r404.status_code}")

page = client.get(f"/v/{VIN}/job/{JOB}?step=7")
saved = client.post(f"/v/{VIN}/job/{JOB}/hypotheses/{HYP}/plan/save", data={"step": "7"},
                    follow_redirects=False)
nt = next(h for h in jobs_bridge.get_job(JOB)["hypotheses"] if h["id"] == HYP).get("next_test") or ""
check("job page shows Mechanic steps; Save writes next_test",
      page.status_code == 200 and "Mechanic steps" in page.text and f"plan-{HYP}" in page.text
      and saved.status_code == 303 and nt.startswith("0. Never clear codes") and "77-100-26" in nt,
      f"page {page.status_code} saved {saved.status_code} nt {nt[:120]!r}")

# 8-10. refinements: dependency steps need a code, proof-of-fix step, bulletin inspect needs code overlap
import copy  # noqa: E402

_cat0 = copy.deepcopy(CAT)
CAT["items"] += [
    {"id": "tsb-far", "number": "77-500-26", "kind": "tsb", "title": "Far purge note",
     "systems": ["EVAP"], "dtcs": ["P1CEA"], "applies": "yes", "remedy": "Check hoses.",
     "repair_implied": "inspect"},
    {"id": "tsb-fuelbare", "number": "77-600-26", "kind": "tsb", "title": "Fuel pump note",
     "systems": ["EVAP", "Fuel"], "applies": "yes", "remedy": "Check pump.", "repair_implied": "inspect"},
    {"id": "tsb-dup", "number": "77-410-26", "kind": "tsb", "title": "SLVT sibling",
     "systems": ["EVAP"], "dtcs": ["P0456"], "applies": "yes", "cuore_relevance": "SLVT pass is the proof of fix.",
     "remedy": "Run the SLVT.", "repair_implied": "procedure:wiTECH SLVT"},
]
p3 = M.plan(VIN, JOB, HYP)
s3 = p3["steps"]
proof = [s for s in s3 if s["title"].startswith("Proof of fix:")]
fl = [s for s in s3 if s["kind"] == "flash"]
check("verification procedure -> one 'Proof of fix' test step after the flash, siblings listed",
      len(proof) == 1 and proof[0]["kind"] == "test" and "per 77-" in proof[0]["title"]
      and {"77-400-26", "77-410-26"} <= set(proof[0]["bulletins"])
      and proof[0]["detail"].endswith("If it passes and the codes stay away, stop here; record the result.")
      and (not fl or proof[0]["n"] == fl[-1]["n"] + 1), json.dumps([(s["n"], s["title"]) for s in s3]))
check("bulletin with no code overlap -> no Inspect step, rationale says 'no code overlap'",
      not any("77-500-26" in s["bulletins"] for s in s3)
      and "77-500-26: no code overlap" in p3["rationale"], p3["rationale"][-300:])
dep = [s for s in s3 if s["title"].startswith("Inspect ") and s["title"].endswith(" also")]
check("no Inspect-<system>-also from a bare system tag (77-600-26); reason names the code when present",
      not any(s["title"] == "Inspect Fuel also" for s in s3) and all(any(x in s["source"] for x in ("P0", "P1", "U0", "C1", "B1", "active")) for s in dep), json.dumps(dep)[:300])
CAT.update(_cat0)

print(f"\n{checks - len(failures)}/{checks} checks passed")
sys.exit(1 if failures else 0)
