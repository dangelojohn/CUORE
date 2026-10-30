"""Checks for the warranty evidence pack (services/warranty_pack.py, web/warranty_routes.py).
Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_warranty_pack.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_wp_check_")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import jobs_bridge, warranty_pack as wp  # noqa: E402
from cuore.web.warranty_routes import router  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
fails: list[str] = []
passed = 0


def check(name: str, ok: bool, note: str = "") -> None:
    global passed
    if ok:
        passed += 1
    else:
        fails.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{note}]" if note and not ok else ""))


# --- pure builder, full evidence ------------------------------------------------
JOB = {"id": "j1", "vin": VIN, "opened_at": "2026-10-01T09:00:00", "closed_at": "2026-10-02T10:00:00",
       "technician": "Marco", "complaint": "Shudder when pulling away", "outcome": "fixed",
       "customer_name": "Jane Doe", "customer_phone": "555-0100",
       "verification": {"readiness_at": "2026-10-02T09:50:00", "codes_returned": [], "verdict": "no return"},
       "hypotheses": [{"id": "h1", "text": "EGR stuck", "evidence_for": [
           {"id": "e1", "kind": "test", "label": "EGR a-vs-d", "result": "fail", "at": "2026-10-01T11:00:00", "by": "Marco"}],
           "evidence_against": []}],
       "actions": [
           {"id": "a1", "kind": "inspection", "text": "Smoke test EVAP", "at": "2026-10-01T10:00:00", "ref": {"result": "pass"}},
           {"id": "a2", "kind": "repair", "text": "Replaced EGR valve", "at": "2026-10-02T08:00:00", "ref": None},
           {"id": "a3", "kind": "observation", "text": "Idle MAP 31 kPa", "at": "2026-10-01T09:30:00", "ref": None}]}
SRC = {"vin": VIN, "vehicle": "Stelvio", "job": JOB, "generated_at": "2026-10-30T12:00:00",
       "symptoms": [{"id": "s1", "at": "2026-09-28T08:00:00", "reporter": "driver", "text": "It shakes", "odometer_km": 41200}],
       "dtcs": [{"dtc": "P0401-00", "first_seen": "2026-10-01", "last_seen": "2026-10-01T09:10:00", "sessions": 2,
                 "descriptions": ["EGR flow insufficient"], "odometer_last": 41250}],
       "freeze_frames": [{"code": "P0401", "at": "2026-10-01T09:10:00", "values": {"RPM": "820"}}],
       "observations": [{"at": "2026-10-01T09:20:00", "kind": "live", "stream": "serial COM3@38400", "data": {"MAP": 31}}],
       "xref": {"bulletins": [{"id": "b1", "number": "18-030-17", "title": "ECM update"}],
                "by_code": {"P0401": [{"bulletin": "b1", "type": "code", "reason": "same DTC P0401"}]}, "by_repair": []},
       "media": [{"id": "m1", "captured_at": "2026-10-02T08:30:00", "caption": "Old EGR valve", "filename": "a.jpg", "kind": "photo"}],
       "dealer": []}
full = wp.build(SRC)
check("full evidence: 8 of 8, backed", full["score"] == {"done": 8, "total": 8, "backed": True}, str(full["score"]))
check("checklist order", [c["key"] for c in full["checklist"]] ==
      ["complaint", "codes", "readings", "tests", "bulletins", "repair", "proof", "photos"])
check("sections ordered", [s["key"] for s in full["sections"]][:8] ==
      ["complaint", "codes", "readings", "tests", "bulletins", "repair", "proof", "photos"])
items = [i for s in full["sections"] for i in s["items"]]
check("every item has source", all(i["source"] for i in items))
check("every item but bulletin links/people has a timestamp",
      all(i["at"] for i in items if i["section"] not in ("bulletins", "technicians")))
check("owner's words labelled", any(i["label"] == "owner's words" for i in full["sections"][0]["items"]))
check("outside fact labelled", all(i["label"] == "outside fact" for i in full["sections"][4]["items"]) and full["sections"][4]["items"])
check("snapshot embedded in code", (full["sections"][1]["items"][0]["data"] or {}).get("snapshot") == {"RPM": "820"})
check("odometer carried", full["sections"][1]["items"][0]["data"].get("odometer_last") == 41250
      and full["sections"][0]["items"][0]["data"].get("odometer_km") == 41200)
check("technician attribution", any(i["text"] == "Marco" for s in full["sections"] for i in s["items"] if s["key"] == "technicians"))
check("manifest hashes verify", wp.verify(json.loads(json.dumps(full))) == [])
tampered = json.loads(json.dumps(full))
tampered["sections"][3]["items"][0]["text"] = "changed"
check("tampering detected", wp.verify(tampered) != [])
check("customer excluded by default", "Jane" not in json.dumps(full) and "555-0100" not in json.dumps(full)
      and not any(s["key"] == "customer" for s in full["sections"]))
withc = wp.build(SRC, include_customer=True)
check("customer included when ticked", "Jane Doe" in json.dumps(withc) and wp.verify(withc) == [])

# --- partial and empty ----------------------------------------------------------
part = wp.build({**SRC, "media": [], "xref": None, "job": {**JOB, "outcome": None, "verification": {}}})
miss = [c["key"] for c in part["checklist"] if not c["ok"]]
check("partial: missing items named", miss == ["bulletins", "proof", "photos"], str(miss))
check("partial: not backed with needed text", not part["score"]["backed"] and len(part["missing"]) == 3)
empty = wp.build({"vin": VIN})
check("empty: 0 of 8", empty["score"]["done"] == 0 and wp.verify(empty) == [])

# --- routes with a real seeded job ----------------------------------------------
app = create_app()
app.include_router(router)
c = TestClient(app)
_real_gather = wp.gather
wp.gather = lambda vin, job_id="": {"vin": vin, "generated_at": "2026-10-30T12:00:00", "job": None, "xref": None}  # nothing on file
r = c.get(f"/v/{VIN}/warranty-pack")
wp.gather = _real_gather
check("empty state page renders", r.status_code == 200 and "Warranty evidence pack" in r.text
      and "Nothing recorded for this section." in r.text and "Not fully backed yet: 0 of 8" in r.text, str(r.status_code))
check("note shown", "The claim itself is submitted through the manufacturer's warranty system." in r.text.replace("&#39;", "'"))

job = jobs_bridge.open_job(VIN, technician="Marco", complaint="Shudder when pulling away")
jobs_bridge.add_action(job["id"], "repair", "Replaced EGR valve")
jobs_bridge.add_action(job["id"], "inspection", "Visual check of EGR pipe")
r = c.get(f"/v/{VIN}/warranty-pack")
check("seeded job page", r.status_code == 200 and "Shudder when pulling away" in r.text and "Replaced EGR valve" in r.text)
check("page has actions and no script", "Download pack (JSON + printable HTML)" in r.text and "Print" in r.text
      and all("<script" not in (Path(__file__).resolve().parents[1] / "web" / "templates" / n).read_text(encoding="utf-8")
          for n in ("warranty_pack.html", "_warranty_body.html", "warranty_pack_print.html")))
check("page has customer checkbox off", 'name="customer"' in r.text and "checked" not in r.text.split('name="customer"')[1][:40])
j = c.get(f"/v/{VIN}/warranty-pack.json")
check("json download", j.status_code == 200 and "attachment" in j.headers.get("content-disposition", ""))
pack = j.json()
check("json manifest verifies", wp.verify(pack) == [] and len(pack["manifest"]) > 0)
check("json: repair + complaint present", pack["job_id"] == job["id"] and
      any("Replaced EGR" in i["text"] for s in pack["sections"] for i in s["items"]))
check("json: no customer section by default", not any(s["key"] == "customer" for s in pack["sections"]))
h = c.get(f"/v/{VIN}/warranty-pack.html")
check("printable html", h.status_code == 200 and "@media print" in h.text and "<html" in h.text and "base" not in h.text.lower()[:200])
check("customer flag accepted", c.get(f"/v/{VIN}/warranty-pack.json?customer=1").json()["include_customer"] is True)

print(f"\n{passed} passed, {len(fails)} failed")
if fails:
    print("FAILED:", *fails, sep="\n  ")
    sys.exit(1)
