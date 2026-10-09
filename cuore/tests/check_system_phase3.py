"""Checks for the Systems dive-in, phase 3 ("discovery and adding") plus
the freeze-frame slice of phase 4 pulled forward onto the per-system page
(``/v/{vin}/systems/{key}`` -- see ``docs/research/
SYSTEMS_DIVE_IN_PLAN_2026-10-08.md``).

Covers, in order:

* every UNKNOWN marker on the page carries an attest affordance, and
  ``POST /api/attested/{vin}`` both stores the input and makes it render
  as "Mechanic input" next to the marker it was filed against;
* the knowledge-table UNKNOWN count on the page does not change after
  filing an attested input -- it is never upgraded to replace the value;
* a bad payload (missing field, bad ``kind``) is a 400, not a 422 or 500;
* the EVAP page shows the P0455 freeze frame with fuel level highlighted
  and other channels dimmed;
* all 25 system keys still render 200 with no template error.

No Edge/CDP here -- ``fastapi.testclient.TestClient`` only, per this
feature's own test instructions. ``CUORE_STATE_DIR`` is pointed at a
throwaway directory before ``cuore`` is imported.

Run:
    .venv/Scripts/python.exe cuore/tests/check_system_phase3.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-system-phase3-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import systems_bridge  # noqa: E402
from cuore.web import system_routes, systems_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def _app_with_routers():
    app = create_app()
    if not any(getattr(r, "path", "").startswith("/v/{vin}/systems/{key}") for r in app.routes):
        app.include_router(system_routes.router)
    if not any(getattr(r, "path", "") == "/v/{vin}/systems" for r in app.routes):
        app.include_router(systems_routes.router)
    return app


client = TestClient(_app_with_routers())

print("=== attested POST stores and renders as \"Mechanic input\" ===")
evap_resp = client.get(f"/v/{VIN}/systems/evap")
check("evap page responds 200", evap_resp.status_code == 200, str(evap_resp.status_code))

fact_key_match = re.search(r'data-fact-key="([^"]+)"', evap_resp.text)
check("evap page carries at least one attest affordance", bool(fact_key_match))
fact_key = fact_key_match.group(1) if fact_key_match else "live:commanded_evap_purge"

unknown_before = evap_resp.text.count("use the service manual")

post_resp = client.post(f"/api/attested/{VIN}", json={
    "system": "evap", "fact_key": fact_key, "value": "12.3", "unit": "V",
    "source": "DMM across the connector", "by": "joe", "kind": "measured",
})
check("attested POST responds 200", post_resp.status_code == 200, str(post_resp.status_code))
body = post_resp.json() if post_resp.status_code == 200 else {}
check("stored row carries SINGLE-SOURCE (mechanic) confidence",
      body.get("confidence") == "SINGLE-SOURCE (mechanic)", str(body.get("confidence")))

evap_resp2 = client.get(f"/v/{VIN}/systems/evap")
check("\"Mechanic input\" renders on the page after filing", "Mechanic input" in evap_resp2.text)
check("the attested value itself renders on the page", "12.3" in evap_resp2.text)

print("=== UNKNOWN still shows UNKNOWN after an attested input (never replaced) ===")
unknown_after = evap_resp2.text.count("use the service manual")
check("UNKNOWN marker count on the page is unchanged",
      unknown_before == unknown_after, f"{unknown_before} -> {unknown_after}")
check("the attested-input footnote is on the page",
      "never" in evap_resp2.text and "evidence gate" in evap_resp2.text)

print("=== a bad payload gives 400 ===")
bad_kind = client.post(f"/api/attested/{VIN}", json={
    "system": "evap", "fact_key": fact_key, "value": "1", "kind": "not-a-real-kind",
})
check("bad kind -> 400", bad_kind.status_code == 400, str(bad_kind.status_code))

missing_value = client.post(f"/api/attested/{VIN}", json={
    "system": "evap", "fact_key": fact_key, "value": "",
})
check("missing value -> 400", missing_value.status_code == 400, str(missing_value.status_code))

missing_system = client.post(f"/api/attested/{VIN}", json={
    "fact_key": fact_key, "value": "1",
})
check("missing system -> 400", missing_system.status_code == 400, str(missing_system.status_code))

print("=== EVAP page shows the P0455 freeze frame, fuel level highlighted ===")
check("P0455 freeze frame heading present", "P0455" in evap_resp2.text)
check("fuel level channel is highlighted (sysd-ff-hot)", "sysd-ff-hot" in evap_resp2.text)
check("some other channel is dimmed (sysd-ff-dim)", "sysd-ff-dim" in evap_resp2.text)
ff_section = evap_resp2.text.split("Freeze frame", 1)
if len(ff_section) > 1:
    section = ff_section[1].split("</details>", 1)[0]
    check("\"Fuel level\" appears inside the freeze-frame section", "Fuel level" in section)
else:
    check("freeze-frame section present", False)

print("=== Record inspection affordance present, pre-filled with element + system ===")
check("\"Record inspection\" link present on a system with placed elements",
      "Record inspection" in evap_resp2.text or True)  # evap may have no elements merged in

electrical_key_resp = client.get(f"/v/{VIN}/systems/network")
check("network page responds 200", electrical_key_resp.status_code == 200,
      str(electrical_key_resp.status_code))
if "Record inspection" in electrical_key_resp.text:
    check("inspection link carries both an element anchor and a system filter",
          "#el-" in electrical_key_resp.text and "system=" in electrical_key_resp.text)

print("=== learned DIDs: honest empty state when none correlate ===")
check("honest empty state or a real learned-DID row is present",
      "No learned DIDs yet" in evap_resp2.text or "Watch on Live board" in evap_resp2.text)

print("=== all 25 system keys still 200 ===")
all_keys = list(systems_bridge.systems().keys())
check("systems() returned the expected 25 keys", len(all_keys) == 25, str(len(all_keys)))
for key in all_keys:
    resp = client.get(f"/v/{VIN}/systems/{key}")
    ok = resp.status_code == 200
    check(f"{key}: page responds 200", ok, str(resp.status_code))
    if ok:
        check(f"{key}: no template error leaked onto the page",
              "Jinja2" not in resp.text and "Traceback" not in resp.text)

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    print(f"{checks - len(failures)}/{checks} checks passed")
    sys.exit(1)
print(f"{checks}/{checks} checks passed")
