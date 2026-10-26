"""Checks for the wiring harness maps page (``/v/{vin}/harnesses``).

The catalogue is a fixture in a temp dir (CUORE_STATE_DIR); the real ProgramData
catalogue is never read for content assertions.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_harnesses.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="cuore_hn_"))
os.environ["CUORE_STATE_DIR"] = str(TMP)

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


DATA = json.loads((ROOT / "cuore/data/harnesses_stelvio_2018.json").read_text(encoding="utf-8"))
CID = "stelvio-2018-2.0l"
FAKE_PN = "ZZ9999FIX01"
diagrams = {}
for i, h in enumerate(DATA["harnesses"]):
    for did in h["diagram_ids"]:
        img = f"{i:020x}.png"
        (TMP / "parts_catalog" / CID / "img").mkdir(parents=True, exist_ok=True)
        (TMP / "parts_catalog" / CID / "img" / img).write_bytes(b"\x89PNG\r\n")
        diagrams[did] = {"id": did, "slug": "s", "group": "electrical", "title": h["title"], "image": {"file": img},
                         "parts": [{"ref": "1", "pn": FAKE_PN, "name": f"Fixture part {i}", "description": "Fixture"}]
                         if i % 2 == 0 else []}
(TMP / "parts_catalog" / CID / "catalog.json").write_text(json.dumps({
    "id": CID, "title": "fixture", "groups": [], "sections": [], "diagrams": diagrams}), encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import harnesses as svc  # noqa: E402

client = TestClient(create_app(), follow_redirects=False)
VIN = "ZASFAKPN5J7B88115"

r = client.get(f"/v/{VIN}/harnesses")
html = r.text
check(r.status_code == 200, f"page renders ({r.status_code})")
check('id="hn-call"' in html and "harness diagrams" in html, "call line at the top")
check(len(DATA["harnesses"]) == 9, "nine harness entries in the data file")

v = svc.view(VIN)
svg = svc.map_svg(v["harnesses"])
for h in DATA["harnesses"]:
    hid = h["id"]
    check(h["areas"] and all(a in {x["id"] for x in DATA["areas"]} for a in h["areas"]), f"{hid}: areas known")
    check(f'data-harness="{hid}"' in svg, f"{hid}: route on the map")
    m = re.search(rf'data-harness="{re.escape(hid)}">.*?</g>', svg, re.S)
    check(bool(m) and 'class="hn-line"' in m.group(0) and 'class="hn-arrow"' in m.group(0), f"{hid}: route line + arrow")
    check(f'id="harness-{hid}"' in html, f"{hid}: card")
    check(h["confidence"] and h["direction"] and h["ends"], f"{hid}: confidence, direction and ends stated")
    check(all(f"/catalog/d/{d}" in html for d in h["diagram_ids"]), f"{hid}: link to the catalogue diagram")
check(html.count('class="hn-line"') == 9 and html.count('class="hn-arrow"') == 9, "9 lines, 9 arrows")
check("Mopar parts diagram - harness as drawn for parts, not a wiring diagram" in html, "image caption")
check("service manual" in html and "CUORE does not have" in html, "pin-level wiring note")
check(f"/v/{VIN}/electrical" in html, "link to electrical")

imgs = re.findall(r'<img src="([^"]+)" alt="Mopar', html)
check(len(imgs) == 9 and all(i.startswith(f"/catalog/img/{CID}/") for i in imgs), "images come from /catalog/img")
check(client.get(imgs[0]).status_code == 200, "an image URL resolves")
check(FAKE_PN in html, "part numbers come from the runtime catalogue")

# related links resolve
hrefs = set(re.findall(r'href="(/v/[^"#]+(?:#[^"]+)?)"', html))
boxes = {b["id"] for b in json.loads((ROOT / "cuore/data/fuses_stelvio_2018.json").read_text(encoding="utf-8"))["boxes"]}
sens = {s["id"] for s in json.loads((ROOT / "cuore/data/sensors_stelvio_2018.json").read_text(encoding="utf-8"))["sensors"]}
for h in DATA["harnesses"]:
    for b in h["related"]["fuse_boxes"]:
        check(b in boxes and f"/v/{VIN}/fuses#fuse-box-{b}" in hrefs, f"fuse box link {b}")
    for s in h["related"]["sensors"]:
        check(s in sens and f"/v/{VIN}/sensors#sensor-{s}" in hrefs, f"sensor link {s}")
    for e in h["related"]["elements"]:
        check(any(x["id"] == e for h2 in v["harnesses"] for x in h2["related"]["elements"]), f"electrical element {e} resolves")
for path in ("fuses", "sensors", "electrical"):
    check(client.get(f"/v/{VIN}/{path}").status_code == 200, f"related page /{path} renders")

# repo data file: no catalogue data
raw = (ROOT / "cuore/data/harnesses_stelvio_2018.json").read_text(encoding="utf-8")
check(not re.search(r'"pn"|\b[0-9]{8}[A-Z]{0,2}\b|\.png|https?://', raw), "no part numbers, images or URLs in the repo json")

# no catalogue at all: page still renders, says so
os.environ["CUORE_STATE_DIR"] = str(TMP / "empty")
r2 = client.get(f"/v/{VIN}/harnesses")
check(r2.status_code == 200 and "not built on this computer" in r2.text and r2.text.count('class="hn-line"') == 9,
      "page renders without a catalogue")

# links from the electrical page and the More list
check(f"/v/{VIN}/harnesses" in client.get(f"/v/{VIN}/electrical").text, "electrical page links to harnesses")
tabs = (ROOT / "cuore/web/templates/_vtabs.html").read_text(encoding="utf-8")
check('vtab("harnesses"' in tabs, "More list has Harnesses")

# --- page search -----------------------------------------------------------
def hsrch(qs):
    t = client.get(f"/v/{VIN}/harnesses{qs}").text
    m = re.search(r'id="hn-results".*?</section>', t, re.S)
    return t, (m.group(0) if m else "")


t, sec = hsrch("?q=ac-module")
check('href="#harness-ac-module"' in sec and "1 match for" in sec and 'id="harness-ac-module"' in t, "search by id jumps to the card")
check('id="hn-search"' in t and 'type="search"' in t, "search box at the top")
t, sec = hsrch("?q=door")
check('href="#harness-front-door-left"' in sec, "door finds the door harness")
t, sec = hsrch("?q=headlight")
check('href="#harness-headlamp-to-dash"' in sec, "synonym headlight finds headlamp harness")
t, sec = hsrch("?q=air+conditioning")
check('href="#harness-ac-module"' in sec, "synonym air conditioning finds the A/C module")
t, sec = hsrch("?q=hvac")
check('href="#harness-ac-module"' in sec, "synonym hvac finds the A/C module")
t, sec = hsrch("?q=instrument+panel")
check('href="#harness-instrument-panel"' in sec, "instrument panel found")
t, sec = hsrch("?q=dash")
check('href="#harness-instrument-panel"' in sec, "synonym dash finds instrument panel")
t, sec = hsrch("?q=seat")
check('href="#harness-seat-left"' in sec, "seat found")
t, sec = hsrch("?q=door+seat")
check("No match for" in sec, "both words must hit")
t, sec = hsrch("?q=zzzz")
check("No match for" in sec and "Try an area or part word" in sec and "Clear search" in t, "no-match hint + clear link")
t, sec = hsrch("?q=<img src=x onerror=1>")
check("<img src=x" not in t and "&lt;img" in t, "query is escaped")
check(client.get(f"/v/{VIN}/harnesses?q=" + "x" * 500).status_code == 200, "long q is safe")
check('id="hn-results"' not in client.get(f"/v/{VIN}/harnesses").text, "no results block without q")
check(len(re.findall(r'class="hn-card"', client.get(f"/v/{VIN}/harnesses?q=door").text)) == 9, "cards stay without JavaScript")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
