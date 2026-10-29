"""Checks for the parity board (``/v/{vin}/parity``): data file shape, grouping, filters, CSV, page render.
Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_parity_board.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import parity  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


VIN = "ZASFAKPN5J7B88115"
data = json.loads(parity.DATA_FILE.read_text(encoding="utf-8"))
items = data["items"]
check(len(items) >= 40, f"at least 40 rows ({len(items)})")
check(set(data["states"]) == set(parity.STATE_ORDER), "states match the service's order")
ids = [i["id"] for i in items]
check(len(ids) == len(set(ids)), "ids are unique")
for i in items:
    ok = (i["state"] in parity.STATE_ORDER and i["group"] in data["groups"]
          and all(k in i for k in ("function", "mes", "alfaobd", "cuore", "closes", "refs"))
          and i["mes"]["has"] in ("yes", "no", "partial") and i["alfaobd"]["has"] in ("yes", "no", "partial", "unknown")
          and i["cuore"]["has"] in ("yes", "no", "partial") and isinstance(i["refs"], list))
    if not ok:
        failures.append(f"row shape: {i.get('id')}")
        break
else:
    passed += 1
check(all(len((i.get(t) or {}).get("note", "")) <= 160 for i in items for t in ("mes", "alfaobd", "cuore")), "notes are short")
check(any(i["state"] == "done" for i in items) and any(i["state"] == "documents" for i in items)
      and any(i["state"] == "car_session" for i in items), "every working state is used")
check(any(i["id"].startswith("paddle") or "addle" in i["function"] for i in items), "the paddle-shifter row exists")
check(all(i["cuore"]["has"] == "yes" for i in items if i["state"] == "done"), "done rows have CUORE = yes")

b = parity.board()
check(b["total"] == len(items) and b["shown"] == len(items), "board shows every row unfiltered")
check([s["key"] for s in b["sections"]] == parity.STATE_ORDER, "sections in work order, car session first")
check(sum(s["n"] for s in b["sections"]) == len(items), "sections partition the rows")
bf = parity.board(state="documents")
check(bf["shown"] == b["counts_state"]["documents"] and all(s["key"] == "documents" for s in bf["sections"]), "state filter")
g0 = next(iter(data["groups"]))
bg = parity.board(group=g0)
check(bg["shown"] == b["counts_group"][g0], "group filter")
csv = parity.to_csv()
check(csv.count("\n") == len(items) + 1 and csv.startswith("id,group,function"), "CSV has one line per row")

client = TestClient(create_app(), follow_redirects=False)
r = client.get(f"/v/{VIN}/parity")
check(r.status_code == 200, f"page renders ({r.status_code})")
html = r.text
check('id="parity"' in html and html.count('class="pb-row') == len(items), "every row is on the page")
check(html.count("<details") >= len(items) + 4, "rows and sections are folds")
check("pb-chip" in html and "parity.csv" in html, "filters and CSV link present")
check("<script" not in html.split('id="parity"')[1].split("Related:")[0], "no script in the board")
r2 = client.get(f"/v/{VIN}/parity?state=car_session")
check(r2.status_code == 200 and r2.text.count('class="pb-row') == b["counts_state"]["car_session"], "state filter on the page")
r3 = client.get(f"/v/{VIN}/parity.csv")
check(r3.status_code == 200 and r3.headers.get("content-type", "").startswith("text/csv"), "CSV route")

if failures:
    print("FAIL:", *failures, sep="\n  ")
    sys.exit(1)
print(f"all {passed} checks passed")
