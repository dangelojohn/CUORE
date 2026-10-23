"""Checks for the AlfaCore export bundle (cuore.services.bundle_export + bundle_schema).

Scripted fixtures only: a throwaway state dir, a synthetic VIN, canned
observations from a "serial" stream and a job built through ``mes.jobs``.
Nothing touches a serial port.

Five checks:
  1. A scan bundle and a job bundle validate against the schema.
  2. Every file's sha256 and size in the manifest match the zip.
  3. Exporting unchanged data twice gives the same bundle_uuid.
  4. The download route refuses paths outside the exports folder.
  5. The job export carries evidence class labels (and tz_assumed on naive stamps).

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_bundle_export.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-bundle-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)
os.environ.pop("CUORE_STATION_ID", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import store  # noqa: E402
from cuore.services import bundle_export, bundle_schema  # noqa: E402
from mes import jobs  # noqa: E402

VIN = "ZASYNTH0000000001"  # synthetic
CAR = "serial COM3@115200"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


SCAN_ID = datetime.now().strftime("SCAN_%y%m%d%H%M")


def obs(kind: str, data: dict, bus: str = "can_c") -> None:
    store.record_observation(kind, data, vin=VIN, bus=bus, cable="none", stream=CAR)


obs("module_identity", {"ecu": "ECM", "bus": "can_c",
                        "fields": {"F190": {"name": "VIN", "ascii": VIN, "bytes": [], "nrc": None}}})
obs("module_dtcs", {"ecu": "ECM", "bus": "can_c", "mask": 255, "dtcs": [
    {"code": "P0456-00", "raw": "045600", "status": 0x2F,
     "flags": {"testFailed": True}},
    {"code": "P0455-00", "raw": "045500", "status": 0x20},
    {"code": "P0171-00", "raw": "017100", "status": 0x50}]})
obs("module_dtcs", {"ecu": "BCM", "bus": "can_c", "dtcs": [], "warning": "no answer from the module"})
obs("obd_dtcs", {"dtc_kind": "stored", "dtcs": [], "error": "ADAPTER/BUS ERROR NOT 'no codes'"})
obs("mode06", {"results": {"3C": {"by_ecu": {"18DAF110": [{"mid": "3C", "value": 1, "min": 0, "max": 5,
                                                              "passed": True}]}}}})
obs("readiness", {"since_clear": {"mil_on": True, "monitors": []}})
obs("dtc_detail", {"ecu": "ECM", "dtc": "P0456-00", "snapshot": {"records": []}})
obs("scan_coverage", {"scan_id": SCAN_ID, "vin": VIN, "cable": "none", "buses_attempted": ["can_c"],
                      "steps": [{"step": "verify_bus can_c", "ok": True}],
                      "coverage": [{"bus": "can_c", "module": "ECM", "category": "answered",
                                    "why": None, "active": 1, "history": 1, "not_run": 0},
                                   {"bus": "can_c", "module": "BCM", "category": "silent",
                                    "why": "no answer", "active": 0, "history": 0, "not_run": 0}],
                      "counts": {"active": 1, "history": 1, "not_run": 0}})

job = jobs.open(VIN, technician="T", complaint="CEL on")
hyp = jobs.add_hypothesis(job["id"], "EVAP small leak", system="evap", codes=["P0456"])
hid = [h for h in jobs.get(job["id"])["hypotheses"]][0]["id"]
jobs.attach(job["id"], {"kind": "code", "id": "P0456", "label": "P0456 active"}, hyp_id=hid, supports=True)
jobs.attach(job["id"], {"kind": "bulletin", "id": "tsb-x", "label": "forum thread"}, hyp_id=hid, supports=True)
jobs.add_action(job["id"], "inspection", "Checked the filler neck", event_date="2026-09-14")

if True:
    scan_zip = bundle_export.export_scan(SCAN_ID, VIN)
    job_zip = bundle_export.export_job(job["id"], VIN)
    errs = bundle_schema.validate_bundle(scan_zip) + bundle_schema.validate_bundle(job_zip)
    check("scan and job bundles validate against the schema", not errs, "; ".join(errs[:5]))

    bad = []
    for z in (scan_zip, job_zip):
        with zipfile.ZipFile(z) as zf:
            m = json.loads(zf.read("manifest.json"))
            for f in m["files"]:
                raw = zf.read(f["path"])
                if hashlib.sha256(raw).hexdigest() != f["sha256"] or len(raw) != f["bytes"]:
                    bad.append(f["path"])
            if set(zf.namelist()) != {"manifest.json"} | {f["path"] for f in m["files"]}:
                bad.append("member list")
    check("manifest sha256 and byte counts match the zip", not bad, str(bad))

    m1 = bundle_export.read_manifest(scan_zip)
    j1 = bundle_export.read_manifest(job_zip)
    again = bundle_export.export_scan(SCAN_ID, VIN)
    jagain = bundle_export.export_job(job["id"], VIN)
    check("same data exported twice gives the same bundle_uuid",
          bundle_export.read_manifest(again)["bundle_uuid"] == m1["bundle_uuid"]
          and bundle_export.read_manifest(jagain)["bundle_uuid"] == j1["bundle_uuid"]
          and m1["bundle_uuid"] != j1["bundle_uuid"],
          f"{m1['bundle_uuid']} vs {bundle_export.read_manifest(again)['bundle_uuid']}")

    client = TestClient(create_app())
    ok = client.get("/api/export/download", params={"path": str(scan_zip)})
    outside = Path(tempfile.mkdtemp(prefix="cuore-outside-")) / "x.cuore.zip"
    outside.write_bytes(b"PK")
    traversal = str(scan_zip.parent / ".." / "station.json")
    codes = [client.get("/api/export/download", params={"path": p}).status_code
             for p in (str(outside), traversal, str(Path(os.environ["CUORE_STATE_DIR"]) / "observations.jsonl"))]
    check("download streams an export and refuses paths outside the exports folder",
          ok.status_code == 200 and ok.content[:2] == b"PK" and all(c == 400 for c in codes),
          f"ok={ok.status_code} refused={codes}")

    with zipfile.ZipFile(job_zip) as zf:
        jj = json.loads(zf.read("job.json"))["job"]
        steps = json.loads(zf.read("mechanic_steps.json"))
    h = jj["hypotheses"][0]
    classes = {r["kind"]: r["evidence_class"] for r in h["evidence_for"]}
    check("job export labels evidence classes and flags assumed time zones",
          classes == {"code": "reading", "bulletin": "outside_literature"}
          and h["evidence_class"] == "outside_literature"
          and jj["actions"][0]["evidence_class"] == "owner_attested"
          and jj["actions"][0]["tz_assumed"] is True and jj["actions"][0]["at_iso"][-6] in "+-"
          and all("evidence_class" in s for p in steps["plans"] for s in p["steps"]),
          f"{classes} hyp={h['evidence_class']}")

if failures:
    print(f"FAIL ({len(failures)} of {checks}):")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"OK: {checks} checks passed")
