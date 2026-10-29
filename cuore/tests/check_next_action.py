"""Checks for the Bench's single Next-action card (cuore/services/next_action.py).

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_next_action.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cuore.services.next_action import next_action  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
fails: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{note}]" if note and not ok else ""))
    if not ok:
        fails.append(name)


PLAN = {"steps": [{"id": "a", "order": 1, "title": "Done one", "done": True},
                  {"id": "b", "order": 2, "title": "Cold read", "why": "Because.", "done": False,
                   "preconditions": "Car cold, key on; MES closed", "href": f"/v/{VIN}/scan",
                   "link_label": "Guided scan", "source": "note x"}]}
JOB = {"id": "j1", "has_evidence": True}
CARD = {"key": "code:P0455", "code": "P0455", "label": "P0455 EVAP", "href": f"/v/{VIN}/code/P0455",
        "next_test": {"text": "Inspect the fuel cap seal", "source": "suspect"}}

r = next_action(VIN, {"active": True, "simulation": False}, JOB, CARD, PLAN)
check("rule1 live session", r["href"] == "/live" and "rule 1" in r["source"])
r = next_action(VIN, {"active": True, "simulation": True}, None, None, None)
check("rule1 simulation", r["href"] == "/live" and "simulation" in r["source"])
r = next_action(VIN, {}, JOB, CARD, PLAN)
check("rule2 no-car test", r["title"] == "Inspect the fuel cap seal" and "j1" in r["source"] and "rule 2" in r["source"])
r = next_action(VIN, {}, JOB, {**CARD, "next_test": {"text": "Read Mode 06 3A after cold soak", "source": "s"}}, PLAN)
check("rule2 skipped when test needs car", "rule 3" in r["source"])
r = next_action(VIN, {}, None, CARD, PLAN)
check("rule2 needs an open job", "rule 3" in r["source"])
r = next_action(VIN, {}, JOB, CARD, PLAN) if False else next_action(VIN, {}, JOB, None, PLAN)
check("rule3 first not-done step", r["title"] == "Cold read" and "b" in r["source"]
      and r["needs"][0] == "Car cold" and r["href"].endswith("/scan"))
r = next_action(VIN, {}, {"id": "j2", "has_evidence": False}, None, {"steps": [{"id": "a", "done": True}]})
check("rule4 job without evidence", r["title"] == "Read the car" and "j2" in r["source"])
r = next_action(VIN, {}, JOB, None, None)
check("rule5 job with evidence, nothing else -> start", r["href"] == "/start")
r = next_action(VIN, {}, None, None, None)
check("rule5 nothing open", r["title"] == "Start a job" and r["href"] == "/start")

os.environ.setdefault("CUORE_STATE_DIR", tempfile.mkdtemp(prefix="cuore_na_"))
from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402

resp = TestClient(create_app()).get(f"/v/{VIN}")
check("bench 200", resp.status_code == 200, str(resp.status_code))
html = resp.text
i = html.find('class="bench"')
j = html.find("<section", i)
check("card is first section in content", i > 0 and j > 0 and html[j:j + 80].count('id="next-action"') == 1)
m = re.search(r'<section class="next-action".*?</section>', html, re.S)
check("exactly one action link", bool(m) and len(re.findall(r"<a\b", m.group(0))) == 1)
if m:
    print("CARD:", re.sub(r"\s+", " ", re.sub(r"<style.*?</style>|<[^>]+>", " ", m.group(0), flags=re.S))[:400])
sys.exit(1 if fails else 0)
