"""Checks for the tech-entered element location feature (state in a temp dir).
Run: .venv/Scripts/python.exe cuore/tests/check_element_locations.py"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-eloc-")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import element_locations as el  # noqa: E402
from cuore.web import electrical_routes as er, electrical_svg  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
OTHER = "ZASFAKPN1J7B00001"
failures: list[str] = []
n = 0


def check(label, cond, detail=""):
    global n
    n += 1
    print(f"  [{'ok' if cond else 'FAIL'}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


app = create_app()
if not any(getattr(r, "path", "") == "/v/{vin}/electrical/location" for r in app.routes):
    app.include_router(er.router)
c = TestClient(app)

base = er._elements_raw()
unknown = [i for i, e in base.items()
           if electrical_svg.resolve_zone((e.get("location") or {}).get("zone")) == "other"]
sourced = [i for i, e in base.items()
           if el._RANK.get(str((e.get("location") or {}).get("confidence") or "").lower(), 0) >= 3
           and electrical_svg.resolve_zone((e.get("location") or {}).get("zone")) != "other"
           and not el._UNSOURCED.search(str((e.get("location") or {}).get("source") or ""))]
print(f"  elements={len(base)} unknown={len(unknown)} sourced-high={len(sourced)}")
check("have an unplaced element and a sourced one to test", bool(unknown) and bool(sourced))
U, S = unknown[0], sourced[0]
S_zone = base[S]["location"]["zone"]
page0 = c.get(f"/v/{VIN}/electrical").text
check("unplaced cards show a Set location form", "Set location" in page0 and "/electrical/location" in page0)


def post(**kw):
    d = {"element": U, "zone": "trunk", "description": "left of spare well", "access": "lift floor",
         "source": "observed on car by tester", "confidence": "observed", "by": "tester",
         "redirect_to": f"/v/{VIN}/electrical"}
    d.update(kw)
    return c.post(f"/v/{VIN}/electrical/location", data=d, follow_redirects=False)


check("source is required", "error=" in post(source="").headers["location"])
check("unknown zone rejected", "error=" in post(zone="moon").headers["location"])
check("unknown element rejected", "error=" in post(element="nope_x").headers["location"])
check("bad confidence rejected", "error=" in post(confidence="sure").headers["location"])
check("overlong description rejected", "error=" in post(description="x" * 301).headers["location"])
check("unsafe redirect replaced", post(redirect_to="//evil.com", source="").headers["location"].startswith("/v/"))
check("nothing written by rejected posts", not el._path().exists() or not el._read())

r = post()
check("valid POST redirects with located=1", r.status_code == 303 and "located=1" in r.headers["location"])
check("element moved to its zone", er._elements(vin=VIN)[U]["location"]["zone"] == "trunk")
page = c.get(f"/v/{VIN}/electrical").text
check("card shows description and source", "left of spare well" in page and "observed on car by tester" in page)

esc = post(description="<script>alert(1)</script>", element=unknown[1] if len(unknown) > 1 else U)
check("output escaped", "<script>alert(1)</script>" not in c.get(f"/v/{VIN}/electrical").text)
post(description="left of spare well", element=unknown[1] if len(unknown) > 1 else U)

# sourced original not overridden: proposed instead
post(element=S, zone="trunk", description="tech says elsewhere", source="observed by tester", confidence="observed")
e = er._elements(vin=VIN)[S]
check("sourced original kept", e["location"]["zone"] == S_zone and not e["location"].get("tech_entry"))
check("tech entry shown as proposed", (e.get("location_proposed") or {}).get("description") == "tech says elsewhere")
check("page shows Proposed correction", "Proposed correction" in c.get(f"/v/{VIN}/electrical").text)

# model inheritance
inh = er._elements(vin=OTHER)[U]["location"]
check("same-model car inherits", inh["zone"] == "trunk" and inh["from_other_car"] is True)
_od = er._dossier; er._dossier = lambda v, _d=_od: _d(VIN); _o = c.get(f"/v/{OTHER}/electrical"); check("other-car page says so", "from another car of the same model" in _o.text, str(_o.status_code))
er._dossier = _od
check("different model does not inherit", er._elements(vin="1HGCM82633A004352")[U]["location"].get("zone") != "trunk")
check("same car not flagged other-car", er._elements(vin=VIN)[U]["location"]["from_other_car"] is False)

# hop overlay
hops = [{"id": U, "location": dict(base[U].get("location") or {}), "role": "x"}]
el.apply_to_hops(VIN, hops, electrical_svg.resolve_zone)
check("hop shows description + confidence + source",
      hops[0]["location"]["description"] == "left of spare well" and hops[0]["confidence"] == "observed"
      and "tester" in hops[0]["source"])

# retract
entry = el.latest_for_model(VIN)[U]
rr = c.post(f"/v/{VIN}/electrical/location", data={"op": "retract", "entry_id": entry["id"],
            "redirect_to": f"/v/{VIN}/electrical"}, follow_redirects=False)
check("retract accepted", "located=1" in rr.headers["location"])
check("retract restores original", er._elements(vin=VIN)[U]["location"].get("zone") == base[U].get("location", {}).get("zone"))
check("file is append-only (set + retract lines kept)", len(el._read()) >= 4)

print(f"\n{n - len(failures)}/{n} checks passed")
sys.exit(1 if failures else 0)
