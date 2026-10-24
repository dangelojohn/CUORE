"""Vehicle facts quick-view: page renders key values with sources, a VIN with
no facts file gets a plain notice (200), the header nav carries a Facts link,
and the landing page shows the summary card. In-process TestClient; no COM3.

Run:  .venv/Scripts/python.exe cuore/tests/check_facts_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-facts-")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

VIN = "ZASFAKPN5J7B88115"


def check_page() -> None:
    from fastapi.testclient import TestClient
    from cuore.app import create_app
    c = TestClient(create_app(), follow_redirects=False)
    r = c.get(f"/v/{VIN}/facts")
    assert r.status_code == 200, r.status_code
    t = r.text
    for needle in ("09/2017", "Cassino", "148,207 km", "30 psi (210 kPa)", "33 psi (230 kPa)",
                   "MV-002.010.041", "MV-002.009.043", "door label", "2026-10-23", "UNKNOWN",
                   "U36", "18V-205", "unconfirmed", "inference",
                   'id="facts-radio-compare"', "RECOMMENDED", "INSTALLED", "NOT FOR THIS CAR",
                   "MV-090.000.061", "TSB 08-029-20 (2020-03-05)"):
        assert needle in t, needle
    assert f'href="/v/{VIN}/facts"' in t  # nav link, vehicle-scoped

    r = c.get("/v/ZZZZZZZZZZZZZZZZZ/facts")
    assert r.status_code == 200 and "No facts file" in r.text

    r = c.get("/facts")
    assert r.status_code == 303 and r.headers["location"].endswith("/facts")
    print("page OK")


def check_nav_and_card() -> None:
    from fastapi.testclient import TestClient
    from cuore.app import create_app
    c = TestClient(create_app(), follow_redirects=False)
    r = c.get("/start")
    assert r.status_code == 200 and 'class="icon-btn facts-link' in r.text and 'href="/facts"' in r.text
    r = c.get(f"/v/{VIN}")
    assert r.status_code == 200, r.status_code
    assert f'href="/v/{VIN}/facts"' in r.text and "Vehicle facts" in r.text and "MV-002.010.041" in r.text
    print("nav and landing card OK")


if __name__ == "__main__":
    check_page()
    check_nav_and_card()
