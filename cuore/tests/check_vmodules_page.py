"""Smoke checks for the module-tree pages: ``/v/{vin}/modules`` and
``/v/{vin}/modules/{code}``.

Same posture as ``cuore/tests/check_dossier_view.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE cuore is imported, so nothing here
touches the bench's real state. The MES log corpus is NOT overridden --
VIN ZASFAKPN5J7B88115's real corpus (chronic EVAP trio, incl. P0440) is the
fixture, same as every other dossier test in this suite.

``cuore.app.create_app`` may not yet wire ``cuore.web.modules_routes``
(another agent owns that edit to ``app.py``) -- this file includes it
itself, defensively, so it is self-sufficient today and a harmless no-op
once ``app.py`` is updated.

Run:
    .venv/Scripts/python.exe cuore/tests/check_vmodules_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-vmodules-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import modules_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, EVAP trio incl. P0440

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


app = create_app()
existing_paths = {getattr(r, "path", None) for r in app.routes}
if "/v/{vin}/modules" not in existing_paths:
    app.include_router(modules_routes.router)

client = TestClient(app)


# --- 1. modules page 200s and lists ECM and BCM with identity -------------

r = client.get(f"/v/{VIN}/modules")
check("modules page 200", r.status_code == 200, f"got {r.status_code}")
body = r.text
check("modules page lists ECM", "ECM" in body)
check("modules page lists BCM", "BCM" in body)

from cuore.services import modules_bridge  # noqa: E402

rows = modules_bridge.list_modules(VIN)
check("list_modules returns rows", len(rows) > 0)
by_code = {m["code"]: m for m in rows}
check("ECM present in list_modules", "ECM" in by_code)
if "ECM" in by_code:
    ecm = by_code["ECM"]
    check("ECM has identity dict", isinstance(ecm.get("identity"), dict))
    check("ECM identity has hardware or software or iso",
          any(ecm["identity"].get(k) for k in ("hardware", "software", "iso")),
          str(ecm["identity"]))


# --- 2. ECM detail shows P0440 under errors with a status chip -----------

r = client.get(f"/v/{VIN}/modules/ECM")
check("ECM detail page 200", r.status_code == 200, f"got {r.status_code}")
detail_body = r.text
check("ECM detail shows P0440", "P0440" in detail_body)
check("ECM detail shows a status chip for P0440",
      any(cls in detail_body for cls in
          ("status-active", "status-cleared_unverified", "status-stale")))

detail = modules_bridge.module_detail(VIN, "ECM")
check("module_detail has errors_detail", len(detail.get("errors_detail") or []) > 0)
check("module_detail errors_detail has P0440",
      any("P0440" in (e.get("dtc") or "") for e in detail.get("errors_detail") or []))


# --- 3. parameters tab lists >= 5 channels --------------------------------

check("ECM parameters tab lists >= 5 channels",
      len(detail.get("parameters") or []) >= 5,
      f"got {len(detail.get('parameters') or [])}")


# --- 4. actuators tab shows a consent phrase and blocks TCM/ABS ----------
# Blocking is a property of the module code itself (``_blocked``), not of
# whether this particular VIN happens to have scanned it -- checked at that
# level so the assertion holds regardless of this corpus's own module mix.

tcm_blocked, tcm_reason = modules_bridge._blocked("TCM")
check("TCM is blocked", tcm_blocked is True, tcm_reason)
abs_blocked, abs_reason = modules_bridge._blocked("ABS")
check("ABS is blocked", abs_blocked is True, abs_reason)

# And wherever a module IS known to this vehicle, the page surfaces it too.
known_blocked = [m for m in rows if m["code"] in ("TCM", "ABS", "ESM", "DTCM", "RFHUB",
                                                   "EPS", "ORC", "HALF", "DASM")]
for m in known_blocked:
    check(f"{m['code']} marked blocked on the module list", m["actuators"]["blocked"] is True)
    r_detail = client.get(f"/v/{VIN}/modules/{m['code']}")
    check(f"{m['code']} detail page 200", r_detail.status_code == 200)
    check(f"{m['code']} detail page shows blocked reason",
          "safety-critical" in r_detail.text or "CAN-CH" in r_detail.text)
if not known_blocked:
    print("note: no CAN-CH / blocked module is in this VIN's own corpus; "
          "blocking is still verified directly via _blocked() above")

# A consent phrase is only printed when this VIN has a learned actuator for
# some module; check the format is right wherever one exists, on any module.
any_consent = False
for m in rows:
    d = modules_bridge.module_detail(VIN, m["code"])
    for a in d.get("actuators_detail") or []:
        any_consent = True
        check(f"{m['code']} actuator has a consent phrase",
              bool(a.get("consent_phrase")) and a["consent_phrase"].split()[0]
              in ("ACTUATE", "RUN"))
if not any_consent:
    print("note: no learned actuators exist for this VIN in this corpus -- "
          "consent-phrase format is exercised structurally via "
          "actuate.consent_phrase() instead")
    phrase = modules_routes.modules_bridge.actuate.consent_phrase("ECM", "Test Actuator")
    check("consent_phrase format", phrase == "ACTUATE ECM TEST ACTUATOR", phrase)


# --- 5. unknown module -> 404 ---------------------------------------------

r = client.get(f"/v/{VIN}/modules/ZZZNOTAMODULE")
check("unknown module code -> 404", r.status_code == 404, f"got {r.status_code}")


# --- summary ---------------------------------------------------------------

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
if failures:
    sys.exit(1)
print("OK")
