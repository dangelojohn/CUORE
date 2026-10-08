"""Smoke checks for electrical architecture + inspection records.

Same posture as ``check_notes.py``: ``CUORE_STATE_DIR`` is pointed at a
throwaway directory before anything under ``mes``/``cuore`` is imported, so
this suite never touches the real bench's inspection log.

Five checks, per the build spec:
1. every element's location carries a source, or is explicitly UNKNOWN.
2. the P0455 electrical path includes a ground and the ESIM connector.
3. the network-family path starts at electrical supply (F82/BCM feeds).
4. inspection add/latest round trip.
5. the /api/electrical/elements route returns 200.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="mes-check-electrical-")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mes-log-mcp
sys.path.insert(0, str(REPO_ROOT))                             # repo root (cuore)

from mes import electrical, electrical_inspections  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


# --- 1. every element location has a source, or is UNKNOWN -----------------
print("=== element location sourcing ===")
bad = []
for eid, e in electrical.ELEMENTS.items():
    loc = e.get("location", {})
    conf = loc.get("confidence")
    src = loc.get("source")
    if conf is None or conf not in electrical.CONFIDENCE_LEVELS:
        bad.append(f"{eid}: bad confidence {conf!r}")
        continue
    if conf == electrical.UNKNOWN:
        if "UNKNOWN" not in loc.get("description", ""):
            bad.append(f"{eid}: UNKNOWN confidence but description doesn't say so")
    else:
        if not src:
            bad.append(f"{eid}: confidence {conf} but no source")
check("every element location sourced or UNKNOWN", not bad, "; ".join(bad))

# --- 2. P0455 path includes a ground and the ESIM connector ----------------
print("=== P0455 path ===")
p0455 = electrical.code_electrical_path("P0455")
check("P0455 resolves to the evap family", p0455["family"] == "evap",
      str(p0455["family"]))
roles = {hop["element"]: hop["role"] for hop in p0455["path"]}
check("P0455 path includes a ground", "ground" in [h["role"] for h in p0455["path"]],
      str(roles))
check("P0455 path includes the ESIM connector", "esim_connector" in roles,
      str(roles))

# also exercise the code with a failure-type byte, like a real log would give
p0455_byte = electrical.code_electrical_path("P0455-00")
check("P0455-00 (failure byte) resolves the same as P0455",
      p0455_byte["family"] == "evap")

# --- 3. network path starts at electrical supply (F82/BCM feeds) -----------
print("=== network path ===")
net = electrical.code_electrical_path("U1700")
check("U1700 resolves to the network family", net["family"] == "network",
      str(net["family"]))
check("network path non-empty", len(net["path"]) > 0)
first = net["path"][0] if net["path"] else {}
check("network path starts at electrical supply (F82/BCM feeds)",
      first.get("element") in ("f82", "bcm_feed_20a") and first.get("role") == "supply",
      str(first))

# a code outside any curated family must come back empty, not invented
unknown = electrical.code_electrical_path("P9999")
check("unsourced code returns empty path, not invented data",
      unknown["family"] is None and unknown["path"] == [])

# --- 4. inspection add/latest round trip ------------------------------------
print("=== inspection add/latest round trip ===")
rec = electrical_inspections.add(VIN, "xy201", "corroded", by="technician",
                                 note="green corrosion on both pins")
check("add returns a stored record with an id", bool(rec.get("id")))
got = electrical_inspections.latest(VIN, "xy201")
check("latest returns the just-added record", got is not None and got["id"] == rec["id"],
      str(got))

rec2 = electrical_inspections.add(VIN, "xy201", "repaired", note="re-seated, cleaned")
got2 = electrical_inspections.latest(VIN, "xy201")
check("latest tracks the newest record after a second add",
      got2 is not None and got2["id"] == rec2["id"], str(got2))

all_rows = electrical_inspections.load(vin=VIN, element="xy201")
check("load returns both records", len(all_rows) == 2, str(len(all_rows)))

try:
    electrical_inspections.add(VIN, "xy201", "bogus-condition")
    check("invalid condition rejected", False)
except ValueError:
    check("invalid condition rejected", True)

# --- 5. API 200 --------------------------------------------------------------
print("=== API ===")
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cuore.api import electrical as electrical_api
    from cuore.config import Settings

    app = FastAPI()
    app.state.settings = Settings(token="")  # auth off, same as require_token's no-op path
    app.include_router(electrical_api.router, prefix="/api")
    client = TestClient(app)

    resp = client.get("/api/electrical/elements")
    check("GET /api/electrical/elements -> 200", resp.status_code == 200,
          str(resp.status_code))
    body = resp.json()
    check("elements payload has rows", body.get("count", 0) > 0, str(body.get("count")))

    resp2 = client.get("/api/electrical/path/P0455")
    check("GET /api/electrical/path/P0455 -> 200", resp2.status_code == 200,
          str(resp2.status_code))

    resp3 = client.get(f"/api/vehicles/{VIN}/electrical/inspections")
    check("GET .../electrical/inspections -> 200", resp3.status_code == 200,
          str(resp3.status_code))
except Exception as exc:  # noqa: BLE001
    check("API checks ran without raising", False, repr(exc))

print()
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
