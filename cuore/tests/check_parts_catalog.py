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
    ad = STATE / "autodoc.json"
    ad.write_text(json.dumps({"source": "https://autodoc.example", "fetched_at": "2026-10-26T09:00:00Z", "currency": "GBP",
        "vehicle": {"label": "TEST Stelvio 2.0", "engine_code": "TEST.ENG"},
        "categories": [{"cat": "brake-pad-set-10130", "title": "Brake pad set for TEST", "rows": [
            {"n": "TESTBRAND TEST-001 Brake pad set", "no": "TEST-001", "b": "TESTBRAND", "ean": "0000000000001",
             "pr": "£24.49", "u": "https://autodoc.example/p1", "im": "https://cdn.example/p1.jpg",
             "sp": {"Height 1 [mm]": "58,7"}}]},
            {"cat": "mystery-widget-999", "title": "Widget", "rows": [{"n": "TESTBRAND TEST-002 Widget", "no": "TEST-002", "b": "TESTBRAND", "pr": "£1.00", "im": None}]}]}), encoding="utf-8")
    wr = STATE / "wrangler.json"
    wr.write_text(json.dumps({"source": "https://store.example", "vehicle": "TEST Wrangler 2.0L", "fetched_at": "2026-10-26T10:00:00Z",
        "currency": "USD", "categories": [{"title": "Test Turbo Parts", "path": "/v-test/2-0l-i4-dohc-di-turbo-engine--turbo-and-super-chargers",
        "rows": [
            {"title": "Test Bolt Same", "part_number": "68311-596 aa", "manufacturer": "Mopar", "list_price": "$15.00", "sale_price": "$11.56",
             "description": "Test bolt.", "url": "https://store.example/a", "image": "https://cdn.example/w1.jpg"},
            {"title": "Test Pad Kit Newer Revision", "part_number": "68400577AB", "manufacturer": "Mopar", "sale_price": "$20.00", "url": "https://store.example/b"},
            {"title": "Test Wrangler Only", "part_number": "TEST-1234AA", "manufacturer": "Mopar", "sale_price": "$5.00", "url": "https://store.example/c"}]}]}), encoding="utf-8")
    wimg = STATE / "parts_catalog" / "sources" / "wrangler-gme" / "img"
    wimg.mkdir(parents=True)
    (wimg / "abcdef012345.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # tiny stand-in drawing
    (STATE / "secret.png").write_bytes(b"x")
    wj = json.loads(wr.read_text(encoding="utf-8"))
    wj["diagrams"] = [{"category": "Test Turbo Parts", "category_path": "/v-test/2-0l-i4-dohc-di-turbo-engine--turbo-and-super-chargers",
        "index": 0, "title": "Diagram 1: Test Bolt (31)", "image_file": "wrangler-gme/img/abcdef012345.png", "natural_w": 200, "natural_h": 100,
        "hotspots": [{"code": "1", "style": "top:50px;left:100px;width:20px;height:20px;line-height:20px;"},
                     {"code": "2", "style": "top:10px;left:190px;width:20px;height:20px;"}],
        "rows": [{"callout": "1", "part_number": "68311596AA", "title": "Test Bolt Same", "sale_price": "$11.56"},
                 {"callout": "2", "part_number": "TEST-1234AA", "title": "Test Wrangler Only", "sale_price": "$5.00"}]}]
    wr.write_text(json.dumps(wj), encoding="utf-8")
    out = b.build(exp, fetch_images=False, supplements=[sup, sup2], autodoc=ad, wrangler=wr)
    lst = json.loads((out / "catalog.json").read_text(encoding="utf-8"))["listings"]
    adl = {x["pn"]: x for x in lst if x["source_name"] == "Autodoc UK"}
    assert adl["TEST-001"]["group"] == "brakes" and adl["TEST-002"]["group"] == "other", adl
    assert adl["TEST-001"]["fitment"] == "unverified" and adl["TEST-001"]["currency"] == "GBP" and adl["TEST-001"]["specs"]["Height 1 [mm]"] == "58,7"
    assert not list((out / "img").glob("*")), "autodoc images must stay remote"
    wl = {x["pn"]: x for x in lst if x["kind"] == "wrangler"}
    assert wl["68311-596AA"]["interchange"]["status"] == "same-pn", wl  # spaces/dashes normalised
    assert wl["68400577AB"]["interchange"]["status"] == "same-base" and wl["68400577AB"]["interchange"]["stelvio_pns"] == ["68400577AA"]
    assert wl["TEST-1234AA"]["interchange"]["status"] == "none" and all(x["fitment"] == "unverified" for x in wl.values())
    assert wl["68311-596AA"]["price"] == "$11.56" and wl["TEST-1234AA"]["group"] == "engine"
    assert b.load_wrangler_gme(STATE / "absent.json", {}) == [] and not list((out / "img").glob("*")), "wrangler images stay remote"
    lst = [x for x in lst if x["source_name"] not in ("Autodoc UK", b.WRANGLER_SOURCE_NAME)]
    assert b.load_autodoc(STATE / "absent.json") == []
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
    r = c.get("/catalog/other")
    t = r.text
    for needle in ("Autodoc UK", "TEST-001", "TESTBRAND", "EAN 0000000000001", "58,7", "Specs (1)",
                   "£24.49 (Autodoc UK, 2026-10-26)", "AUTODOC VEHICLE SELECTION", "https://cdn.example/p1.jpg"):
        assert needle in t, needle
    assert "TEST-001" in c.get("/catalog?q=0000000000001").text  # EAN search
    r = c.get("/catalog/other")
    t = r.text
    for needle in ("Jeep Wrangler 2.0L GME (engine)", "Test Turbo Parts", "SAME MOPAR NUMBER AS THE STELVIO CATALOGUE",
                   "SAME BASE NUMBER, DIFFERENT REVISION", "Stelvio 68400577AA", "WRANGLER GME 2.0L ONLY",
                   "interchangeability with the Stelvio unverified", "$11.56 (store.example, 2026-10-26)",
                   "https://cdn.example/w1.jpg", 'href="/catalog/p/68311596AA"', "not proof of fit on this exact VIN"):
        assert needle in t, needle
    sec = t.split("Jeep Wrangler 2.0L GME (engine)", 1)[1].split("</section>")[0]
    assert sec.index("SAME MOPAR NUMBER") < sec.index("68311-596AA") and " fits" not in sec.replace("a Wrangler part fits", "")
    assert "Test Wrangler Only" in c.get("/catalog?q=TEST-1234AA").text  # searchable like the other shops
    assert "Also listed for 2019 Jeep Wrangler 2.0L GME (same part number)" in c.get("/catalog/p/68311596AA").text
    assert "See it on the Wrangler GME schematic: " in c.get("/catalog/p/68311596AA").text and "callout 1" in c.get("/catalog/p/68311596AA").text
    assert 'href="/catalog/w/wr-test-turbo-parts-1#row-1"' in c.get("/catalog/other").text
    r = c.get("/catalog/w/wr-test-turbo-parts-1")
    t = r.text
    for needle in ("Diagram 1: Test Bolt (31)", "/catalog/wrangler-img/abcdef012345.png", 'href="#row-1"', 'href="#row-2"', 'id="row-2"',
                   "SAME MOPAR NUMBER AS THE STELVIO CATALOGUE", "WRANGLER GME 2.0L ONLY", "scaled by the largest hotspot extent"):
        assert needle in t, needle
    assert "left: 52.38%" in t and "left: 95.24%" in t  # (100+10)/210, (190+10)/210: basis = largest hotspot extent
    assert c.get("/catalog/wrangler-img/abcdef012345.png").status_code == 200
    for bad in ("..%2Fsecret.png", "%2e%2e%2f%2e%2e%2fsecret.png", "../secret.png", "secret.png", "abcdef012345.PNG"):
        assert c.get(f"/catalog/wrangler-img/{bad}").status_code == 404, bad
    assert c.get("/catalog/w/nope").status_code == 303
    assert "Also listed for 2019 Jeep Wrangler" not in c.get("/catalog/p/68400577AA").text  # suffix match is not "same part number"
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

    # standard parts (owner-attested): synthetic fixture only
    tvin = "TESTVIN0000000001"
    sdir = STATE / "parts_catalog" / "sources" / "standard"
    (sdir / "img").mkdir(parents=True)
    (sdir / "img" / "test-h1-aaaaaaaaaaaa.jpg").write_bytes(bytes([255, 216, 255, 217]))
    (sdir / "test-h1.json").write_text(json.dumps({"brand": "TESTMAKER", "article_number": "TEST-H1",
        "specs": {"Height": "85", "Thread Size": "M0x0", "Colour": "blue"},
        "oe_numbers": [{"number": "OE-TEST-1", "maker": "TESTCO"}]}), encoding="utf-8")
    (STATE / "parts_catalog" / "standard_parts.json").write_text(json.dumps({"vehicles": {tvin: {"oil_filter": {
        "role": "Engine oil filter", "brand": "TESTMAKER", "part_number": "TEST-H1", "type": "spin-on", "thread": "M0x0",
        "detail_file": "sources/standard/test-h1.json", "images": ["sources/standard/img/test-h1-aaaaaaaaaaaa.jpg"],
        "oe_alfa": ["ALFA-TEST-9"], "status": "standard", "basis": "owner-attested: the only oil filter used on this car",
        "retailer_ref": {"shop": "TestShop", "url": "https://shop.example/x", "price": "£9.29", "fetched": "2026-10-26"}}}}}),
        encoding="utf-8")
    from cuore.services import standard_parts as sp
    got = sp.for_vin(tvin)
    assert len(got) == 1 and got[0]["part_number"] == "TEST-H1" and got[0]["images"] == ["test-h1-aaaaaaaaaaaa.jpg"]         and got[0]["key_specs"][0] == ("Height", "85") and sp.for_vin("NOPE") == [] and sp.oil_filter_conflict(tvin)
    r = c.get("/catalog", cookies={"cuore_vin": tvin})
    t = r.text
    for needle in ("Standard on this car", "TESTMAKER", "TEST-H1", "ALFA-TEST-9", "OE-TEST-1", "M0x0",
                   "Owner-attested: the only oil filter used on this car", "£9.29</b> at TestShop (2026-10-26)",
                   "/catalog/standard-img/test-h1-aaaaaaaaaaaa.jpg"):
        assert needle in t, needle
    assert c.get("/catalog/standard-img/test-h1-aaaaaaaaaaaa.jpg").status_code == 200
    for bad in ("..%2Fstandard_parts.json", "%2e%2e%2fcatalog.json", "test-h1-aaaaaaaaaaaa.png", "x.jpg"):
        assert c.get(f"/catalog/standard-img/{bad}").status_code == 404, bad
    r = c.get(f"/v/{tvin}/oil-change")
    t = r.text
    assert r.status_code == 200 and "Fit: TESTMAKER TEST-H1 (standard on this car)" in t, r.status_code
    assert "Conflicts with this car" in t and "spin-on filter (TESTMAKER TEST-H1)" in t and "CONFLICTS WITH THIS CAR" in t
    assert "Not applicable until checked on the car" in t
    (STATE / "parts_catalog" / "standard_parts.json").write_text("{not json", encoding="utf-8")
    assert sp.for_vin(tvin) == []
    r = c.get("/start")
    assert 'href="/catalog"' in r.text and 'class="icon-btn parts-link' in r.text
    print("parts catalogue OK")


if __name__ == "__main__":
    main()
