"""Check the ABS snapshot scaffold, proposals and owner bindings with a synthetic
19 04 reply (no adapter, no car).

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_abs_layout.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-abs-layout-")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import dtc_detail, snapshot_bindings as sb  # noqa: E402
from cuore.live.errors import BadCommand  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


hi, mid, lo = dtc_detail.dtc_to_bytes("C104B-92")
# record 01, 3 DIDs: F186 (standard 1 byte), 1234 (length not in the frame), 9999 (unknown)
REPLY = ["59", "04", hi, mid, lo, "2F", "01", "03", "F1", "86", "03", "12", "34", "79", "99", "99", "00", "11"]
NAMES = ["Operating time", "Startups counter", "Brake switches", "Battery voltage", "Vehicle speed",
         "Hydraulic circuit pressure", "Brake pedal pressure"]

# 1. scaffold: seven names, everything unbound, anchored to the MES log
sc = sb.scaffold("ABS")
check("scaffold has the seven names", [f["name"] for f in sc] == NAMES)
check("scaffold all unbound/None", all(f["did"] is None and f["length"] is None and f["scale"] is None
                                       and f["status"] == "unbound" for f in sc))
check("scaffold cites FESLog_2609042001", all("FESLog_2609042001" in f["anchor"] for f in sc))

# 2. nothing bound: walk parses F186, stops at 1234 (length unknown) -> raw bytes + candidates + proposal
r = dtc_detail.decode_snapshot_record(REPLY, "ABS", VIN)
check("ABS still returns raw undecoded_from", "undecoded_from" in r and "1234" in r["undecoded_from"], str(r.get("undecoded_from")))
check("unresolved_did reported", r.get("unresolved_did") == "1234")
check("candidate_fields = all seven", r.get("candidate_fields") == NAMES)
props = r.get("proposals") or []
check("one proposal for the parsed F186 record", len(props) == 1 and props[0]["did"] == "F186"
      and props[0]["length"] == 1 and props[0]["raw"] == 3, str(props))
check("proposals are 'proposed' only", all(c["status"] == "proposed" for p in props for c in p["candidates"]))
idents = r["records"][0]["identifiers"]
check("proposal did not bind F186", idents[0].get("status") != sb.BOUND_STATUS and idents[0]["name"] != "Brake switches")
check("no bindings file written by decoding", not sb.bindings_path().exists())

# 3. non-scaffold modules unchanged
e = dtc_detail.decode_snapshot_record(["59", "04", hi, mid, lo, "2F"], "ECM")
check("ECM result has no scaffold keys", "candidate_fields" not in e and "proposals" not in e)

# 4. bind: validation, persistence, used at decode time
for bad in (dict(did="ZZZZ", field_name="Battery voltage"), dict(did="1234", field_name="Not a field"),
            dict(did="1234", field_name="Battery voltage", length=0)):
    try:
        sb.bind(VIN, "ABS", **bad)
        check(f"bind rejects {bad}", False)
    except BadCommand:
        check(f"bind rejects {bad}", True)
b = sb.bind(VIN, "ABS", "1234", "Battery voltage", length=1, unit="V", div=10)
check("bind saved to snapshot_bindings.json", sb.bindings_path().exists() and b["status"] == "bound (owner)")
r2 = dtc_detail.decode_snapshot_record(REPLY, "ABS", VIN)
ids2 = r2["records"][0]["identifiers"]
bound = next((i for i in ids2 if i["did"] == "1234"), None)
check("bound DID decoded with owner scale", bound is not None and bound["value"] == 12.1
      and bound["name"] == "Battery voltage" and bound["status"] == "bound (owner)", str(bound))
check("walk now stops at the next unknown DID", r2.get("unresolved_did") == "9999")
check("bound name leaves candidate_fields", "Battery voltage" not in r2["candidate_fields"]
      and len(r2["candidate_fields"]) == 6)
check("bound DID not proposed again", all(p["did"] != "1234" for p in r2["proposals"]))
r3 = dtc_detail.decode_snapshot_record(REPLY, "ABS", None)
check("another/no VIN sees no bindings", r3.get("unresolved_did") == "1234" and len(r3["candidate_fields"]) == 7)

# 5. bind without scale keeps value withheld
sb.bind(VIN, "ABS", "1234", "Vehicle speed", length=1)
r4 = dtc_detail.decode_snapshot_record(REPLY, "ABS", VIN)
i4 = next(i for i in r4["records"][0]["identifiers"] if i["did"] == "1234")
check("re-binding moves the name, no scale -> value None", i4["name"] == "Vehicle speed" and i4["value"] is None
      and "Battery voltage" in r4["candidate_fields"])

if failures:
    print(f"FAIL {len(failures)}/{checks}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"OK: {checks} checks passed")
