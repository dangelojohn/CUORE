"""Checks for the SLVT replica: cuore/services/slvt_bridge.py and
GET /slvt, POST /slvt/run (cuore/web/slvt_routes.py).

``CUORE_STATE_DIR`` points at a throwaway directory BEFORE cuore is imported.
The ECM reads are fakes: ``slvt_bridge.live_ops`` is swapped for an object with
exactly the three read-only operations the replica may call, so a call to
anything else (a clear, a routine) would raise.

Five checks: pass, fail, inconclusive, page renders, observation recorded.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_slvt.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-slvt-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import store as live_store  # noqa: E402
from cuore.services import jobs_bridge, slvt_bridge  # noqa: E402
from cuore.web import slvt_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- fake reads in the exact shapes ops returns -----------------------------------

def readiness(evap_complete: bool | None = True) -> dict:
    mons = [] if evap_complete is None else [{"monitor": "Evaporative system",
                                              "supported": True, "complete": evap_complete}]
    return {"since_clear": {"monitors": mons},
            "this_drive_cycle": {"monitors": mons, "ecu": "7E8"}}


def mode06(value: int = 12, lo: int = 0, hi: int = 40) -> dict:
    rec = {"mid": "3C", "mid_name": 'EVAP monitor 0.020" leak', "tid": "81", "uasid": "01",
           "unit": "raw", "value": value, "min": lo, "max": hi, "passed": lo <= value <= hi}
    return {"results": {"3C": {"by_ecu": {"7E8": [rec]}}, "3B": {"warning": "NO DATA"}}}


def dtcs(p0456: int = 0x00, p0455: int = 0x00, p0440: int = 0x00) -> dict:
    return {"ecu": "ECM", "dtcs": [{"code": "P0456", "status": p0456},
                                   {"code": "P0455", "status": p0455},
                                   {"code": "P0440", "status": p0440},
                                   {"code": "P0300", "status": 0x08}]}


class FakeOps:
    """Only the three reads the replica is allowed; anything else AttributeErrors."""

    def __init__(self, **reads):
        self.reads, self.calls = reads, []

    def obd_readiness(self, **kw):
        self.calls.append("obd_readiness")
        return self.reads["readiness"]

    def obd_mode06(self, mids=None, **kw):
        self.calls.append(("obd_mode06", tuple(mids or ())))
        return self.reads["mode06"]

    def module_dtcs(self, code, vin="", **kw):
        self.calls.append(("module_dtcs", code))
        return self.reads["dtcs"]


# 1. pass: monitor complete, small-leak MID within limits, all three codes clear
ok = slvt_bridge.evaluate(VIN, {"readiness": readiness(True), "mode06": mode06(12, 0, 40),
                                "dtcs": dtcs()})
row = next((r for r in ok["mode06"]["rows"] if r["graded"]), {})
check("pass: monitor + Mode 06 + status bits", ok["verdict"] == "pass"
      and ok["monitor"]["state"] == "complete" and ok["mode06"]["small_leak"] == "within"
      and (row.get("value"), row.get("min"), row.get("max")) == (12, 0, 40)
      and [d["code"] for d in ok["dtcs"]] == ["P0456", "P0455", "P0440"]
      and all(d["state"] == "clear" for d in ok["dtcs"]), str(ok["verdict"]))

# 2. fail: P0456 failed this cycle; and, separately, Mode 06 value out of limits
bad_dtc = slvt_bridge.evaluate(VIN, {"readiness": readiness(True), "mode06": mode06(),
                                     "dtcs": dtcs(p0456=0x0B)})
bad_m06 = slvt_bridge.evaluate(VIN, {"readiness": readiness(True), "mode06": mode06(55, 0, 40),
                                     "dtcs": dtcs()})
check("fail: any failed", bad_dtc["verdict"] == "fail" and "P0456" in bad_dtc["summary"]
      and bad_m06["verdict"] == "fail" and bad_m06["mode06"]["small_leak"] == "outside"
      and "55" in bad_m06["summary"], f"{bad_dtc['verdict']} / {bad_m06['verdict']}")

# 3. inconclusive: monitor not run (even though nothing failed), or no small-leak result
not_run = slvt_bridge.evaluate(VIN, {"readiness": readiness(False), "mode06": mode06(),
                                     "dtcs": dtcs(p0456=0x40)})
no_m06 = slvt_bridge.evaluate(VIN, {"readiness": readiness(True),
                                    "mode06": {"results": {"3C": {"warning": "NO DATA"}}},
                                    "dtcs": dtcs()})
nothing = slvt_bridge.evaluate(VIN, {})
check("inconclusive: monitor not run", not_run["verdict"] == "inconclusive"
      and not_run["monitor"]["state"] == "not_complete" and no_m06["verdict"] == "inconclusive"
      and nothing["verdict"] == "inconclusive",
      f"{not_run['verdict']} / {no_m06['verdict']} / {nothing['verdict']}")

# 4. the page renders: header sentence, checkboxes, Run button, bulletin + /tsb links
slvt_routes._safe_bar = lambda vin: None  # type: ignore[assignment]  # no corpus workup needed
slvt_bridge.link_available = lambda: True  # type: ignore[assignment]
client = TestClient(create_app())
resp = client.get(f"/slvt?vin={VIN}")
html = resp.text
n_pre = len(slvt_bridge.preconditions())
n_boxes = html.count('type="checkbox" name="pre"')
check("GET /slvt renders", resp.status_code == 200 and "unpublished RoutineControl" in html
      and n_boxes == n_pre and 'id="slvt-run"' in html
      and "18-048-23" in html and "MC-10236933-9999.pdf" in html
      and f"/tsb?vin={VIN}#tsb-row-tsb-18-048-23" in html and 'href="/slvt"' in html
      and "Not ticked" not in html, f"status {resp.status_code}, {n_boxes} boxes")

# 5. a run records one slvt_replica observation and one 'test' action on the open job,
#    and only the three read-only operations were called
job = jobs_bridge.open_job(VIN, technician="check", complaint="P0456")
fake = FakeOps(readiness=readiness(True), mode06=mode06(12, 0, 40), dtcs=dtcs())
slvt_bridge.live_ops = fake  # type: ignore[assignment]
post = client.post("/slvt/run", data={"vin": VIN, "pre": ["sequence", "no_clear"]},
                   follow_redirects=False)
obs = live_store.recent_observations(10, vin=VIN, kind="slvt_replica")
actions = jobs_bridge.get_job(job["id"])["actions"]
tests = [a for a in actions if a["kind"] == "test"]
page = client.get(f"/slvt?vin={VIN}&ran=1").text
check("run records observation + job test action", post.status_code == 303 and len(obs) == 1
      and obs[0]["data"]["verdict"] == "pass" and obs[0]["data"]["preconditions"]["confirmed"]
      == ["sequence", "no_clear"] and len(tests) == 1 and "SLVT replica" in tests[0]["text"]
      and [c if isinstance(c, str) else c[0] for c in fake.calls]
      == ["obd_readiness", "obd_mode06", "module_dtcs"]
      and 'data-verdict="pass"' in page and "Not ticked:" in page and "0..40" not in page
      and ">12<" in page and ">40<" in page,
      f"{post.status_code} obs={len(obs)} tests={len(tests)} calls={fake.calls}")

if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"OK: {checks} checks")
