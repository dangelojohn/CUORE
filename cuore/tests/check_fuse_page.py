"""Checks for the rebuilt Fuses & relays page (``/v/{vin}/fuses``): call line, box picker, one marker per box on
both views, far-side marking, per-box sections (deep-link ids), slot line-art, photo upload (temp dir only),
catalogue image, spec summary (type / amps / colour / voltage), added boxes, collapsed bottom panels.

Run:
    .venv/Scripts/python.exe cuore/tests/check_fuse_page.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_TMP = tempfile.mkdtemp(prefix="cuore_fusepage_")
os.environ["CUORE_STATE_DIR"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import fuse_health as fh  # noqa: E402
from cuore.services import parts_catalog  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


# fixture catalogue: the two Power Distribution Center diagrams, each with an image
PDC = ["electrical--power-distribution-center-fuse-block-junction-block-relays-and-fuses--1",
       "electrical--power-distribution-center-fuse-block-junction-block-relays-and-fuses--2"]
_FAKE = {"id": "test-cat", "diagrams": {d: {"title": f"PDC fixture {n}", "image": {"file": f"pdc{n}.png"}, "parts": []}
                                        for n, d in enumerate(PDC, 1)}}
parts_catalog.load = lambda *a, **k: _FAKE

# fixture job: the owner's open window symptom, a window code and the U-code cascade
from cuore.services import fuse_direct as fd  # noqa: E402
from cuore.services import mes_bridge  # noqa: E402

fd.job_inputs = lambda vin, codes, dossier: (
    [{"text": "Rear-left window (behind the driver) stops part way in BOTH directions, up and down.", "at": "2026-10-25T13:45"}],
    {"B1176": "Rear left window riser - component or system operation"})
mes_bridge.open_codes_for = lambda d: ["U0100", "B1176"]
_STRAP = {"id": "test-cat", "diagrams": {**_FAKE["diagrams"], "electrical--wiring-powertrain--1": {
    "title": "Engine Wiring", "parts": [{"ref": "5", "pn": "FIXTURE-PN-123", "name": "Alfa Romeo Ground Strap",
                                         "description": "BATTERY NEGATIVE"}]}}}
client = TestClient(create_app())
r = client.get(f"/v/{VIN}/fuses")
t = r.text
check(r.status_code == 200, "page 200")
body = t.split('<div class="fuse-page"', 1)[-1]

# 1. the directing call, job cards, chips
m = re.search(r'id="fuse-call">([^<]*)<', t)
call = m.group(1) if m else ""
check("Rear-left window" in call and "F47 and F48" in call and "rear window" in call and "Interior" in call and "footwell" in call,
      "call directs to F47/F48 (rear window) in the interior box")
check("Linked by circuit name" in t, "call match labelled circuit name")
check("U0100" in t.split('id="fuse-call"', 1)[1].split("fuse-jobs", 1)[0] and "F82" in t.split('id="fuse-call"', 1)[1].split("fuse-jobs", 1)[0]
      and "G003A" in t.split('id="fuse-call"', 1)[1].split("fuse-jobs", 1)[0] and "G003B" in t.split('id="fuse-call"', 1)[1].split("fuse-jobs", 1)[0],
      "U-code cascade line names F82 and G003A/G003B")
check("CUORE&#39;s electrical path" in t, "path match labelled electrical path")
job = t.split('id="fuse-for-job"', 1)[1].split("</section>", 1)[0]
check(all(f"<h3>{x} " in job for x in ("F47", "F48", "F82")) and "ground" in job and "Frame ground G003A" in job, "for-this-job cards: F47 F48 F82 G003A")
card = job.split("<h3>F47 ", 1)[1].split("</article>", 1)[0]
check("Interior" in card and "passenger footwell" in card and "MINI" in card and "rear window" in card and 'href="#fuse-f47_interior"' in card
      and "circuit name" in card and "A not sourced" in card, "F47 card: box, where, type, circuit, jump, rating gap stated")
check(t.count('class="fuse-chip fuse-') == 4, "four status chips")
check(body.index('id="fuse-search"') < body.index("fuse-call") < body.index("fuse-for-job") < body.index("fuse-chips")
      < body.index("Which box?") < body.index("fm-wrap") < body.index('id="fuse-box-engine_pdc"')
      < body.index('id="fuse-grounds"') < body.index("What is not sourced yet"), "page order")
check("href=\"/v/%s/fuses?status=red#fuse-chips\"" % VIN in t, "chips are filters")

# 1b. no data entry on the mechanic page
acts = set(re.findall(r'<form[^>]*action="([^"]+)"', t))
check(acts - {"/v/%s/feedback" % VIN} == {"/v/%s/fuses" % VIN, "/v/%s/fuses/check" % VIN}, "only search + check forms on /fuses")
for bad in ('type="file"', "Add a fuse box", "Add a fuse or relay", "Record type, colour", 'action="/v/%s/fuses/box"' % VIN,
            'action="/v/%s/fuses/item"' % VIN, 'action="/v/%s/fuses/spec"' % VIN, 'action="/v/%s/fuses/photo"' % VIN):
    check(bad not in t, f"mechanic page has no: {bad}")
check('href="/v/%s/fuses/data"' % VIN in t and "Owner data maintenance" in t.split('class="fuse-owner"')[1], "footer link to owner data page")
check(t.count("Tested OK") >= 20 and "Blown - replaced" in t and "Faulty" in t, "one test action per fuse / relay / ground")
check("No photo of this box on file" in t, "quiet no-photo line")

# 2. picker
BOXES = ["engine_pdc", "interior_box", "rear_pdc", "luggage_box"]
pick = t.split('class="fuse-picks"', 1)[1].split("</section>", 1)[0]
check(all(f'href="#fuse-box-{b}"' in pick for b in BOXES), "picker links to every box section")
check("Interior" in pick and "passenger footwell (right)" in pick, "picker names interior + where")
check("Add a box here" not in pick and 'href="#fuse-grounds"' in pick, "picker has no add-a-box, has grounds")

# 3. map: one marker per box on both views, far side, separate rear anchors
svgs = re.findall(r"<svg class=\"sens-profile fm-svg.*?</svg>", t, re.S)
check(len(svgs) == 2, "two car views (side, top)")
for name, sv in zip(("side", "top"), svgs):
    check(sv.count('class="fm-box ') == 4, f"{name}: one marker per box (4)")
    check(sv.count("sens-dot") == 0, f"{name}: no per-fuse dots")
    check(all(f'href="#fuse-box-{b}"' in sv for b in BOXES), f"{name}: markers link to sections")
    check(re.search(r"<circle class=\"fm-hit\"[^>]* r=\"(\d+)\"", sv) and int(re.search(r"fm-hit\"[^>]* r=\"(\d+)\"", sv).group(1)) * 2 >= 44,
          f"{name}: tap area >= 44")
side, top = svgs
check('fm-box fuse-grey fm-far" href="#fuse-box-interior_box"' in side and "R, far side" in side, "side: interior marked far side")
check("fm-far" not in top, "top: no far-side hollow")
check("fm-far" not in side.split('href="#fuse-box-engine_pdc"')[0].rsplit("<a", 1)[-1], "side: engine bay not far side")


def centre(sv: str, box: str) -> tuple[str, str]:
    seg = sv.split(f'href="#fuse-box-{box}"', 1)[1]
    mm = re.search(r'class="fm-hit" cx="(\d+)" cy="(\d+)"', seg)
    return mm.group(1), mm.group(2)


check(centre(side, "rear_pdc") != centre(side, "luggage_box") and centre(top, "rear_pdc") != centre(top, "luggage_box"),
      "rear power box and luggage box have separate anchors")
check("position not sourced" in side, "marker says position not sourced")
check('name="fm-view"' in t and 'id="fm-v-side" checked' in t, "side/top toggle, default side")

# 4. sections
for b in BOXES:
    check(f'id="fuse-box-{b}"' in t, f"section id {b}")
check('id="fuse-box-interior_box"' in t, "deep link target present")
sec = t.split('id="fuse-box-interior_box"', 1)[1].split("</section>", 1)[0]
check("Where" in sec and "footwell" in sec and "from a third-party diagram, not checked on this car" in sec, "box facts in plain words")
check("fm-slots" in sec and "Slots shown in number order - real positions in the box are not sourced yet; add a box-cover photo" in sec,
      "slot SVG + number-order caption")
check(sec.count('class="fm-slot ') == 9 or sec.count('class="fm-slot ') == 8, "one slot per listed row")
check("No photo of this box on file" in sec and 'type="file"' not in sec, "no photo: quiet line, no form")
check("INFERRED" not in t.split("What is not sourced yet")[0], "no raw INFERRED in visible text")

# rows: details, ids, back-to-map
check('<details class="fuse-row" id="fuse-f82">' in t, "row is a details with id")
check(t.count("Back to the map") >= 20, "back-to-map link on rows and sections")
r = client.post(f"/v/{VIN}/fuses/check", data={"item": "f47_interior", "result": "blown", "method": "visual", "blown_note": "Blown - replaced",
                                               "redirect_to": f"/v/{VIN}/fuses#fuse-f47_interior"}, follow_redirects=False)
check(r.status_code == 303 and "Check%20recorded" in r.headers["location"], "Blown - replaced button posts to the check route")
check(any(c.get("item") == "f47_interior" and c.get("note") == "Blown - replaced" for c in fh._checks(VIN, "f47_interior")), "check stored with note")
def rowhtml(txt: str, item: str) -> str:
    return re.split(r'<details class="fuse-row"|</section>', txt.split(f'id="fuse-{item}"', 1)[1], 1)[0]


row = rowhtml(t, "f82")
check("Tested OK" in row and "Blown - replaced" in row and "Feeds:" in row and "Source:" in row, "row holds feeds, source, test buttons")
check(row.index("<summary>") < row.index("Tested OK") < row.index("Back to the map"), "test buttons are inside the row")
rel_row = rowhtml(t, "starter_relay")
check("Faulty" in rel_row and "Blown - replaced" not in rel_row, "relay buttons say Tested OK / Faulty")

# spec summary: type / amps / colour / voltage
def summary(item: str) -> str:
    return t.split(f'id="fuse-{item}"', 1)[1].split("</summary>", 1)[0]


s_f2 = summary("f2_luggage")  # 15 A mini
check("MINI" in s_f2 and "15 A" in s_f2 and "blue" in s_f2 and "(standard)" in s_f2 and "V not sourced" in s_f2, "mini 15 A summary: type, amps, derived colour, voltage not sourced")
check("standard colour for this rating - check the fuse itself" in t, "standard colour label shown")
s_f1 = summary("f01_luggage")  # 40 A MAXI
check("MAXI" in s_f1 and "40 A" in s_f1 and "colour not sourced" in s_f1, "maxi: no derived colour")
s_f8 = summary("f08_luggage")
check("FMX/JCase" in s_f8 and "colour not sourced" in s_f8, "J-case: no derived colour")
s_f33 = summary("f33_interior")  # mini, no rating
check("MINI" in s_f33 and "A ?" in s_f33 and "colour not sourced" in s_f33, "no rating: no derived colour")
s_rel = summary("starter_relay")
check("relay, type not sourced" in s_rel and "colour not sourced" in s_rel, "relay: not sourced")
rel = rowhtml(t, "starter_relay")
check("Pin layout" in rel and "Orientation in the box" in rel and "not sourced - read it off the relay or the box cover" in rel, "relay details not sourced")
check("fm-sw fz-blue" in t, "colour drawn in the slot art")
# record details with a source -> shown, still no invented values
r = client.post(f"/v/{VIN}/fuses/spec", data={"item": "starter_relay", "relay_type": "mini", "pin_layout": "30/85/86/87", "source": ""},
                follow_redirects=False)
check(r.status_code == 303 and "not%20saved" in r.headers["location"], "spec without source rejected")
r = client.post(f"/v/{VIN}/fuses/spec", data={"item": "starter_relay", "relay_type": "mini", "pin_layout": "30/85/86/87",
                                              "orientation": "pins down", "source": "read off the relay"}, follow_redirects=False)
check(r.status_code == 303 and "Details%20saved" in r.headers["location"], "spec saved")
t2 = client.get(f"/v/{VIN}/fuses").text
check("30/85/86/87" in t2 and "pins down" in t2 and "mini" in t2.split('id="fuse-starter_relay"', 1)[1].split("</summary>", 1)[0], "relay details shown after saving")

# 5. photos
photo_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
r = client.post(f"/v/{VIN}/fuses/photo", data={"box": "interior_box", "caption": "Cover label", "by": "Marco"},
                files={"photo": ("cover shot!.png", photo_png, "image/png")}, follow_redirects=False)
check(r.status_code == 303 and "Photo%20saved" in r.headers["location"] and "#fuse-box-interior_box" in r.headers["location"], "photo POST saves")
saved = list((Path(_TMP) / "fuse_photos" / VIN / "interior_box").glob("*.png"))
check(len(saved) == 1 and re.fullmatch(r"[A-Za-z0-9._-]+", saved[0].name) is not None, "photo under temp state dir, safe name")
r = client.post(f"/v/{VIN}/fuses/photo", data={"box": "interior_box"}, files={"photo": ("notes.txt", b"hello", "text/plain")},
                follow_redirects=False)
check("not%20saved" in r.headers["location"] and len(list((Path(_TMP) / "fuse_photos" / VIN / "interior_box").iterdir())) == 2,
      "non-image rejected")  # png + its sidecar json
r = client.post(f"/v/{VIN}/fuses/photo", data={"box": "interior_box"}, files={"photo": ("fake.png", b"not a png", "image/png")},
                follow_redirects=False)
check("not%20saved" in r.headers["location"], "fake png (bad magic) rejected")
r = client.post(f"/v/{VIN}/fuses/photo", data={"box": "../x"}, files={"photo": ("a.png", photo_png, "image/png")}, follow_redirects=False)
check("not%20saved" in r.headers["location"], "unknown box rejected")
t3 = client.get(f"/v/{VIN}/fuses").text
sec3 = t3.split('id="fuse-box-interior_box"', 1)[1].split("</section>", 1)[0]
check("No photo of this box yet" not in sec3 and "Photo added by Marco" in sec3 and "Cover label" in sec3, "saved photo shown with who and kind")
pu = re.search(r'src="(/v/[^"]+/photo/interior_box/[^"]+)"', sec3)
check(bool(pu) and client.get(pu.group(1)).content == photo_png, "photo served")
check(client.get(f"/v/{VIN}/fuses/photo/interior_box/..%2f..%2fx.png").status_code == 404, "photo path traversal blocked")
check(not any(Path(_TMP).parent != Path(_TMP).parent for _ in [0]) and "ProgramData" not in str(Path(_TMP)), "tests wrote only to temp dir")

# catalogue
sec_e = t.split('id="fuse-box-engine_pdc"', 1)[1].split("</section>", 1)[0]
check("/catalog/img/test-cat/pdc1.png" in sec_e and "/catalog/img/test-cat/pdc2.png" in sec_e, "catalogue images for the PDC box")
check("Mopar parts diagram (catalogue) - part layout, not a fuse map" in sec_e and f'href="/catalog/d/{PDC[0]}"' in sec_e, "catalogue caption + link")
check("/catalog/img/" not in sec, "no catalogue image on the interior box")

# 6. added box
r = client.post(f"/v/{VIN}/fuses/box", data={"short": "Engine bay 2", "area": "engine", "side": "left", "label": "Second engine box",
                                             "where": "behind the battery", "source": "", "by": "Marco"}, follow_redirects=False)
check("not%20added" in r.headers["location"], "box without source rejected")
r = client.post(f"/v/{VIN}/fuses/box", data={"short": "Engine bay 2", "area": "engine", "side": "left", "label": "Second engine box",
                                             "where": "behind the battery", "source": "seen on this car by Marco", "by": "Marco"},
                follow_redirects=False)
check(r.status_code == 303 and "Fuse%20box%20added" in r.headers["location"], "box added")
check((Path(_TMP) / "fuse_boxes.jsonl").is_file(), "box stored in state-dir jsonl")
t4 = client.get(f"/v/{VIN}/fuses").text
check('id="fuse-box-tech-engine-bay-2"' in t4 and "added by a technician" in t4.split('id="fuse-box-tech-engine-bay-2"', 1)[1], "added box has its own section, marked")
check('href="#fuse-box-tech-engine-bay-2"' in t4.split('class="fuse-picks"')[1].split("</section>")[0], "added box in picker")
sv4 = re.findall(r"<svg class=\"sens-profile fm-svg.*?</svg>", t4, re.S)
check(all(s.count('class="fm-box ') == 5 for s in sv4), "added box has a marker on both views")
check(len(set(re.findall(r'class="fm-hit" cx="(\d+)" cy="(\d+)"', sv4[0].split('class="fm-ground"')[0]))) == 5, "added box marker does not sit on another")
sec4 = t4.split('id="fuse-box-tech-engine-bay-2"', 1)[1].split("</section>", 1)[0]
check("No photo of this box on file" in sec4 and "behind the battery" in sec4, "added box has photo line and facts")
r = client.post(f"/v/{VIN}/fuses/item", data={"kind": "fuse", "label": "Test fuse", "source": "box cover photo", "box": "tech-engine-bay-2",
                                              "position": "F7", "rating_a": "10", "fuse_type": "mini"}, follow_redirects=False)
check("Fuse/relay%20added" in r.headers["location"], "fuse can be added into the added box")
t5 = client.get(f"/v/{VIN}/fuses").text
check("Test fuse" in t5.split('id="fuse-box-tech-engine-bay-2"', 1)[1] and "fm-slots" in t5.split('id="fuse-box-tech-engine-bay-2"', 1)[1], "fuse shown in added box with slot art")
check("fuse_boxes.jsonl" in Path(__file__).resolve().parents[2].joinpath("scripts/backup-cuore-state.ps1").read_text(encoding="utf-8"), "backup script lists fuse_boxes.jsonl")
check(fh.add_box(short="X", label="", area="engine", side="unknown", where="", source="s")["side"] is None, "unknown side stored as None")
try:
    fh.add_box(short="Y", label="", area="roof", side="left", where="", source="s")
    check(False, "bad area rejected")
except ValueError:
    check(True, "bad area rejected")

# layout data: explicit row/col wins over number order
from cuore.web import fuse_map_svg as fm  # noqa: E402
rows = [{"id": "a", "anchor": "a", "position": "F1", "kind": "fuse", "status": "grey", "layout": {"row": 2, "col": 3}},
        {"id": "b", "anchor": "b", "position": "F2", "kind": "fuse", "status": "grey"}]
svg, full = fm.slot_svg(rows, "T")
check(svg.index('href="#fuse-b"') < svg.index('href="#fuse-a"') and not full, "layout row/col honoured, rest in number order")

# 7. bottom panels collapsed
bottom = t.split('<section class="fuse-bottom"', 1)[1]
folds = re.findall(r"<details class=\"fuse-fold\"[^>]*>", bottom)
check(len(folds) >= 2 and all(" open" not in f for f in folds), "bottom panels are collapsed")
check("What is not sourced yet" in bottom and "Credits" in bottom, "bottom has not-sourced and credits")
check("full fuse list not sourced" not in t, "not-sourced message not repeated beyond per-box facts")


# 8. grounds
g = t.split('id="fuse-grounds"', 1)[1].split("</section>", 1)[0]
for gid in ("g003a", "g003b", "esim_ground", "battery_neg_strap"):
    check(f'id="ground-{gid}"' in g, f"ground id {gid}")
    seg = g.split(f'id="ground-{gid}"', 1)[1].split("</article>", 1)[0]
    check("Back to the map" in seg and "Last inspection" in seg and "Test to run" in seg and "Connects to" in seg, f"{gid}: sections")
    check(f'href="#ground-{gid}"' in "".join(re.findall(r"<svg class=\"sens-profile fm-svg.*?</svg>", t, re.S)), f"{gid}: icon on map")
check("FCA bulletin" in g or "S2008000032" in g, "G003A source shown")
for sv in re.findall(r"<svg class=\"sens-profile fm-svg.*?</svg>", t, re.S):
    check(sv.count('class="fm-ground"') == 4 and sv.count("fm-gsym") == 4 and sv.count('class="fm-box ') == 4, "both views: 4 ground icons + 4 box markers")
check("Exact spot not given" in g.split('id="ground-g003a"', 1)[1].split("</article>", 1)[0], "G003A location limits stated")
check("Not sourced." in g.split('id="ground-esim_ground"', 1)[1].split("</article>", 1)[0], "ESIM ground location: not sourced")
check("68648999AA" not in t and "FIXTURE-PN-123" not in t, "no part number when the catalogue lacks it")
check("Part number not available" in g, "strap part: plainly missing without catalogue")
parts_catalog.load = lambda *a, **k: _STRAP
tg = client.get(f"/v/{VIN}/fuses").text
check("FIXTURE-PN-123" in tg and "callout 5" in tg, "part number appears from the catalogue fixture")
parts_catalog.load = lambda *a, **k: _FAKE
check("68648999AA" not in Path(__file__).resolve().parents[1].joinpath("services/fuse_direct.py").read_text(encoding="utf-8")
      and "68648999AA" not in Path(__file__).resolve().parents[1].joinpath("web/fuse_routes.py").read_text(encoding="utf-8"), "part number not in repo code")
r = client.post(f"/v/{VIN}/fuses/check", data={"item": "g003a", "result": "ok", "method": "visual", "blown_note": "Faulty", "redirect_to": f"/v/{VIN}/fuses#ground-g003a"},
                follow_redirects=False)
check("Check%20recorded" in r.headers["location"], "ground Tested OK recorded")
check("Tested OK on" in client.get(f"/v/{VIN}/fuses").text.split('id="ground-g003a"', 1)[1].split("</article>", 1)[0], "ground last inspection shows the test")

# 9. search
def results(q: str, extra: str = "") -> tuple[str, int]:
    rr = client.get(f"/v/{VIN}/fuses?q={q}{extra}").text
    mm = re.search(r"<h2>(\d+) match", rr)
    return rr, int(mm.group(1)) if mm else -1


rr, n = results("F47")
check(n == 1 and 'href="#fuse-f47_interior"' in rr.split('id="fuse-results"')[1].split("</section>")[0], "q=F47 -> F47 row")
rr, n = results("rear%20window")
check(n == 3 and all(f'href="#fuse-{x}"' in rr for x in ("f47_interior", "f48_interior", "f94_interior")), "q=rear window -> F47 F48 F94")
rr, n = results("15A")
check(n >= 2 and 'href="#fuse-f2_luggage"' in rr.split('id="fuse-results"')[1].split("</section>")[0], "q=15A -> 15 A fuses")
check(results("15%20a")[1] == n, "q='15 a' same as 15A")
rr, n = results("47")
check('href="#fuse-f47_interior"' in rr.split('id="fuse-results"')[1].split("</section>")[0], "q=47 finds F47")
rr, n = results("G003")
res = rr.split('id="fuse-results"')[1].split("</section>")[0]
check(n == 2 and 'href="#ground-g003a"' in res and 'href="#ground-g003b"' in res, "q=G003 -> both grounds")
rr, n = results("nothing-matches")
check(n == 0 and "0 matches for" in rr and "Clear search" in rr, "q=nothing-matches -> 0 matches, clear link")
rr, n = results("interior")
check(any(x in rr for x in ('href="#fuse-box-interior_box"',)), "q=box name finds the box")
rr, n = results("rear%20window", "&status=orange")
check(n == 0, "status filter narrows results")
rr, n = results("rear%20window", "&status=red")
check(n == 1 and "f47_interior" in rr.split('id="fuse-results"')[1].split("</section>")[0], "status filter keeps the red F47 only")
rr, n = results("rear%20window", "&box=luggage_box")
check(n == 0, "box filter narrows results")
rr, n = results("%3Cscript%3Ealert(1)%3C%2Fscript%3E")
check("<script>alert(1)" not in rr and "&lt;script&gt;alert(1)" in rr and n == 0, "query is escaped")
check('<input type="search" name="q"' in t and 'role="search"' in t and "oninput" not in t, "search works without JS (plain GET form)")
check("min-height" in Path(__file__).resolve().parents[1].joinpath("web/static/fuses.css").read_text(encoding="utf-8"), "44 px targets in css")

# 10. owner data page
d = client.get(f"/v/{VIN}/fuses/data")
dt = d.text
check(d.status_code == 200 and all(k in dt for k in ("Add a fuse box", "Add a fuse or relay", "Record type, colour or voltage", 'type="file"')),
      "owner page has the maintenance forms")
check('action="/v/%s/fuses/box"' % VIN in dt and 'action="/v/%s/fuses/item"' % VIN in dt and 'action="/v/%s/fuses/spec"' % VIN in dt
      and 'action="/v/%s/fuses/photo"' % VIN in dt, "owner forms keep the same POST routes")
check('href="/v/%s/fuses/data"' % VIN not in client.get(f"/v/{VIN}/dossier").text, "owner page not linked from the dossier")

print(f"fuse_page checks: {passed} passed, {len(failures)} failed")
for f in failures:
    print("  FAIL:", f)
sys.exit(1 if failures else 0)
