"""Landing page and brand flow: "/" is the brand picker (never redirects), a brand
opens its car list (VIN/WMI rule), Add a car uses the existing intake, the logo
always returns to "/", the header carries no tagline or leftover buttons.
Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_landing.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-landing-")
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.services import landing_bridge  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
ALFA = "ZASFAKPN5J7B88115"
MASERATI = "ZN661XUA9JX000001"
failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


c = TestClient(create_app(), follow_redirects=False, raise_server_exceptions=False)

# --- brand list is data -------------------------------------------------------------------------
data = json.loads((ROOT / "cuore/data/brands.json").read_text(encoding="utf-8"))["brands"]
check("brand list lives in data, three brands in order", [b["key"] for b in data] == ["alfa", "maserati", "ferrari"])
check("every brand mark file exists", all((ROOT / "cuore/web/static/brand" / b["mark"]).is_file() for b in data))
check("code names no brand (only the data file does)",
      not re.search(r"Maserati|Ferrari|Alfa", (ROOT / "cuore/web/templates/landing.html").read_text(encoding="utf-8")
                    + (ROOT / "cuore/web/templates/cars.html").read_text(encoding="utf-8")))

# --- "/" never redirects, empty or not ----------------------------------------------------------
r = c.get("/")
check("/ is 200 (no redirect) with no car known", r.status_code == 200, str(r.status_code))
for b in data:
    check(f"brand tile: {b['key']}", f'data-brand="{b["key"]}"' in r.text and f'href="/cars?brand={b["key"]}"' in r.text)
check("three buttons, named for screen readers only", r.text.count('class="brand-tile') == 3
      and 'aria-label="Alfa Romeo"' in r.text and "bt-name" not in r.text)
check("no writing on the landing page", "Test: no real vehicle data" not in r.text and "bt-count" not in r.text
      and 'class="sr-only">Choose a brand' in r.text)
check("splash kept", "intro-overlay" in r.text and "The mechanic's own record of the car" in r.text)

# --- header: logo -> "/", no tagline, no leftover buttons, Menu is the navigation ----------------
check("header tagline removed", "top-tagline" not in r.text and "Passion and the joy of driving" not in r.text.split("<main")[0].split("intro-overlay")[-1].split("</header>")[0])
check("logo links to the brand picker", 'class="brand" href="/"' in r.text)
check("no leftover header buttons", not any(k in r.text for k in ("live-link", "facts-link", "parts-link")))
check("Menu offers Change brand and Change car", 'data-nav="home"' in r.text and 'data-nav="cars"' in r.text)

# --- Add a car -> existing intake; cars show on their brand only ---------------------------------
c.post("/start", data={"vin": ALFA, "complaint": "CEL, smells like gas", "technician": "t"})
c.post("/start", data={"vin": MASERATI, "complaint": "test visit", "technician": "t"})
r = c.get("/")
check("/ still the picker with cars in the bay", r.status_code == 200 and "brand-tile" in r.text)

a = c.get("/cars?brand=alfa")
check("alfa list 200, carries the Alfa car and the Add a car card",
      a.status_code == 200 and f'href="/v/{ALFA}/menu"' in a.text and 'href="/add?brand=alfa"' in a.text and "data-add-car" in a.text)
check("alfa list holds no Maserati car", f'href="/v/{MASERATI}/menu"' not in a.text)
check("alfa card: make, year from VIN, short VIN, state word",
      "Alfa Romeo" in a.text and "2018" in a.text and "…B88115" in a.text and "chip-verdict" in a.text)
check("alfa list says nothing about missing data", "Test: no real vehicle data" not in a.text)
check("alfa card shows the traced line art (Stelvio has art)", "<svg" in a.text.split("car-grid")[1])
check("change brand link back to /", 'class="cars-back" href="/"' in a.text)
check("brand is remembered for the session, tile highlighted", "cuore_brand" in a.headers.get("set-cookie", "")
      and 'class="brand-tile last"' in c.get("/").text)

m = c.get("/cars?brand=maserati")
check("maserati list: its own car, themed, with the test line",
      m.status_code == 200 and f'href="/v/{MASERATI}/menu"' in m.text and 'data-marque="maserati"' in m.text
      and "Test: no real vehicle data for this brand yet" in m.text and f'href="/v/{ALFA}/menu"' not in m.text)
check("a model without art gets a clean card, no invented drawing", "<svg" not in m.text.split("car-grid")[1])

f = c.get("/cars?brand=ferrari")
check("brand with no cars: plain empty state and Add a car",
      f.status_code == 200 and "No Ferrari cars yet" in f.text and 'href="/add?brand=ferrari"' in f.text
      and "Test: no real vehicle data for this brand yet" in f.text)
check("empty-state page also themed ferrari", '<html lang="en" data-marque="ferrari"' in f.text)

s = c.get(f"/cars?brand=alfa&q={ALFA[-6:]}")
check("search by VIN finds the car", f'href="/v/{ALFA}/menu"' in s.text)
s = c.get("/cars?brand=alfa&q=ZZZZZZZZZZZZZZZZZ")
check("unknown VIN offers to start a job for it", "/start?vin=ZZZZZZZZZZZZZZZZZ" in s.text)

# --- the logo goes to "/" even with a remembered brand and from a car page -----------------------
c.cookies.set("cuore_brand", "alfa")
for url in (f"/v/{ALFA}", f"/v/{ALFA}/codes", "/cars?brand=alfa", "/about", f"/m/{ALFA}"):
    rr = c.get(url)
    check(f"logo -> '/' on {url}" if url.startswith("/m/") is False else "mobile page reachable", rr.status_code == 200, str(rr.status_code))
    if not url.startswith("/m/"):
        check(f"logo link is '/' on {url}", 'class="brand" href="/"' in rr.text)
check("/ never redirects with a remembered brand", c.get("/").status_code == 200)

# --- car bar replaces the tab strip --------------------------------------------------------------
mp = c.get(f"/v/{ALFA}/menu")
check("the car opens on its Menu page, with no overlay copy", mp.status_code == 200 and "navsheet-page" in mp.text
      and mp.text.count('id="navsheet"') == 1 and 'data-nav="bench"' in mp.text and "navsheet-close" not in mp.text)
b = c.get(f"/v/{ALFA}").text
check("car page: Change car -> its brand list, search kept, no tab strip",
      'class="vchange" href="/cars?brand=alfa"' in b and 'class="vsearch"' in b and 'class="vtabs"' not in b)
check("no duplicate header tagline on car pages", "top-tagline" not in b)

# --- header: badge + wordmark, car name, Menu -- nothing else ------------------------------------
hdr = b.split("<header class=\"top\">")[1].split("</header>")[0]
before_sheet = hdr.split('id="navsheet"')[0]
check("header shows the car name in the display font slot", 'class="top-car"' in before_sheet)
check("header holds only brand, car name, Menu (no buttons, links, chips or labels)",
      before_sheet.count("<a ") == 1 and "icon-btn" not in before_sheet and "<button" not in before_sheet
      and "profile" not in before_sheet and "chip" not in before_sheet)
check("theme toggle and print live inside the Menu", 'id="theme-toggle"' in hdr.split('id="navsheet"')[1]
      and "window.print()" in hdr.split('id="navsheet"')[1])
check("search is reached from the Menu", 'role="search"' in hdr.split('id="navsheet"')[1])
check("no car name on the brand picker", 'class="top-car"' not in c.get("/").text)
check("Menu button is 56px+ tall and outlined, not an accent fill", re.search(r"\.top \.menu-btn \{[^}]*min-height: 56px[^}]*background: transparent", (ROOT / "cuore/web/static/cuore.css").read_text(encoding="utf-8")) is not None)

# --- unit: year from VIN, mark files -------------------------------------------------------------
check("model year from VIN position 10", landing_bridge.model_year(ALFA) == 2018 and landing_bridge.model_year("SHORT") is None)

# --- CSS: tokens only, 44px, no horizontal scroll at phone width ---------------------------------
css = (ROOT / "cuore/web/static/landing.css").read_text(encoding="utf-8")
check("landing.css uses no hex colours or raw px font sizes", not re.search(r"#[0-9a-fA-F]{3,8}\b|font-size:\s*\d+px", css))
check("touch targets use --tap", css.count("min-height: var(--tap)") >= 4)
check("grids never force a width wider than the phone", "minmax(min(100%, 300px), 1fr)" in css and "min(72vw, 280px)" in css)
check("motion respects reduced-motion", "prefers-reduced-motion" in css)

print(f"{checks} checks, {len(failures)} failures")
for x in failures:
    print("FAIL:", x)
sys.exit(1 if failures else 0)
