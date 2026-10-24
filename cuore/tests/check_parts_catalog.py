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
                {"d": 0, "ref": "5", "pn": "68400577AA", "name": "Pad Kit, Front Disc Brake",
                 "href": "/oem-parts/x-68400577aa", "img": "", "info": {}},
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
    out = b.build(exp, fetch_images=False)
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
    assert r.status_code == 200 and "Front Brakes" in t and "Disc Brake Caliper Assembly, Right" in t, r.status_code
    assert "Not for this car" in t and "/catalog/d/brakes--front-brakes--1" in t

    r = c.get("/catalog", params={"q": "68400577AA"})
    assert r.status_code == 303 and r.headers["location"] == "/catalog/p/68400577AA", r.headers.get("location")
    r = c.get("/catalog", params={"q": "6842018"})
    assert r.status_code == 200 and "68420187AA" in r.text and "68420186AA" in r.text and "OTHER ENGINE" in r.text
    r = c.get("/catalog", params={"q": "pad kit"})
    assert r.status_code == 200 and "68400577AA" in r.text and "1 result" in r.text

    r = c.get("/catalog/d/brakes--front-brakes--1")
    t = r.text
    assert r.status_code == 200 and f"/catalog/img/stelvio-2018-2.0l/{img_name}" in t
    for needle in ("Without Brake Pads. Front.", "What the mechanic needs to know", "Fixed front calipers.",
                   "Retract the EPB", "2017+ Giulia", "Torque (CUORE torque library)"):
        assert needle in t, needle

    r = c.get("/catalog/p/68420187AA")
    t = r.text
    assert r.status_code == 200, r.status_code
    for needle in ("Where it fits", "68420186AA", "Same callout", "diagram: Disc Brake Caliper Assembly, Right"):
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
