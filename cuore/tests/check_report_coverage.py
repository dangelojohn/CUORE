"""Coverage check for the owner's own question: does the Report page
(``cuore/web/report_routes.py`` -> ``templates/report.html``) carry a
description, a failure type, a fault-tree next step and an explicit parts
line -- real or ``UNKNOWN``, never silently omitted -- for *every* live
code on this car right now, P-codes and module (U/B) codes alike.

Same posture as the other ``check_*.py`` scripts: plain script, ``check()``,
exit 1 on failure, no pytest, no subagents, never opens COM3.
``CUORE_STATE_DIR`` is pointed at a fresh temp directory BEFORE cuore is
imported, seeded only with the 2026-10-13 lines copied from
``C:\\ProgramData\\cuore\\observations.jsonl`` (that real file is read, never
written) so this car's own UDS 0x19 module sweep from that night -- the one
that found U1736 and B10AA, which no FES log on file ever logged -- is
present. The P-code (EVAP) history comes from the real MES-log corpus on
this machine directly, same fixture ``check_report.py`` already relies on.

Run:
    .venv/Scripts/python.exe cuore/tests/check_report_coverage.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_TMP = tempfile.mkdtemp(prefix="cuore-check-report-coverage-")
os.environ["CUORE_STATE_DIR"] = _TMP

_REAL_OBS = Path(r"C:\ProgramData\cuore\observations.jsonl")
if _REAL_OBS.exists():
    lines = [ln for ln in _REAL_OBS.read_text(encoding="utf-8").splitlines()
             if ln.startswith('{"at": "2026-10-13')]
    text = "\n".join(lines) + ("\n" if lines else "")
    Path(_TMP, "observations.jsonl").write_text(text, encoding="utf-8")

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mes-log-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import report_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio

# Every live code on this car right now, per the owner's own question:
# ECM EVAP family, then the BCM/IPC/RFHUB module sweep from 2026-10-13.
LIVE_CODES = ["P0440", "P0455", "P0456",
              "U1713", "U1736", "U1765",
              "B1176", "B10AA", "B1040"]

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: object = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + str(detail)) if detail != '' else ''}")


client = TestClient(create_app())

resp = client.get(f"/v/{VIN}/report")
check("report page renders", resp.status_code == 200, resp.status_code)
body = resp.text if resp.status_code == 200 else ""

ctx = report_routes._report_context(VIN)
all_codes = report_routes._all_report_codes(ctx["view"])

for code in LIVE_CODES:
    check(f"{code}: this fixture (real MES-log corpus + the seeded "
         "2026-10-13 live sweep) actually carries it -- a failure here "
         "means the fixture is stale, not the report", code in all_codes,
         sorted(all_codes))

# (a)/(b)/(c): every live code either rides an open-work card (its own
# hand-curated/generic family, same machinery a P-code already uses) or
# earns report_routes' own fallback entry -- never silently dropped from
# "Possible fixes".
covered = report_routes._codes_covered_by_open_work(ctx["view"])
fallback_by_code = {f["code"]: f for f in ctx["fixes_fallback"]}

for code in LIVE_CODES:
    fb = fallback_by_code.get(code)
    check(f"{code}: appears on an open-work card or the fallback list "
         "(Possible fixes never silently drops a live code)",
         code in covered or fb is not None)

    if fb is not None:
        desc = fb.get("description") or {}
        check(f"{code}: (a) description text is present", bool((desc.get("text") or "").strip()), desc)
        ft = fb.get("failure_type") or {}
        check(f"{code}: (b) failure-type text is present", bool((ft.get("text") or "").strip()), ft)
        has_steps = bool(fb.get("steps"))
        is_honest_unknown = "UNKNOWN" in (desc.get("text", "") + ft.get("text", ""))
        check(f"{code}: (c) a fault-tree next step is present, or an "
             "explicit UNKNOWN (never silently empty)",
             has_steps or is_honest_unknown, fb)
    else:
        card = next((c for c in ctx["view"]["open_work"] if code in c.get("codes", [])), None)
        check(f"{code}: (a)/(b)/(c) its open-work card has a title and at least one step",
             bool(card) and bool(card.get("title")) and bool(card.get("steps")), card)

# Parts for the open codes: every live code gets a group -- real parts or
# an explicit `unknown` flag -- never omitted outright the way a silent
# `if rows:` skip used to drop every module code.
parts_by_code = {g["code"]: g for g in ctx["parts"]}
for code in LIVE_CODES:
    group = parts_by_code.get(code)
    check(f"{code}: appears in 'Parts for the open codes' (real parts or "
         "an explicit UNKNOWN, never omitted)", group is not None, sorted(parts_by_code))
    if group is not None:
        check(f"{code}: parts group carries real parts or is explicitly flagged unknown",
             bool(group.get("parts")) or group.get("unknown") is True, group)

# Cross-check against the rendered page itself -- not just the context dict
# this test built the assertions above from.
if resp.status_code == 200:
    for code in LIVE_CODES:
        check(f"{code}: the rendered /v/{{vin}}/report page text mentions it", code in body)
    check("rendered page carries an explicit UNKNOWN/TechAuthority line "
         "for at least one module code with no catalogued part",
         "UNKNOWN" in body and "TechAuthority" in body)

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
