"""Checks for the Systems map layers, Overlap (Venn / intersection boxes) and guided path
(cuore/services/systems_interactive.py overlap / guide_path / guide_view / _layers + _systems_interactive.html/.js/.css).

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_systems_layers.py
"""
from __future__ import annotations

import re
import sys
import tempfile
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import systems_interactive as si  # noqa: E402

WEB = ROOT / "cuore" / "web"
failures: list[str] = []
passed = 0


def check(cond, label):
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def it(key, guess=False, kind="system"):
    return {"key": key, "label": key.upper(), "href": "/s/" + key, "guess": guess, "kind": kind, "path": "/p/" + key}


def issue(label, keys, present=1, codes=2, guess=()):
    return {"id": label, "label": label, "n_codes": codes, "codes": [f"P{i}" for i in range(codes)], "present": bool(present),
            "n_present": present, "why": "", "last_seen": "2026-10-26T08:00:00", "letter": "",
            "direct": ["s:" + keys[0]], "items": [it(k, k in guess) for k in keys]}


def regs(o):
    return {tuple(r["letters"]): sorted(t["key"] for t in r["its"]) for r in o["regions"] if r["size"]}


# --- overlap: 0 / 1 / 2 / 3 / 5 issues
check(si.overlap([])["mode"] == "none", "0 issues -> none")
check(si.overlap([issue("a", ["x"])])["mode"] == "single", "1 issue -> single")
o2 = si.overlap([issue("A", ["x", "y"]), issue("B", ["y", "z"])])
check(o2["mode"] == "venn" and len(o2["circles"]) == 2, "2 issues -> venn with 2 circles")
check(regs(o2) == {("A",): ["x"], ("B",): ["z"], ("A", "B"): ["y"]}, f"2-set regions: {regs(o2)}")
o3 = si.overlap([issue("A", ["x", "y", "w"]), issue("B", ["y", "z", "w"]), issue("C", ["w", "q"])])
check(o3["mode"] == "venn" and len(o3["circles"]) == 3 and len(o3["regions"]) == 7, "3 issues -> venn, 7 regions drawn")
check(regs(o3)[("A", "B", "C")] == ["w"] and regs(o3)[("A", "B")] == ["y"] and regs(o3)[("C",)] == ["q"], f"3-set regions: {regs(o3)}")
five = [issue(c, k) for c, k in zip("ABCDE", [["a", "s"], ["b", "s"], ["c", "s", "t"], ["d", "t"], ["e", "s"]])]
o5 = si.overlap(five)
check(o5["mode"] == "boxes" and not o5["circles"], "5 issues -> intersection boxes, no circles")
sizes = [r["size"] for r in o5["regions"]]
check(sizes == sorted(sizes, reverse=True) and all(sizes), f"boxes sorted by size, none empty: {sizes}")
check(regs(o5)[("A", "B", "C", "E")] == ["s"] and regs(o5)[("C", "D")] == ["t"], f"5-set intersections: {regs(o5)}")
og = si.overlap([issue("A", ["x", "y"], guess=("y",)), issue("B", ["y"])])
check([t["guess"] for r in og["regions"] for t in r["its"] if t["key"] == "y"] == [True], "a guess-reached item stays a guess in the overlap")

# --- guided path
sc = [issue("A", ["evap", "esim"], present=2, codes=3), issue("B", ["fuel", "esim"], present=1, codes=2)]
sc[0]["items"][1]["kind"] = "part"
sc[1]["items"].append(it("sup", kind="upstream"))
check(si.rank_issues(sc) == [0, 1] and si.rank_issues(list(reversed(sc))) == [1, 0], "ranking: more present faults first")
st = si.guide_path(0, sc)
check([s["kind"] for s in st] == ["issue", "shared", "test"], f"path order issue -> shared suspect -> test: {[s['kind'] for s in st]}")
check(st[1]["highlight"] == ["esim"] and st[1]["basis"] == "finding" and "other issue" in st[1]["why"], "shared suspect is the item both issues share")
check(st[-1]["links"] and all(h for _, h in st[-1]["links"]), "test step links to the electrical path / system page")
check([s["n"] for s in st] == [1, 2, 3] and st[0]["total"] == 3, "steps numbered")
up = [issue("A", ["evap", "sup"]), issue("B", ["fuel"])]
up[0]["items"][1]["kind"] = "upstream"
up[0]["items"][1]["guess"] = True
st2 = si.guide_path(0, up)
check([s["kind"] for s in st2] == ["issue", "upstream", "test"] and st2[1]["basis"] == "guess" and "guess" in st2[1]["why"], "guessed upstream step is labelled guess")
none = si.guide_path(0, [issue("A", ["evap"])])
check(none[-1]["kind"] == "capture" and none[-1]["basis"] == "none" and "Capture next" in none[-1]["why"] and not none[-1]["links"], "evidence runs out -> what to capture next, no suspect")
gv = si.guide_view(st, 2, "A")
check(gv["progress"] == "Step 2 of 3" and gv["prev"] == "?guide=A&step=1#sx-guide" and gv["next"] == "?guide=A&step=3#sx-guide", f"prev/next: {gv['prev']} {gv['next']}")
check([c["href"] for c in gv["crumbs"]] == ["?guide=A&step=1#sx-guide", "?guide=A&step=2#sx-guide"] and gv["crumbs"][1]["current"], "breadcrumbs jump back; current marked")
check(gv["exit"] == "?#sx" and si.guide_view(st, 9, "A")["n"] == 3 and si.guide_view(st, 0, "A")["n"] == 1, "exit link; step clamped")
check(si.guide_view(st, 3, "A")["next"] == "" and si.guide_view(st, 1, "A")["prev"] == "", "no Next on last / Back on first")
check(si.guide_view(st, 1, "A", "token=t&")["exit"] == "?token=t#sx", "exit keeps the token")

# --- layer buttons from data
base = {"edges": [{"layer": "dep", "confidence": "CONFIRMED"}, {"layer": "guess", "confidence": "UNKNOWN"}],
        "legend_sev": si.LEGEND_SEV, "nodes": [{"cls": "sev-act", "key": "evap"}],
        "cards": {"evap": {"faults": [{"last_seen": "2026-10-26T08:00:00"}]}}, "issues_all": []}
ly = {l["id"]: l for l in si._layers(base, {"connected": False, "n": 0})}
check(ly["dep"]["text"] == "Depends on · 1 link · 1 confirmed", ly["dep"]["text"])
check(ly["pg"]["text"].endswith("none captured yet") and ly["conn"]["text"].endswith("none captured yet"), "empty relation layer -> none captured yet")
check(ly["sev-act"]["text"] == "Active or permanent fault · 1 system · last read 26 Oct", ly["sev-act"]["text"])
check(ly["sev-pend"]["text"].endswith("none captured yet"), "no pending -> none captured yet")
check(ly["issues"]["text"].endswith("none captured yet"), "no issues -> none captured yet")
check(ly["live"]["text"] == "Live · not connected · none captured yet", ly["live"]["text"])
lv = {l["id"]: l for l in si._layers(base, {"connected": True, "n": 4})}
check(lv["live"]["text"] == "Live · 4 channels · now", lv["live"]["text"])
check(ly["guess"]["on"] is False and ly["dep"]["on"] and ly["issues"]["on"] and ly["live"]["on"], "defaults: guesses off, others on")

# --- rendered page (reference car)
c = TestClient(create_app())
V = "ZASFAKPN5J7B88115"
html = c.get(f"/v/{V}/systems").text
btns = re.findall(r'<button[^>]*class="sx-lbtn[^>]*>', html)
check(len(btns) >= 10, f"layer buttons rendered: {len(btns)}")
check(any('data-layer="guess"' in b and 'aria-pressed="false"' in b for b in btns), "guess layer starts off")
check(all('aria-pressed="true"' in b for b in btns if 'data-layer="guess"' not in b), "other layers start on")
check('id="sx-layers" role="group" aria-label="Map layers" hidden' in html, "layer bar hidden until JS enables it")
check("sx-view-graph" in html and "sx-view-overlap" in html and 'data-layer="dep"' in html, "no-JS: both views and all edges are in the page (nothing is hidden server-side)")
check("sx-guide-go" in html and "guide=" in html, "Guide me button on the Overlap view")
g = c.get(f"/v/{V}/systems?guide=A&step=2").text
check("Step 2 of" in g and 'class="sx is-guided"' in g and "Exit guide" in g and "Start over" in g and "&lsaquo; Back" in g and "Next &rsaquo;" in g, "no-JS step render")
check('href="?guide=A&amp;step=1#sx-guide"' in g or 'href="?guide=A&step=1#sx-guide"' in g, "Back link / crumb target step 1")

# --- css / js
css = (WEB / "static" / "systems_interactive.css").read_text(encoding="utf-8")
js = (WEB / "static" / "systems_interactive.js").read_text(encoding="utf-8")
check(re.search(r"\.sx-vbtn, \.sx-lbtn \{[^}]*min-height: 56px", css) is not None, "layer / view buttons >= 56 px")
check(re.search(r"\.sx-big \{[^}]*min-height: 56px", css) is not None, "guide Next / Back / Start over / Exit >= 56 px")
check("gap: 12px" in css.split(".sx-lgroup")[1].split("}")[0], "layer buttons >= 12 px apart")
check("position: sticky; bottom: 0" in css, "layer bar sticky at the bottom of the map")
check("sessionStorage" in js and "try" in js and "aria-pressed" in js, "JS keeps the choice in sessionStorage (try/catch) and sets aria-pressed")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
