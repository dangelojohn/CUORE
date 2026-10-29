"""Checks for the wiTECH hand-off page (``/v/{vin}/handoff``). Read-only against the real job store: structure only.
Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_handoff_page.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


VIN = "ZASFAKPN5J7B88115"
client = TestClient(create_app())
r = client.get(f"/v/{VIN}/handoff")
check(r.status_code == 200, f"200 ({r.status_code})")
html = r.text
for h in ("Vehicle and job", "Codes now", "Evidence", "Hypotheses ranked", "Already done", "Needs wiTECH"):
    check(f"<h2>{h}</h2>" in html, f"heading {h}")
check("Prepared by CUORE before wiTECH; readings-only conclusions; outside sources labelled" in html, "footer text")
check("Generated 20" in html, "generation time")
body = html[html.find('<div class="ho"'):]
body = body[: body.find("ho-foot")]
check("<form" not in body, "no form")
check(len(re.findall(r"<script", body)) == 0, "no script in page section")
check(body.count("window.print()") == 1, "single print handler")
check("Back to job" in body and ">Print<" in body, "both buttons")
m = re.search(r'href="/v/[^"]+/job/([0-9a-f]+)"', body)
if m:
    r2 = client.get(f"/v/{VIN}/handoff?job={m.group(1)}")
    check(r2.status_code == 200 and "Needs wiTECH" in r2.text, "?job=<id> renders")
r3 = client.get(f"/v/{VIN}/handoff?job=doesnotexist")
check(r3.status_code == 200, "unknown job id still renders")
rj = client.get(f"/v/{VIN}/job")
check("/handoff" in rj.text, "job page links to hand-off")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
