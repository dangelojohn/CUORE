"""Checks for MIL diagnostics: the newest MES clear being recognised, and
the ECM-commanded-MIL-vs-dash-lamp finding on Bench/Report.

Same posture as ``cuore/tests/check_marque_port.py``/``check_tests_page.py``:
``CUORE_STATE_DIR`` and ``MES_LOG_DIR`` are both pointed at throwaway
directories BEFORE ``cuore`` (and therefore ``mes``) is imported, so this
test is self-contained -- it never touches the real MultiEcuScan install or
the real ``C:\\ProgramData\\cuore`` state, and does not depend on either
being present on the machine it runs on.

The MES-log fixture reproduces the real 2026-10-08 scenario byte-for-byte:
``SCAN_2610080920.txt`` and ``SCAN_2610080926.txt`` are copied verbatim (read
-only) from the real MultiEcuScan install when present, else from a baked-in
copy of the same text below (so this check still runs on a machine without
that install). A synthetic ``FESLog_2610041116...txt`` with no DTCs, dated
2026-10-04 -- *older* than the SCAN clear -- reproduces the exact condition
that made the old clear-assessment logic miss it: the newest FES engineering
session on file predates the newest clear, which was SCAN-only.

The from-car and owner-attested fixtures are narrower slices of the same two
real stores: the 2026-10-13 lines of the real ``observations.jsonl`` (MIL
commanded on, read 20:03) when that file exists, else a baked-in equivalent
line, and one ``incidents/warning_light_seen`` owner event written through
the real ``cuore.live.owner_events`` store API into this test's own
throwaway state dir (never the production one).

Four groups of checks:
  1. ``mes.workup.build()``'s ``clear_assessment`` picks the 2026-10-08
     09:20 SCAN clear (not the 2026-09-29/stale-FES-anchor date) and names
     the four DTCs it cleared.
  2. The MIL block (``cuore.services.dossier_bridge``'s new MIL section)
     carries both statements -- the ECM's and the owner's -- detects the
     mismatch, and offers the three ordered, hedged explanations, each
     paired with the mechanic_tests key that settles it. Its own text never
     uses the bare word "cause" or "proven".
  3. The three new ``mes.mechanic_tests`` entries
     (``mil_bulb_check``/``mil_request_vs_lamp``/``ipc_mil_status_read``)
     exist with a valid schema (real ``systems`` keys, allowed
     ``pass_criteria`` confidence, no numeric spec paired with UNKNOWN).
  4. Bench (``/v/{vin}``) and Report (``/v/{vin}/report``) both render 200
     and show the MIL block.

Run:
    .venv/Scripts/python.exe cuore/tests/check_mil.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-mil-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real VIN this whole feature was built against

# ===========================================================================
# MES-log fixture: SCAN_2610080920/26 copied verbatim, plus a synthetic
# older FES session that reproduces the stale-anchor bug.
# ===========================================================================

_REAL_MES_DIR = Path(r"C:\Program Files (x86)\MultiEcuScan")
_LOG_DIR = Path(tempfile.mkdtemp(prefix="cuore-check-mil-logs-"))
os.environ["MES_LOG_DIR"] = str(_LOG_DIR)

# Baked-in fallback text (byte-identical in substance to the real files)
# for a machine that does not have the real MultiEcuScan install -- the
# real files are preferred when present, never modified either way.
_FALLBACK_SCAN_920 = """Scan vehicle for available modules and check each module for errors...

Engine / ECM
Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)
ISO Code: 00 01 50 40 18
VIN code: ZASFAKPN5J7B88115
Hardware number: MM10JAHW232 - Ver: 00
Software number: P235QB39 - Ver: 0000
Errors found:
P0456-00 - Evaporation system leak
P0455-00 - Evaporation system leak

Body / RFHUB (Radio Frequency Hub Module)
Radio frequency hub (RFHUB) Continental
ISO Code: 00 41 50 89 15
VIN code: ZASFAKPN5J7B88115
Hardware number: 10161500AA - Ver: 01
Software number: 10307064AB - Ver: 0940
Errors found:
B1040-64 - Communication with Body Computer (BCM/NBC) - Signal/message plausibility

Other / DASM (Driver Assistant System Module)
Driver assistant system module (DASM) radar Bosch
ISO Code: 00 39 70 7E 15
VIN code: ZASFAKPN5J7B88115
Hardware number: MRR1evo14F - Ver: 00
Software number: 52081920 - Ver: 0500
Errors found:
C141B-97 - Camera blinded/obstructed/blocked - Component or system operation obstructed or blocked


CLEARING STORED FAULT CODES...

Engine / ECM
Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)
ISO Code: 00 01 50 40 18
************************************************************
VEHICLE SCAN REPORT
************************************************************
Scanning ...

Engine / ECM
Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)
ISO Code: 00 01 50 40 18
VIN code: ZASFAKPN5J7B88115
Hardware number: MM10JAHW232 - Ver: 00
Software number: P235QB39 - Ver: 0000
Errors found:
P0456-00 - Evaporation system leak
P0455-00 - Evaporation system leak

Body / RFHUB (Radio Frequency Hub Module)
Radio frequency hub (RFHUB) Continental
ISO Code: 00 41 50 89 15
VIN code: ZASFAKPN5J7B88115
Hardware number: 10161500AA - Ver: 01
Software number: 10307064AB - Ver: 0940
Errors found:
B1040-64 - Communication with Body Computer (BCM/NBC) - Signal/message plausibility

Other / DASM (Driver Assistant System Module)
Driver assistant system module (DASM) radar Bosch
ISO Code: 00 39 70 7E 15
VIN code: ZASFAKPN5J7B88115
Hardware number: MRR1evo14F - Ver: 00
Software number: 52081920 - Ver: 0500
Errors found:
C141B-97 - Camera blinded/obstructed/blocked - Component or system operation obstructed or blocked

COMPLETED
VEHICLE MAKE: 07
VEHICLE MODEL:
VEHICLE YEAR:

SENDING DIAGNOSTIC REPORT ...




CLEARING STORED FAULT CODES

Engine / ECM
Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)
ISO Code: 00 01 50 40 18

SUCCESS

Body / RFHUB (Radio Frequency Hub Module)
Radio frequency hub (RFHUB) Continental
ISO Code: 00 41 50 89 15
SUCCESS

Other / DASM (Driver Assistant System Module)
Driver assistant system module (DASM) radar Bosch
ISO Code: 00 39 70 7E 15
SUCCESS
"""

_FALLBACK_SCAN_926 = """Scan vehicle for available modules and check each module for errors...

Engine / ECM
Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)
ISO Code: 00 01 50 40 18
VIN code: ZASFAKPN5J7B88115
Hardware number: MM10JAHW232 - Ver: 00
Software number: P235QB39 - Ver: 0000

Body / RFHUB (Radio Frequency Hub Module)
Radio frequency hub (RFHUB) Continental
ISO Code: 00 41 50 89 15
VIN code: ZASFAKPN5J7B88115
Hardware number: 10161500AA - Ver: 01
Software number: 10307064AB - Ver: 0940

Other / DASM (Driver Assistant System Module)
Driver assistant system module (DASM) radar Bosch
ISO Code: 00 39 70 7E 15
VIN code: ZASFAKPN5J7B88115
Hardware number: MRR1evo14F - Ver: 00
Software number: 52081920 - Ver: 0500

COMPLETED
VEHICLE MAKE: 07
VEHICLE MODEL:
VEHICLE YEAR:
"""


def _place_scan(name: str) -> None:
    real = _REAL_MES_DIR / name
    dest = _LOG_DIR / name
    if real.exists():
        shutil.copyfile(real, dest)  # read-only copy; the real file is never touched
    else:
        text = _FALLBACK_SCAN_920 if "920" in name else _FALLBACK_SCAN_926
        dest.write_text(text, encoding="utf-8")


_place_scan("SCAN_2610080920.txt")
_place_scan("SCAN_2610080926.txt")

# Synthetic -- NOT a copy of a real file -- reproducing the stale-anchor
# condition: the newest FES engineering session on file (2026-10-04 11:16)
# predates the newest clear (2026-10-08 09:20, SCAN-only, no FES session
# ever follows it in this corpus).
(_LOG_DIR / "FESLog_2610041116_Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir.txt").write_text(
    "(Multiecuscan 5.4)\n"
    "10/4/2026 11:16:37 AM\n"
    "Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir\n"
    "Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)\n"
    "--------------------------------------------------------------\n"
    "\n"
    "ECU ISO code: 00 01 50 40 18\n"
    f"VIN code: {VIN}\n"
    "ECU serial number: TD4192427B17540\n"
    "Spare part number: 50544870\n"
    "Hardware number: MM10JAHW232\n"
    "Hardware version: 00\n"
    "Software number: P235QB39\n"
    "Software version: 0000\n"
    "\n"
    "READING ERROR CODES:\n"
    "No fault codes\n",
    encoding="utf-8",
)

# ===========================================================================
# From-car + owner-attested fixtures
# ===========================================================================

_REAL_OBSERVATIONS = Path(r"C:\ProgramData\cuore\observations.jsonl")
_FALLBACK_READINESS = (
    '{"at": "2026-10-13T20:03:00", "kind": "readiness", "vin": "' + VIN + '", '
    '"bus": "can_c", "cable": "none", "stream": "serial COM3@115200", '
    '"data": {"since_clear": {"mil_on": true, "stored_dtc_count": 1, '
    '"monitors": [], "all_complete": true}}}'
)
if _REAL_OBSERVATIONS.exists():
    _fixture_lines = [ln for ln in
                      _REAL_OBSERVATIONS.read_text(encoding="utf-8").splitlines()
                      if '"2026-10-13' in ln]
else:
    _fixture_lines = [_FALLBACK_READINESS]
if _fixture_lines:
    (Path(os.environ["CUORE_STATE_DIR"]) / "observations.jsonl").write_text(
        "\n".join(_fixture_lines) + "\n", encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import owner_events as owner_events_store  # noqa: E402
from cuore.services import dossier_bridge  # noqa: E402

from mes import mechanic_tests, workup  # noqa: E402

# The owner's attested statement, filed through the real store API (never
# its files directly) into this test's own throwaway state dir.
owner_events_store.add(
    VIN, "incidents", "warning_light_seen",
    at="2026-10-14",
    by_role="owner",
    fields={"which": "Check engine / MIL",
           "how_long": "not seen since clear 2026-10-08"},
    fields_meta={"which": "typed", "how_long": "typed"},
    note="Owner attests the dash MIL has not lit since the 2026-10-08 09:20 MES clear.",
)

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


_NO_CAUSE = re.compile(r"\bcause\b", re.IGNORECASE)
_NO_PROVEN = re.compile(r"\bproven\b", re.IGNORECASE)


def _hedge_clean(label: str, text: str) -> None:
    check(f"{label}: never states the bare word 'cause'", not _NO_CAUSE.search(text or ""),
         repr(text))
    check(f"{label}: never states the bare word 'proven'", not _NO_PROVEN.search(text or ""),
         repr(text))


# ===========================================================================
# 1. clear assessment picks the newest (2026-10-08 09:20) clear
# ===========================================================================

print("=== clear assessment ===")
dossier = workup.build(vin=VIN)
ca = (dossier.get("current_picture") or {}).get("clear_assessment") or {}
check("clear assessment picks the 2026-10-08 09:20 SCAN clear, not a stale FES anchor",
     ca.get("cleared_at") == "2026-10-08 09:20:00", str(ca.get("cleared_at")))
check("clear assessment names the clearing scan as its source",
     ca.get("source") == "SCAN_2610080920.txt", str(ca.get("source")))
check("all four pre-clear codes are recorded as cleared",
     set(ca.get("codes_cleared") or []) == {"B1040-64", "C141B-97", "P0455-00", "P0456-00"},
     str(ca.get("codes_cleared")))
check("the clean re-scan six minutes later is recognised (re_read_after_clear)",
     ca.get("re_read_after_clear") is True, str(ca.get("re_read_after_clear")))
check("no module is left wrongly refused (the ECM's own blank second clear-result line "
     "is resolved from evidence, not read as a refusal)",
     not (ca.get("modules_refused") or {}), str(ca.get("modules_refused")))

# ===========================================================================
# 2. the MIL block
# ===========================================================================

print("=== MIL block ===")
view = dossier_bridge.build_view(VIN, dossier, None)
mil = (view.get("verdict") or {}).get("mil")
check("MIL block is present", mil is not None)

if mil:
    check("ECM line states the MIL commanded on, since the first from-car read",
         "MIL commanded ON since" in mil["ecm_line"], mil["ecm_line"])
    check("ECM line carries the 34 km distance read from the car",
         "34" in mil["ecm_line"] and "km with MIL" in mil["ecm_line"], mil["ecm_line"])
    check("dash line carries the owner's attested statement verbatim",
         "not seen since clear 2026-10-08" in mil["dash_line"], mil["dash_line"])
    check("dash line shows it is attested, not measured",
         "attested" in mil["dash_line"], mil["dash_line"])
    check("mismatch between the ECM's request and the dash lamp is detected",
         mil["mismatch"] is True)

    exps = mil.get("explanations") or []
    check("exactly three explanations, in order", len(exps) == 3, str(len(exps)))
    if len(exps) == 3:
        check("explanation 1: cluster/bus path, settled by mil_request_vs_lamp "
             "+ ipc_mil_status_read",
             "cluster did not receive or show the request" in exps[0]["text"]
             and set(exps[0]["tests"]) == {"mil_request_vs_lamp", "ipc_mil_status_read"},
             str(exps[0]))
        check("explanation 2: lamp/bulb-check failure, settled by mil_bulb_check",
             exps[1]["text"] == "lamp/bulb-check failure"
             and exps[1]["tests"] == ["mil_bulb_check"],
             str(exps[1]))
        check("explanation 3: owner did not notice, no test claimed to settle it",
             exps[2]["text"] == "owner did not notice" and exps[2]["tests"] == [],
             str(exps[2]))
        check("never states which explanation is right (no explanation is marked true/"
             "confirmed/selected)",
             all("tests" in e and "text" in e and len(e) == 2 for e in exps), str(exps))

    for field in ("ecm_line", "dash_line", "next_action_note"):
        _hedge_clean(f"mil.{field}", mil.get(field) or "")
    for i, e in enumerate(exps):
        _hedge_clean(f"mil.explanations[{i}]", e.get("text") or "")

    check("verdict.next_action mentions the mismatch, hedged ('consistent with', "
         "never asserted)",
         mil.get("next_action_note") and "consistent with" in mil["next_action_note"],
         str(mil.get("next_action_note")))
    _hedge_clean("verdict.next_action", view["verdict"].get("next_action") or "")

# ===========================================================================
# 3. the three new mechanic_tests entries
# ===========================================================================

print("=== mechanic_tests catalogue ===")
_MIL_TEST_IDS = ("mil_bulb_check", "mil_request_vs_lamp", "ipc_mil_status_read")
for tid in _MIL_TEST_IDS:
    t = mechanic_tests.test(tid)
    check(f"{tid} exists in the catalogue", t is not None)
    if t is None:
        continue
    bad_sys = [s for s in t["systems"] if s not in mechanic_tests.SYSTEMS]
    check(f"{tid}: every systems entry is a real SYSTEMS key", not bad_sys, str(bad_sys))
    bad_conf = [pc["confidence"] for pc in t["pass_criteria"]
               if pc["confidence"] not in mechanic_tests.CONFIDENCE_LEVELS]
    check(f"{tid}: every pass_criteria confidence is allowed", not bad_conf, str(bad_conf))
    numeric_unknown = [pc["parameter"] for pc in t["pass_criteria"]
                      if pc["confidence"] == mechanic_tests.UNKNOWN
                      and isinstance(pc["spec"], (int, float))]
    check(f"{tid}: no pass_criteria pairs a numeric spec with UNKNOWN confidence",
         not numeric_unknown, str(numeric_unknown))
    _hedge_clean(f"mechanic_tests.{tid}.fail_means", t.get("fail_means") or "")

ipc_test = mechanic_tests.test("ipc_mil_status_read")
check("ipc_mil_status_read is honest that no IPC DID is catalogued (UNKNOWN, not polled)",
     ipc_test is not None
     and any(pc["confidence"] == mechanic_tests.UNKNOWN and "UNKNOWN DID" in str(pc["spec"])
            for pc in ipc_test["pass_criteria"]),
     str(ipc_test["pass_criteria"]) if ipc_test else "missing")

# ===========================================================================
# 4. Bench and Report render the MIL block
# ===========================================================================

print("=== Bench / Report pages ===")
client = TestClient(create_app())

bench_resp = client.get(f"/v/{VIN}")
check("bench page responds 200", bench_resp.status_code == 200, str(bench_resp.status_code))
if bench_resp.status_code == 200:
    body = bench_resp.text
    check("bench shows the ECM MIL-commanded line", "MIL commanded ON since" in body)
    check("bench shows the owner's dash-lamp statement",
         "not seen since clear 2026-10-08" in body)
    check("bench shows all three explanations",
         all(s in body for s in (
             "cluster did not receive or show the request",
             "lamp/bulb-check failure", "owner did not notice")))
    _hedge_clean("bench MIL block", body[body.find("bench-mil"):body.find("bench-mil") + 4000]
                if "bench-mil" in body else "")

report_resp = client.get(f"/v/{VIN}/report")
check("report page responds 200", report_resp.status_code == 200, str(report_resp.status_code))
if report_resp.status_code == 200:
    body = report_resp.text
    check("report shows the ECM MIL-commanded line", "MIL commanded ON since" in body)
    check("report shows the owner's dash-lamp statement",
         "not seen since clear 2026-10-08" in body)
    check("report shows all three explanations",
         all(s in body for s in (
             "cluster did not receive or show the request",
             "lamp/bulb-check failure", "owner did not notice")))

print(f"\n{checks} checks, {len(failures)} failures")
if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
sys.exit(0)
