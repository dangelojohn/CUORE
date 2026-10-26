"""Checks for the Components section of the Fuses & relays page: one icon + label per category, legend, ?cat= filter,
search (incl. synonyms), car drawing only for sourced areas, circuit links, no part numbers, photo only on a clear match.

Run:  .venv/Scripts/python.exe cuore/tests/check_fuse_components.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_fusecomp_")

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import components as cp  # noqa: E402
from cuore.services import fuse_direct as fd  # noqa: E402
from cuore.services import mes_bridge  # noqa: E402
from cuore.web import fuse_icons  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


fd.job_inputs = lambda vin, codes, dossier: ([], {})
mes_bridge.open_codes_for = lambda d: []
client = TestClient(create_app())
rows = cp.load()
data_raw = (Path(cp.DATA)).read_text(encoding="utf-8")
cats = {cp.cat_of(r) for r in rows}
t = client.get(f"/v/{VIN}/fuses").text
sec = t.split('id="fuse-components"', 1)[1].split('class="fuse-bottom"', 1)[0]

check(len(rows) == 145, "all 145 sourced rows copied")
check(set(fuse_icons.CATEGORIES) == set(cp.CATS) and len(cp.CATS) == 17, "17 categories, one icon each")
check(len({v for v in fuse_icons._P.values()}) == 17, "every category icon drawing is different")
for c in cp.CATS:
    check(f'<symbol id="ci-{c}"' in t, f"sprite has {c}")
    leg = sec.split('class="ci-legend"', 1)[1].split("</ul>", 1)[0]
    check(f'href="#ci-{c}"' in leg and f"<span>{cp.CATS[c][0]}</span>" in leg, f"legend: {c} icon + label")
for c in cats:
    h = sec.split(f'id="comp-cat-{c}"', 1)
    check(len(h) == 2 and f'href="#ci-{c}"' in h[1].split("</ul>", 1)[0] and cp.CATS[c][1] in h[1][:300], f"{c} group: icon + label")
    check(re.search(rf'<details class="comp-grp" id="comp-cat-{c}">\s*<summary class="comp-h">', sec) is not None, f"{c} group collapsed by default")
    check(f"cat={c}#fuse-components" in sec, f"chip for {c}")
check(sec.count('class="comp-row"') == len(rows), "every component listed")
check("location not sourced" in sec, "no-area rows say location not sourced")

# filter
tf = client.get(f"/v/{VIN}/fuses?cat=switch").text
sf = tf.split('id="fuse-components"', 1)[1].split('class="fuse-bottom"', 1)[0]
nsw = sum(1 for r in rows if r["category"] == "switch")
check(sf.count('class="comp-row"') == nsw and 'id="comp-cat-motor"' not in sf, "?cat=switch filters the list")
check('comp-chip on' in sf and "Show all 145" in sf, "active chip + show all")
check(client.get(f"/v/{VIN}/fuses?cat=zzz").text.count('class="comp-row"') == len(rows), "unknown cat ignored")

# search incl. synonyms
def res(q: str) -> str:
    x = client.get(f"/v/{VIN}/fuses", params={"q": q}).text
    return x.split('id="fuse-results"', 1)[1].split("</section>", 1)[0] if 'id="fuse-results"' in x else ""
motor = next(r for r in rows if r["category"] == "motor")
check('href="#comp-' in res(motor["name"].split()[0]), "q finds a component by name")
check('href="#comp-' in res("servo") and "Motor" in res("servo"), "servo -> motors/actuators")
check(any(cp.cat_of(r) == "switch" for r in cp.search("button", rows)), "button -> switch")
check(any(cp.cat_of(r) == "gauge_display" for r in cp.search("cluster", rows)), "cluster -> gauge/display")
check(any(cp.cat_of(r) == "lamp" for r in cp.search("bulb", rows)), "bulb -> lamp")
sv = cp.search("servo", rows)
check(bool(sv) and all(re.search(r"motor|actuator|servo", r["name"].lower()) and cp.cat_of(r) in ("motor", "actuator", "other") for r in sv),
      "servo -> only motor/actuator rows by name")
check(not any(re.search(r"thermostat|injector|coil|compressor|cooling fan", r["name"].lower()) for r in sv), "servo excludes thermostat/injector/coil/compressor/fan")
check(not any(cp.cat_of(r) in ("solenoid_valve", "pump") for r in sv), "servo excludes solenoids and pumps")
check(all(cp.cat_of(r) == "switch" or "button" in r["name"].lower() for r in cp.search("button", rows)) and cp.search("button", rows), "button -> switches only")
check(all(cp.cat_of(r) == "lamp" or "bulb" in r["name"].lower() for r in cp.search("bulb", rows)), "bulb -> lamps only")
check(bool(cp.search("MultiEcuScan", rows)) or bool(cp.search("brake pedal", rows)), "q finds source text")
check(bool(cp.search("rear left wheel well", rows)) and bool(cp.search("engine bay", rows)), "q finds area")
check(bool(cp.search("ECM", rows)), "q finds module")

# car drawing: only sourced areas
sourced = [r for r in rows if r.get("area")]
nullarea = [r for r in rows if not r.get("area")]
svg = t.split('id="fuse-map"', 1)[1].split("</section>", 1)[0]
marks = re.findall(r'<a class="fm-comp"[^>]*>.*?</a>', svg)
check(len(sourced) > 0 and len(nullarea) > 0, "fixture has both kinds")
check(len(marks) == 2 * len({(r["area"], r["category"]) for r in sourced if r["area"] in cp.AREA_VIEW}), "one cluster per area+category per view")
total_drawn = sum(int(re.search(r'class="fm-cnum"[^>]*>(\d+)<', m).group(1)) for m in marks) // 2
check(total_drawn == len(sourced), "drawn count == components with a sourced area")
for r in sourced:
    check(f'href="#ci-{r["category"]}"' in svg and f"area={r['area']}" in svg, f"{r['id']} drawn with its icon")
for r in nullarea:
    check(f'comp-{r["id"]}"' in sec, f"{r['id']} listed")
check(all('class="fm-comp"' not in m or "area=" in m for m in marks), "every drawn cluster links to its area")
ta = client.get(f"/v/{VIN}/fuses?area=engine_bay").text.split('id="fuse-components"', 1)[1].split('class="fuse-bottom"', 1)[0]
check(ta.count('class="comp-row"') == sum(1 for r in rows if r.get("area") == "engine_bay"), "?area= filters")

# circuit link
fl = next(r for r in rows if r["id"] == "rear_window_heater")
check("Also on this circuit" in t and 'href="#comp-rear_window_heater"' in t, "fuse row shows 'Also on this circuit'")
body = t.split('id="fuse-f47_interior"', 1)[1].split("</details>", 1)[0]
check("Also on this circuit" in body and "Rear window" in body or "rear window" in body.lower(), "F47 row lists the rear window heater")
check('href="#fuse-f47_interior"' in sec, "component links to its fuse")

# data hygiene
check(not re.search(r"\b\d{8}[A-Z]{2}\b|\b68\d{6}[A-Z]{0,2}\b|part_number|\"pn\"", data_raw), "no part numbers in the data file")
check(not re.search(r"\d{8}[A-Z]{2}|68\d{6}[A-Z]{0,2}|<code>", sec), "no part numbers shown")

# photo only on a clear match
cache: dict = {}
from cuore.services import component_images as ci  # noqa: E402
_real = ci.images_for
ci.images_for = lambda terms, **k: [{"name": "Rear Window Motor", "photo_url": "/x.png", "part_url": "/p", "pn": "X", "description": "", "diagram_id": "d"}]
check(cp.photo_for("Rear window motor", {}) is not None, "photo when part name contains every core word")
check(cp.photo_for("Washer pump", {}) is None, "no photo when the catalogue name differs")
ci.images_for = _real
check(cp.photo_for("Nothing here", {}) is None, "no catalogue -> no photo")
check("Mopar catalogue photo" not in sec or "the part, not this car" in sec, "photo caption")

# --- review fixes -------------------------------------------------------------------------------------------
from cuore.web import fuse_map_svg as fm  # noqa: E402
from cuore.web import fuse_routes as fr  # noqa: E402

css = (Path(__file__).resolve().parents[1] / "web/static/fuses.css").read_text(encoding="utf-8")
# collapsed groups / icon key / one-line rows
check('class="comp-grp" id="comp-cat-' in sec and 'comp-grp" id="comp-cat-switch" open' not in sec, "category groups are collapsed <details>")
check('id="comp-legend">' in sec and 'id="comp-legend" open' not in sec, "icon key folded")
check('<summary class="comp-main">' in sec and 'class="comp-body"' in sec, "row = one-line summary + own fold")
check(re.search(r"\.comp-main\s*\{[^}]*min-height:\s*56px", css) is not None, "row height ~56 px")
check("max-width: 700px" in css and "flex-wrap: nowrap; overflow-x: auto" in css, "category chips scroll in one row on narrow screens")
ts = client.get(f"/v/{VIN}/fuses?cat=switch").text.split('id="fuse-components"', 1)[1]
check('id="comp-cat-switch" open' in ts and 'id="comp-cat-motor" open' not in ts, "chip-selected group opens")
tq = client.get(f"/v/{VIN}/fuses", params={"q": "rear window"}).text.split('id="fuse-components"', 1)[1]
n_open = len(re.findall(r'comp-cat-\w+" open', tq))
check(0 < n_open < len(cats), "search-match groups open, others stay closed")

# distinct icons for the confusable pairs
for a_, b_ in (("actuator", "solenoid_valve"), ("relay", "fuse")):
    check(fuse_icons._P[a_] != fuse_icons._P[b_], f"{a_} vs {b_} icons differ")
check("<rect" in fuse_icons._P["fuse"] and fuse_icons._P["solenoid_valve"].count("v12") >= 3, "fuse blade outline, solenoid coil")

# search rows: icon + label + sans name, cap at 10 with Show all, clear header
r1 = res("window")
cr = re.findall(r'<a class="comp-res"[^>]*>.*?</a>', r1)
check(bool(cr) and all('href="#ci-' in x and 'class="comp-res-name"' in x for x in cr), "component result rows: category icon + name")
check(any(cp.CATS[cp.cat_of(r)][0] in cr[0] for r in rows), "component result rows: category label")
check(re.search(r'class="res-head">\d+ fuses? · \d+ components? match ‘window’', r1) is not None, "header count: fuses · components match 'window'")
rms = client.get(f"/v/{VIN}/fuses", params={"q": "a"}).text.split('id="fuse-results"', 1)[1].split("</section>", 1)[0]
nm = len(cp.search("a", rows, fd.SYNONYMS))
check(nm > 10 and len(re.findall(r'class="comp-res"', rms)) == 10 and f"Show all {nm}" in rms and "q=a" in rms and "all=1" in rms,
      "components capped at 10 + Show all N")
ra = client.get(f"/v/{VIN}/fuses", params={"q": "a", "all": "1"}).text.split('id="fuse-results"', 1)[1].split("</section>", 1)[0]
check(len(re.findall(r'class="comp-res"', ra)) == nm and "Show all" not in ra.split("Components (", 1)[1], "all=1 lists every component")
check(len(re.findall(r'<a href="#(?:fuse|ground)', rms)) <= 10, "fuse group capped at 10")

# area anchors + collision check
cl = fr._components_ctx(VIN, "", "", "", set())["clusters"]
boxes = [{"id": "engine_pdc", "short": "Engine power box", "side": None, "status": "green", "status_word": "OK", "count": 20},
         {"id": "interior_box", "short": "Interior fuse box", "side": "right", "status": "red", "status_word": "Blown", "count": 50},
         {"id": "rear_pdc", "short": "Rear power box", "side": None, "status": "grey", "status_word": "Not checked", "count": 9},
         {"id": "luggage_box", "short": "Luggage box", "side": "left", "status": "grey", "status_word": "Not checked", "count": 7}]
for view in ("side", "top"):
    pos = fm.comp_positions(cl, boxes, view)
    check(len(pos) == len([c for c in cl if c["view_area"] in fm._CPOS]), f"{view}: every cluster placed")
    fixed = fm._box_rects(boxes, view)
    bad = [(p["cluster"]["cat"], n) for p in pos for n, r in fixed if fm._hit(p["rect"], r, fm._CLEAR)]
    check(not bad, f"{view}: every cluster keeps >= {fm._CLEAR}px clear of box markers and labels {bad}")
    bad2 = [1 for i, p in enumerate(pos) for q_ in pos[i + 1:] if fm._hit(p["rect"], q_["rect"])]
    check(not bad2, f"{view}: no two clusters overlap")
    rear = [p for p in pos if p["cluster"]["view_area"] == "rear"]
    ub = [p for p in pos if p["cluster"]["view_area"] == "underbody"]
    check(bool(rear) and bool(ub), f"{view}: rear and underbody clusters exist")
    for p in rear:   # ESIM over the rear-left wheel arch, rear axle x=650
        if view == "side":
            check(abs(p["x"] - 650) <= 60 and 190 <= p["y"] <= 250, "side: rear cluster on the rear wheel arch")
        else:
            check(591 <= p["x"] <= 709 and 310 <= p["y"] <= 348, "top: rear cluster inside the left-rear wheel-arch box")
    for p in ub:
        if view == "side":
            check(300 <= p["y"] <= 330 and 258 < p["x"] < 591, "side: underbody below the sill, between the axles")
        else:
            check(199 < p["x"] < 650 and abs(p["y"] - 200) <= 70, "top: underbody on the centre line between the axles")
    check(any(p["label"] == "Underbody" for p in ub), f"{view}: underbody has its own label")
# the rear box label keeps >= 8 px off the ESIM marker and off the rear tyre (centre 650,269, radius 59)
import math  # noqa: E402
_b = [b for b in boxes if b["id"] == "rear_pdc"]
_lab = [r for n, r in fm._box_rects(_b, "side") if n.startswith("label:")]
check(all(math.hypot(max(r[0] - 650, 0, 650 - r[2]), max(r[1] - 269, 0, 269 - r[3])) >= 59 + 8 for r in _lab), "side: rear box label 8px clear of the rear tyre")
svg_s = fm.box_map(boxes, None, comps=cl)
check(svg_s.count(">Underbody<") == 2, "Underbody label drawn in both views")
# the nudge really moves a cluster that starts on a label
lab_box = [{"id": "x1", "short": "Rear power box", "side": None, "status": "grey", "status_word": "x", "count": 1, "area": "rear"}]
fm_save = fm._CPOS["rear"]["side"]
fm._CPOS["rear"]["side"] = (775, 262, (0,))
mv = fm.comp_positions(cl, lab_box, "side")
rr_ = [p for p in mv if p["cluster"]["view_area"] == "rear"][0]
check((rr_["x"], rr_["y"]) != (775, 262) and not any(fm._hit(rr_["rect"], r) for _, r in fm._box_rects(lab_box, "side")),
      "collision nudge clears a cluster started on a label")
fm._CPOS["rear"]["side"] = fm_save

# placeholder photos: shared file / logo hints excluded on the fuse page, kept for other callers
from cuore.services import parts_catalog as pcat  # noqa: E402
core: list[str] = []
for r in rows:
    tk = " ".join(cp.photo_terms(r["name"]))
    if tk and all(tk not in o and o not in tk for o in core):
        core.append(tk)
    if len(core) == 8:
        break
parts_ = [{"pn": f"FX-{i}", "name": c.title(), "description": "x", "fitment": "own", "photos": [{"file": "badge.jpg"}]}
          for i, c in enumerate(core[:6])]
parts_.append({"pn": "FX-REAL", "name": core[6].title(), "description": "x", "fitment": "own", "photos": [{"file": "real.jpg"}]})
parts_.append({"pn": "FX-LOGO", "name": core[7].title(), "description": "x", "fitment": "own", "photos": [{"file": "alfa-logo.png"}]})
_fake = {"diagrams": {"d1": {"parts": parts_}}}
_sv = (pcat.default_id, pcat.load)
pcat.default_id = lambda: "fx"
pcat.load = lambda *a, **k: _fake
ci._idx["sig"] = None
check(ci.is_placeholder("/catalog/img/fx/badge.jpg") and not ci.is_placeholder("/catalog/img/fx/real.jpg"), "is_placeholder: same file on >= 5 parts")
check(ci.is_placeholder("/catalog/img/fx/alfa-logo.png") and ci.is_placeholder({"photo_url": "/a.jpg", "name": "Placeholder"}),
      "is_placeholder: logo / placeholder hint")
t0 = core[0].split()
check(bool(ci.images_for(t0, limit=3, exclude_placeholders=False)) and not ci.images_for(t0, limit=3), "filter option: placeholders dropped by default, kept only when asked")
tp = client.get(f"/v/{VIN}/fuses").text
check("badge.jpg" not in tp and "alfa-logo.png" not in tp, "fuse page shows no placeholder photo")
check("/catalog/img/fx/real.jpg" in tp, "fuse page still shows a real part photo")
pcat.default_id, pcat.load = _sv
ci._idx["sig"] = None

# Showing chip + theme set before paint
_t = client.get(f"/v/{VIN}/fuses", params={"cat": "motor", "area": "engine_bay"}).text
check('id="comp-showing"' in _t and "Showing:" in _t and ">clear</a>" in _t, "?cat=&area= shows a Showing chip with clear")
check('id="comp-showing"' not in client.get(f"/v/{VIN}/fuses").text, "no Showing chip unfiltered")
check("of all" in _t, "chip counts labelled of all")
check(_t.find('localStorage.getItem("cuore-theme")') != -1 and _t.find('localStorage.getItem("cuore-theme")') < _t.find("<link rel=\"stylesheet\""), "saved theme applied in <head> before the stylesheets")

print(f"fuse_components checks: {passed} passed, {len(failures)} failed")
for f in failures:
    print("  FAIL:", f)
sys.exit(1 if failures else 0)
