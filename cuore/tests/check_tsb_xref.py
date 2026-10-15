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
    {"id": "sib-x", "kind": "tsb", "number": "SIB-001", "title": "Jeep purge valve",
     "vehicle_scope": "sibling_engine", "sibling_vehicle": "2019 Jeep Wrangler JL 2.0T",
     "systems": ["EVAP"], "dtcs": ["P0440"], "applies": "vin_check", "verified": True,
     "stelvio_equivalent": "77-001-26", "remedy": "Replace the purge valve.",
     "components": ["purge valve"], "transferability": "inference: same engine"},
    {"id": "sib-fr", "kind": "field_report", "number": "FIELD REPORT 1", "title": "Forum: P0440 fixed",
     "vehicle_scope": "sibling_engine", "sibling_vehicle": "Jeep Wrangler JL", "systems": ["EVAP"],
     "dtcs": ["P0440"], "applies": "yes", "summary": "analogue only", "verified": False},
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
      and [b["score"] for b in v["bulletins"] if b["vehicle_scope"] == "this_model"]
      == sorted((b["score"] for b in v["bulletins"] if b["vehicle_scope"] == "this_model"), reverse=True)
      and "not_applicable" in next(b for b in v["bulletins"] if b["id"] == "tsb-e")["flags"], str(sc))

# (h) sibling-engine analogues: half score + own list; equivalent link; field_report cap
SIB = next(x for x in v["bulletins"] if x["id"] == "sib-x")
base = next(x for x in v["bulletins"] if x["id"] == "tsb-a")
check("h: analogue scores half and lands in analogues", SIB["score"] == base["score"] // 2
      and SIB["vehicle_scope"] == "sibling_engine" and has(v, "sib-x", "analogue") is not None
      and [a["id"] for a in v["analogues"]][:1] == ["sib-x"]
      and any(e["bulletin"] == "sib-x" for e in v["analogues_by"]["by_code"].get("P0440", []))
      and all(e["bulletin"] != "sib-x" for e in v["by_code"].get("P0440", []))
      and [b["vehicle_scope"] for b in v["bulletins"]] == sorted(
          (b["vehicle_scope"] for b in v["bulletins"]), key=lambda t: t == "sibling_engine")
      and any(a["id"] == "sib-x" for a in base["analogues"]), f"{SIB['score']} vs {base['score']}")
r = has(v, "sib-x", "analogue")
check("h2: stelvio_equivalent link in reason", "analogue of Stelvio 77-001-26" in r["reason"]
      and r.get("stelvio_equivalent") == "tsb-a", str(r))
FR = next(x for x in v["bulletins"] if x["id"] == "sib-fr")
check("h3: field_report capped at 1", FR["score"] <= 1 and bool(has(v, "sib-fr", "field_report"))
      and FR["score"] == 1, str(FR["score"]))

# (i) date logic, remedy matching and relation names, on a second fake car
CAT2 = {"vehicle": {"make": "Alfa Romeo", "model": "Stelvio", "year": 2018, "vin": VIN},
        "updated": "2026-10-15", "items": [
    {"id": "t-can", "number": "66-001-26", "title": "Canister", "systems": ["EVAP"],
     "dtcs": ["P0440"], "applies": "yes", "repair_implied": "replace:vapour canister",
     "components": ["EVAP vapour canister"]},
    {"id": "t-cap", "number": "66-002-26", "title": "Fuel cap", "systems": ["EVAP"],
     "dtcs": ["P0440"], "applies": "yes", "repair_implied": "replace:fuel cap",
     "components": ["fuel cap"]},
    {"id": "t-pv", "number": "66-003-26", "title": "Purge valve", "systems": ["EVAP"],
     "dtcs": ["P0440"], "applies": "yes", "repair_implied": "replace:purge valve",
     "components": ["purge valve"]},
    {"id": "t-fl", "number": "66-004-26", "title": "Flash: PCM update", "systems": ["ECM"],
     "dtcs": ["P0440"], "applies": "yes", "repair_implied": "flash", "nhtsa_id": "10170001",
     "components": ["ECM", "wiTECH 2 Phonic Wheel Replacement"], "remedy": "Reprogram ECM."},
    {"id": "t-pr", "number": "66-005-26", "title": "SLVT", "systems": ["EVAP"],
     "dtcs": ["P0440"], "applies": "yes", "repair_implied": "procedure:wiTECH SLVT",
     "components": ["wiTECH SLVT (Small Leak Verification Test)"]},
    {"id": "t-yr", "number": "66-006-26", "title": "Later years", "systems": ["EVAP"],
     "applies": "vin_check", "applies_to": "2020-2021 Stelvio"},
]}
HIST2 = [{"dtc": "P0440-00", "first_seen": "2026-08-01 10:00:00", "last_seen": "2026-10-05 09:00:00",
          "sessions": 4, "modules": ["Engine / ECM"],
          "occurrences": [{"timestamp": "2026-10-05 09:00:00", "status": "cleared"}]},
         {"dtc": "P0300-00", "first_seen": "2026-10-14 10:00:00", "last_seen": "2026-10-14 10:00:00",
          "sessions": 1, "modules": ["Engine / ECM"],
          "occurrences": [{"timestamp": "2026-10-14 10:00:00", "status": "stored"}]}]
REC = "2026-10-15T01:16:18"   # every action recorded now, for events in the past
ACTS = [
    {"at": REC, "kind": "part", "text": "REPAIR HISTORY, 2026-09-02. Done: EVAP canister replaced; "
     "ECM connector cleaned, wiTECH 2 Phonic Wheel Replacement noted. Meaning: canister not the cause."},
    {"at": REC, "kind": "part", "text": "2026-10-10: fuel cap replaced."},
    {"at": REC, "kind": "part", "text": "REPAIR HISTORY, between 2026-09-02 and 2026-09-25 "
     "(exact date unknown). Engine-side purge valve, part 68337662AC, replaced."},
    {"at": REC, "kind": "test", "text": "2026-10-12: EVAP leak test performed with wiTECH, "
     "verification of the small hose passed."},
]


def run2(extra: list[dict]) -> dict:
    job = {"id": "job2", "vin": VIN, "status": "open", "hypotheses": [], "actions": ACTS + extra}
    saved = (X._load_catalogue, X._load_dtc_history, X._load_live_active, X._load_jobs)
    X._load_catalogue = lambda: load_tsb_catalogue(json.dumps(CAT2))  # type: ignore[assignment]
    X._load_dtc_history = lambda vin: [dict(r) for r in HIST2]  # type: ignore[assignment]
    X._load_live_active = lambda vin: set()  # type: ignore[assignment]
    X._load_jobs = lambda vin: [json.loads(json.dumps(job))]  # type: ignore[assignment]
    try:
        return X.xref(VIN)
    finally:
        X._load_catalogue, X._load_dtc_history, X._load_live_active, X._load_jobs = saved


v2 = run2([])
a, d = has(v2, "t-can", "already_applied"), has(v2, "t-can", "did_not_resolve")
ac, dc = has(v2, "t-cap", "already_applied"), has(v2, "t-cap", "did_not_resolve")
check("i1: event date, not record date", bool(a) and bool(d) and "2026-09-02" in a["reason"]
      and "recorded 2026-10-15" in a["reason"] and "'canister'" in a["reason"]
      and d["reason"].startswith("canister replaced 2026-09-02 (recorded 2026-10-15); P0440 last seen 2026-10-05")
      and "01:16" not in d["reason"]
      and bool(ac) and "2026-10-10" in ac["reason"] and dc is None, f"{a} / {d} / {ac} / {dc}")
pa, pd = has(v2, "t-pv", "already_applied"), has(v2, "t-pv", "did_not_resolve")
check("i2: uncertain 'between' range uses the later date and says so", bool(pa) and bool(pd)
      and "uncertain: between 2026-09-02 and 2026-09-25" in pa["reason"]
      and "2026-09-25" in pd["reason"] and "uncertain" in pd["reason"], f"{pa} / {pd}")
check("i3: flash not matched by a parts action", has(v2, "t-fl", "already_applied") is None
      and bool(has(v2, "t-fl", "candidate")), str(rels(v2, "t-fl")))
v3 = run2([{"at": REC, "kind": "repair", "text": "2026-10-13: dealer reflashed ECM to the latest calibration."}])
fa = has(v3, "t-fl", "already_applied")
check("i4: flash matched by 'reflashed ECM'", bool(fa) and "'reflashed' + 'ECM'" in fa["reason"]
      and "flash/reprogram" in fa["reason"] and "2026-10-13" in fa["reason"]
      and sum(1 for r in rels(v3, "t-fl") if r.get("relation") == "already_applied") == 1, str(fa))
v4 = run2([{"at": REC, "kind": "test", "text": "2026-10-14: wiTECH Small Leak Verification Test passed."}])
pr4 = has(v4, "t-pr", "already_applied")
check("i5: procedure not matched by generic words, matched by its name",
      has(v2, "t-pr", "already_applied") is None and bool(has(v2, "t-pr", "candidate"))
      and bool(pr4) and "'Small Leak Verification Test'" in pr4["reason"], f"{rels(v2, 't-pr')} / {pr4}")
appl = {b["id"]: [r.get("relation") for r in b["relations"] if r["type"] == "applicability"]
        for vv in (v, v2) for b in vv["bulletins"]}
check("i6: applicability relations are named", appl["tsb-a"] == ["applies"]
      and appl["tsb-b"] == ["vin_check"] and appl["tsb-e"] == ["not_applicable"]
      and "other_model_doubt" in appl["tsb-d"] and "model_year_doubt" in appl["t-yr"]
      and all(all(x for x in lst) for lst in appl.values()), str(appl))

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
