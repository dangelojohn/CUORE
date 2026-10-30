"""Checks for the wiring harness maps page (``/v/{vin}/harnesses``).

The catalogue is a fixture in a temp dir (CUORE_STATE_DIR); the real ProgramData
catalogue is never read for content assertions.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_harnesses.py
"""
from __future__ import annotations

import json
from html import escape
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
check('id="hn-call"' in html and "harness diagrams" in html and "What this page is" not in html, "call line at the top")
check(len(DATA["harnesses"]) == 9, "nine harness entries in the data file")

v = svc.view(VIN)
svg = svc.map_svg(v["harnesses"])
for h in DATA["harnesses"]:
    hid = h["id"]
    check(h["areas"] and all(a in {x["id"] for x in DATA["areas"]} for a in h["areas"]), f"{hid}: areas known")
    low = h.get("confidence_level") == "low"
    m = re.search(rf'data-harness="{re.escape(hid)}">.*?</g>', svg, re.S)
    if low:
        check(f'data-harness="{hid}"' not in svg, f"{hid}: low confidence, no route drawn")
    else:
        check(bool(m) and 'class="hn-line"' in m.group(0) and 'class="hn-arrow"' in m.group(0), f"{hid}: route line + arrow")
    check(f'id="harness-{hid}"' in html, f"{hid}: card")
    check(h["confidence"] and h["direction"] and h["ends"], f"{hid}: confidence, direction and ends stated")
    check(all(f"/catalog/d/{d}" in html for d in h["diagram_ids"]), f"{hid}: link to the catalogue diagram")
check(html.count('class="hn-line"') == 7 and html.count('class="hn-arrow"') == 7, "7 lines, 7 arrows (2 low-confidence not drawn)")
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
check(r2.status_code == 200 and "not built on this computer" in r2.text and r2.text.count('class="hn-line"') == 7,
      "page renders without a catalogue")

# links from the electrical page and the More list
check(f"/v/{VIN}/harnesses" in client.get(f"/v/{VIN}/electrical").text, "electrical page links to harnesses")
from cuore.web import nav_items as _nav  # noqa: E402
check(any(i["key"] == "harnesses" and not i["primary"] for i in _nav.ITEMS), "Menu sheet has Harnesses")

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
check(len(re.findall(r'class="hn-card[ "]', client.get(f"/v/{VIN}/harnesses?q=door").text)) == 9, "cards stay without JavaScript")


# --- rebuild: call, fold, low confidence, labels, rows, summaries, zoom, parts, 44 px -------------------------
from cuore.web import harness_routes as hroutes  # noqa: E402

lows = [h["id"] for h in DATA["harnesses"] if h.get("confidence_level") == "low"]
check(set(lows) == {"instrument-panel-body", "console"}, "two low-confidence harnesses flagged in the data")
for hid in lows:
    card = re.search(rf'<article class="hn-card[^"]*" id="harness-{hid}".*?</article>', html, re.S).group(0)
    check('class="chip hollow">unresolved' in card, f"{hid}: hollow unresolved chip")
    check("No route drawn" in card, f"{hid}: says no route is drawn")
    check(f'data-harness="{hid}"' not in html, f"{hid}: no drawn route in the page")
check("areas, not paths" in html, "'areas, not paths' next to the routes")

# no overlapping label boxes
boxes = svc.label_layout([a for a in v["areas"]])
for i, a in enumerate(boxes):
    for b in boxes[i + 1:]:
        sep = a["x1"] + 1 <= b["x0"] or b["x1"] + 1 <= a["x0"] or a["y1"] <= b["y0"] or b["y1"] <= a["y0"]
        check(sep, f"label boxes distinct: {a['id']} / {b['id']}")
svg_boxes = re.findall(r'class="hn-lbox" data-area="([^"]+)" x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)"', svg)
check(len(svg_boxes) == len({a for h in v["harnesses"] if not h["low"] for a in [x["id"] for x in h["route"]]}),
      "one label box per drawn area")
rects = [(int(x), int(y), int(x) + int(w), int(y) + int(hh)) for _, x, y, w, hh in svg_boxes]
check(all(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
          for i, a in enumerate(rects) for b in rects[i + 1:]), "rendered label rectangles do not overlap")

# one-line summaries: route + chip, details in one fold, caption once per card
for h in v["harnesses"]:
    card = re.search(rf'<article class="hn-card[^"]*" id="harness-{h["id"]}".*?</article>', html, re.S).group(0)
    check(card.count('class="hn-sum"') == 1 and escape(h["summary"]) in card, f"{h['id']}: one-line summary")
    check(card.count("<details class=\"hn-more\"") == 1, f"{h['id']}: details in one fold")
    check(card.count("Mopar parts diagram - harness as drawn") == 1, f"{h['id']}: caption once")
    check("<b>Direction:</b>" not in card and "<dt>Direction</dt>" in card, f"{h['id']}: direction inside the fold")
check(html.count("Not shown in the diagram:") == 9, "not-shown line only where there is something")

# empty-harness fold: harnesses touching nothing sit behind a fold
m = re.search(r'<details class="hn-bare" id="hn-bare"[^>]*><summary[^>]*>(.*?)</summary>(.*?)<p class="hn-foot">', html, re.S)
check(bool(m) and "7 harnesses that touch nothing CUORE knows" in m.group(1), "empty harnesses behind a fold with a count")
linked_ids = {"headlamp-to-dash", "engine"}
check(bool(m) and all(f'id="harness-{x}"' not in m.group(2) for x in linked_ids)
      and all(f'id="harness-{h["id"]}"' in m.group(2) for h in DATA["harnesses"] if h["id"] not in linked_ids),
      "only the two linked harnesses sit outside the fold")
check("2 of the 9 harness diagrams link to anything CUORE knows" in html, "honest count of connected harnesses")

# whole rows are links, 44 px
area_rows = re.findall(r'<a class="row" href="#harness-[^"]+">', re.search(r'id="hn-by-area".*?</div>', html, re.S).group(0))
check(len(area_rows) >= 8, "By area rows are links")
by_item = re.search(r'By fuse box, sensor or electrical item.*?</div>', html, re.S).group(0)
check(by_item.count('<a class="row"') == by_item.count('class="row"') >= 2, "By item rows are links")
css = (ROOT / "cuore/web/static/harnesses.css").read_text(encoding="utf-8")
check("min-height: var(--tap, 44px)" in css and ".hn-key a" in css, "44 px rows and swatch links")
check(not re.search(r".hn-(?!area|num)[w-]+[^{]*{[^}]*font-size: (1[0-5]|[0-9])(.d+)?px", css.split("/* --- mechanic-first")[1]), "no text under 16 px in the rebuild css")

# enlarge + caption + door parts dedupe (fixture: same ref/name twice with two part numbers)
check('class="hn-zoomlink"' in html and 'class="hn-zoom"' in html and "Tap the picture to enlarge" in html, "tap to enlarge")
dd = svc.dedupe_parts([{"ref": "1", "name": "Front Door Wiring, Left", "description": "", "pn": "A1"},
                       {"ref": "1", "name": "Front Door Wiring, Left", "description": "", "pn": "A2"},
                       {"ref": "1", "name": "Front Door Wiring, Right", "description": "FRONT DOOR", "pn": "B1"},
                       {"ref": "2", "name": "Wiring Rear Door", "description": "Wiring Rear Door", "pn": "C1"}])
check(len(dd) == 3 and dd[0]["pns"] == ["A1", "A2"], "door parts deduped, part numbers merged")
check([r["side"] for r in dd] == ["left", "right", ""], "side marked only when the catalogue text says so")

# the directing call, from a fixture job (pure function)
hv = v["harnesses"]
def fake_path(c):
    return {"path": {"B9": [{"element": "battery", "role": "supply"}],
                     "B8": [{"element": "bcm", "role": "controller"}, {"element": "window_riser_circuit", "role": "component"}],
                     "P1": [{"element": "ecm", "role": "controller"}]}.get(c, [])}
items = [{"id": "f1", "box": "engine_pdc", "position": "F1", "label": "x", "feeds_elements": ["bcm"]}]
d1 = svc.direct(VIN, hv, [], v["elem_labels"], [], ["B9"], {"B9": "Battery thing"}, fake_path)
check(d1["order"] == ["engine"] and "Look at harness 9, Engine Wiring, first" in d1["call"], "call: element on the path names the harness")
d2 = svc.direct(VIN, hv, items, v["elem_labels"], [], ["B8"], {}, fake_path)
check(d2["order"] == ["headlamp-to-dash"] and "PDC" in d2["hits"]["headlamp-to-dash"][0], "call: fuse box on the path names the harness")
d3 = svc.direct(VIN, hv, [], v["elem_labels"], [{"text": "Front left window stops"}], [], {}, fake_path)
check(d3["order"] == ["front-door-left"], "call: symptom words name the left front door harness")
d4 = svc.direct(VIN, hv, [], v["elem_labels"], [{"text": "Rear-left window stops part way"}], ["B8"], {"B8": "Rear left window riser"}, fake_path)
check(d4["order"] == [] and d4["call"].startswith("No open job points to a harness - harness maps are areas, not wiring paths"),
      "call: rear window does not point at the front door harness")
check(d4["instead"] and d4["instead"]["href"] == f"/v/{VIN}/electrical#el-window_riser_circuit", "'what to do instead' links the electrical item")
d5 = svc.direct(VIN, hv, [], v["elem_labels"], [], [], {}, fake_path)
check("No open job" in d5["call"] and d5["instead"] is None, "call: no job at all")
check("2 of the 9" in d1["stat"], "stat counts linked harnesses")

# the page uses the job inputs: matched card goes first, call + go-to chip + reason
orig = hroutes._inputs
hroutes._inputs = lambda vin, dossier: (["B9"], [], {"B9": "Battery thing"}, fake_path, [])
th = client.get(f"/v/{VIN}/harnesses").text
cs = re.search(r'id="hn-call".*?</section>', th, re.S).group(0)
check("Look at harness 9, Engine Wiring, first" in cs and 'class="chip hn-gochip" href="#harness-engine"' in cs, "page call + go-to chip from the job")
check("Why these?" in cs and "on the open job" in th, "why fold + card chip")
check(th.index('id="harness-engine"') < th.index('id="harness-headlamp-to-dash"'), "matched harness listed first")
hroutes._inputs = orig

# --- review fixes: title call, badges/labels clear, top-view title, search first + highlight, folds ----------------
import math  # noqa: E402
check('class="hn-callline"' in html and 'href="https://' not in html and "Nothing on this job needs a harness - follow the electrical path for" in html
      or "No open job - nothing points to a harness" in html, "call is the card title")
check(re.search(r'class="hn-callline">.*?</h2>', html, re.S) is not None and "Counts" not in html[:0] and 'class="hn-stat"' in html.split('class="hn-why"')[1], "counts sit in the fold")
check("Top view only" in html, "map titled Top view only")
lay = svc.route_layout(v["harnesses"])
check(len(lay) == 7, "layout for 7 drawn harnesses")
for i, a in enumerate(lay):
    for b in lay[i + 1:]:
        check(math.dist(a["badge"], b["badge"]) >= 2 * svc.BADGE_R + 2, f"badges {a['n']}/{b['n']} do not overlap")
    for o in lay:
        if o is not a:
            dmin = min(svc._seg_dist(*a["badge"], o["pts"][k], o["pts"][k + 1]) for k in range(len(o["pts"]) - 1))
            check(dmin >= svc.BADGE_R + 3, f"badge {a['n']} clear of route {o['n']}")
            check(math.dist(a["badge"], o["end"]) >= svc.BADGE_R + 8, f"badge {a['n']} clear of arrow {o['n']}")
    check(all(svc.BADGE_R <= c <= lim for c, lim in zip(a["badge"], (svc.MAP_W, svc.MAP_H))), f"badge {a['n']} inside the map")
for b in boxes:   # no leader runs through a label box nearer the car
    for o in boxes:
        if o is not b and o["side"] == b["side"] and o["row"] < b["row"]:
            check(not (o["x0"] - 2 <= b["x"] <= o["x1"] + 2), f"leader of {b['id']} clear of label {o['id']}")
for a in lay:   # badges never sit on a label box
    for b in boxes:
        check(not (b["x0"] <= a["badge"][0] <= b["x1"] and b["y0"] - svc.BADGE_R <= a["badge"][1] <= b["y1"] + svc.BADGE_R),
              f"badge {a['n']} off label {b['id']}")
check(svg.count('class="hn-badge"') == 7, "seven badges, none matched without a search")
check(len({(round(l["start"][0]), round(l["start"][1])) for l in lay}) == 7, "no two routes start at the same point")

tq = client.get(f"/v/{VIN}/harnesses?q=door").text
check(tq.index('id="hn-results"') < tq.index('id="hn-call"'), "matches sit above the call card")
check('class="hn-route hn-match" data-harness="front-door-left"' in tq and 'class="hn-badge hn-match" data-harness="front-door-left"' in tq,
      "matched harness route and badge are highlighted")
check('hn-route hn-match" data-harness="engine"' not in tq, "unmatched routes are not highlighted")
check("closest('a[href^=\"#harness-\"]')" in html and "details.hn-more" in html, "hash/tap opens the target card's fold")
check('<summary class="hn-fold">7 harnesses that touch nothing' in html and ".hn-bare > summary::after" in css, "bare fold has a chevron summary")
check(".hn-key { grid-template-columns: 1fr; }" in css and "hn-brk" in html, "legend one column, unresolved chip on its own line")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
