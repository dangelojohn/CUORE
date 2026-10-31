"""Checks for the technician feedback loop (helped / wrong buttons + summary).

Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_helped.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-helped-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import helped_routes  # noqa: E402

TPL = ROOT / "cuore" / "web" / "templates"
VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
n = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global n
    n += 1
    if not cond:
        failures.append(f"{label} {detail}".strip())


app = create_app()
if not any(getattr(r, "path", "") == "/v/{vin}/helped" for r in app.routes):
    app.include_router(helped_routes.router)
c = TestClient(app)

# --- posts store correctly, redirect back ---
r = c.post(f"/v/{VIN}/helped", data={"page": "codes", "item": "P0455", "label": "P0455 EVAP large leak",
                                     "verdict": "helped", "redirect_to": f"/v/{VIN}/codes#row-P0455"},
           follow_redirects=False)
check("helped redirects back", r.status_code == 303 and r.headers["location"] == f"/v/{VIN}/codes#row-P0455",
      f"{r.status_code} {r.headers.get('location')}")
r = c.post(f"/v/{VIN}/helped", data={"page": "codes", "item": "P0455", "label": "P0455", "verdict": "wrong",
                                     "text": "x" * 300, "redirect_to": "//evil.example"}, follow_redirects=False)
check("unsafe redirect_to falls back inside the app", r.headers["location"] == "/", r.headers.get("location"))
c.post(f"/v/{VIN}/helped", data={"page": "bench", "item": "next-action", "label": "Run EVAP test",
                                 "verdict": "wrong", "text": "car was already fixed", "redirect_to": f"/v/{VIN}"})
c.post(f"/v/{VIN}/helped", data={"page": "bench", "item": "next-action", "verdict": "bogus", "redirect_to": "/"})

from mes import feedback as fb  # noqa: E402
rows = [x for x in fb.load(VIN) if x["target"]["section"] == "helped"]
check("3 valid rows stored, bogus verdict ignored", len(rows) == 3, str(len(rows)))
h = rows[0]
check("helped row: confirm, page, item, vin, time, who",
      h["kind"] == "confirm" and h["target"]["page"] == "codes" and h["target"]["item"] == "P0455"
      and h["vin"] == VIN and h["at"] and h["author"], str(h))
check("helped row dismissed (keeps inbox clean)", h["status"] == "dismissed", h["status"])
check("wrong row: disagree, open, note capped at 140", rows[1]["kind"] == "disagree"
      and len(rows[1]["text"]) == 140 and rows[1]["status"] == "open", str(rows[1]))

# --- summary ---
s = c.get("/feedback-summary")
check("summary 200", s.status_code == 200, str(s.status_code))
check("summary answer-first counts", "1 helped, 2 wrong this week" in s.text)
check("summary names most-wrong item", "Most-wrong item: Bench next action, next-action" in s.text
      or "Most-wrong item: Codes advice, P0455" in s.text)
check("summary lists the note", "car was already fixed" in s.text)
check("summary per-page table", "Codes advice" in s.text and "Bench next action" in s.text)

# --- partial on each page (template wiring) ---
for name, page in [("_next_action.html", "bench"), ("codes.html", "codes"), ("tests.html", "tests"),
                   ("_systems_interactive.html", "systems"), ("arrive_ready.html", "arrive"), ("find.html", "find")]:
    t = (TPL / name).read_text(encoding="utf-8")
    check(f"{name} includes _helped.html for {page}",
          '_helped.html' in t and f"h_page='{page}'" in t)

# --- partial renders: two forms, no script, 56 px ---
part = (TPL / "_helped.html").read_text(encoding="utf-8")
check("partial has no <script", "<script" not in part.lower())
check("partial buttons min-height 56px", len(re.findall(r"min-height:\s*56px", part)) >= 2)
check("partial has This helped and This was wrong", "This helped" in part and "This was wrong" in part)
check("partial note box capped", 'maxlength="140"' in part)

f = c.get("/find", params={"q": "codes", "vin": VIN})
check("find page renders", f.status_code == 200, str(f.status_code))
if "find-best" in f.text:
    check("find top result carries the buttons", "This helped" in f.text and f"/v/{VIN}/helped" in f.text)
    check("find page: no script added by partial", "<script" not in f.text.split("find-best")[1].split("</div>")[0])

if failures:
    print(f"FAIL {len(failures)}/{n}")
    for x in failures:
        print(" -", x)
    sys.exit(1)
print(f"OK {n} checks")
