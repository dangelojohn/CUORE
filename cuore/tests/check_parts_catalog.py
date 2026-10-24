"""Parts catalogue: build from a small export, then the index, search (number
and words, single exact hit redirects), diagram page (image, callouts, torque
library rows), part page (appearances, callout mates, CUORE record mention),
other-engine tagging, excluded group, image route safety, empty state.
In-process TestClient; temp state dir; no network, no COM3.

Run:  .venv/Scripts/python.exe cuore/tests/check_parts_catalog.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="cuore-check-catalog-"))
os.environ["CUORE_STATE_DIR"] = str(STATE)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

IMG = "https://cdn-illustrations.example/strapr1/abc/front.png"
EXPORT = {
    "source": "https://parts.example.com/v-2018-alfa-romeo-stelvio--base--2-0l-l4-gas",
    "fetched_at": "2026-10-24T12:00:00Z",
    "cats": ["brakes--front-brakes", "2-9l-gas-engine--engine-mounting"],
    "errors": [],
    "pages": {
        "brakes--front-brakes": {
            "slug": "brakes--front-brakes", "title": "Front Brakes for 2018 Alfa Romeo Stelvio",
            "heads": ["Diagram 1: Disc Brake Caliper Assembly, Right"], "thumbs": [IMG],
            "rows": [
                {"d": 0, "ref": "1", "pn": "68420187AA", "name": "Disc Brake Caliper Assembly, Right",
                 "href": "/oem-parts/x-68420187aa", "img": "//cdn-static.example/assets/images/alfa-romeo.png",
                 "info": {"Notes": "Engines: 2.0L 280HP I4 DI TURBO ENGINE.", "Description": "Without Brake Pads. Front."}},
                {"d": 0, "ref": "1", "pn": "68420186AA", "name": "Disc Brake Caliper Assembly, Right",
                 "href": "/oem-parts/x-68420186aa", "img": "",
                 "info": {"Notes": "Engines: 2.9L V6 TWIN TURBO ENGINE."}},
                {"d": 0, "ref": "1", "pn": "68420185AA", "name": "Disc Brake Caliper Assembly, Left",
                 "href": "/oem-parts/x-68420185aa", "img": "",
                 "info": {"Notes": "Engines: 2.0L 280HP I4 DI TURBO ENGINE.", "Description": "Without Brake Pads. Front. [XTK]"}},
                {"d": 0, "ref": "5", "pn": "68400577AA", "name": "Pad Kit, Front Disc Brake",
                 "href": "/oem-parts/x-68400577aa", "img": "", "info": {}},
                {"d": 0, "ref": "7", "pn": "68311596AA", "name": "Bolt, Brake Mounting",
                 "href": "/oem-parts/x-68311596aa", "img": "", "info": {"Description": "Caliper Guide Pin."}},
            ]},
        "2-9l-gas-engine--engine-mounting": {
            "slug": "2-9l-gas-engine--engine-mounting", "title": "Engine Mounting for 2018 Alfa Romeo Stelvio",
            "heads": ["Diagram 1: Mount"], "thumbs": [],
            "rows": [{"d": 0, "ref": "1", "pn": "99999999AA", "name": "Engine Mount", "href": "", "img": "", "info": {}}]},
    },
}


def main() -> None:
    from fastapi.testclient import TestClient
    from cuore.app import create_app
    c = TestClient(create_app(), follow_redirects=False)

    r = c.get("/catalog")
    assert r.status_code == 200 and "Not built yet" in r.text, r.status_code

    exp = STATE / "export.json"
    exp.write_text(json.dumps(EXPORT), encoding="utf-8")
    sys.path.insert(0, str(ROOT / "scripts" / "parts"))
    import build_parts_catalog as b
    sup = STATE / "shop.json"
    sup.write_text(json.dumps({"source": "https://shop.example/store", "brand_type": "aftermarket", "items": [
        {"brand": "bproauto", "part_number": "1BP01360AA", "name": "Disc Brake Rotor", "position": "Front", "price": "$114.80"},
        {"brand": "Mopar", "part_number": "68400577AA", "name": "Duplicate of a dealer part"}]}), encoding="utf-8")
    sup2 = STATE / "shop2.json"
    sup2.write_text(json.dumps({"source": "https://retail.example/store", "items": [
        {"name": "Intercooler Gasket Giulia Stelvio 2.0", "sku": "EG213", "price": "$32.05"},
        {"name": "Throttle Body Giulia Stelvio QV", "sku": "FI217"},
        {"name": "Alfa Romeo Dealership Sign", "sku": "X1"}]}), encoding="utf-8")
    out = b.build(exp, fetch_images=False, supplements=[sup, sup2])
    lst = json.loads((out / "catalog.json").read_text(encoding="utf-8"))["listings"]
    assert {x["pn"] or x["sku"] for x in lst} == {"1BP01360AA", "EG213", "FI217"}, lst  # dealer duplicate + merch dropped
    assert {x["sku"]: x["fitment"] for x in lst if x["sku"]} == {"EG213": "by-name", "FI217": "other-engine"}, lst
    img_name = b._img_name(IMG)
    (out / "img" / img_name).write_bytes(b"\x89PNG\r\n\x1a\n")
    cat = json.loads((out / "catalog.json").read_text(encoding="utf-8"))  # rebuild to point at the file
    cat["diagrams"]["brakes--front-brakes--1"]["image"]["file"] = img_name
    (out / "catalog.json").write_text(json.dumps(cat), encoding="utf-8")
    (out / "mechanic_test.json").write_text(json.dumps({"sections": {"brakes--front-brakes": {
        "summary": "Fixed front calipers.", "cautions": ["Retract the EPB with a scan tool first."],
        "shared_with": [{"vehicles": "2017+ Giulia", "source": "test"}]}}}), encoding="utf-8")
    (STATE / "notes.jsonl").write_text(json.dumps({"id": "n1", "at": "2026-10-24T00:00:00",
                                                   "text": "fitted pad kit 68400577AA today"}) + "\n", encoding="utf-8")

    r = c.get("/catalog")
    t = r.text
    assert r.status_code == 200 and 'href="/catalog/g/brakes"' in t and "Brakes" in t, r.status_code
    assert "Not for this car" in t  # Quadrifoglio tile
    r = c.get("/catalog/g/brakes")
    assert r.status_code == 200 and "/catalog/d/brakes--front-brakes--1" in r.text and "Front Brakes" in r.text
    assert "torque value" in r.text  # section spec count
    assert c.get("/catalog/g/nope").status_code == 303

    # number search: exact single hit redirects; partial lists
    r = c.get("/catalog", params={"q": "68400577AA"})
    assert r.status_code == 303 and r.headers["location"] == "/catalog/p/68400577AA", r.headers.get("location")
    r = c.get("/catalog", params={"q": "6842018"})
    assert r.status_code == 200 and "68420187AA" in r.text and "68420186AA" in r.text and "OTHER ENGINE" in r.text
    assert r.text.index("68420187AA") < r.text.index("68420186AA")  # this car's parts first
    r = c.get("/catalog?q=rotor")
    assert r.status_code == 200 and "from other shops" in r.text and "1BP01360AA" in r.text and "LISTED FOR THIS CAR" in r.text, r.text[-1500:]
    r = c.get("/catalog/other")
    assert r.status_code == 200 and "EG213" in r.text and "OTHER ENGINE / MODEL" in r.text and "Dealership Sign" not in r.text
    # words, with the mechanic's own phrasing: torque values first, then parts
    r = c.get("/catalog", params={"q": "caliper bolt torque"})
    t = r.text
    assert r.status_code == 200 and "Torque values for" in t and "30 Nm" in t and "68311596AA" in t, t[-2000:]
    assert t.index("Torque values for") < t.index("68311596AA")
    assert "Wheel lug" not in t  # the fastener must be named, not just its schematic
    r = c.get("/catalog", params={"q": "pad kit"})
    assert r.status_code == 200 and "68400577AA" in r.text and "1 part " in r.text

    # schematic: torque first, matched to the bolt row, other-engine hidden by default
    r = c.get("/catalog/d/brakes--front-brakes--1")
    t = r.text
    assert r.status_code == 200 and f"/catalog/img/stelvio-2018-2.0l/{img_name}" in t
    for needle in ("Torque values for this assembly", "Brake caliper guide/slide pin bolt", "22 ft-lb",
                   "Before you start", "Fixed front calipers.", "Retract the EPB", "2017+ Giulia",
                   "listed only for another engine hidden", "Diagram ↑"):
        assert needle in t, needle
    assert t.index("Torque values for this assembly") < t.index("68400577AA")
    assert "68420186AA" not in t  # other engine hidden
    assert '<span class="cat-callout sm">7</span> Brake caliper guide' in t  # spec points at its callout
    row = t[t.index("68311596AA"):t.index("68311596AA") + 1500]
    assert "30 Nm" in row, "torque not matched to the guide-pin bolt row"
    cal = t[t.index(">68420187AA<"):t.index(">68420187AA<") + 600]
    assert "30 Nm" not in cal, "fastener torque leaked onto the caliper row"
    r = c.get("/catalog/d/brakes--front-brakes--1", params={"all": 1})
    assert "68420186AA" in r.text and "OTHER ENGINE" in r.text
    # McMaster-style: rail, filter chips with counts, clickable rows, type-ahead
    assert 'class="cat-rail"' in t and 'href="/catalog/g/brakes#s-brakes--front-brakes" class="on"' in t
    assert 'data-href="/catalog/p/68311596AA"' in t and "catalog.js" in t
    assert ">Left<small>1</small>" in t and ">Right<small>" in t and ">XTK<small>1</small>" in t
    r = c.get("/catalog/d/brakes--front-brakes--1", params={"side": "Left"})
    t = r.text
    assert "68420185AA" in t and ">68420187AA<" not in t and "68400577AA" in t and "68311596AA" in t  # untagged rows stay
    r = c.get("/catalog/d/brakes--front-brakes--1", params={"opt": "XTK"})
    assert "68420185AA" in r.text and "68400577AA" in r.text
    j = c.get("/catalog/api/typeahead", params={"q": "caliper bolt"}).json()
    assert j["specs"] and j["specs"][0]["value"] == "30 Nm" and any(p["pn"] == "68311596AA" for p in j["parts"]), j
    assert c.get("/catalog/api/typeahead", params={"q": "x"}).json() == {"parts": [], "specs": []}
    assert c.get("/static/catalog.js").status_code == 200

    # part page: torque, then see it (callout), then alternatives
    r = c.get("/catalog/p/68311596AA")
    t = r.text
    assert r.status_code == 200 and "30 Nm" in t and 'Find <span class="cat-callout">7</span>' in t, r.status_code
    assert t.index("cat-torque") < t.index("cat-see")
    r = c.get("/catalog/p/68420187AA")
    t = r.text
    for needle in ("Same callout, other part numbers", "68420186AA", "No torque value names this part",
                   "Other torque values in this assembly", "Brakes</a>"):
        assert needle in t, needle
    r = c.get("/catalog/p/68400577AA")
    assert "fitted pad kit" in r.text  # CUORE record mention
    r = c.get("/catalog/p/00000000ZZ")
    assert r.status_code == 303

    assert c.get(f"/catalog/img/stelvio-2018-2.0l/{img_name}").status_code == 200
    assert c.get("/catalog/img/stelvio-2018-2.0l/..%2Fcatalog.json").status_code == 404
    assert c.get("/catalog/img/../x.png").status_code == 404
    r = c.get("/start")
    assert 'href="/catalog"' in r.text and 'class="icon-btn parts-link' in r.text
    print("parts catalogue OK")


if __name__ == "__main__":
    main()
