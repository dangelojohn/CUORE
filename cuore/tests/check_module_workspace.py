"""Checks for the module workspace (``/v/{vin}/modules/{code}``) and ``services.module_workspace``.

Throwaway ``CUORE_STATE_DIR``; the reference VIN's real corpus is the fixture, as in
check_vmodules_page.py. Nothing here opens an adapter.

Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_module_workspace.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-workspace-")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import module_workspace as mw  # noqa: E402
from cuore.web import modules_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


app = create_app()
if "/v/{vin}/modules" not in {getattr(r, "path", None) for r in app.routes}:
    app.include_router(modules_routes.router)
client = TestClient(app)

# 1. section order on the page
r = client.get(f"/v/{VIN}/modules/ECM")
check("workspace 200", r.status_code == 200, str(r.status_code))
html = r.text
ids = ["sec-answer", "sec-connect", "sec-info", "sec-errors", "sec-params", "sec-adjust",
       "sec-notread", "sec-next"]
pos = [html.find(f'id="{i}"') for i in ids]
check("all sections present", all(p >= 0 for p in pos), str(pos))
check("sections in fixed order", pos == sorted(pos), str(pos))
check("section order constant matches", mw.SECTION_ORDER == ("answer", "connect", "identity", "faults",
      "live", "adjust", "notread", "next"))

# 2. NOT READ is shown for the module whose last read failed (ECM on this corpus)
ws = mw.build(VIN, "ECM")
check("answer first line is the NOT READ rule when not read",
      ("NOT READ" in ws["answer"]) == bool(ws["not_read_list"] and ws["not_read_list"][0].startswith("NOT READ")))
check("what-was-not-read lists something", len(ws["not_read_list"]) > 0)
check("NOT READ wording on page", "NOT READ" in html)
check("never says clean when not read", "read clean" not in ws["answer"] or "NOT READ" not in ws["answer"])

# 3. cable step
plan = mw.connect_plan("can_ch", "none")
check("wrong cable -> not ok", plan["ok"] is False)
check("cable step names fitted, needed and steps", "Wrong cable" in plan["step"] and "Disconnect" in plan["step"]
      and "grey" in plan["step"].lower() and "500k" in plan["step"], plan["step"])
plan_ok = mw.connect_plan("can_c", "none")
check("right cable -> ok and no step", plan_ok["ok"] and plan_ok["step"] == "")
check("bus rate shown", plan_ok["rate"] == "500k" and mw.connect_plan("can_ihs", "blue_a5")["rate"] == "125k")
check("splitter flagged listen-only", mw.connect_plan("can_c", "witech_splitter")["listen_only"] is True)
unk = mw.connect_plan(None, "none")
check("unknown bus -> do not connect", unk["ok"] is False and "do not connect" in unk["headline"].lower())
os.environ["CUORE_OBD_CABLE"] = "grey_a6"
r2 = client.get(f"/v/{VIN}/modules/ECM")
os.environ.pop("CUORE_OBD_CABLE")
check("page shows cable step when wrong cable fitted", "Wrong cable" in r2.text)
check("page shows bus and rate before connecting", "500k" in html and "Connect" in html)

# 4. honest adjustment states
for k, (state, todo) in mw.HONEST.items():
    check(f"honest state {k}", bool(state) and bool(todo))
check("awaiting source says manufacturer tool",
      "manufacturer" in mw.HONEST["awaiting source"][1].lower() and "wiTECH" in mw.HONEST["awaiting source"][1])
check("page states adjustments need manufacturer procedure", "Needs the manufacturer procedure" in client.get(
    f"/v/{VIN}/modules/BCM").text)
check("no overclaim: no 'Run' control", "can_run" not in html and ">Run<" not in html)

# 5. no write route
post_paths = [(r.path, r.methods) for r in app.routes
              if getattr(r, "path", "").startswith("/v/{vin}/modules")]
check("modules routes are GET only", all(m <= {"GET", "HEAD"} for _, m in post_paths), str(post_paths))
check("POST to workspace refused", client.post(f"/v/{VIN}/modules/ECM").status_code in (404, 405))
src = Path(mw.__file__).read_text(encoding="utf-8")
check("service imports no transport/safety/consent_gate",
      not re.search(r"^\s*(from|import)\s+.*(transport|safety|consent_gate|serial)", src, re.M))
body = html[html.find('id="sec-answer"'):html.find('id="sec-next"')]
check("workspace body has no form", "<form" not in body)

# 6. marque neutrality: no marque or model literal in the service or the template
tmpl = (Path(modules_routes.__file__).parent / "templates" / "vmodule.html").read_text(encoding="utf-8")
for word in ("stelvio", "alfa", "giulia", "maserati", "ferrari", "jeep", "fiat"):
    check(f"no '{word}' literal in service", word not in src.lower())
    check(f"no '{word}' literal in template", word not in tmpl.lower())

# 7. links to job, bulletins, wiring, bay sheet, proof, same on another module
for mod in ("ECM", "BCM"):
    t = client.get(f"/v/{VIN}/modules/{mod}").text
    for href in (f"/v/{VIN}/job", f"/v/{VIN}/bay-sheet", f"/v/{VIN}/electrical", f"/v/{VIN}/bench/proof"):
        check(f"{mod} links {href}", f'href="{href}"' in t)
    check(f"{mod} same section order", [t.find(f'id="{i}"') for i in ids] == sorted(t.find(f'id="{i}"') for i in ids))
check("why-it-matters from systems map on ECM", "Why it matters" in html or not ws["why"])

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
