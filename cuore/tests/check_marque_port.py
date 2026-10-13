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
     + vehicle bar only, not the full page): ``mes.known_good``'s reference
     bands are a single always-the-same, confidence-labelled knowledge base
     (see its own docstring -- "Nothing here invents a number") shown
     identically regardless of marque, e.g. the idle-RPM band's "notes"
     cites a real stelvioforum.com thread. That is sourced Alfa case-sample
     material (MARQUE_PORT_AUDIT_2026-10-13.md classifies it (b), not a
     drift bug) -- rebuilding an equivalent Maserati/Ferrari-sourced
     knowledge base is out of this pass's scope, and inventing one would
     violate the "never invented" experience-links rule. Flagged as a
     follow-up in the audit doc, not fixed here.

Run:
    .venv/Scripts/python.exe cuore/tests/check_marque_port.py
"""

from __future__ import annotations

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
    else:
        check(f"{label} page has no literal \"Stelvio\" text", "Stelvio" not in text)
        check(f"{label} page has no literal \"Alfa\" text", "Alfa" not in text)


# --- report ------------------------------------------------------------------

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
