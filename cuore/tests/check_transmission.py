"""Checks for the Transmission surface -- owner's request, 2026-10-14:
"I don't see any transmission development."

Covers:
  * the ``/v/{vin}/systems/transmission_driveline`` page's new "Transmission"
    section (identity/TCM software number, fill window, both empty states,
    both action buttons) -- see ``cuore/services/system_detail_bridge.py``'s
    ``_transmission_section`` and ``cuore/web/templates/_transmission.html``.
  * the phone home screen's "Transmission" quick-action tile and its route
    alias (``cuore/web/owner_routes.py``).
  * the renamed ``fluids/driveline_fluid`` kind label
    (``cuore/live/owner_events.py``).
  * the ATF/pan label still prints for a recorded driveline_fluid event.

``fastapi.testclient.TestClient`` only, no live hardware. ``CUORE_STATE_DIR``
is pointed at a throwaway directory before ``cuore`` is imported, same
posture as ``cuore/tests/check_system_page.py``/``check_drivetrain_page.py``.

Run:
    .venv/Scripts/python.exe cuore/tests/check_transmission.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-transmission-")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import system_routes, systems_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, this platform's own TCM
TEST_VIN = "TESTVIN0000TXPG1"  # owner-events round trip only -- no MES corpus entry (the
                               # system page 404s for a VIN like this, same as every other
                               # page that calls cuore.web.routes._dossier for an unknown VIN)

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

print("=== system page shows the Transmission section ===")
r = client.get(f"/v/{VIN}/systems/transmission_driveline")
check("transmission_driveline page responds 200", r.status_code == 200, str(r.status_code))
check("page shows the Transmission section heading", "Transmission</h2>" in r.text)
check("Transmission section renders before Relationships (first under the status strip)",
      r.text.index("Transmission</h2>") < r.text.index("Relationships</h2>"))
check("page shows the TCM software number", "GK0902OE2HN" in r.text)
check("page shows the TCM hardware number", "10344202761" in r.text)
check("page shows the TCM spare part number", "46337308" in r.text)
check("page mentions TSB 21-035-20", "21-035-20" in r.text)
check("page shows the dealer/wiTECH handoff status",
      "not checked" in r.text and "wiTECH" in r.text)
check("page shows the ZF 8HP fill window", "30-50" in r.text)
check("page shows both action buttons",
      "Record a transmission service" in r.text and "Print the ATF/pan label" in r.text)
check("record button links the phone form",
      f"/m/{VIN}/add/fluids/driveline_fluid" in r.text)
check("print button links the transmission_service label kind",
      f"/v/{VIN}/labels?kind=transmission_service" in r.text)

print("=== honest empty states for data this fresh CUORE_STATE_DIR has none of ===")
# CUORE_STATE_DIR is a throwaway tempdir (see top of file): no learned DIDs,
# no MES recording, and no drivetrain ledger entries have ever been written
# here, so the real VIN's own page already exercises every honest empty
# state -- no need for a second, data-less VIN (which 404s anyway: this
# VIN's MES log corpus is external to CUORE_STATE_DIR and a fictitious VIN
# has no corpus match at all, same "no logs match" 404 every other page
# that calls cuore.web.routes._dossier hits for an unknown VIN).
check("no learned DIDs yet for this system's channels",
      "No learned DIDs yet" in r.text)
check("no MES recording on file yet, with the MES handoff card",
      "No MES recording with a transmission channel on file yet" in r.text
      and "Record ATF temperature" in r.text and "gear in MES" in r.text)
check("'none yet' for all three drivetrain ledger entries",
      r.text.count("none yet") >= 3)

print("=== every other system page is unaffected (no Transmission section) ===")
r_evap = client.get(f"/v/{VIN}/systems/evap")
check("evap page responds 200", r_evap.status_code == 200)
check("evap page carries no Transmission section", "Transmission</h2>" not in r_evap.text)

print("=== mobile home shows the Transmission quick action and renamed kind ===")
r_home = client.get(f"/m/{VIN}")
check("mobile home responds 200", r_home.status_code == 200, str(r_home.status_code))
check("mobile home shows a Transmission quick-action tile", "Transmission" in r_home.text)
check("mobile home's Transmission tile links the route alias",
      f"/m/{VIN}/add/transmission" in r_home.text)

r_alias = client.get(f"/m/{VIN}/add/transmission", follow_redirects=False)
check("the route alias redirects", r_alias.status_code in (302, 303), str(r_alias.status_code))
check("the route alias redirects to the real driveline_fluid form",
      r_alias.headers.get("location", "") == f"/m/{VIN}/add/fluids/driveline_fluid")

r_alias_followed = client.get(f"/m/{VIN}/add/transmission")
check("following the alias lands on a 200 form page", r_alias_followed.status_code == 200,
      str(r_alias_followed.status_code))
check("the renamed kind label shows on the form",
      "Transmission / transfer case / differential oil" in r_alias_followed.text)

r_kinds = client.get(f"/m/{VIN}/add/fluids")
check("fluids kinds page responds 200", r_kinds.status_code == 200)
check("fluids kinds page shows the renamed driveline_fluid label",
      "Transmission / transfer case / differential oil" in r_kinds.text)

print("=== the ATF/pan label still prints for a recorded driveline_fluid event ===")
post = client.post(f"/m/{TEST_VIN}/add/fluids/driveline_fluid", data={
    "which": "transmission", "fluid_spec": "ZF LifeguardFluid 8", "brand": "ZF",
    "qty": "9.2", "pan_filter_part_no": "68XXXXXXAA", "fill_temp_c": "40",
    "method": "pan drop", "by_role": "mechanic", "by_name": "Tony",
    "odometer_km": "142300",
}, follow_redirects=False)
check("POST driveline_fluid responds with a redirect to the confirm screen",
      post.status_code == 303, str(post.status_code))
confirm = client.get(post.headers["location"])
check("confirm screen responds 200", confirm.status_code == 200)
print_href = None
for line in confirm.text.splitlines():
    if f"/m/{TEST_VIN}/labels/" in line:
        start = line.index(f"/m/{TEST_VIN}/labels/")
        print_href = line[start:].split('"')[0]
        break
check("confirm screen carries a Print label link", print_href is not None, confirm.text[:200])
if print_href:
    label_resp = client.get(print_href)
    check("the ATF/pan label PDF responds 200", label_resp.status_code == 200,
          str(label_resp.status_code))
    check("the ATF/pan label is a PDF",
          label_resp.headers.get("content-type", "").startswith("application/pdf"))


print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
