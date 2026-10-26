"""Checks for real component photos (service, keys file, endpoint, sensor card).

Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_component_images.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
TMP = Path(tempfile.mkdtemp(prefix="cuore_ci_"))
os.environ["CUORE_STATE_DIR"] = str(TMP)

from fastapi.testclient import TestClient  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond, label):
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def sensor(id_, label):
    return {"id": id_, "label": label, "system": "Engine", "module": "ECM", "bus": "CAN", "channels": ["value"],
            "readable": True, "readable_note": "", "element_id": None, "zone": "engine_bay", "side": "centre",
            "location_confidence": "SOURCED", "location_source": "fixture", "status": "green", "reasons": [],
            "last_read": None, "values": [], "codes": []}


SENSORS = [sensor("map_sensor", "MAP sensor"), sensor("o2_b1s1", "Upstream O2"), sensor("humidity_sensor", "Humidity")]
fake = types.ModuleType("cuore.services.sensor_health")
fake.health = lambda vin: {"vin": vin, "checked_at": None, "sensors": list(SENSORS),
                           "counts": {"green": 3}, "unplaced": []}
import cuore.services as _svc  # noqa: E402

sys.modules["cuore.services.sensor_health"] = fake
_svc.sensor_health = fake

from cuore.app import create_app  # noqa: E402
from cuore.services import component_images as ci  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
client = TestClient(create_app(), follow_redirects=False)

# missing catalogue
check(ci.images_for(["map sensor"]) == [], "missing catalogue -> []")
check(ci.images_for_pn("PNONE") == [], "missing catalogue pn -> []")
r = client.get(f"/v/{VIN}/sensors")
check(r.status_code == 200 and "Mopar catalogue photo" not in r.text, "sensors page renders without catalogue")
r = client.get(f"/v/{VIN}/component-images?key=map_sensor")
check(r.status_code == 200 and r.json()["images"] == [], "endpoint empty without catalogue")

# fixture catalogue
cdir = TMP / "parts_catalog" / "fix-cat"
(cdir / "img").mkdir(parents=True)


def part(pn, name, desc, fit, photo):
    return {"ref": "1", "pn": pn, "name": name, "description": desc, "notes": "", "fitment": fit, "url": "",
            "photos": [{"file": photo, "url": "x"}] if photo else []}


cat = {"id": "fix-cat", "title": "fix", "sections": [], "groups": [], "diagrams": {
    "d1": {"id": "d1", "title": "Engine", "parts": [
        part("AAA111", "Map Sensor", "", "other", "a" * 20 + ".png"),
        part("BBB222", "Map Sensor", "own one", "own", "b" * 20 + ".png"),
        part("CCC333", "Oxygen Sensor", "Used After 2021", "own", "c" * 20 + ".webp"),
        part("DDD444", "Map Sensor Bracket", "", "own", None),
        part("EEE555", "Mini Fuse", "15 AMP", "own", "e" * 20 + ".png")]}}}
(cdir / "catalog.json").write_text(json.dumps(cat), encoding="utf-8")

res = ci.images_for(["MAP", "sensor"])
check([x["pn"] for x in res] == ["BBB222"], "keyword match, case-insensitive, own only, photo required")
check(res and res[0]["photo_url"] == "/catalog/img/fix-cat/" + "b" * 20 + ".png"
      and res[0]["part_url"] == "/catalog/p/BBB222" and res[0]["diagram_id"] == "d1", "result fields")
res = ci.images_for(["map sensor"], fitment_own=False)
check([x["pn"] for x in res] == ["BBB222", "AAA111"], "own preferred, others after when not restricted")
check(len(ci.images_for(["map sensor"], fitment_own=False, limit=1)) == 1, "limit")
check(ci.images_for(["map", "oxygen"]) == [], "all terms must match")
check(ci.images_for_pn("ccc-333")[0]["name"] == "Oxygen Sensor", "images_for_pn normalises")

r = client.get(f"/v/{VIN}/component-images?key=map_sensor")
j = r.json()
check(r.status_code == 200 and [x["pn"] for x in j["images"]] == ["BBB222"], "endpoint JSON")
check(client.get(f"/v/{VIN}/component-images?key=nope").json()["images"] == [], "unknown key -> []")

r = client.get(f"/v/{VIN}/sensors")
check("/catalog/img/fix-cat/" + "b" * 20 + ".png" in r.text, "sensor card shows photo")
check("The part type, not this car" in r.text, "sensor card caption")
check('href="/catalog/p/BBB222"' in r.text and "Oxygen Sensor" in r.text, "photo links to part page, part name shown")
check(r.text.count("<figcaption>Mopar catalogue photo") == r.text.count("class=\"sens-photo-frame\"") >= 1, "only sensors with photos get a caption, one photo each")

# keys file
raw = (Path(__file__).resolve().parents[1] / "data" / "component_image_keys.json").read_text(encoding="utf-8")
import re  # noqa: E402

check(not re.search(r"\b\d{5,}[A-Z]{1,2}\b", raw) and not re.search(r"\b[0-9]{4,}[A-Z0-9]{2,}\b", raw),
      "no part numbers in keys file")
check("_notes" in json.loads(raw) and len(ci.keys()) > 10, "keys file has notes and keys")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
