"""Checks for the car-session checklist (services/car_session.py, /v/{vin}/car-session) and a dry run of
every Next-connection step link against the app with no adapter. Run:
  .venv/Scripts/python.exe -X utf8 cuore/tests/check_car_session.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-car-session-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import demo_source, interlock  # noqa: E402
from cuore.services import car_session, next_session, parity  # noqa: E402
from cuore.web import car_session_routes  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
VIN = "ZASFAKPN5J7B88115"
fails: list[str] = []


def check(label, cond):
    print(("ok   " if cond else "FAIL ") + label)
    if not cond:
        fails.append(label)


cs = car_session.build(VIN)
open_rows = {i["id"] for i in parity.load()["items"] if i["state"] == "car_session"}
check("13 car_session rows", cs["n_rows"] == len(open_rows) == 13)
check("every car_session row has a step", not cs["rows_uncovered"])
check("two rows were uncovered before the added steps", cs["rows_uncovered_before"] == ["bus-can-ihs", "dtc-read-can-ihs"])
check("every shipped plan step is mapped", not cs["missing_from_plan"] and sum(1 for s in cs["steps"] if not s["added"]) == 13)
check("3 groups, off first", [g["key"] for g in cs["groups"]] == ["off", "run", "cable"])
check("rfhub-first is first", cs["groups"][0]["steps"][0]["id"] == "rfhub-first")
check("minutes add up", cs["total_minutes"] == sum(g["minutes"] for g in cs["groups"]))
check("nothing ready before any step is done", cs["ready"] == [])
next_session.mark(VIN, "abs-round", True)
r = car_session.build(VIN)["ready"]
check("done step lists its rows, not freeze-abs", {x["id"] for x in r} == {"dtc-read-can-ch", "mod-abs", "bus-can-ch"})
check("each ready row names the MES read needed", all(x["mes"] for x in r))
check("parity state never changed", all(i["state"] == "car_session" for i in parity.load()["items"] if i["id"] in open_rows))
check("no overrides file written", not (Path(STATE) / "parity_overrides.json").exists())

app = create_app()
app.include_router(car_session_routes.router)
c = TestClient(app)
p = c.get(f"/v/{VIN}/car-session")
check("page 200", p.status_code == 200)
check("page has steps, rules and ready table", "Rules:" in p.text and "Blue cable" in p.text and "Ready to mark done" in p.text)
check("template has no script tag", "<script" not in (Path(__file__).resolve().parents[1] / "web" / "templates" / "car_session.html").read_text(encoding="utf-8"))

# dry run: every step link and the pages the Menu change could have broken
links = {s["href"] for s in (next_session.view(VIN) or {"steps": []})["steps"] if s.get("href")}
links |= {f"/v/{VIN}/{x}" for x in ("next-session", "configuration", "parity", "scan", "job", "liveboard")}
for u in sorted(links):
    try:
        code = c.get(u.split("#")[0]).status_code
    except Exception as exc:  # noqa: BLE001
        code = repr(exc)[:80]
    check(f"GET {u} -> {code}", code in (200, 303))
check("demo source importable", callable(getattr(demo_source, "demo_value", None)))
print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
