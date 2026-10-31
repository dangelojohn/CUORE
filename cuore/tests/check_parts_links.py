"""Parts-to-car derived links: pure mapping (cuore/services/parts_links.py), the
"Where it lives on this car" block on the catalogue part page, the
/catalog/system/{key} page, and honest coverage counts. Synthetic catalogue,
temp state dir; no network, no COM3. If the real catalogue exists under
C:/ProgramData it is only read to print coverage.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_parts_links.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="cuore-check-parts-links-"))
os.environ["CUORE_STATE_DIR"] = str(STATE)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

EXPORT = {
    "source": "https://parts.example.com/v-test", "fetched_at": "2026-10-24T12:00:00Z",
    "cats": ["brakes--front-brakes", "electrical--tire-monitoring-system", "body--fenders"], "errors": [],
    "pages": {
        "brakes--front-brakes": {"slug": "brakes--front-brakes", "title": "Front Brakes", "heads": ["Diagram 1: Pads"],
            "thumbs": [""], "rows": [{"d": 0, "ref": "5", "pn": "68400577AA", "name": "Pad Kit, Front Disc Brake",
                                      "href": "", "img": "", "info": {}}]},
        "electrical--tire-monitoring-system": {"slug": "electrical--tire-monitoring-system", "title": "Tire Monitoring",
            "heads": ["Diagram 1: Sensor"], "thumbs": [""], "rows": [{"d": 0, "ref": "1", "pn": "68407400AA",
                "name": "Tire Pressure Sensor", "href": "", "img": "", "info": {}}]},
        "body--fenders": {"slug": "body--fenders", "title": "Fenders", "heads": ["Diagram 1: Fender"], "thumbs": [""],
            "rows": [{"d": 0, "ref": "1", "pn": "11111111AA", "name": "Fender", "href": "", "img": "", "info": {}}]},
    },
}


def main() -> None:
    from cuore.services import parts_links as pl

    # --- pure mapping -------------------------------------------------
    assert pl.system_for_section("brakes--front-brakes") == "brakes_abs"
    assert pl.system_for_section("body--fenders") is None, "unlisted sections stay unmatched"
    r = pl.row_links("electrical--tire-monitoring-system", "Tire Pressure Sensor")
    assert r["systems"] == ["wheels_tpms"] and r["sensors"] == ["tpms_fl", "tpms_fr", "tpms_rl", "tpms_rr"], r
    assert pl.row_links("electrical--power-distribution-center-fuse-block-junction-block-relays-and-fuses--1", "Mini Fuse")["fuse"]
    assert not pl.row_links("body--fenders", "Fuse Cover")["fuse"], "fuse only inside the PDC/battery sections"
    m = pl.load_map()
    assert all(isinstance(v, str) for v in m["sections_to_systems"].values()), "map holds no vendor rows"

    part = {"appearances": [{"diagram": {"slug": "electrical--tire-monitoring-system", "section": "Tire Monitoring"},
                             "row": {"name": "Tire Pressure Sensor"}}]}
    with_vin = pl.for_part(part, "VIN1", {"wheels_tpms": "Wheels & TPMS"})
    assert with_vin["systems"][0]["href"] == "/v/VIN1/systems/wheels_tpms" and with_vin["systems"][0]["label"] == "Wheels & TPMS"
    assert with_vin["sensors"][0]["href"] == "/v/VIN1/sensors#sensor-tpms_fl"
    assert pl.for_part(part, "")["systems"][0]["href"] == "", "no vehicle, no link"

    from cuore.services import systems_bridge
    keys = set(systems_bridge.systems())
    assert set(m["sections_to_systems"].values()) <= keys and {x["system"] for x in m["name_to_systems"]} <= keys, "unknown system key in map"
    sensors = {s["id"] for s in json.loads((ROOT / "cuore" / "data" / "sensors_stelvio_2018.json").read_text(encoding="utf-8"))["sensors"]}
    assert {i for x in m["name_to_sensors"] for i in x["sensors"]} <= sensors, "unknown sensor id in map"

    # --- pages --------------------------------------------------------
    from fastapi.testclient import TestClient
    from cuore.app import create_app
    sys.path.insert(0, str(ROOT / "scripts" / "parts"))
    import build_parts_catalog as b
    exp = STATE / "export.json"
    exp.write_text(json.dumps(EXPORT), encoding="utf-8")
    b.build(exp, fetch_images=False)
    c = TestClient(create_app(), follow_redirects=False)

    h = c.get("/catalog/p/68407400AA")
    assert h.status_code == 200 and "Where it lives on this car" in h.text and "wheels tpms" in h.text.lower() or "TPMS" in h.text, h.status_code
    assert "Sensor:" in h.text and "System:" in h.text
    h = c.get("/catalog/p/11111111AA")
    assert h.status_code == 200 and "no mapping table names this section" in h.text
    h = c.get("/catalog/system/brakes_abs")
    assert h.status_code == 200 and "Front Brakes" in h.text and "1 part rows" in h.text
    h = c.get("/catalog/system/nope")
    assert h.status_code == 200 and "No catalogue section is mapped" in h.text

    from cuore.services import parts_catalog as pc
    cat = pc.load()
    cv = pl.coverage(cat)
    assert cv["rows"] == 3 and cv["with_any"] == 2 and cv["unmatched"] == 1 and cv["with_sensor"] == 1, cv
    secs = pl.sections_for_system(cat, "brakes_abs")
    assert len(secs) == 1 and secs[0]["parts"] == 1 and secs[0]["diagram_id"], secs

    real = Path("C:/ProgramData/cuore/parts_catalog/stelvio-2018-2.0l/catalog.json")
    if real.is_file():
        rc = pl.coverage(json.loads(real.read_text(encoding="utf-8")))
        print(f"real catalogue: {rc['with_any']}/{rc['rows']} rows linked ({rc['unmatched']} unmatched); "
              f"system {rc['with_system']}, sensor {rc['with_sensor']}, fuse {rc['with_fuse']}")
    print("check_parts_links: OK")


if __name__ == "__main__":
    main()
