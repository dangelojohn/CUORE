"""Minimal check for fault_similarity (synthetic state in a temp CUORE_STATE_DIR).

  1. shared_cause found from the dependency chains, with the shared element named
  2. co_occurrence counted from reads ("3 of 4 times either appeared")
  3. ordering: most link kinds first, then most recent
  4. groups(): components over strong links; a lone fault is not a group
  5. unknown key / empty VIN: [] and no exception

Run:  .venv/Scripts/python.exe cuore/tests/check_fault_similarity.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-faultsim-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore import bootstrap  # noqa: E402,F401
from cuore.services import cache, common_cause, fault_similarity as fsim, tsb_xref_bridge  # noqa: E402

VIN = "TESTVIN0000000002"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


FLAGS = {"testFailed": False, "pendingDTC": False, "confirmedDTC": True, "testFailedSinceLastClear": False,
         "warningIndicatorRequested": False}


def read(ecu, at, codes):
    with open(Path(STATE) / "observations.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": at, "kind": "module_dtcs", "vin": VIN, "stream": "serial COM3@115200",
                            "data": {"ecu": ecu, "error": None, "nrc": None,
                                     "dtcs": [{"code": c + "-00", "flags": FLAGS} for c in codes]}}) + "\n")
    cache.clear()


read("ECM", "2026-10-01T10:00:00", ["P0171", "P0172"])
read("ECM", "2026-10-02T10:00:00", ["P0171", "P0172"])
read("ECM", "2026-10-03T10:00:00", ["P0171", "P0172"])
read("ECM", "2026-10-04T10:00:00", ["P0171"])
read("ECM", "2026-10-05T10:00:00", ["P0300"])
read("ECM", "2026-10-06T10:00:00", ["P0174"])
read("BCM", "2026-10-03T11:00:00", ["U0100"])
read("BCM", "2026-10-04T11:00:00", ["B1040"])
read("BCM", "2026-10-07T11:00:00", ["U0100", "B1040"])
read("BCM", "2026-10-08T11:00:00", ["B1176", "B101D"])


KIND = {"bcm": "module", "F82": "fuse", "G003A": "ground"}


def chain(*ids):
    return [{"id": i, "label": i, "kind": KIND.get(i, "connector"), "role": ""} for i in ids]


def fake_faults(vin, view=None, now=None):
    mk = lambda code, ids: {"id": f"code:{code}", "kind": "code", "label": code, "chain": chain(*ids), "sys_chain": []}
    return [mk("P0171", ["maf"]), mk("P0172", ["maf"]), mk("P0300", ["plug"]), mk("P0174", ["pcv"]),
            mk("U0100", ["bcm", "G003A", "F82"]), mk("B1040", ["bcm", "G003A", "F82", "xy201"]),
            mk("B1176", ["bcm"]), mk("B101D", ["bcm"])]


common_cause.gather_faults = fake_faults
tsb_xref_bridge.xref = lambda vin, *a, **k: {"by_code": {}}
cache.clear()

K = lambda m, c: f"code:{m}:{c}"
# 1-2. links on P0171
res = fsim.similar(VIN, K("ECM", "P0171"))
by = {r["fault_key"]: r for r in res}
p172 = by.get(K("ECM", "P0172"), {"links": [], "n_kinds": 0})
kinds = {l["kind"]: l for l in p172["links"]}
check("shared_cause" in kinds and kinds["shared_cause"]["evidence"]["elements"][0]["id"] == "maf",
      f"shared_cause on maf: {p172['links']}")
co = kinds.get("co_occurrence", {}).get("evidence", {})
check(co.get("together") == 3 and co.get("either") == 4, f"co_occurrence 3 of 4: {co}")
check("3 of 4" in kinds.get("co_occurrence", {}).get("label", ""), "co_occurrence label carries the counts")
check(p172["n_kinds"] == 3 and {"same_module"} <= set(kinds), f"kinds {sorted(kinds)}")
# 3. ordering: 3 kinds first, then 1-kind faults newest first (P0174 read after P0300)
order = [r["fault_key"] for r in res]
check(order[:3] == [K("ECM", "P0172"), K("ECM", "P0174"), K("ECM", "P0300")], f"order {order}")
check(K("BCM", "U0100") not in order, "unrelated fault not listed")
check(fsim.similar(VIN, K("ECM", "P0171"), limit=1)[0]["fault_key"] == K("ECM", "P0172"), "limit honoured")
# 4. groups
g = fsim.groups(VIN)
sets = [set(x["members"]) for x in g]
check({K("ECM", "P0171"), K("ECM", "P0172")} in sets, f"P0171+P0172 grouped: {sets}")
check({K("BCM", "U0100"), K("BCM", "B1040")} in sets, "U0100+B1040 grouped")
check(len(g) == 3, f"three groups (BCM split in two, lone faults excluded), got {[x['label'] for x in g]}")
ug = next(x for x in g if K("BCM", "U0100") in x["members"])
check(set(ug["members"]) == {K("BCM", "U0100"), K("BCM", "B1040")}, f"split: fuse/ground subset {ug['members']}")
check(ug["label"] == "F82 / G003A", f"split label names the fuse then the ground: {ug['label']}")
check({e["id"] for e in ug["why_elements"]} >= {"F82", "G003A"} and "[F82]" in ug["why"] and "(2)" in ug["why"],
      f"why carries element ids and counts: {ug['why']}")
rg = next(x for x in g if K("BCM", "B1176") in x["members"])
check(set(rg["members"]) == {K("BCM", "B1176"), K("BCM", "B101D")} and rg["label"] == "behind the bcm",
      f"remainder keeps the broader label: {rg['label']} {rg['members']}")
check(ug["newest"] >= "2026-10-07", f"newest {ug['newest']}")
# 4b. stale-while-revalidate: changed inputs -> previous result at once (marked), one background rebuild, then fresh
import time  # noqa: E402
read("BCM", "2026-10-09T11:00:00", ["U0100"])
st = fsim.groups(VIN)
check(st and all(x.get("stale") and x.get("updating") for x in st), "changed inputs: stale result returned and marked")
for _ in range(100):
    if not fsim.is_updating(VIN):
        break
    time.sleep(0.1)
fresh = fsim.groups(VIN)
check(fresh and not any(x.get("stale") for x in fresh), "next call is fresh and unmarked")
# 5. robustness
check(fsim.similar(VIN, "code:XXX:P9999") == [], "unknown key -> []")
check(fsim.similar("", "x") == [] and fsim.groups("") == [] and fsim.error_note(), "empty VIN -> [] with a note")
check(fsim.groups("NOSUCHVIN00000001") == [], "unknown VIN -> []")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
