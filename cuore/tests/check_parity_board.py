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
check(len(items) >= 500, f"at least 500 rows ({len(items)})")
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

check(all(i.get("status") in parity.STATUS_ORDER for i in items), "every row has one of the five statuses")
check(all(i.get("module") for i in items), "every row has a module")
import collections  # noqa: E402
cnt = collections.Counter(i["status"] for i in items)
mes_items = [i for i in items if i["group"] != "cuore_only" and i.get("applies_to_reference_car", True) is not False]
check(cnt["PROVEN"] == 36 and all(i.get("mes_item") for i in items if i["status"] == "PROVEN"), "36 proven, all identity-field rows from the work list")
check(all(i["cuore"]["has"] == "yes" for i in items if i["status"] == "PROVEN"), "proven rows have CUORE = yes")
check(all(i["status"] == "NEEDS MANUFACTURER SOURCE" for i in items if i["group"] in ("mes_config", "mes_adjustments", "mes_actuators") and i.get("mes_item")),
      "every write-type MES item waits on a manufacturer source")
check(all(i.get("seen_in") for i in items if i.get("mes_item")), "every added row names where it was seen")
added = sum(1 for i in items if i.get("mes_item"))
named = sum(len(i.get("also_seen_as", [])) for i in items)
check(added + named >= 427 + 38, f"work-list items and MES F7 options are all on the board: {added} rows + {named} named on function rows")

b = parity.board()
check(b["total"] == len(items) and b["shown"] == len(items), "board shows every row unfiltered")
check([s["key"] for s in b["sections"]] == parity.STATUS_ORDER, "sections follow the five statuses")
check(sum(s["n"] for s in b["sections"]) == len(items), "sections partition the rows")
check(sum(b["counts_status_all"].values()) == len(items), "status counts add up to the total")
check(b["mes_total"] == len(mes_items) and b["mes_proven"] == cnt["PROVEN"] - sum(1 for i in items if i["status"] == "PROVEN" and i not in mes_items), "headline N of M")
bf = parity.board(status="needs-nothing")
check(bf["shown"] == len(items), "unknown status is ignored, not an empty page")
bs = parity.board(status="buildable")
check(bs["shown"] == cnt["MISSING BUILDABLE"] and all(s["key"] == "MISSING BUILDABLE" for s in bs["sections"]), "status filter by slug")
bm = parity.board(module="ECM")
check(bm["shown"] == bm["counts_module"]["ECM"] and sum(bm["counts_status"].values()) == bm["shown"], "module filter and its status counts")
check(sum(r["n"] for r in b["by_module"]) == len(items) and sum(r["n"] for r in b["by_group"]) == len(items), "module and group tables cover every row")
g0 = next(iter(data["groups"]))
bg = parity.board(group=g0)
check(bg["shown"] == b["counts_group"][g0], "group filter")
bl = parity.board(state="documents")
check(bl["shown"] == b["counts_state"]["documents"], "legacy state filter still works")
csv = parity.to_csv()
check(csv.count("\n") == len(items) + 1 and csv.startswith("id,group,function"), "CSV has one line per row")

client = TestClient(create_app(), follow_redirects=False)
r = client.get(f"/v/{VIN}/parity")
check(r.status_code == 200, f"page renders ({r.status_code})")
html = r.text
check('id="parity"' in html and html.count('class="pb-row') == len(items), "every row is on the page")
check(f"{b['mes_proven']} of {b['mes_total']} MES items proven" in html and "not equal to MES" in html, "honest total at the top, never called equal")
check(html.count("<details") >= len(items) + 4, "rows and sections are folds")
check("pb-chip" in html and "parity.csv" in html, "filters and CSV link present")
check("<script" not in html.split('id="parity"')[1].split("Related:")[0], "no script in the board")
r2 = client.get(f"/v/{VIN}/parity?status=car&module=ECM")
check(r2.status_code == 200 and r2.text.count('class="pb-row') == sum(1 for i in items if i["status"] == "NEEDS CAR" and i["module"] == "ECM"), "status plus module filter on the page")
r3 = client.get(f"/v/{VIN}/parity.csv")
check(r3.status_code == 200 and r3.headers.get("content-type", "").startswith("text/csv"), "CSV route")

if failures:
    print("FAIL:", *failures, sep="\n  ")
    sys.exit(1)
print(f"all {passed} checks passed")
