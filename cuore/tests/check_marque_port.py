"""Checks for the Alfa -> Maserati/Ferrari marque port (roadmap item 9;
see ``docs/research/MARQUE_PORT_AUDIT_2026-10-13.md`` for the full audit
this test backs).

No Edge, no real server: everything here runs against a plain
``TestClient`` (same posture as ``cuore/tests/check_screens.py``'s
TestClient-only checks), because the question is template/data wiring
(``data-marque``, which model name renders, whether Alfa's own copy leaked
onto another marque's car), not layout -- nothing here needs real browser
measurement.

The fixture vehicle is NOT the project's real Stelvio (``ZASFAKPN5J7B88115``,
used by every other ``check_*.py`` in this directory). It is a synthetic
Maserati VIN, ``ZN661XUA9JX000001`` (WMI ``ZN6`` -- Maserati North America;
see ``mes.platform.marque_for_vin`` and ``cuore.services.shop_bridge.
_WMI_MAKES``), with one synthetic clean FES log written into a throwaway
``MES_LOG_DIR`` so this test is fully self-contained -- it does not touch
the real MultiEcuScan install, and does not need the Stelvio's real corpus
to be present. The log has no DTCs, so no sibling-platform case-memory
cross-reference (``mes.experience``) has anything to surface for it; the
"no Stelvio/Alfa text" checks below are therefore a plain substring
search, not a case-memory-aware one -- there is nothing in this fixture's
own history for that carve-out to need to apply to.

Six checks:
  1. ``GET /start`` (before any VIN is chosen) responds 200 and its own
     copy is marque-neutral ("Start this car", not "Start this Stelvio" --
     MARQUE_PORT_AUDIT_2026-10-13.md item 1).
  2. ``POST /start`` with the Maserati VIN opens the visit + job and lands
     on that car's job page, 200.
  3. Each of Bench (``/v/{vin}``), Job (``/v/{vin}/job``), Systems
     (``/v/{vin}/systems``) and Tests (``/v/{vin}/tests``) responds 200.
  4. Each of those four pages carries ``data-marque="maserati"`` on
     ``<html>`` (base.html; computed by ``cuore.web.routes._marque_for``
     from ``mes.platform.marque_for_vin`` -- see the audit doc's item 1).
  5. Each of those four pages' vehicle name shows "Maserati" somewhere
     (the Bench/Job/Systems/Tests status line -- ``shop_bridge.
     resolve_vehicle_name`` / the dossier identity's own ``vehicle``
     field, both ultimately fed by this fixture's synthetic log).
  6. Bench, Job and Tests contain no literal "Stelvio"/"Alfa" text at all.
     Systems gets a narrower version of the same check (title + data-marque
     + vehicle bar only, not the full page) for "Stelvio"/"Alfa" prose --
     a system's own label/description text is not this check's concern.

  6b. (2026-10-14 fix) The Systems page's own *body* -- not just its title
     chrome -- now carries zero literal "stelvioforum" citations for the
     Maserati fixture: ``cuore/web/systems_routes.py``'s ``_live_channel_info``
     now passes ``vin`` through to ``known_good_bridge.known_good_for``/
     ``sourced_band``, the same gate the known-good API route already
     applies, so a Stelvio-forum-sourced row (e.g. ``engine_rpm``,
     ``engine_coolant_temp``) reached through a system's ``live_channels``
     never surfaces on another marque's Systems page.

  7. (2026-10-14 marque-port fix) The data layer itself IS now gated: the
     only two non-generic, Stelvio-forum-sourced rows ``mes.known_good``
     has (``engine_rpm``, ``engine_coolant_temp``) carry an ``applies_to``
     of ``("giorgio_gme_2.0t", "grecale_2.0t")`` (see that module's
     docstring), and ``known_good_bridge.known_good_payload``/
     ``bands_for_vin`` gate on it given a VIN. Checked directly against
     ``cuore.services.known_good_bridge`` and the ``GET /api/live/
     known-good?vin=...`` route (not the Systems page body, per item 6
     above) for the synthetic Maserati VIN: no "stelvioforum" citation
     anywhere in that payload, while the generic/UNKNOWN channels and the
     Stelvio VIN's own full set of bands are unaffected.

Run:
    .venv/Scripts/python.exe cuore/tests/check_marque_port.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-marque-")
os.environ.pop("CUORE_AUDIT_PATH", None)

# --- the synthetic Maserati fixture -----------------------------------------
#
# MES_LOG_DIR must be set, and the log file written, before `cuore` (and
# therefore `mes`) is imported -- mes.paths.configured_roots() reads the env
# var once, lazily, but nothing here relies on that laziness, so the order
# is kept strict and obvious. Pointing MES_LOG_DIR at a throwaway directory
# (rather than appending to the real install) means this test sees ONLY the
# Maserati fixture -- no real Stelvio data, no risk of the two corpora's
# vehicles getting merged or this test accidentally passing because of
# something the real corpus happened to contain.

VIN = "ZN661XUA9JX000001"  # Maserati North America WMI (ZN6); synthetic fixture

_LOG_DIR = Path(tempfile.mkdtemp(prefix="cuore-check-marque-logs-"))
_FES_LOG = _LOG_DIR / "FESLog_2610130900_Maserati Grecale.txt"
_FES_LOG.write_text(
    "(Multiecuscan 5.4)\n"
    "10/13/2026 9:00:00 AM\n"
    "Maserati Grecale\n"
    "Magneti Marelli 8HP Engine Control (2.0)\n"
    "--------------------------------------------------------------\n"
    "\n"
    "ECU ISO code: 00 01 50 40 18\n"
    f"VIN code: {VIN}\n"
    "ECU serial number: TESTFIXTURE00001\n"
    "Hardware number: TESTHW001\n"
    "Hardware version: 00\n"
    "Software number: TESTSW001\n"
    "Software version: 0000\n"
    "\n"
    "READING ERROR CODES:\n"
    "No fault codes\n",
    encoding="utf-8",
)
os.environ["MES_LOG_DIR"] = str(_LOG_DIR)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())


# --- 1. /start before any VIN is chosen: marque-neutral copy --------------

start_get = client.get("/start")
check("GET /start responds 200", start_get.status_code == 200, str(start_get.status_code))
check('GET /start reads "Start this car", not "...Stelvio"',
      "Start this car" in start_get.text and "Stelvio" not in start_get.text,
      "marque-neutral intake copy not found, or Stelvio text leaked in")


# --- 2. POST /start with the Maserati VIN opens the visit + job -----------

start_post = client.post(
    "/start",
    data={"vin": VIN, "complaint": "Pre-delivery inspection", "technician": "tester"},
    follow_redirects=True,
)
check("POST /start with the Maserati VIN responds 200 (after redirect)",
      start_post.status_code == 200, str(start_post.status_code))
check("POST /start lands on this VIN's job page",
      str(start_post.url).rstrip("/").endswith(f"/v/{VIN}/job"), str(start_post.url))


# --- 3-6. Bench / Job / Systems / Tests ------------------------------------

PAGES = {
    "bench": f"/v/{VIN}",
    "job": f"/v/{VIN}/job",
    "systems": f"/v/{VIN}/systems",
    "tests": f"/v/{VIN}/tests",
}

for label, url in PAGES.items():
    resp = client.get(url)
    check(f"{label} page ({url}) responds 200", resp.status_code == 200,
          str(resp.status_code))
    if resp.status_code != 200:
        continue
    text = resp.text
    check(f"{label} page carries data-marque=\"maserati\"",
          'data-marque="maserati"' in text,
          "data-marque attribute not found or not maserati")
    check(f"{label} page's vehicle name shows Maserati",
          "Maserati" in text, "no \"Maserati\" text found on the page")
    if label == "systems":
        # Narrower scope -- see check 6 in the module docstring: the
        # correlation knowledge body (mes.known_good) is a sourced Alfa
        # case sample shown unconditionally, out of scope for this pass.
        title_and_chrome = text.split("<body", 1)[0] + text[text.find('class="vbar"'):][:400]
        check("systems page's <title>/data-marque chrome has no "
              "literal \"Stelvio\" text", "Stelvio" not in title_and_chrome)
        check("systems page's <title>/data-marque chrome has no "
              "literal \"Alfa\" text", "Alfa" not in title_and_chrome)
        check("systems page's full body has zero \"stelvioforum\" citations "
              "(vin now threaded through known_good_bridge)",
              "stelvioforum" not in text.lower())
    else:
        check(f"{label} page has no literal \"Stelvio\" text", "Stelvio" not in text)
        # "AlfaCore" is the shop-system product name (Export panel), not the marque.
        check(f"{label} page has no literal \"Alfa\" text",
              "Alfa" not in text.replace("AlfaCore", ""))


# --- 7. known_good gating itself (2026-10-14 marque-port fix) -------------
#
# Not the Systems page body (item 6 above, out of scope) -- the bridge and
# its one HTTP surface, which this pass does own.

from cuore.services import known_good_bridge  # noqa: E402

payload = known_good_bridge.known_good_payload(vin=VIN)
check("known-good payload for the Maserati VIN carries no stelvioforum "
      "citation anywhere", "stelvioforum" not in json.dumps(payload))
check("known-good payload for the Maserati VIN drops the Stelvio-forum "
      "idle-RPM/coolant rows", "engine_rpm" not in payload["channels"]
      and "engine_coolant_temp" not in payload["channels"])
check("known-good payload for the Maserati VIN still has generic/UNKNOWN "
      "channels", "battery_voltage" in payload["channels"])

stelvio_payload = known_good_bridge.known_good_payload(vin="ZASFAKPN5J7B88115")
check("known-good payload for the real Stelvio VIN keeps its "
      "stelvioforum citations", "stelvioforum" in json.dumps(stelvio_payload))

api_resp = client.get(f"/api/live/known-good?vin={VIN}")
check("GET /api/live/known-good?vin=<Maserati VIN> responds 200",
      api_resp.status_code == 200, str(api_resp.status_code))
check("GET /api/live/known-good response for the Maserati VIN has no "
      "stelvioforum citation", "stelvioforum" not in api_resp.text)


# --- report ------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
