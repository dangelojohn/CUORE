"""The 19-module list, identity remainder and 28-field snapshot view against fakes.

No adapter, no port: observations and the audit file are written into a throwaway
state directory BEFORE cuore is imported. Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_mes_coverage.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="cuore-check-mescov-"))
os.environ["CUORE_STATE_DIR"] = str(STATE)
os.environ["CUORE_AUDIT_PATH"] = str(STATE / "audit.jsonl")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

VIN = "ZASFAKPN5J7B88115"
SER = "serial COM3@115200"


def ob(kind, data, at="2026-10-30T23:55:00", stream=SER):
    return json.dumps({"at": at, "kind": kind, "vin": VIN, "bus": "can_c", "cable": "none",
                       "stream": stream, "data": data})


def ident(ecu, answered, at):
    dids = ["F190", "F187", "F188", "F189", "F18C", "F191", "F192", "F194", "F195"]
    f = {d: ({"name": d, "ascii": "X", "bytes": ["58"], "nrc": None} if answered else
             {"name": d, "ascii": None, "bytes": None, "nrc": None}) for d in dids}
    return ob("identity", {"ecu": ecu, "fields": f}, at)


def ident_partial(ecu, at):
    o = json.loads(ident(ecu, True, at))
    o["data"]["fields"]["F195"] = {"name": "F195", "ascii": None, "bytes": None, "nrc": None}
    return json.dumps(o)


def dtcs(ecu, ok, at):
    d = {"ecu": ecu, "dtcs": [], "error": None, "nrc": None}
    if not ok:
        d["warning"] = "no answer from the module"
    return ob("module_dtcs", d, at)


# the paired ECM record: bytes as the real layout decodes them (values equal MES)
def idf(did, b, value=None):
    return {"did": did, "name": "n", "bytes": b, "value": value}


REC = [idf("1008", ["00", "04", "94", "4E"], 300110), idf("1009", ["00", "00"]),
       idf("200A", ["39", "67"], 14695), idf("6082", ["00"]), idf("1000", ["00", "00"], 0),
       idf("1002", ["00", "00"], 0), idf("2001", ["16", "7A", "B3"], 147320.3),
       idf("1003", ["34"], 12), idf("1004", ["00", "78"], 12), idf("1937", ["03", "DC"], 988),
       idf("1935", ["34"], 12), idf("195A", ["03", "E6"], 998), idf("1956", ["03", "E7"], 999),
       idf("1302", ["00", "0C"], 12), idf("19BD", ["64"], 100), idf("198C", ["01"], "Late opening"),
       idf("1001", ["9B"], 60.78), idf("192D", ["00"], 0), idf("1812", ["00", "00"], 0),
       idf("182F", ["00", "00"]), idf("1B0D", ["00", "04", "00", "00", "00", "00", "00", "00"])]
lines = [
    ob("dtc_detail", {"ecu": "ECM", "dtc": "P0456-00", "snapshot": {"records": [
        {"record_number": 0, "identifiers": REC}]}}),
    ident("ECM", True, "2026-10-24T13:22:00"), dtcs("ECM", True, "2026-10-31T00:36:00"),
    ident_partial("TCM", "2026-10-24T13:22:00"), dtcs("TCM", False, "2026-10-31T00:36:00"),
    ident("ABS", False, "2026-10-31T01:03:00"), dtcs("ABS", False, "2026-10-31T01:07:00"),
    ob("identity", {"ecu": "BCM", "fields": {"F190": {"name": "VIN", "ascii": "X", "bytes": ["58"]}}},
       "2026-10-24T13:22:00", stream="scripted"),   # a fake stream is not evidence
]
(STATE / "observations.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
# one recorded 22 F193 reply from the TCM: payload 62 F1 93 20 (MES prints hardware version 20)
(STATE / "audit.jsonl").write_text(json.dumps(
    {"ts": 1, "iso": "2026-10-24T13:22:43-04:00", "event": "uds", "ecu": "TCM", "bus": "can_c",
     "req": "22F193", "header": "18DA18F1", "raw": "18DAF1180462F19320", "error": None}) + "\n",
    encoding="utf-8")

from cuore.live import uds  # noqa: E402
from cuore.services import mes_coverage as mc  # noqa: E402

failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label} {detail}")


# --- 19 modules
cov = mc.all_modules(VIN)
rows = {r["code"]: r for r in cov["rows"]}
check("19 rows every time", cov["total"] == 19 and len(cov["rows"]) == 19, str(cov["total"]))
check("count line is N of 19", cov["line"].startswith(f"{cov['read']} of 19 read"), cov["line"])
check("ECM READ", rows["ECM"]["state"] == mc.READ, str(rows["ECM"]))
check("TCM PARTLY (identity partial, newest code read failed)", rows["TCM"]["state"] == mc.PARTLY)
check("TCM names the failed code read with a date", "NOT READ" in " ".join(rows["TCM"]["detail"])
      and "2026-10-31" in " ".join(rows["TCM"]["detail"]))
check("ABS NOT READ with reason and date", rows["ABS"]["state"] == mc.NOT_READ
      and "2026-10-31" in rows["ABS"]["headline"], rows["ABS"]["headline"])
check("a scripted-stream observation is not evidence", rows["BCM"]["state"] == mc.NOT_TRIED)
check("never-tried module is NOT TRIED with its blocker", rows["EPS"]["state"] == mc.NOT_TRIED
      and "Address unknown" in rows["EPS"]["blocker"])
check("climate keeps its dated silent attempt", rows["CLIMATE"]["state"] == mc.NOT_READ
      and "2026-10-23" in rows["CLIMATE"]["headline"])
check("only ECM counts as read", cov["read"] == 1 and cov["counts"][mc.READ] == 1, str(cov["counts"]))
check("states are exhaustive", sum(cov["counts"].values()) == 19)
check("no unread row says clean", all("clean" not in r["headline"].lower()
                                       for r in cov["rows"] if r["state"] != mc.READ))
check("other cars and demo cars get no list", not mc.all_modules("1HGCM82633A004352")["applies"])

# --- identity remainder
ir = {r["key"]: r for r in mc.identity_remainder(VIN, "TCM")}
check("TCM hardware version decoded from the recorded F193 reply",
      ir["hw_version"]["cuore"] == "20" and ir["hw_version"]["match"] is True, str(ir["hw_version"]))
check("TCM ISO code NOT READ, DID not on file, not added",
      ir["iso"]["state"] == mc.NOT_READ and "no source on file" in ir["iso"]["next"])
check("homologation NOT READ", ir["homologation"]["state"] == mc.NOT_READ)
ecm = {r["key"]: r for r in mc.identity_remainder(VIN, "ECM")}
check("ECM hardware version not read, F193 not in the plan, marked not added",
      ecm["hw_version"]["state"] == mc.NOT_READ and "not added" in ecm["hw_version"]["next"]
      and 0xF193 not in uds.IDENTITY_ORDER)
check("ECM homologation shows MES FIBA00", ecm["homologation"]["mes"] == "FIBA00")
check("blank MES homologation stays blank", ir["homologation"]["mes"] == "blank")
check("eight modules have rows, others none", all(len(mc.identity_remainder(VIN, c)) == 3
      for c in mc.CAN_C_EIGHT) and mc.identity_remainder(VIN, "ABS") == [])

# --- snapshot
sf = mc.snapshot_fields(VIN, "ECM")
c = sf["counts"]
check("28 fields", sf["total"] == 28 and len(sf["rows"]) == 28)
check("9 bound, 9 candidates, 10 NOT DECODED",
      (c["BOUND"], c["CANDIDATE"], c["NOT DECODED"]) == (9, 9, 10), str(c))
check("every field has a state", sum(c.values()) == 28)
by = {r["name"]: r for r in sf["rows"]}
check("odometer bound", by["Odometer"]["state"] == "BOUND" and by["Odometer"]["raw"] == "16 7A B3")
check("three temperatures stay candidates", all(by[n]["state"] == "CANDIDATE" for n in
      ("Engine temperature", "Air temperature", "Engine oil temperature")))
check("zero-valued rpm is only a candidate", by["Engine speed"]["state"] == "CANDIDATE")
check("pedals NOT DECODED, no DID, no value", by["Brake pedal"]["state"] == "NOT DECODED"
      and by["Brake pedal"]["did"] is None and by["Brake pedal"]["raw"] is None)
check("no scale is ever confirmed here", all(r["scale"] != "accepted by a person" for r in sf["rows"]))
check("unassigned bytes are listed raw", any(x["did"] == "1B0D" and x["length"] == 8 for x in sf["spare"]))
check("non-ECM module has no snapshot view", not mc.snapshot_fields(VIN, "TCM")["applies"])

nr = mc.not_read_lines(VIN)
check("report lines list every non-READ module", len(nr["lines"]) == 18, str(len(nr["lines"])))
check("report line carries the identity and snapshot totals", "24" in nr["identity_line"]
      and "NOT DECODED" in nr["snapshot_line"])

# a missing paired reply: nothing is shown as verified
(STATE / "observations.jsonl").write_text("", encoding="utf-8")
sf2 = mc.snapshot_fields(VIN, "ECM")
check("without the paired reply nothing is BOUND", sf2["counts"]["BOUND"] == 0
      and not sf2["paired_record_found"])
cov2 = mc.all_modules(VIN, live={})
check("with no reads on file: 0 of 19, none READ", cov2["read"] == 0 and cov2["line"].startswith("0 of 19"))

print(f"{checks - len(failures)} of {checks} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
