"""Check the field-quality early-warning pipeline with synthetic cases (no adapter, no car).

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_field_quality.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-fq-")
os.environ["CUORE_STATE_DIR"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import field_quality as fq  # noqa: E402
from cuore.web import field_quality_routes  # noqa: E402
from mes import cases as cases_mod  # noqa: E402

failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


VINS = [f"ZASFAKPN5J7B8811{i}" for i in range(5)]
SECRET_TEXT = "Mrs Tremblay plate ABC123 rattles at idle"
now = datetime.now()


def case(n, vin, code, outcome="fixed", verified=True, part="68413231AA", closed_days_ago=90, tests=None):
    closed = now - timedelta(days=closed_days_ago)
    return {"id": f"case-job{n}", "vin": vin, "model": "stelvio", "codes": [code], "complaint": SECRET_TEXT,
            "symptoms_summary": SECRET_TEXT, "pitfalls": [SECRET_TEXT], "outcome": outcome,
            "verification_state": "verified clean" if verified else "released unverified: x",
            "parts_used": [{"name": "Customer Jane's part", "part_no": part, "qty": 1}],
            "tests": tests or [{"text": SECRET_TEXT, "result": "out of range"}, {"text": "x", "result": "pass"}],
            "opened": (closed - timedelta(days=1)).isoformat(), "closed": closed.isoformat()}


def client():
    app = create_app()
    app.include_router(field_quality_routes.router)      # until app.py registers it
    return TestClient(app, follow_redirects=False, raise_server_exceptions=False)


# 1. one-car state: not a pattern
cases_mod._append(case(1, VINS[0], "P0456-00"))
c = client()
page = c.get("/field-quality")
check("page 200", page.status_code == 200, str(page.status_code))
check("one car: not a pattern yet", "single case, not a pattern yet" in page.text)
check("one car: zero patterns", "Patterns ready for engineering: 0 (cars in pool: 1; sharing: off)" in page.text, page.text[:0])
check("platform 949 and year 2018", "<td>949</td><td>2018</td>" in page.text)

# 2. consent off: export empty
j = c.get("/field-quality.json").json()
check("off: no rows", j["rows"] == [] and j["sharing"] == "off" and j["message"] == "sharing is off", str(j))
check("default settings off", fq.settings()["sharing"] is False)

# 3. below cohort with two cars, then cohort met with three
cases_mod._append(case(2, VINS[1], "P0456-00", verified=False))
v = fq.view()
check("two cars below cohort", v["patterns"] == 0 and v["rows"][0]["cars"] == 2, str(v["rows"][0]["status"]))
cases_mod._append(case(3, VINS[2], "P0456-00"))
cases_mod._append(case(4, VINS[2], "P0456-00", closed_days_ago=60))      # same car twice: cases 4, cars 3
cases_mod._append(case(5, VINS[3], "P0171-00", outcome="not_fixed", verified=False))
v = fq.view()
row = next(r for r in v["rows"] if r["dtc"] == "P0456")
check("cohort met", row["is_pattern"] and v["patterns"] == 1, str(row))
check("cars vs cases", row["cars"] == 3 and row["cases"] == 4, f"{row['cars']}/{row['cases']}")
check("proven count", row["proven_fixes"] == 3, str(row["proven_fixes"]))
check("fix grouped", row["fixes"][0]["fix"] == "part 68413231AA" and row["fixes"][0]["cases"] == 4, str(row["fixes"]))
check("pattern sorted first", v["rows"][0]["dtc"] == "P0456")
other = next(r for r in v["rows"] if r["dtc"] == "P0171")
check("unfixed not proven", other["proven_fixes"] == 0 and not other["is_pattern"])

# 4. comeback counting: job3 closed 90 d ago, job4 (same car, same code) opened 61 d ago, within 30 d? no (29 d later)
cb = row["comebacks_30d"]
check("comeback yes for repeat within 30 d", cb["yes"] == 1, str(cb))
check("comebacks no/unknown", cb["no"] + cb["unknown"] == 3, str(cb))
cases_mod._append(case(6, VINS[4], "P0456-00", closed_days_ago=5))
row = next(r for r in fq.view()["rows"] if r["dtc"] == "P0456")
check("recent close is unknown", row["comebacks_30d"]["unknown"] == 1, str(row["comebacks_30d"]))

# 5. sharing on: export has pattern rows, nothing identifying
check("toggle on", client().post("/field-quality/sharing", data={"sharing": "on"}).status_code == 303)
check("settings file", json.loads(Path(_TMP, "field_quality.json").read_text())["sharing"] is True)
c = client()
feed = c.get("/field-quality.json")
j = feed.json()
check("on: pattern rows only", j["sharing"] == "on" and len(j["rows"]) == 1 and j["rows"][0]["dtc"] == "P0456", str(j)[:300])
page = c.get("/field-quality")
check("page shows sharing on", "sharing: on" in page.text)

# 6. anonymisation
blob = feed.text + page.text
for needle in VINS + ["Tremblay", "ABC123", "rattles", "Jane", "customer", "ZASFAKPN"]:
    if needle == "customer":
        continue
    check(f"no {needle!r} anywhere", needle not in blob)
check("no raw VIN fragment", "7B8811" not in blob)
check("export keys limited", set(j["rows"][0]) == {"platform", "model_year", "market", "dtc", "failure_type",
      "readings_signature", "cars", "cases", "proven_fixes", "comebacks_30d", "fixes"})

# 7. toggle off again, configurable cohort
c.post("/field-quality/sharing", data={"sharing": "off"})
check("off again: no rows", c.get("/field-quality.json").json()["rows"] == [])
Path(_TMP, "field_quality.json").write_text(json.dumps({"sharing": True, "min_cohort": 5}))
check("min cohort configurable", fq.view()["patterns"] == 0 and fq.export()["rows"] == [])

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
