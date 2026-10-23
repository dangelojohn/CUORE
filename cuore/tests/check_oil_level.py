"""Two checks for the Oil level card: (1) model maths incl. over-full and
below-MIN; (2) the dashboard page renders with and without a reading, and the
API / form round-trip works. In-process TestClient, temp state dir; no COM3,
no live server.

Run:  .venv/Scripts/python.exe cuore/tests/check_oil_level.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-oil-")
os.environ.pop("CUORE_OIL_DIPSTICK_RANGE_L", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

VIN = "ZASFAKPN5J7B88115"


def check_model() -> None:
    from mes import oil_level as m
    assert m.CAPACITY_L == 5.2 and m.dipstick_range_l() == 1.0 and m.range_is_assumed()
    mx = m.compute({"method": "dipstick", "dipstick_position_pct": 100})
    assert mx["sump_l"] == 5.2 and mx["pct_of_capacity"] == 100.0 and not mx["over_full"]
    assert abs(mx["sump_qt"] - 5.5) < 0.01
    mid = m.compute({"method": "dipstick", "dipstick_position_pct": 70})
    assert mid["sump_l"] == 4.9 and mid["pct_of_capacity"] == 94.2 and mid["pct_between"] == 70
    mn = m.compute({"method": "dipstick", "dipstick_position_pct": 0})
    assert mn["sump_l"] == 4.2 and not mn["below_min"]
    over = m.compute({"method": "dipstick", "dipstick_position_pct": 130})
    assert over["over_full"] and over["sump_l"] == 5.5 and over["pct_of_capacity"] > 100
    low = m.compute({"method": "dipstick", "dipstick_position_pct": -40})
    assert low["below_min"] and low["sump_l"] == 3.8
    dr = m.compute({"method": "drain_volume", "litres": 4.7})
    assert dr["sump_l"] == 4.7 and dr["pct_between"] == 50.0
    assert m.validate({"method": "dipstick"}) and m.validate({"method": "drain_volume"})
    assert m.validate({"method": "bogus"}) and m.compute({"method": "dipstick"}) is None
    print("model OK")


def check_page() -> None:
    from fastapi.testclient import TestClient
    from cuore.app import create_app
    from cuore.web import oil_level_routes

    app = create_app()
    c = TestClient(app, follow_redirects=False)
    base = f"/v/{VIN}/dashboard"
    r = c.get(base)
    assert r.status_code == 200, r.status_code
    assert "No oil reading yet" in r.text and 'action="/v/%s/oil-level"' % VIN in r.text
    assert "ASSUMED" in r.text and "oil-bar" not in r.text.split("</style>")[1]

    # bad reading rejected with a 400 naming the problem
    bad = c.post(f"/api/vehicles/{VIN}/oil-level", json={"method": "dipstick"})
    assert bad.status_code == 400, bad.text
    # card form -> redirect back, reading stored
    r = c.post(f"/v/{VIN}/oil-level", data={"date": "2026-10-20", "odometer_km": "40100",
               "method": "dipstick", "dipstick_position_pct": "70", "note": "cold"})
    assert r.status_code == 303 and r.headers["location"].endswith("#oil-level")
    r = c.post(f"/api/vehicles/{VIN}/oil-level", json={
        "date": "2026-10-23", "method": "dipstick", "dipstick_position_pct": 120})
    assert r.status_code == 200, r.text
    api = c.get(f"/api/vehicles/{VIN}/oil-level").json()
    assert api["count"] == 2 and api["latest"]["over_full"] and len(api["history"]) == 2
    r = c.get(base)
    assert r.status_code == 200
    t = r.text
    assert "OVER-FULL" in t and "in sump" in t and "MIN" in t and "MAX" in t
    assert "2026-10-20" in t and "No oil reading yet" not in t
    # phone form comes from the taxonomy
    m = c.get(f"/m/{VIN}/add/fluids/oil_level")
    assert m.status_code == 200 and "Dipstick position" in m.text
    print("page OK")


if __name__ == "__main__":
    check_model()
    check_page()
