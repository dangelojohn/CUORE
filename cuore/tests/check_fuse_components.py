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

print(f"fuse_components checks: {passed} passed, {len(failures)} failed")
for f in failures:
    print("  FAIL:", f)
sys.exit(1 if failures else 0)
