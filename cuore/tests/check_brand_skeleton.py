"""Crawl every Menu page of a Maserati and a Ferrari car and prove each is an empty,
brand-themed skeleton: no Alfa/Stelvio data, no 500, no dead Menu link.

Uses a temporary CUORE_STATE_DIR (nothing goes into the real store) and never touches
the adapter. Run:  PYTHONPATH=mes-log-mcp .venv/Scripts/python.exe cuore/tests/check_brand_skeleton.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-skeleton-")
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.services import car_identify as ci  # noqa: E402
from cuore.web import nav_items  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
failures: list[str] = []
GLOBAL_PAGES: set[str] = set()
checks = 0
BANNED = ("Stelvio", "Giulia", "Alfa Romeo", "Giorgio")


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def vin_with_check(v17: str) -> str:
    return v17[:8] + ci._check_digit(v17)[1] + v17[9:]


CARS = {"maserati": vin_with_check("ZN661XUA0JX000001"), "ferrari": vin_with_check("ZFF79ALA0K0000001")}
MAKES = {"maserati": "Maserati", "ferrari": "Ferrari"}


def visible_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html))


c = TestClient(create_app(), follow_redirects=True, raise_server_exceptions=False)

for marque, vin in CARS.items():
    r = c.post("/api/car/create-service", json={"fields": {
        "vin": ci.make_field(vin, ci.SRC_TYPED), "make": ci.make_field(MAKES[marque], ci.SRC_TYPED)},
        "reason": "skeleton check"})
    check(f"{marque}: car created", r.status_code == 200, r.text[:200])
    menu = nav_items.nav_menu(vin)
    hrefs = {it["href"] for g in menu["groups"] for it in g["items"]}
    hrefs |= {it["href"] for g in menu["more_groups"] for it in g["items"]}
    hrefs.add(f"/v/{vin}/menu")
    for h in sorted(hrefs):
        resp = c.get(h)
        tag = f"{marque} {h}"
        check(f"{tag}: status", resp.status_code == 200, str(resp.status_code))
        if resp.status_code != 200:
            continue
        html = resp.text
        # global (not car-bound) pages theme to the default marque unless they carry the car
        per_car = vin in h
        if not per_car:
            GLOBAL_PAGES.add(h)
            continue
        check(f"{tag}: data-marque", f'data-marque="{marque}"' in html[:300])
        text = visible_text(html)
        for w in BANNED:
            check(f"{tag}: no '{w}'", w not in text, text[max(0, text.find(w) - 40):text.find(w) + 40])
        if per_car:
            check(f"{tag}: no '949'", not re.search(r"\b949\b", text))
            art = re.findall(r"""(?:src|href|url)\s*[=(]\s*["']?([^"')\s>]*stelvio[^"')\s>]*)""", html, re.I)
            check(f"{tag}: no Stelvio art", not art, str(art[:2]))

    # --- the skeleton itself, and what must not be offered -----------------------------------
    fz = c.get(f"/v/{vin}/fuses")
    check(f"{marque}: Fuses is the empty panel", "No fuses data for this model yet." in fz.text and 'data-brand-empty="fuses"' in fz.text)
    check(f"{marque}: Fuses keeps the brand frame (heading)", "<h1>Fuses</h1>" in fz.text)
    check(f"{marque}: TSB for this car is the empty panel", "No TSB data for this model yet." in c.get(f"/tsb?vin={vin}").text)
    bench = c.get(f"/v/{vin}").text
    check(f"{marque}: Connect disabled on Bench", 'id="connect-car-btn" aria-disabled="true"' in bench and "connect.js" not in bench)
    check(f"{marque}: Bench says no scan on file", "no scan on file" in bench)
    check(f"{marque}: Bench offers no 'Connect and read'", "Connect and read" not in bench)
    lb = c.get(f"/v/{vin}/liveboard").text
    check(f"{marque}: Live board has no Start and no liveboard.js", 'id="lb-start"' not in lb and "liveboard.js" not in lb and "No scan is on file" in lb)
    sc = c.get(f"/v/{vin}/scan")
    check(f"{marque}: Full scan says connecting is unconfirmed", "not confirmed" in sc.text and "scan/start" not in sc.text)
    post = c.post(f"/v/{vin}/scan/start")
    check(f"{marque}: scan start refused (409, no read)", post.status_code == 409, str(post.status_code))
    check(f"{marque}: five-minute run refused", c.post(f"/v/{vin}/five-minute/run").status_code == 409)
    menu_html = c.get(f"/v/{vin}/menu").text
    check(f"{marque}: Menu next step is not the Five-minute test", 'data-nav-next="job"' in menu_html and "Five-minute" not in visible_text(menu_html))
    check(f"{marque}: Facts label is neutral", 'data-nav="facts"' in menu_html and "Stelvio facts" not in menu_html)

print("global (not car-bound) pages not checked:", ", ".join(sorted(GLOBAL_PAGES)))
print(f"{checks} checks, {len(failures)} failed")
for f in failures:
    print("FAIL", f)
sys.exit(1 if failures else 0)
