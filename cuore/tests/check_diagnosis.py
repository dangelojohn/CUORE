"""Checks for the diagnosis layer: cuore/services/common_cause.py,
cuore/services/suspect_ranking.py and cuore/web/diagnosis_routes.py.

Synthetic fixtures only (temp CUORE_STATE_DIR); the page check renders against
the MES corpus with an empty state dir.

Run: .venv/Scripts/python.exe cuore/tests/check_diagnosis.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-diagnosis-")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import common_cause as cc  # noqa: E402
from cuore.services import suspect_ranking as sr  # noqa: E402
from cuore.web import diagnosis_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label} {detail}")
        print("FAIL", label, detail)


def hop(i: str, role: str = "connector", kind: str = "connector") -> dict:
    return {"id": i, "label": i.upper(), "kind": kind, "role": role}


def fault(i: str, *hops: dict) -> dict:
    return {"id": i, "kind": "code", "label": i, "chain": list(hops), "sys_chain": []}


# 1. shared dependency ranks first; uncovered fault listed, never dropped ---------
faults = [
    fault("A", hop("g1", "ground", "ground"), hop("x")),
    fault("B", hop("g1", "ground", "ground"), hop("y")),
    fault("C", hop("g1", "ground", "ground"), hop("z")),
    fault("D"),                                  # no dependency data
]
r = cc.solve(faults)
check("single shared cause is the first set", r["sets"] and r["sets"][0]["size"] == 1
      and r["sets"][0]["members"][0]["ids"] == ["g1"], str(r["sets"][:1]))
check("it explains all covered faults", r["sets"][0]["explains_n"] == 3 and r["sets"][0]["of_n"] == 3)
check("uncovered fault is listed, not dropped", [f["id"] for f in r["uncovered"]] == ["D"], str(r["uncovered"]))
check("uncovered fault is not counted as explained",
      all("D" not in [f["id"] for f in s["explains"]] for s in r["sets"]))
check("every set carries a dependency path with the candidate marked",
      any(h["hit"] for g in r["sets"][0]["paths"][0]["groups"] for h in g["chain"]))

faults2 = faults + [fault("E", hop("e1"))]
r2 = cc.solve(faults2)
check("no single cause covers all four: first partial is g1 with 3 of 4",
      not [s for s in r2["sets"] if s["size"] == 1] and r2["partial"][0]["explains_n"] == 3
      and r2["partial"][0]["of_n"] == 4, str(r2["partial"][:1]))
check("it names the fault it does not explain",
      [f["id"] for f in r2["partial"][0]["does_not_explain"]] == ["E"])
check("a two-cause set covers everything", r2["sets"] and r2["sets"][0]["size"] == 2)


# 2. next test splits the suspects; effort is weighed -----------------------------------------------
def hyp(i: str, status: str, ev_for: list, system: str, code: str) -> dict:
    return {"id": i, "text": f"{i} unique zebra{i}", "_title": f"Hypothesis {i}", "status": status,
            "evidence_for": ev_for, "evidence_against": [], "system": system, "codes": [code],
            "next_test": ""}


def test_row(i: str, systems: list, rel: list, minutes) -> dict:
    return {"id": i, "name": f"Test {i}", "systems": systems, "related_codes": rel,
            "supports_hypotheses": [], "refutes_hypotheses": [], "duration_min": minutes,
            "tools": [], "car_state": "KOEO"}


def inp(tests: list) -> dict:
    ev = [{"kind": "measurement", "id": "m1", "label": "m1"}, {"kind": "measurement", "id": "m2", "label": "m2"}]
    return {"vin": VIN, "cc": {"sets": [], "partial": [], "n_covered": 0}, "xref": {}, "cases": [],
            "hypotheses": [hyp("s1", "confirmed", ev, "sa", "P0001"),
                           hyp("s2", "supported", [{"kind": "test", "id": "t", "label": "t"}], "sb", "P0002"),
                           hyp("s3", "open", [], "sc", "P0003")],
            "tests": tests, "test_results": {}, "tree_hyps": [], "actions": []}


t_all = test_row("all", ["sa", "sb", "sc"], ["P000"], 5)
t_s1 = test_row("only_s1", ["sa"], ["P0001"], 30)
t_s23 = test_row("s2_s3", ["sb", "sc"], ["P000"], 5)
res = sr.build(inp([t_all, t_s1, t_s23]))
bands = {s["ref_id"]: s["band"] for s in res["suspects"]}
check("bands derive from the table", bands == {"s1": "High", "s2": "Medium", "s3": "Low"}, str(bands))
check("every suspect score carries reasons with source ids",
      all(r_["source_id"] for s in res["suspects"] for r_ in s["reasons"]) and res["suspects"][0]["reasons"])
nt = res["next_test"]
check("next test is one that splits the suspects, not the all-touching test",
      nt and nt["id"] in ("s2_s3", "only_s1") and nt["splits"], str(nt and nt["id"]))
check("per unit of effort: the 5-minute split beats the 30-minute split", nt and nt["id"] == "s2_s3",
      str(nt and nt["id"]))
check("the one-line why says what a pass and a fail do, with the effort",
      nt and "a pass clears" in nt["why"] and "a fail points" in nt["why"] and "5 min" in nt["why"],
      str(nt and nt["why"]))
res2 = sr.build(inp([t_all, t_s1, test_row("s2_s3", ["sb", "sc"], ["P000"], 240)]))
check("a very long split loses to a short one", res2["next_test"]["id"] == "only_s1", res2["next_test"]["id"])
res3 = sr.build(inp([t_all, test_row("unk", ["sa"], ["P0001"], None)]))
check("unknown effort is labelled, not invented", res3["next_test"]["id"] == "unk"
      and res3["next_test"]["effort"] == "effort unknown" and not res3["next_test"]["effort_known"])

# 3. no percentages anywhere in what we produce ---------------------------------------------------
blob = json.dumps(res, default=str)
check("no percent sign in synthetic result", "%" not in blob, re.findall(r".{20}%.{5}", blob)[:2].__str__())

# 4. the page and the JSON render ------------------------------------------------------------------
app = create_app()
app.include_router(diagnosis_routes.router)
client = TestClient(app)
page = client.get(f"/v/{VIN}/diagnosis")
check("page renders 200", page.status_code == 200, f"{page.status_code} {page.text[:200]}")
html = page.text
sec = html[html.find('<section class="dx"'):html.find("</section>", html.find('<section class="dx"')) + 10]
check("page carries the panel and the call", 'id="dx-call-h"' in sec and 'class="dx-call"' in sec)
check("page shows no percentages", not re.search(r"\d\s*%", re.sub(r"(?s)<style.*?</style>", "", sec)),
      str(re.findall(r".{30}\d\s*%.{10}", sec)[:2]))
api = client.get(f"/api/vehicles/{VIN}/diagnosis")
check("JSON endpoint 200 with the three parts", api.status_code == 200 and
      {"suspects", "common_cause", "next_test", "call"} <= set(api.json()), str(api.status_code))

print(f"{checks - len(failures)}/{checks} checks passed")
sys.exit(1 if failures else 0)
