"""Checks for the touch-first top menu (cuore/web/nav_items.py, _navsheet.html; the tab strip is gone).
Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_nav_menu.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-nav-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.services import accounts  # noqa: E402
from cuore.web import accounts_routes, nav_items  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def build():
    app = create_app()
    app.include_router(accounts_routes.router)
    return TestClient(app, follow_redirects=False, raise_server_exceptions=False)


TOKEN = "nav-token-123"
Path(_TMP, "web_token.txt").write_text(TOKEN, encoding="utf-8")
c = build()
c.get(f"/login?token={TOKEN}")

# --- 1. data source -----------------------------------------------------------------------------
keys = [i["key"] for i in nav_items.ITEMS]
check("item keys are unique", len(keys) == len(set(keys)))
check("every item has a known group", all(i["group"] in nav_items.GROUPS for i in nav_items.ITEMS))
check("exactly the everyday 9 are primary", {i["key"] for i in nav_items.ITEMS if i["primary"]}
      == {"bench", "job", "codes", "liveboard", "tests", "systems", "sensors", "fuses", "report"})
for must in ("home", "cars", "start", "witech-recording", "adjustments", "power-budget", "inbox", "procedures", "accounts"):
    check(f"item present: {must}", must in keys)
src = (ROOT / "cuore/web/nav_items.py").read_text(encoding="utf-8")
for added in ("arrive-ready", "warranty-pack", "field-quality"):   # live since 2026-10-30
    check(f"item present: {added}", added in keys and not re.search(rf"^\s*# _i\(\"{added}\"", src, re.M))

# --- 2. vehicle page renders every item ---------------------------------------------------------
r = c.get(f"/v/{VIN}/job")
check("vehicle page 200", r.status_code == 200, str(r.status_code))
html = r.text
menu = nav_items.nav_menu(VIN, "job", "admin", f"/v/{VIN}/job")
allitems = [i for g in menu["groups"] for i in g["items"]]
check("menu has items for every group, read by task", [g["title"] for g in menu["groups"]] == list(nav_items.GROUPS)
      and list(nav_items.GROUPS) == ["Cars", "Diagnose", "Look up", "Service", "Records", "Shop"])
for it in allitems:
    check(f"tile on vehicle page: {it['key']}", f'href="{it["href"]}"' in html and f'data-nav="{it["key"]}"' in html
          or it["key"] == "accounts", it["href"])
check("exactly one Menu button in header", html.count('class="menu-btn') == 1 and 'for="navsheet-toggle"' in html)
check("current page tile highlighted", 'data-nav="job"' in html and re.search(r'class="navtile ni-job on[ "][^>]*aria-current="page"', html) is not None)
check("sheet is labelled for screen readers", 'aria-label="All CUORE pages"' in html and "<h2" in html)
check("old hidden header menu gone", 'class="navmenu"' not in html and "vmore-tab" not in html)
check("tab strip is gone", 'class="vtabs"' not in html and "vtab-all" not in html)
check("header leftovers (Live link, Facts, Parts buttons) are gone",
      not any(c in html for c in ("live-link", "facts-link", "parts-link")))
check("car bar: Change car link, brand picker via the logo, search kept",
      'class="vchange"' in html and 'class="brand" href="/"' in html and 'class="vsearch"' in html)
check("everyday pages are drawn stronger in the Menu",
      all(re.search(rf'class="navtile [^"]*navtile-main[^"]*"[^>]*data-nav="{k}"', html)
          for k in ("bench", "job", "codes", "liveboard", "tests", "systems", "sensors", "fuses", "report")))
sheet = html.split('id="navsheet"')[1].split("</header>")[0]
check("More is a plain <details>/<summary> fold (works with no JavaScript)",
      '<details class="navmore"><summary' not in sheet and '<details class="navmore">' in sheet
      and 'class="navmore-sum">More</summary>' in sheet and sheet.count("<details") == 1 and "onclick" not in
      sheet.replace('onclick="window.print()"', ""))
check("Facts and Parts catalogue tiles live in the Menu (Look up)",
      'data-nav="facts"' in html and 'data-nav="catalog"' in html)

# --- 2b. new structure: top row, open count, More, no loss ------------------------------------------
TOP_ORDER = ["bench", "scan", "codes", "liveboard", "job", "electrical", "report", "cars"]
OLD_KEYS = {  # every ITEMS key before the 2026-10-31 rebuild: none may be dropped
    "home", "cars", "start", "bench", "job", "codes", "liveboard", "tests", "diagnosis", "tree", "gate",
    "crosschecks", "intermittent", "trends", "power-budget", "systems", "sensors", "fuses", "electrical",
    "harnesses", "modules", "gauges", "configuration", "service-hub", "adjustments", "witech-recording",
    "parity", "parts", "mods", "procedures", "tsb", "report", "dossier", "timeline", "recordings", "scans",
    "scan", "media", "labels", "inbox", "dashboard", "logs", "mobile", "facts", "vehicles", "catalog",
    "g-tsb", "slvt", "tools", "live", "hardware", "coverage", "cables", "g-modules", "g-recordings",
    "g-logs", "settings", "accounts", "about", "arrive-ready", "warranty-pack", "car-session", "bay-sheet",
    "field-quality", "library", "handbook"}
check("nothing lost from ITEMS", OLD_KEYS <= set(keys), str(OLD_KEYS - set(keys)))
check("every tile has a plain one-line sub under 40 characters",
      all(0 < len(i["sub"]) < 40 for i in nav_items.ITEMS), str([i["key"] for i in nav_items.ITEMS if not 0 < len(i["sub"]) < 40]))
mm = nav_items.nav_menu(VIN, "", "admin", "")
check("top row order with a car open", [i["key"] for i in mm["top"]] == TOP_ORDER, str([i["key"] for i in mm["top"]]))
check("tiles open between 12 and 17 with a car (top row included)", 12 <= mm["open_count"] <= 17, str(mm["open_count"]))
more_keys = {i["key"] for g in mm["more_groups"] for i in g["items"]}
for k in ("procedures", "witech-recording", "parity", "field-quality", "accounts", "about", "cables", "hardware", "facts",
          "library", "vehicles", "dashboard", "home", "start", "g-tsb", "g-logs", "g-recordings", "scans", "car-session"):
    check(f"in More with a car: {k}", k in more_keys)
open_keys = {i["key"] for i in mm["top"]} | {i["key"] for g in mm["open_groups"] for i in g["items"]}
check("open + More is every visible item, once", open_keys | more_keys == {i["key"] for g in mm["groups"] for i in g["items"]}
      and not (open_keys & more_keys))
check("shop-wide TSB not open with a car; TSB for this car is", "g-tsb" not in open_keys and "tsb" in open_keys)
check("What could not be read tile is open and points at the not-read list",
      "unread" in open_keys and any(i["key"] == "unread" and i["href"] == f"/v/{VIN}/modules#module-lead" for g in mm["open_groups"] for i in g["items"]))
check("Next step row always shows with a car (five-minute test when the flow has none)",
      f'href="/v/{VIN}/five-minute"' in html or "data-nav-next=" in html)
nv = nav_items.nav_menu(None, "", "admin", "")
check("no car: Cars first (Brands, Change car, Add Service)", [i["key"] for i in nv["top"]] == ["home", "cars", "start"])
check("no car: no per-car tile", all(not i["per_car"] for g in nv["groups"] for i in g["items"]))
check("renamed labels", {i["key"]: i["label"] for i in nav_items.ITEMS if i["key"] in ("home", "service-hub", "gate", "crosschecks", "coverage")}
      == {"home": "Brands", "service-hub": "Service resets", "gate": "Ready to repair?", "crosschecks": "Readings agree?", "coverage": "What can be read"})
for k, label in (("service-hub", "Service resets"), ("gate", "Ready to repair?"), ("crosschecks", "Readings agree?")):
    check(f"t() does not override the new label: {k}", re.search(rf'data-nav="{k}"[^>]*>.*?<span class="navlabel">{re.escape(label)}', html.replace("&#34;", '"'), re.S) is not None)
check("tile markup: icon, label, sub", re.search(r'<a class="navtile ni-bench[^"]*" href="[^"]+" data-nav="bench"[^>]*><svg class="navico" aria-hidden="true"><use href="[^"]*nav_icons.svg[^"]*#ni-bench"></use></svg><span class="navlabel">Bench</span><small class="navsub">[^<]+</small></a>', html) is not None)
check("top row is the first block after Next step, no visible heading",
      re.search(r'class="navnext".*?<h2 id="navsec-everyday" class="sr-only">.*?<ul class="navtiles navtop">', html, re.S) is not None)
check("search field, Close, theme toggle kept", 'id="navsheet-q"' in html and 'for="navsheet-toggle" class="navtile navsheet-close"' in html and 'id="theme-toggle"' in html)
for it in nav_items.ITEMS:   # every page answers 200 (per-car with the test car, global as is)
    href = nav_items.resolve_href(it, VIN)
    if href and it["key"] != "accounts":
        rr = c.get(href)
        check(f"ITEMS href answers 200: {href}", rr.status_code == 200, str(rr.status_code))
for page, link in ((f"/v/{VIN}/scan", f"/v/{VIN}/scans"), (f"/v/{VIN}/recordings", "/recordings"), (f"/v/{VIN}/modules", "/modules"),
                   (f"/logs?vin={VIN}", "/logs"), (f"/tsb?vin={VIN}", "/tsb")):
    check(f"history/all-cars link on {page}", f'href="{link}"' in c.get(page).text)

# --- 3. no vehicle: only shop tiles ---------------------------------------------------------------
r = c.get("/about")
check("global page 200", r.status_code == 200)
check("no per-car tiles without a vehicle", f"/v/{VIN}" not in r.text.split('id="navsheet"')[1].split("</main>")[0]
      and 'data-nav="job"' not in r.text)
check("shop tiles present without a vehicle", all(f'data-nav="{k}"' in r.text for k in ("home", "cars", "start", "facts", "catalog", "settings", "about")))

# --- 4. every route href returns 200 --------------------------------------------------------------
seen = set()
for it in allitems:
    if it["href"] in seen or it["key"] == "accounts":
        continue
    seen.add(it["href"])
    rr = c.get(it["href"])
    check(f"GET {it['href']} -> 200", rr.status_code == 200, str(rr.status_code))

# --- 5. CSS: tile sizes and menu button -----------------------------------------------------------
css = (ROOT / "cuore/web/static/cuore.css").read_text(encoding="utf-8")
m = re.search(r"\.top \.menu-btn \{[^}]*\}", css)
check("Menu button >= 56px tall", m is not None and "min-height: 56px" in m.group(0))
m = re.search(r"\.navtile \{[^}]*\}", css)
check("tile >= 72px tall, >= 120px wide, --fs-lg label",
      m is not None and "min-height: 72px" in m.group(0) and "min-width: 120px" in m.group(0)
      and "font-size: var(--fs-lg)" in m.group(0))
m = re.search(r"\.navtiles \{[^}]*\}", css)
_mm = re.search(r"minmax\((\d+)px", m.group(0)) if m else None
check("tile gap >= 12px and grid columns >= 120px", m is not None and "gap: 14px" in m.group(0)
      and _mm is not None and int(_mm.group(1)) >= 120)
check("sheet is full screen via :checked, no JS", ".navsheet-toggle:checked ~ .navsheet" in css and "inset: 0" in css)
check("current tile style exists", ".navtile.on" in css)

# --- 6. Accounts tile role gating -----------------------------------------------------------------
accounts.create("boss", "correct horse 1", "admin", "Boss", "main", "dealer")
accounts.create("lead1", "lead password 1", "shop_lead", "Lead", "shopA", "independent")
accounts.create("tech1", "tech password 1", "technician", "Tech", "shopA", "independent")
accounts.set_mode(True)


def page_as(user, pw):
    cl = build()
    cl.post("/login", data={"username": user, "password": pw, "next": "/"})
    return cl.get(f"/v/{VIN}/job")


for u, pw, want in (("boss", "correct horse 1", True), ("lead1", "lead password 1", True),
                    ("tech1", "tech password 1", False)):
    rr = page_as(u, pw)
    check(f"{u}: page 200", rr.status_code == 200, str(rr.status_code))
    check(f"{u}: Accounts tile {'shown' if want else 'hidden'}", ('data-nav="accounts"' in rr.text) == want)
anon = build().get("/about")
check("anonymous: no Accounts tile", 'data-nav="accounts"' not in anon.text)
check("role filter in data layer", all(i["key"] != "accounts" for g in nav_items.nav_menu(VIN, "", "technician", "")["groups"] for i in g["items"])
      and any(i["key"] == "accounts" for g in nav_items.nav_menu(VIN, "", "shop_lead", "")["groups"] for i in g["items"]))

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
