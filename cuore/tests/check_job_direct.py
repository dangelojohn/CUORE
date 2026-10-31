"""Checks for the mechanic-first Job page: the call built from the job's blocker / next test, short hypothesis
titles with the long text in a "Full reasoning" fold, every authoring control under "Manage ledger", the once-only
stuck hint, readable system labels, "Step N of 12", Export at the bottom, and the page-only search.

Run:
    .venv/Scripts/python.exe cuore/tests/check_job_direct.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-jobdirect-")

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import job_direct as jd  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


# --- pure helpers (fixture job: one long research hypothesis, a fuel blocker) -----------------
LONG = ("PRIORITY 1 (top of this job). CLAIM: the network codes on the BCM and IPC (U1711, U1712) are one supply event. "
        + "Research detail. " * 200)
NT = "1) Free: ask the owner the open questions (battery work, jump start). 2) Multimeter: BCM supply voltage drop."
HYPS = [
    {"id": "h1", "text": LONG, "system": "network", "status": "open", "next_test": NT, "codes": ["U1711"],
     "evidence_for": [{"label": "U1700 freeze frame 10.6 V", "kind": "code"}], "evidence_against": []},
    {"id": "h2", "text": "PRIORITY 5 (LOW: owner-attested resolved, pending a confirming ABS read). OWNER STATEMENT x",
     "system": "brakes_abs", "status": "open", "next_test": "1) Read-only: ABS DTC read; save the log. 2) Optional: fluid.",
     "codes": [], "evidence_for": [], "evidence_against": []},
]
LABELS = {"network": "Network / CAN buses", "brakes_abs": "Brakes / ABS"}
VERDICT = {"blocker": "fuel out of window", "summary": "Cannot verify yet.", "basis": ["no readiness read since the clear"],
           "next_action": "Cannot verify yet: the EVAP monitor will not run above 85 % fuel (set at 93.725 %) (PID $2F)."}

t1 = jd.hyp_title(HYPS[0], LABELS)
check(len(t1) <= 120 and t1.startswith("The network codes on the BCM and IPC"), f"title from CLAIM: {t1!r}")
check("PRIORITY" not in t1 and "Research detail" not in t1, "title carries no research text")
t2 = jd.hyp_title(HYPS[1], LABELS)
check(t2.startswith("Brakes / ABS - owner-attested resolved"), f"title from priority note: {t2!r}")
check(jd.first_step(NT) == "Ask the owner the open questions (battery work, jump start).", "first step is the first numbered item")
check(jd.system_label("brakes_abs", LABELS) == "Brakes / ABS" and jd.system_label("some_key", {}) == "Some key",
      "raw system key becomes a label")

call = jd.build_call(VIN, VERDICT, HYPS, LABELS)
check(call["text"].startswith("Fuel 93.7 %: burn fuel into the 15-85 % window. Go to Bench fuel gate."), call["text"])
check(any(s["text"] == "Bench fuel gate" and s["href"] == f"/v/{VIN}" for s in call["segs"]), "blocker links to the Bench fuel gate")
check("Meanwhile" not in call["text"] and call["text"].endswith("Do it now") and len(call["text"]) <= 110
      and "..." not in call["text"] and any("Also next: " in w and "Ask the owner the open questions" in w for w in call["why"]),
      "blocker call is one short sentence; the test moves to 'Also next:' in Why this?")
check(call["next_href"] == f"/v/{VIN}/job?step=6&hypothesis=h1#hyp-h1", call["next_href"])
nb = jd.build_call(VIN, None, HYPS, LABELS)
check(nb["text"].startswith("Next test: ") and nb["text"].endswith("Do it now"), "no blocker: the call is the next test")
check(jd.build_call(VIN, None, [], LABELS)["text"].startswith("No test is waiting"), "no blocker and no hypotheses reads plainly")

s = jd.search("brake", VIN, HYPS, [{"code": "U0418", "description": "Error in communication with ABS module"}], [], LABELS)
check(s["hyp_ids"] == ["h2"], f"search finds the brake hypothesis: {s['hyp_ids']}")
check(any(r["kind"] == "Code" and r["ref"] == "U0418" for r in s["results"]), "search finds a code by its description")
check(jd.search("zzzz", VIN, HYPS, [], [], LABELS)["results"] == [], "no match gives no results")
check(jd.search("", VIN, HYPS, [], [], LABELS)["results"] == [], "empty query gives nothing")

# --- the rendered page, fixture job in a throwaway state dir -------------------------------------
# The page's verdict is built from the car's live dossier (MES logs, readiness), which changes as
# the car is worked on (a clear tonight made it "awaiting drive cycle"). Pin it to "no blocker" so
# the page checks read only this test's own throwaway job.
from cuore.services import dossier_bridge as _db  # noqa: E402
_real_build_view = _db.build_view
_db.build_view = lambda *a, **k: {**_real_build_view(*a, **k), "verdict": None}
client = TestClient(create_app())
client.post(f"/v/{VIN}/job/open", data={"technician": "t", "complaint": "check engine light"}, follow_redirects=True)
jid = re.search(r'/job/([0-9a-f]+)/', client.get(f"/v/{VIN}/job?step=7").text)
jid = jid.group(1) if jid else ""
check(bool(jid), "fixture job opened")
client.post(f"/v/{VIN}/job/{jid}/hypotheses", follow_redirects=True,
            data={"text": LONG, "system": "Network / CAN buses", "next_test": NT, "step": "7"})

p0 = client.get(f"/v/{VIN}/job").text
check(p0.count('id="job-call"') == 1 and "Next test:" in p0.split('id="job-call"')[1].split("</p>")[0]
      or "Fuel" in p0.split('id="job-call"')[1].split("</p>")[0], "page opens on a one-line call")
check("Do it now" in p0.split('id="job-call"')[1].split("</p>")[0], "the call links 'Do it now'")
check(re.search(r"Step \d+ of 12: \S", p0) is not None, "stepper reads 'Step N of 12: <name>'")
check(p0.rfind("Export for AlfaCore") > p0.find("</nav>", p0.find("process-map")) and
      p0.rfind('data-export') > p0.find('id="job-call"'), "Export for AlfaCore sits below the steps")

p7 = client.get(f"/v/{VIN}/job?step=7").text
card = p7[p7.find('class="job-card hyp-card'):]
card = card[:card.find('class="job-card hyp-card', 40)] if card.find('class="job-card hyp-card', 40) > 0 else card
check("<summary>Full reasoning</summary>" in card, "hypothesis has a Full reasoning fold")
head = card.split("Full reasoning")[0]
check("Research detail" not in head, "long research text is not in the default view")
check("hyp-next" in head and "Do it now" in head, "Next test and Do it now show by default")
check("Manage ledger" in card, "hypothesis has a Manage ledger fold")
mg = card[card.find("<summary>Manage ledger</summary>"):]
check("hyp-status-row" in mg and "hyp-edit-details" in mg and "hyp-delete-form" in mg and "evidence-picker" in mg,
      "status buttons, Edit, Delete and +Evidence live under Manage ledger")
check("hyp-status-row" not in card.split("Manage ledger")[0] and "hyp-delete-form" not in card.split("Manage ledger")[0],
      "no authoring control outside the fold")
pm = p7[p7.find('id="manage-ledger"'):]
check("add-hypothesis-collapsed" in pm and "Add to ledger" not in p7.split('id="manage-ledger"')[0],
      "+Add hypothesis and Add to ledger sit under the page Manage ledger")
check(p7.count("stuck-hint") == 1 and "Mark supported first. Mark supported first" not in p7, "the stuck hint is said once")
check("brakes_abs" not in re.sub(r'data-hyp-system="[^"]*"', "", p7), "no raw system key is visible")

p6 = client.get(f"/v/{VIN}/job?step=6").text
check("Record result" in p6 or "record" in p6.lower(), "recording a test result stays on step 6")

ps7 = client.get(f"/v/{VIN}/job?step=7&q=network").text
check('id="job-results"' in ps7 and "match" in ps7.split('id="job-results"')[1][:400], "search shows results under the call")
check('class="job-card hyp-card' in ps7 and "is-search-hit" in ps7, "matching hypothesis is marked and listed")
check("No match" in client.get(f"/v/{VIN}/job?q=zzzzqq").text, "no-match search says so with a hint")
check(client.get(f"/v/{VIN}/job?q=" + "x" * 500).status_code == 200, "an over-long query is clipped, not an error")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
