"""Checks for the bulletin cross-reference engine
(cuore/services/tsb_xref_bridge.py), GET /api/tsb/xref and the page surfaces.

Fake catalogue + fake DTC history + fake job are swapped in for the
bridge's ``_load_*`` loaders; ``CUORE_STATE_DIR`` points at a throwaway
directory BEFORE cuore is imported. No serial, no real job store touched.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_tsb_xref.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-tsbxref-")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.data import load_tsb_catalogue  # noqa: E402
from cuore.services import systems_bridge, tsb_bridge, tsb_xref_bridge as X  # noqa: E402
from cuore.web import tsb_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

CAT = {"vehicle": {"make": "Alfa Romeo", "model": "Stelvio", "year": 2018, "vin": VIN},
       "updated": "2026-10-15", "items": [
    {"id": "tsb-a", "number": "77-001-26", "title": "Purge valve", "systems": ["EVAP"],
     "dtcs": ["P0440"], "applies": "yes", "remedy": "Replace the purge valve.",
     "components": ["purge valve"]},
    {"id": "tsb-b", "number": "77-002-26", "title": "Fuel pump", "systems": ["Fuel"],
     "applies": "vin_check", "remedy": "Replace fuel delivery module."},
    {"id": "tsb-c", "number": "77-003-26", "title": "ESIM", "systems": ["EVAP"],
     "dtcs": ["P0456"], "applies": "yes", "repair_implied": "replace:ESIM",
     "components": ["ESIM"]},
    {"id": "tsb-d", "number": "18-030-17 REV. B", "title": "Flash (Giulia-only)",
     "systems": ["ECM"], "applies": "vin_check", "summary": "Covers the Giulia only.",
     "remedy": "Reprogram ECM."},
    {"id": "tsb-e", "number": "99-001-01", "title": "Other car flash", "systems": ["ECM"],
     "applies": "no", "remedy": "Reprogram ECM."},
    {"id": "tsb-f", "number": "9100471", "title": "Canister flooded", "systems": ["EVAP"],
     "applies": "yes", "remedy": "Check hoses; replace canister and ESIM."},
    {"id": "rc-g", "kind": "recall", "number": "18V147", "title": "Wiper motor",
     "applies": "vin_check", "remedy": "Replace wiper motor."},
]}

HIST = [
    {"dtc": "P0440-00", "first_seen": "2026-08-01 10:00:00", "last_seen": "2026-10-10 09:00:00",
     "sessions": 5, "modules": ["Engine / ECM"],
     "occurrences": [{"timestamp": "2026-10-10 09:00:00", "status": "stored"}]},
    {"dtc": "P0456-00", "first_seen": "2026-07-01 10:00:00", "last_seen": "2026-10-01 09:00:00",
     "sessions": 3, "modules": ["Engine / ECM"],
     "occurrences": [{"timestamp": "2026-10-01 09:00:00", "status": "cleared"}]},
]

JOB = {"id": "job1", "vin": VIN, "status": "open", "hypotheses": [
    {"id": "h1", "system": "evap", "deleted": False,
     "text": "ESIM signal / ECM calibration per TSB 18-030-17 and 99-001-01.",
     "evidence_for": [], "evidence_against": []}],
    "actions": [
        {"at": "2026-09-01T10:00:00", "kind": "part", "text": "Replaced ESIM (Mopar)."},
        {"at": "2026-09-26T11:00:00", "kind": "inspection",
         "text": "TSB 9100471 checked: no fuel in canister or vapour hose, ruled out."},
    ]}

X._load_catalogue = lambda: load_tsb_catalogue(json.dumps(CAT))  # type: ignore[assignment]
X._load_dtc_history = lambda vin: [dict(r) for r in HIST]  # type: ignore[assignment]
X._load_live_active = lambda vin: {"P0440"}  # type: ignore[assignment]
X._load_jobs = lambda vin: [json.loads(json.dumps(JOB))]  # type: ignore[assignment]
X._load_identity = lambda vin: {}  # type: ignore[assignment]

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def rels(view: dict, bid: str) -> list[dict]:
    return next(b for b in view["bulletins"] if b["id"] == bid)["relations"]


def has(view: dict, bid: str, relation: str) -> dict | None:
    return next((r for r in rels(view, bid) if r.get("relation") == relation), None)


v = X.xref(VIN)

# (a) code match explains an active code
r = has(v, "tsb-a", "explains")
check("a: explains active P0440", bool(r) and r["code"] == "P0440" and "live link" in r["reason"]
      and any(e["relation"] == "explains" for e in v["by_code"].get("P0440", [])), str(r))
check("a2: P0456 historical, not explains", bool(has(v, "tsb-c", "historical"))
      and not has(v, "tsb-c", "explains"))

# (b) dependent_system via related_systems (fuel is upstream of evap)
rs = {x["system"]: x for x in systems_bridge.related_systems("evap", 1)}
r = has(v, "tsb-b", "dependent_system")
check("b: dependent_system via related_systems", "fuel" in rs and rs["fuel"]["direction"] == "upstream"
      and bool(r) and r["path"] == ["evap", "fuel"] and "EVAP" in r["reason"], str(r))

# (c) already_applied + did_not_resolve
a, d = has(v, "tsb-c", "already_applied"), has(v, "tsb-c", "did_not_resolve")
check("c: already_applied + did_not_resolve", bool(a) and bool(d) and "2026-09-01" in a["reason"]
      and "2026-10-01" in d["reason"] and "not_the_fix" in
      next(b for b in v["bulletins"] if b["id"] == "tsb-c")["score_parts"], f"{a} / {d}")

# (d) weakens when a hypothesis cites a bulletin whose applies is "no" (and other-model text)
we = has(v, "tsb-e", "weakens")
wd = has(v, "tsb-d", "weakens")
check("d: weakens (applies no / Giulia-only)", bool(we) and "not applicable" in we["reason"]
      and bool(wd) and "Giulia" in wd["reason"] and we["suggestion"]["side"] == "against"
      and we["suggestion"]["action"] == f"/v/{VIN}/job/job1/hypotheses/h1/evidence", f"{we} / {wd}")

# (e) ruled_out_by_inspection from an inspection action
ro = has(v, "tsb-f", "ruled_out_by_inspection")
check("e: ruled_out_by_inspection", bool(ro) and "2026-09-26" in ro["reason"]
      and not has(v, "tsb-f", "candidate"), str(rels(v, "tsb-f")))

# (f) score ordering
sc = {b["id"]: b["score"] for b in v["bulletins"]}
order = [b["id"] for b in v["bulletins"]]
check("f: score ordering", sc["tsb-a"] == 7 and sc["tsb-b"] == 2 and sc["tsb-e"] == 0
      and sc["rc-g"] == 0 and order[0] == "tsb-a"
      and [s for s in (b["score"] for b in v["bulletins"])] == sorted(sc.values(), reverse=True)
      and "not_applicable" in next(b for b in v["bulletins"] if b["id"] == "tsb-e")["flags"], str(sc))

# (g) /api/tsb/xref returns 200 and the pages render
FAKE = {"identity": {}, "tsb_matches": {"per_code": {}}}
tsb_routes._dossier = lambda vin: FAKE  # type: ignore[assignment]
tsb_bridge.catalogue = lambda: load_tsb_catalogue(json.dumps(CAT))  # type: ignore[assignment]
client = TestClient(create_app())
resp = client.get(f"/api/tsb/xref?vin={VIN}")
page = client.get(f"/tsb?vin={VIN}")
check("g: /api/tsb/xref 200", resp.status_code == 200 and resp.json()["bulletins"][0]["id"] == "tsb-a",
      f"{resp.status_code} {resp.text[:200]}")
check("g2: /tsb renders cross-reference + suggestion form", page.status_code == 200
      and 'data-xref="tsb-a"' in page.text and "Cross-reference" in page.text
      and f'action="/v/{VIN}/job/job1/hypotheses/h1/evidence"' in page.text,
      f"status {page.status_code}")

print(f"{checks - len(failures)}/{checks} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
