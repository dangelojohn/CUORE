"""Checks for the Adjustments screen (``/v/{vin}/adjustments``): procedure files, derived statuses, no run path.
Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_adjustments_page.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# throwaway state dir: test runs never touch the real store
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_adj_check_")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import procedure_sources  # noqa: E402
from cuore.services import adjustments  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


VIN = "ZASFAKPN5J7B88115"
files = sorted(procedure_sources.DATA_DIR.glob("*.json"))
names = {p.stem for p in files}
check({"engine_oil_reset", "service_interval_reset", "paddle_shift_market"} <= names, f"three procedure files present ({sorted(names)})")
for p in files:
    try:
        json.loads(p.read_text(encoding="utf-8"))
        check(procedure_sources.load(p.stem)["name"] == p.stem, f"{p.stem} loads")
    except Exception as e:  # noqa: BLE001
        failures.append(f"{p.stem} does not load: {e}")

pd = procedure_sources.load("paddle_shift_market")
check(len(pd.get("options") or []) == 2 and all(o.get("source") and o.get("meaning") for o in pd["options"]), "paddle: two options, each with meaning and source")
check({o["id"] for o in pd["options"]} == {"europe", "north_america"}, "paddle: europe and north_america")
check(pd["status"] == "awaiting source" and pd["steps"] == [] and pd["accepted_by_owner"] is False, "paddle: awaiting source, no steps, not accepted")
check(len(pd.get("risks") or []) == 2 and len(pd.get("needs_from_manufacturer") or []) == 5 and bool(pd.get("follow_up")), "paddle: 2 risks, 5 needs, follow-up")
check(all(r.get("source") for r in pd["risks"]), "paddle: every risk has a source")

cs = adjustments.cards()
check(len(cs) >= 3, f"three or more cards ({len(cs)})")
check(all(c["can_run"] is False and c["why_not"] for c in cs), "can_run false everywhere, with a reason")
by = {c["name"]: c for c in cs}
check(all(by[n]["status"] == "awaiting source" for n in ("engine_oil_reset", "service_interval_reset", "paddle_shift_market")), "three seed procedures awaiting source")
check(by["paddle_shift_market"]["group"] == "config" and by["engine_oil_reset"]["group"] == "resets", "grouping")
bd = adjustments.board()
check(sum(bd["counts"].values()) == len(cs) == bd["total"], "counts add up")

client = TestClient(create_app(), follow_redirects=False)
r = client.get(f"/v/{VIN}/adjustments")
check(r.status_code == 200, f"page renders ({r.status_code})")
html = r.text
sec = html.split('id="adjustments"')[1].split("MES_PARITY_PLAN.md")[0] if 'id="adjustments"' in html else ""
check(sec.count('class="adj-card"') == len(cs), "one card per procedure")
check(sec.count("Run (not available)") == len(cs), "Run (not available) once per card")
check("<form" not in sec and "<script" not in sec, "no form and no script in the adjustments section")
check("<button" not in sec, "no button element")
r2 = client.get(f"/v/{VIN}/adjustments/paddle_shift_market")
tail = r2.text.split('id="adj-paddle_shift_market"')[1][:200] if 'id="adj-paddle_shift_market"' in r2.text else ""
check(r2.status_code == 200 and "<details class=\"fold\" open>" in tail, "named card opens")
check(r2.text.count('class="adj-card"') == len(cs), "named page lists every card")
bad = [rt for rt in client.app.routes
       if "adjustments" in getattr(rt, "path", "") and (getattr(rt, "methods", None) or set()) - {"GET", "HEAD"}]
check(not bad, "no non-GET adjustments route")
check(client.post(f"/v/{VIN}/adjustments").status_code in (404, 405), "POST refused")

if failures:
    print("FAIL:", *failures, sep="\n  ")
    sys.exit(1)
print(f"all {passed} checks passed")
