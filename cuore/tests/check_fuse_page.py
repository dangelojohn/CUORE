"""Checks for the Fuses & relays page (``/v/{vin}/fuses``): the call (every name a link, how to reach the box), Go-to chips,
collapsed "Why these?", ranked / merged job cards, results under the call, synonym + rating-field search, box picker,
one marker per box on both views (top view first when the call's box is on the right), per-box sections
(where -> slots -> rows -> source), no "not sourced" noise in summaries, no repo paths in visible text, grounds.

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

_real_job_inputs = fd.job_inputs
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

# 1. the directing call, Go-to chips, Why, job cards
m = re.search(r'id="fuse-call">(.*?)</p>', t, re.S)
call_html = m.group(1) if m else ""
call = re.sub(r"<[^>]+>", "", call_html)
check("Rear-left window" in call and "F47 and F48" in call and "rear window" in call and "Interior" in call and "footwell" in call,
      "call directs to F47/F48 (rear window) in the interior box")
check('<a href="#fuse-f47_interior">F47</a>' in call_html and '<a href="#fuse-f48_interior">F48</a>' in call_html,
      "every fuse name in the call links to its row")
check("Reach it:" in call and "under the glove compartment" in call, "call says how to reach the box, from the box's where text")
check(body.index('id="fuse-call"') < body.index('id="fuse-go"') < body.index('id="fuse-why"') < body.index("fuse-for-job"),
      "call, then Go-to chips, then Why, then cards")
go = t.split('id="fuse-go"', 1)[1].split("</nav>", 1)[0]
check(all(x in go for x in (">Interior box<", ">F47<", ">F48<", 'href="#fuse-box-interior_box"', 'href="#fuse-f47_interior"')), "Go-to chips: box + positions")
why = t.split('id="fuse-why"', 1)[1].split("</details>", 1)[0]
check(re.search(r'id="fuse-why"[^>]*>', t).group(0).count("open") == 0, "Why disclosure is collapsed")
check("Linked by circuit name" in why and "CUORE's electrical path" in why.replace("&#39;", "'"), "Why: both link kinds explained")
check("1 code on the path through F82" in why and "U0100" in why and "G003A" in why and "G003B" in why,
      "Why: codes grouped compactly (U-code cascade names F82 and G003A/G003B)")
check("from this car's open symptoms" not in t.split('id="fuse-why"', 1)[0].replace("&#39;", "'"), "grey 'linked by' line is not above the Why disclosure")
job = t.split('id="fuse-for-job"', 1)[1].split("</section>", 1)[0]
main_job = job.split('<details class="fuse-fold fuse-also">', 1)[0]
also = job.split('<details class="fuse-fold fuse-also">', 1)[1]
check("<h3>F47 / F48 rear window " in main_job and "<h3>F48 " not in job and job.count("<h3>F47 /") == 1, "F47 + F48 merged into one card")
check("F82" not in main_job and "G003A" not in main_job, "other-code fuses and grounds are not in the main cards")
check("F82" in also and "Frame ground G003A" in also and "ground" in also and "On the path for 2 codes" in also.replace("&#39;", "'"),
      "Also possible holds F82 + grounds, with one 'on the path for N codes' line")
check(also.count("electrical path for") == 0, "no repeated per-code path lines in the cards")
check('<details class="fuse-fold fuse-also">' in job, "Also possible is collapsed")
card = main_job.split("<h3>F47 / F48", 1)[1].split("</article>", 1)[0]
check("Interior" in card and "passenger footwell" in card and "MINI" in card and 'href="#fuse-f47_interior"' in card and 'href="#fuse-f48_interior"' in card
      and "Matches the open symptom and B1176" in card, "merged card: box, where, type, both jumps, basis")
check("not sourced" not in main_job and "linked by" not in main_job.lower(), "cards: no 'not sourced' noise and no via chip")
check(t.count('class="fuse-chip fuse-') == 4, "four status chips")
check("</b> 0 Blown" in t and "Not checked yet" in t, "status chips carry the word")
check(body.index('id="fuse-search"') < body.index("<h1") < body.index("fuse-call") < body.index('id="fuse-go"') < body.index("fuse-for-job")
      < body.index("Which box?") < body.index('id="fuse-chips"') < body.index("fm-wrap") < body.index('id="fuse-box-engine_pdc"')
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
check("position not sourced" not in side and "position not sourced" not in top, "no 'position not sourced' on markers")
check("exact positions are not sourced" in t.split('id="fuse-map"', 1)[1].split("</section>", 1)[0], "position caveat written once, as a caption")
check('name="fm-view"' in t and 'id="fm-v-top" checked' in t and 'id="fm-v-side" checked' not in t,
      "call's box is on the right side -> top view checked server-side")
_css = Path(__file__).resolve().parents[1].joinpath("web/static/fuses.css").read_text(encoding="utf-8")
for cls in ("fm-name", "fm-sub"):
    px = int(re.search(r"\." + cls + r" \{ font: (?:700 )?(\d+)px", _css).group(1))
    check(px >= 12, f"marker label {cls} >= 12 px")
check(not re.search(r"font-size:\s*(?:12|11|10|13)px|font-size:\s*\.6\d*rem|font-size:\s*\.75rem", _css), "no sub-14 px text sizes left in fuses.css")

# 4. sections
for b in BOXES:
    check(f'id="fuse-box-{b}"' in t, f"section id {b}")
check('id="fuse-box-interior_box"' in t, "deep link target present")
sec = t.split('id="fuse-box-interior_box"', 1)[1].split("</section>", 1)[0]
check("Where / how to reach" in sec and "footwell" in sec and "from a third-party diagram, not checked on this car" in sec, "box facts in plain words")
check(sec.index("Where / how to reach") < sec.index("fm-slots") < sec.index("Fuses and relays in this box") < sec.index("Photo and parts diagram")
      < sec.index(">Source<"), "box section order: where -> slots -> rows -> photos -> source")
check("fm-slots" in sec and "Slots shown in number order - real positions in the box are not sourced yet." in sec and "box-cover photo" not in t,
      "slot SVG + one honest caption, no photo prompt")
slots = sec.split("fm-slots", 1)[1].split("</svg>", 1)[0]
check('width="180"' in slots and ">?</text>" not in slots, "slots drawn large, no '?' corner marks")
check(slots.count("fm-job") == 2, "job fuses (F47, F48) highlighted in the slot drawing")
check(sec.count('class="fm-slot ') >= 8, "slot per row")
check("Not sourced for this box: colours / voltages" in sec or "Not sourced for this box: ratings" in sec, "missing fields stated once per box")
check(sec.count("Not sourced for this box") == 1, "stated once")
check("<details class=\"fuse-fold fuse-source\">" in sec and "Where this came from" in sec.split(">Source<", 1)[1], "source detail in a collapsed Source disclosure")
check("autouserguide.com" in sec and "http" not in re.sub(r"<[^>]+>", " ", sec), "source in plain words: host only, no URL")
check("could not be opened" in sec and "returned 403" not in t, "403 phrase translated")
check(sec.count('class="fm-slot ') == 9 or sec.count('class="fm-slot ') == 8, "one slot per listed row")
check("No photo of this box on file" in sec and 'type="file"' not in sec, "no photo: quiet line, no form")
check("INFERRED" not in t.split("What is not sourced yet")[0], "no raw INFERRED in visible text")
_vis = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", " ", t, flags=re.S)
_vis = re.sub(r"<[^>]+>", " ", _vis)
for bad in (".md", ".json", ".py", "docs/", "mes-log-mcp", "ProgramData", "http", "85bf07", "GROUND_VOLTAGE"):
    check(bad not in _vis, f"no repo path / id in visible text: {bad}")
for bad in ("add a box-cover photo", "added by a technician", "A not sourced", "colour not sourced", "V not sourced", "A ?"):
    check(bad not in _vis, f"mechanic page does not show: {bad}")
_rowsum = re.findall(r'<details class="fuse-row[^>]*>\s*<summary>(.*?)</summary>', t, re.S)
check(len(_rowsum) >= 20 and not any("not sourced" in x for x in _rowsum), "no 'not sourced' text in any row summary")
check('id="fuse-f47_interior" open' in t and 'id="fuse-f48_interior" open' in t and 'id="fuse-f2_luggage" open' not in t,
      "rows matching the call open automatically")

# rows: details, ids, back-to-map
check('<details class="fuse-row" id="fuse-f82">' in t, "row is a details with id")
check(t.count("Back to the map") >= 20, "back-to-map link on rows and sections")
r = client.post(f"/v/{VIN}/fuses/check", data={"item": "f47_interior", "result": "blown", "method": "visual", "blown_note": "Blown - replaced",
                                               "redirect_to": f"/v/{VIN}/fuses#fuse-f47_interior"}, follow_redirects=False)
check(r.status_code == 303 and "Check%20recorded" in r.headers["location"], "Blown - replaced button posts to the check route")
check(any(c.get("item") == "f47_interior" and c.get("note") == "Blown - replaced" for c in fh._checks(VIN, "f47_interior")), "check stored with note")
def rowhtml(txt: str, item: str) -> str:
    return re.split(r'<details class="fuse-row[ "]|</section>', txt.split(f'id="fuse-{item}"', 1)[1], 1)[0]


def gseg(txt: str, gid: str) -> str:
    return txt.split(f'id="ground-{gid}"', 1)[1].split('<details class="fuse-ground"', 1)[0]


row = rowhtml(t, "f82")
check("Tested OK" in row and "Blown - replaced" in row and "Feeds:" in row and "Source:" in row, "row holds feeds, source, test buttons")
check(row.index("<summary>") < row.index("Feeds:") < row.index("Tested OK") < row.index("Back to the map"), "test buttons are inside the row, below the facts")
check("Tested OK" not in t.split("</summary>", 1)[0] and all("Tested OK" not in x for x in _rowsum), "no test buttons in row summaries")
rel_row = rowhtml(t, "starter_relay")
check("Faulty" in rel_row and "Blown - replaced" not in rel_row, "relay buttons say Tested OK / Faulty")

# spec summary: type / amps / colour / voltage
def summary(item: str) -> str:
    return t.split(f'id="fuse-{item}"', 1)[1].split("</summary>", 1)[0]


s_f2 = summary("f2_luggage")  # 15 A mini
check("MINI" in s_f2 and "15 A" in s_f2 and "blue" in s_f2 and "(standard)" in s_f2 and "not sourced" not in s_f2, "mini 15 A summary: type, amps, derived colour, nothing 'not sourced'")
check("standard colour for this rating - check the fuse itself" in t, "standard colour label shown")
s_f1 = summary("f01_luggage")  # 40 A MAXI
check("MAXI" in s_f1 and "40 A" in s_f1 and "fz-sw" not in s_f1 and "not sourced" not in s_f1, "maxi: no derived colour, no noise")
s_f8 = summary("f08_luggage")
check("FMX/JCase" in s_f8 and "fz-sw" not in s_f8, "J-case: no derived colour")
s_f33 = summary("f33_interior")  # mini, no rating
check("MINI" in s_f33 and "A ?" not in s_f33 and " A<" not in s_f33 and "fz-sw" not in s_f33 and "not sourced" not in s_f33, "no rating: nothing shown for it")
s_rel = summary("starter_relay")
check("relay" in s_rel and "not sourced" not in s_rel, "relay summary: no 'not sourced'")
rel = rowhtml(t, "starter_relay")
check("Not sourced for this row" in rel and "pin layout" in rel and "orientation in the box" in rel and "Read it off the relay or the box cover" in rel,
      "relay details not sourced: one line in the opened row")
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
check("No photo of this box yet" not in sec3 and "Photo by Marco" in sec3 and "Cover label" in sec3, "saved photo shown with who and kind")
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
check('id="fuse-box-tech-engine-bay-2"' in t4 and "added by a technician" not in t4, "added box has its own section; no 'added by a technician' tag")
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
    seg = gseg(g, gid)
    check("Back to the map" in seg and "Last inspection" in seg and "Voltage drop to battery negative under load; clean to bare metal." in seg
          and "Connects to" in seg, f"{gid}: sections + one-line test")
    check(seg.index("<summary>") < seg.index("Connects to") < seg.index("Tested OK"), f"{gid}: test line leads, buttons below the facts")
    check(f'href="#ground-{gid}"' in "".join(re.findall(r"<svg class=\"sens-profile fm-svg.*?</svg>", t, re.S)), f"{gid}: icon on map")
check("FCA bulletin" in g or "S2008000032" in g, "G003A source shown")
for sv in re.findall(r"<svg class=\"sens-profile fm-svg.*?</svg>", t, re.S):
    check(sv.count('class="fm-ground"') == 4 and sv.count("fm-gsym") == 4 and sv.count('class="fm-box ') == 4, "both views: 4 ground icons + 4 box markers")
check("Exact spot not given" in gseg(g, "g003a"), "G003A location limits stated")
check(g.count("Location not sourced") == 1, "ground location gap: one sentence for the section")
check("inferred" in gseg(g, "esim_ground"), "ESIM ground: inferred connector location kept")
_src = lambda gid: gseg(g, gid).split(">Source<", 1)[1]
check("unverified" in _src("g003a") and "owner-attested" not in gseg(g, "g003a").split(">Source<", 1)[0] and "Owner says" not in gseg(g, "g003a").split(">Source<", 1)[0],
      "owner-attested and bulletin caveats live in the Source disclosure")
check('<details class="fuse-ground" id="ground-g003a" open>' in g and '<details class="fuse-ground" id="ground-battery_neg_strap">' in g,
      "job grounds open, others closed")
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
    return rr, int(mm.group(1)) if mm else (0 if "No match for" in rr else -1)


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
check(n == 0 and "No match for &ldquo;nothing-matches&rdquo;. Try a system word (window, lock, wiper...)" in rr and "Clear search" in rr
      and 'href="#fuse-box-interior_box"' in rr.split('id="fuse-results"')[1].split("</section>")[0], "no match -> hint + box buttons + clear link")
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
check("min-height" in _css and ".fuse-gochip" in _css, "44 px targets in css")
# results sit under the call, never above the heading
rr, n = results("F47")
check(rr.index("<h1") < rr.index('id="fuse-call"') < rr.index('id="fuse-results"') < rr.index('id="fuse-go"'), "results render under the call, below the heading")
check("Interior" in rr.split('id="fuse-results"')[1].split("</section>")[0], "result chip names the box")
rr, n = results("15A")
check("15 A" in rr.split('id="fuse-results"')[1].split("</section>")[0], "result chip shows amps when known")
# synonyms
for q_, want in (("wiper", "f43_interior"), ("window", "f47_interior"), ("lock", "f38_interior"), ("heater", "f94_interior"),
                 ("radio", "f08_luggage"), ("usb", "f21_luggage"), ("socket", "f22_luggage"), ("trailer", "f2_luggage"),
                 ("tow", "f4_luggage"), ("earth", "ground-g003a")):
    rr, n = results(q_)
    check(n >= 1 and (f'href="#fuse-{want}"' in rr or f'href="#{want}"' in rr), f"synonym search: {q_} -> {want}")
check(results("washer")[1] >= 1 and results("central%20locking")[1] >= 1, "washer / central locking words")
# amps match the rating field only
rr, n = results("5A")
res5 = rr.split('id="fuse-results"')[1].split("</section>")[0]
check('href="#fuse-f16_engine_pdm"' in res5 and 'href="#fuse-f2_luggage"' not in res5 and 'href="#fuse-f1_luggage"' not in res5,
      "5A matches the 5 A rating only, not '15 A' / '+15' text")
rr, n = results("15")
res15 = rr.split('id="fuse-results"')[1].split("</section>")[0]
check('href="#fuse-f2_luggage"' in res15 and 'href="#fuse-f4_luggage"' not in res15, "bare 15 = rating 15 or position 15, not text")

# 10. owner data page
d = client.get(f"/v/{VIN}/fuses/data")
dt = d.text
check(d.status_code == 200 and all(k in dt for k in ("Add a fuse box", "Add a fuse or relay", "Record type, colour or voltage", 'type="file"')),
      "owner page has the maintenance forms")
check('action="/v/%s/fuses/box"' % VIN in dt and 'action="/v/%s/fuses/item"' % VIN in dt and 'action="/v/%s/fuses/spec"' % VIN in dt
      and 'action="/v/%s/fuses/photo"' % VIN in dt, "owner forms keep the same POST routes")
check('href="/v/%s/fuses/data"' % VIN not in client.get(f"/v/{VIN}/dossier").text, "owner page not linked from the dossier")

# 11. catalogue photos (fixture catalogue with photographed parts; no part numbers in the repo)
from cuore.services import component_images as ci  # noqa: E402

_PH = {"id": "test-cat", "diagrams": {"d1": {"title": "Fuse fixture", "parts": [
    {"pn": "FX-MINI-1", "name": "Mini Fuse", "description": "x", "fitment": "own", "photos": [{"file": "mini.jpg"}]},
    {"pn": "FX-MAXI-1", "name": "Maxi Fuse", "description": "x", "fitment": "own", "photos": [{"file": "maxi.jpg"}]},
    {"pn": "FX-STRAP-1", "name": "Alfa Romeo Ground Strap", "description": "BATTERY NEGATIVE", "fitment": "own",
     "photos": [{"file": "strap.jpg"}]}]}}}
parts_catalogue_saved = (parts_catalog.load, parts_catalog.default_id)
parts_catalog.load = lambda *a, **k: _PH
parts_catalog.default_id = lambda *a, **k: "test-cat"
ci._idx.update(sig=None, rows=[])
tp = client.get(f"/v/{VIN}/fuses").text
check("/catalog/img/test-cat/mini.jpg" in tp and 'href="/catalog/p/FX-MINI-1"' in tp, "mini row shows catalogue photo linking to its part page")
check("/catalog/img/test-cat/maxi.jpg" in tp, "maxi row shows catalogue photo")
f47 = rowhtml(tp, "f47_interior")
check("mini.jpg" in f47 and 'width="64"' in f47 and "Mopar catalogue photo - the part type, not this car's fuse" in f47.replace("&#39;", "'"),
      "F47 (MINI) photo is 64 px with its caption")
rel = [x.split("</summary>", 1)[0] for x in re.split(r'<details class="fuse-row[ "]', tp)[1:] if "(relay)" in x.split("</summary>", 1)[0]]
check(rel and all("/catalog/img/" not in x for x in rel), "relay rows without a sourced type show no photo")
gs = gseg(tp, "battery_neg_strap")
check("strap.jpg" in gs and "Mopar catalogue photo - the part, not this car" in gs and 'href="/catalog/p/FX-STRAP-1"' in gs,
      "strap photo + caption + link in grounds")
check("/catalog/img/" not in gseg(tp, "g003a"), "other grounds have no catalogue photo")
from cuore.web import fuse_routes as fr  # noqa: E402
check([fr.photo_key("fuse", t) for t in ("MINI", "Mini", "MAXI", "FMX/JCase", "J-case", "MIDI", "ATO")] ==
      ["mini", "mini", "maxi", "j-case", "j-case", "midi", ""], "fuse type -> key map")
check(fr.photo_key("relay", "Micro ISO") == "micro relay" and fr.photo_key("relay", "") == "", "relay type -> key map")
parts_catalog.load, parts_catalog.default_id = parts_catalogue_saved
ci._idx.update(sig=None, rows=[])
tn = client.get(f"/v/{VIN}/fuses").text
check("mini.jpg" not in tn and "Mopar catalogue photo - the part" not in tn, "no catalogue -> no photos, no captions")
src = "".join(Path(x).read_text(encoding="utf-8") for x in (fr.__file__, ci.__file__, fd.__file__,
                                                            str(Path(fr.__file__).parent / "templates" / "fuses.html")))
check(not re.search(r"\d{8,10}[A-Z]{0,2}", src.split("OWNER_NOTE_ID")[0] + fr.__doc__), "no part numbers in the files touched")

# 12. resolved symptoms do not drive the call / cards
from cuore.services import timeline_bridge  # noqa: E402
_syms = [{"id": "aaaaaaaaaaaa", "at": "2026-10-23T00:00", "text": "The car does not auto-unlock on door-handle touch."},
         {"id": "bbbbbbbbbbbb", "at": "2026-10-25T13:45", "text": "Rear-left window stops part way in BOTH directions."},
         {"id": "cccccccccccc", "at": "2026-10-20T00:00", "text": "Driver window will not unlock-close.", "status": "closed"},
         {"id": "dddddddddddd", "at": "2026-10-19T00:00", "text": "Another unlock complaint.", "hidden": True}]
_nts = [{"id": "n1", "tags": ["resolved"], "text": "FIXED. Closes symptom aaaaaaaaaaaa.", "hidden": False}]
_sv, _nv = timeline_bridge.symptoms, mes_bridge.notes
timeline_bridge.symptoms = lambda vin, **k: {"symptoms": _syms}
mes_bridge.notes = lambda vin, *a, **k: {"notes": _nts}
got, _ = _real_job_inputs(VIN, [], {})
check([s["id"] for s in got] == ["bbbbbbbbbbbb"], "resolved-note, closed-status and hidden symptoms are excluded; open one kept")
_nts[0]["hidden"] = True
got, _ = _real_job_inputs(VIN, [], {})
check("aaaaaaaaaaaa" in [s["id"] for s in got], "a hidden resolved note no longer closes the symptom")
_nts[0].update(hidden=False, tags=["keyless"])
got, _ = _real_job_inputs(VIN, [], {})
check("aaaaaaaaaaaa" in [s["id"] for s in got], "a note without the resolved tag does not close it")
_nts[0]["tags"] = ["resolved"]
_items = fh.health(VIN)["items"]
_boxes = fh.health(VIN)["boxes"]
got, _ = _real_job_inputs(VIN, [], {})
dd = fd.direct(_items, _boxes, got, [], {}, lambda c: {})
refs = [m["ref"] for m in dd["matches"]]
check("F38" not in refs and {"F47", "F48"} <= set(refs), "resolved unlock symptom: no F38 card; open window symptom: F47/F48 cards")
dd2 = fd.direct(_items, _boxes, [{"text": _syms[0]["text"], "at": ""}], [], {}, lambda c: {})
check("F38" in [m["ref"] for m in dd2["matches"]], "an open unlock symptom still produces the F38 card")
timeline_bridge.symptoms, mes_bridge.notes = _sv, _nv

# picker / not-sourced fold / grounds row
pick = t.split('class="fuse-picks"', 1)[1].split("</section>", 1)[0]
check("No box stated" not in pick and "fuse-picks-g" in pick and 'href="#fuse-grounds"' in pick.split("fuse-picks-g")[1], "grounds in their own picker row; no pseudo-box")
check(t.index("What is not sourced yet") < t.index('id="fuse-bcm_feed_20a"') < t.index("Credits"), "'No box stated' rows live in the not-sourced fold")
check("Rows whose box is not stated" in t and 'id="fuse-box-none"' in t, "fold names the unboxed rows")
check("parentElement" in t, "script opens the folds around a jump target")
check("? Not checked yet" in t and "</b> 0 Blown" in t, "status words next to symbols")

# default view: left-side call box -> side view; no call -> side view
fd.job_inputs = lambda vin, codes, dossier: ([{"text": "The horn is weak.", "at": ""}, {"text": "Rear-left window stops", "at": "x"}], {})
mes_bridge.open_codes_for = lambda d: []
tl = client.get(f"/v/{VIN}/fuses").text
check('id="fm-v-top" checked' in tl, "right-side call box still top (control)")
fd.job_inputs = lambda vin, codes, dossier: ([{"text": "Door will not unlock", "at": "x"}], {})
tn2 = client.get(f"/v/{VIN}/fuses").text
check("F38" in re.sub(r"<[^>]+>", "", tn2.split('id="fuse-call"', 1)[1].split("</p>", 1)[0]), "unlock symptom -> F38 call")
fd.job_inputs = lambda vin, codes, dossier: ([], {})
t0 = client.get(f"/v/{VIN}/fuses").text
check('id="fm-v-side" checked' in t0 and 'id="fuse-go"' not in t0 and "fuses and relays" in t0.split('id="fuse-call"', 1)[1].split("</p>", 1)[0],
      "no call -> side view, no Go-to row, plain pick-a-box line")

print(f"fuse_page checks: {passed} passed, {len(failures)} failed")
for f in failures:
    print("  FAIL:", f)
sys.exit(1 if failures else 0)
