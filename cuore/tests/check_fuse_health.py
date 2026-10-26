"""Checks for fuse health (``cuore.services.fuse_health``) and the page
``/v/{vin}/fuses``.

  1. Every registry row carries a source; grey is the default with no evidence.
  2. Each colour rule: technician blown (red), every fed module silent (red),
     suspect / voltage drop over limit (orange), supply code on a fed module
     (orange), code electrical path naming the fuse (orange), technician OK
     (green), inferred green (labelled), and a newer OK check clears older codes.
  3. add_check / add_item validation (empty source rejected), append-only files.
  4. Page 200, filters, check and item POST redirects.

Run:
    .venv/Scripts/python.exe cuore/tests/check_fuse_health.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_TMP = tempfile.mkdtemp(prefix="cuore_fuse_")
os.environ["CUORE_STATE_DIR"] = _TMP

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import fuse_health as fh  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def write_scan(answered: dict[str, bool], scan_id: str = "SCAN_2610250900") -> None:
    cov = [{"module": m, "category": "answered" if ok else "not_reachable", "why": None, "active": 0}
           for m, ok in answered.items()]
    (Path(_TMP) / "fullscan_last.json").write_text(json.dumps({"scan_id": scan_id, "coverage": cov}), encoding="utf-8")


def reset() -> None:
    for n in (fh.CHECKS_FILE, fh.ITEMS_FILE, fh.FULLSCAN_FILE, fh.SENSOR_CHECKS_FILE):
        p = Path(_TMP) / n
        if p.exists():
            p.unlink()


def by_id(h: dict, i: str) -> dict:
    return next(x for x in h["items"] if x["id"] == i)


# stub the outside world (no MES logs, no inspections store)
fh._inspections = lambda vin, item: []
CODES: list[dict] = []
HOPS: dict[str, set] = {}
fh._current_codes = lambda vin, mods: list(CODES)
fh._path_hops = lambda code: HOPS.get(code, set())
# fixed "now" so the 7-day staleness rule does not make this script date-dependent
from datetime import datetime as _dt  # noqa: E402
_real_age = fh._age_days
fh._age_days = lambda at: (_dt(2026, 10, 25, 12, 0) - _dt.fromisoformat(str(at)[:19])).days

# 1. registry
reg = fh.registry()
check(len(reg) >= 10, "registry has the sourced rows")
check(all(str(r.get("source") or "").strip() for r in reg), "every registry row has a source")
check(all(r["kind"] in ("fuse", "relay") for r in reg), "kinds valid")
check(all(r.get("zone") or r.get("location_confidence") == "UNKNOWN" for r in reg), "unplaced rows are UNKNOWN")
h = fh.health(VIN)
check(h["counts"]["grey"] == len(h["items"]) and h["counts"]["total"] == len(h["items"]), "no evidence -> all grey")
check(all(i["status"] == "grey" and i["reasons"] for i in h["items"]), "grey rows explain themselves")
check(bool(h["gaps"]) and any("full fuse list not sourced yet" in g for g in h["gaps"]), "gaps list present")
check("bcm_feed_20a" in h["unplaced"], "row without location is unplaced")

# 2. rules
fh.add_check(VIN, "f82", "blown", "visual", note="element open")
h = fh.health(VIN)
f82 = by_id(h, "f82")
check(f82["status"] == "red" and "RED" in f82["reasons"][0], "technician blown -> red")
fh.add_check(VIN, "f82", "ok", "continuity")
check(by_id(fh.health(VIN), "f82")["status"] == "green", "newer technician OK -> green")
fh.add_check(VIN, "f82", "suspect", "visual", note="hairline")
check(by_id(fh.health(VIN), "f82")["status"] == "orange", "technician suspect -> orange")

reset()
fh.add_check(VIN, "f82", "ok", "voltage_drop", value="0.45", unit="V", limit="0.2")
r = by_id(fh.health(VIN), "f82")
check(r["status"] == "orange" and any("over the limit" in e["text"] for e in r["evidence"]), "voltage drop over limit -> orange")
reset()
fh.add_check(VIN, "f82", "ok", "voltage_drop", value="0.1", unit="V", limit="0.2")
check(by_id(fh.health(VIN), "f82")["status"] == "green", "voltage drop within limit -> green")

reset()
write_scan({"BCM": False, "ECM": True})
r = by_id(fh.health(VIN), "f82")
check(r["status"] == "red" and "did not answer" in r["reasons"][0], "every fed module silent -> red")
write_scan({"BCM": True, "ECM": True})
r = by_id(fh.health(VIN), "f82")
check(r["status"] == "green" and "inferred: the module it feeds answered at" in r["reasons"][0], "inferred green is labelled")
check(r["evidence"][0]["kind"] == "inferred", "inferred evidence kind")
reset()
write_scan({"BCM": True}, scan_id="SCAN_2610100900")
r_old = by_id(fh.health(VIN), "f82")
check(r_old["status"] == "grey" and r_old.get("stale") and "too old" in r_old["reasons"][-1],
      "inferred green older than 7 days turns grey (stale)")
reset()

CODES[:] = [{"code": "U0140-87", "module": "BCM", "description": "Battery voltage low supply fault", "last_seen": "2026-10-25T10:00:00"}]
r = by_id(fh.health(VIN), "f82")
check(r["status"] == "orange" and "U0140-87" in r["codes"], "supply code on fed module -> orange")
check("inferred" not in " ".join(r["reasons"]), "supply code blocks inferred green")
CODES[:] = [{"code": "P0456-00", "module": "ECM", "description": "EVAP small leak", "last_seen": "2026-10-25T10:00:00"}]
HOPS["P0456-00"] = {"f82"}
r = by_id(fh.health(VIN), "f82")
check(r["status"] == "orange" and any("electrical path" in x for x in r["reasons"]), "code path naming fuse -> orange")
check(by_id(fh.health(VIN), "f01_luggage")["status"] == "grey", "unrelated fuse stays grey")
fh.add_check(VIN, "f82", "ok", "voltage", value="12.4", unit="V")
check(by_id(fh.health(VIN), "f82")["status"] == "green", "newer technician OK clears older code signal")
CODES.clear()
HOPS.clear()

# 3. validation / append-only
def raises(fn, *a, **k) -> bool:
    try:
        fn(*a, **k)
    except ValueError:
        return True
    return False


check(raises(fh.add_check, VIN, "f82", "fine", "visual"), "bad result rejected")
check(raises(fh.add_check, VIN, "f82", "ok", "guess"), "bad method rejected")
check(raises(fh.add_check, VIN, "nope", "ok", "visual"), "unknown item rejected")
check(raises(fh.add_check, VIN, "f82", "ok", "voltage", value="abc"), "non-numeric value rejected")
check(raises(fh.add_item, kind="fuse", label="X", source="  "), "empty source rejected")
check(raises(fh.add_item, kind="fuse", label="", source="manual"), "empty label rejected")
check(raises(fh.add_item, kind="fuse", label="X", source="manual", box="nope"), "unknown box rejected")
check(raises(fh.add_item, kind="fuse", label="X", source="manual", rating_a="abc"), "bad rating rejected")
check(raises(fh.add_item, kind="fuze", label="X", source="manual"), "bad kind rejected")
n0 = len((Path(_TMP) / fh.CHECKS_FILE).read_text().splitlines())
fh.add_check(VIN, "f82", "ok", "visual")
check(len((Path(_TMP) / fh.CHECKS_FILE).read_text().splitlines()) == n0 + 1, "checks append-only")
rec = fh.add_item(kind="relay", label="Fuel pump relay", source="owner's manual p.1 (test)", box="engine_pdc",
                  position="K3", rating_a="30", feeds_modules=["ecm"])
reg = fh.registry()
row = next(r for r in reg if r["id"] == rec["id"])
check(row["added_by_technician"] and "Added by technician" in row["notes"] and row["zone"] == "fuse_box_engine_bay",
      "added item merged, marked, zoned from its box")
check(raises(fh.add_item, kind="relay", label="Fuel pump relay", source="x", box="engine_pdc", position="K3"), "duplicate rejected")
check(by_id(fh.health(VIN), rec["id"])["feeds_modules"] == ["ECM"], "added item module upper-cased")

# 4. page
reset()
fh_health = fh.health
client = TestClient(create_app())
r = client.get(f"/v/{VIN}/fuses")
check(r.status_code == 200 and "Fuses &amp; relays" in r.text, "page 200 with title")
check("What is not sourced yet" in r.text, "gaps panel")
check("Tested OK" in r.text and "Add a fuse or relay" not in r.text and "Add a fuse or relay" in client.get(f"/v/{VIN}/fuses/data").text,
      "test buttons on the mechanic page, add forms on the owner page")
check(f'/v/{VIN}/network' in r.text, "module links to network")
fh.add_check(VIN, "f82", "blown", "visual")
r = client.get(f"/v/{VIN}/fuses?status=red")
check(r.status_code == 200 and "fuse-f82" in r.text and 'id="fuse-f01_luggage"' not in r.text, "status filter")
r = client.get(f"/v/{VIN}/fuses?box=rear_pdc")
check(r.status_code == 200 and "Rear power distribution center" in r.text, "box filter")
r = client.get(f"/v/{VIN}/fuses?status=bogus&box=bogus")
check(r.status_code == 200, "bogus filters ignored")
r = client.post(f"/v/{VIN}/fuses/check", data={"item": "f82", "result": "ok", "method": "visual"}, follow_redirects=False)
check(r.status_code == 303 and "msg=Check%20recorded" in r.headers["location"], "check POST redirects")
r = client.post(f"/v/{VIN}/fuses/check", data={"item": "f82", "result": "zzz", "method": "visual"}, follow_redirects=False)
check(r.status_code == 303 and "not%20saved" in r.headers["location"], "bad check POST explains")
r = client.post(f"/v/{VIN}/fuses/check", data={"item": "f82", "result": "ok", "method": "visual", "redirect_to": "//evil.example"},
                follow_redirects=False)
check(r.headers["location"].startswith(f"/v/{VIN}/fuses"), "unsafe redirect_to ignored")
r = client.post(f"/v/{VIN}/fuses/item", data={"kind": "fuse", "label": "Test fuse", "source": ""}, follow_redirects=False)
check(r.status_code == 303 and "source" in r.headers["location"], "item POST without source rejected")
r = client.post(f"/v/{VIN}/fuses/item", data={"kind": "fuse", "label": "Test fuse", "source": "box cover photo", "box": "interior_box",
                                              "position": "F99", "rating_a": "10"}, follow_redirects=False)
check(r.status_code == 303 and "msg=Fuse/relay%20added" in r.headers["location"], "item POST redirects")
check("Test fuse" in client.get(f"/v/{VIN}/fuses").text, "added item shown")

# page degrades when the service fails
import cuore.services.fuse_health as _m  # noqa: E402
_m.health = lambda vin: (_ for _ in ()).throw(RuntimeError("boom"))
r = client.get(f"/v/{VIN}/fuses")
check(r.status_code == 200 and "not available yet" in r.text, "page survives service failure")
_m.health = fh_health

print(f"fuse_health checks: {passed} passed, {len(failures)} failed")
for f in failures:
    print("  FAIL:", f)
sys.exit(1 if failures else 0)
