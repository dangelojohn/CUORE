"""Checks for cuore/services/path_tests.py and the path-tests routes.

Run: .venv/Scripts/python.exe cuore/tests/check_path_tests.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-pathtests-")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import path_tests as pt  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label} {detail}")
        print("FAIL", label, detail)


def H(i, kind="component", role=None, cond=None):
    return {"id": i, "label": i.upper(), "kind": kind, "role": role or kind, "condition": cond,
            "location": {"description": "somewhere"}}


path = [H("f1", "fuse"), H("c1", "connector"), H("m1", "component"), H("hose", "hose"), H("g1", "ground")]
els = {"c1": {"terminal": "C1-4"}, "m1": {}, "f1": {}, "g1": {}}

# 1. plan -----------------------------------------------------------------
segs = pt.build_segments(path, els)
ids = [s["id"] for s in segs]
check("segments: power f1>c1, c1>m1, ground m1>g1 (hose skipped)",
      ids == ["power:f1>c1", "power:c1>m1", "ground:m1>g1"], str(ids))
check("power limit 0.5 labelled general", segs[0]["limit_v"] == 0.5 and "general practice, not a Stelvio spec" in segs[0]["limit_source"])
check("ground limit 0.2 labelled general", segs[2]["limit_v"] == 0.2 and "general practice, not a Stelvio spec" in segs[2]["limit_source"])
check("terminal named when element has it", "C1-4" in segs[0]["instruction"] and "loaded" in segs[0]["instruction"])
els2 = dict(els, g1={"max_drop_v": 0.05, "label": "G1", "source": "wiring manual"})
sg = pt.build_segments(path, els2)[2]
check("sourced limit wins and is not labelled general", sg["limit_v"] == 0.05 and not sg["general"]
      and "general practice" not in sg["limit_source"], sg["limit_source"])

# 2. split ----------------------------------------------------------------
hops = pt.electrical_hops(path)
sp = pt.split_suggestion(hops, segs, {})
check("split picks middle of 4 remaining", sp["remaining"] == 4 and sp["hop_id"] == "m1"
      and "splits the remaining 4 hops in half" in sp["message"], sp["message"])
res = {"power:f1>c1": {"pass": True}}
sp2 = pt.split_suggestion(hops, segs, res)
check("passed segment clears its hops", sp2["remaining"] == 2 and "f1" not in sp2["remaining_ids"], str(sp2))
hops_ok = [dict(h, condition="ok") if h["id"] == "m1" else h for h in hops]
sp3 = pt.split_suggestion(hops_ok, segs, res)
check("ok inspection clears hop; one left -> only hop", sp3["remaining"] == 1 and sp3["hop_id"] == "g1", str(sp3))

# 3. shared points -------------------------------------------------------
others = {"U1": {"ids": ["g1", "x"], "active": True}, "U2": {"ids": ["c1"], "active": False},
          "U3": {"ids": ["zz"], "active": True}}
sh = pt.shared_points("P0", hops, others)
check("shared: g1 common (active code), c1 shared but not common, f1 none",
      sh["g1"]["common"] and not sh["c1"]["common"] and "f1" not in sh, str(sh))

# flags differ: g1 on 2 active codes, c1 on 1, f1/m1 on none -> g1 and c1 above min 0
oth2 = {"U1": {"ids": ["g1", "c1"], "active": True}, "U2": {"ids": ["g1"], "active": True}}
sh2 = pt.shared_points("P0", hops, oth2)
check("differing counts: both shared hops flagged above minimum",
      sh2["g1"]["common"] and sh2["g1"]["n_active"] == 2 and sh2["c1"]["common"] and pt.shared_summary(hops, sh2) is None)
oth3 = {"U1": {"ids": ["g1"], "active": True}, "U2": {"ids": ["g1", "c1"], "active": True}}
sh3 = pt.shared_points("P0", hops, oth3)
check("g1 (2 active) flagged, c1 (1) also above 0; ranking by count kept",
      sh3["g1"]["n_active"] > sh3["c1"]["n_active"])
# all equal: every hop on the same active codes -> no flags, one summary
allids = [h["id"] for h in hops]
oth4 = {"U1": {"ids": allids, "active": True}, "U2": {"ids": allids, "active": True},
        "U3": {"ids": allids, "active": False}}
sh4 = pt.shared_points("P0", hops, oth4)
sm = pt.shared_summary(hops, sh4)
check("all equal: no hop flagged", not any(v["common"] for v in sh4.values()), str(sh4))
check("all equal: one summary with N and codes", sm == {"n": len(hops), "codes": ["U1", "U2"]}, str(sm))

# 4. validation -----------------------------------------------------------
good = {"segment": "power:f1>c1", "measured_v": "0.31", "state": "ignition_on", "by": "jd"}
rec, err = pt.validate_test(good, VIN, "P0", segs)
check("valid test accepted + pass computed", rec and rec["pass"] and rec["limit_v"] == 0.5, str(err))
rec2, _ = pt.validate_test(dict(good, measured_v="0.9"), VIN, "P0", segs)
check("over limit fails", rec2 and not rec2["pass"])
for label, bad in (("nan", {"measured_v": "nan"}), ("range", {"measured_v": "99"}), ("text", {"measured_v": "abc"}),
                   ("segment", {"segment": "power:zz>yy"}), ("state", {"state": "bogus"})):
    r, e = pt.validate_test(dict(good, **bad), VIN, "P0", segs)
    check(f"reject {label}", r is None and e)
r, e = pt.validate_repair({"element": "nope", "what": "x"}, VIN, "P0", {"g1"})
check("repair rejects unknown element", r is None and e)
r, e = pt.validate_repair({"element": "g1", "what": "x" * 301}, VIN, "P0", {"g1"})
check("repair rejects long text", r is None and e)
r, e = pt.validate_repair({"element": "g1", "what": "cleaned", "date": "2026-13-40"}, VIN, "P0", {"g1"})
check("repair rejects bad date", r is None and e)

# 5. proven logic ----------------------------------------------------------
repair = {"kind": "repair", "element": "g1", "what": "cleaned", "by": "jd", "date": "2026-10-01", "at": "2026-10-01T10:00:00"}
pre = {"kind": "test", "vin": VIN, "code": "P0", "side": "ground", "from_id": "m1", "to_id": "g1",
       "pass": True, "at": "2026-10-01T09:00:00", "measured_v": 0.1}
st = pt.repair_state("g1", repair, segs, [pre], VIN, "P0")
check("pre-repair pass does not prove", st["state"] == "repaired", str(st))
post = dict(pre, at="2026-10-01T11:00:00")
check("post-repair pass proves", pt.repair_state("g1", repair, segs, [pre, post], VIN, "P0")["state"] == "proven")
check("post-repair FAIL does not prove",
      pt.repair_state("g1", repair, segs, [dict(post, **{"pass": False})], VIN, "P0")["state"] == "repaired")
other_seg = dict(post, side="power", from_id="f1", to_id="c1")
check("pass on segment not touching hop does not prove",
      pt.repair_state("g1", repair, segs, [other_seg], VIN, "P0")["state"] == "repaired")
check("code seen after repair blocks proof",
      pt.repair_state("g1", repair, segs, [post], VIN, "P0", code_last_seen="2026-10-05 10:00")["state"] == "code_returned")
check("no repair -> none", pt.repair_state("g1", None, segs, [post], VIN, "P0")["state"] == "none")

# 6. routes ---------------------------------------------------------------
client = TestClient(create_app())
CODE = "U1713"
page = client.get(f"/v/{VIN}/code/{CODE}")
check("code page 200 with test plan", page.status_code == 200 and "Voltage-drop test plan" in page.text
      and "Test here first" in page.text and "path-more" not in page.text and "Print path sheet" in page.text,
      str(page.status_code))
check("general label on page", "general practice, not a Stelvio spec" in page.text)
data = __import__("cuore.web.path_tests_routes", fromlist=["x"]).path_tests_for(VIN, CODE)
seg = data["segments"][0]
url = f"/v/{VIN}/code/{CODE}/path-test"
r = client.post(url, data={"segment": seg["id"], "measured_v": "0.12", "state": "ignition_on", "by": "t",
                           "redirect_to": f"/v/{VIN}/code/{CODE}"}, follow_redirects=False)
check("POST test redirects with saved", r.status_code == 303 and "pt=test" in r.headers["location"], str(r.headers))
check("record stored in jsonl", len(pt.read_all(VIN, CODE)) == 1 and pt.store_path().name == "path_tests.jsonl")
r = client.post(url, data={"segment": seg["id"], "measured_v": "500"}, follow_redirects=False)
check("bad volts not stored", "pt_error" in r.headers["location"] and len(pt.read_all(VIN, CODE)) == 1)
r = client.post(url, data={"segment": seg["id"], "measured_v": "1", "redirect_to": "//evil.com"}, follow_redirects=False)
check("unsafe redirect replaced", r.headers["location"].startswith(f"/v/{VIN}/code/"), r.headers["location"])
page = client.get(f"/v/{VIN}/code/{CODE}")
check("saved result history shown", "0.12 V vs" in page.text and "fail 1.0 V" in page.text)
hop_id = data["hops"][-1]["id"]
r = client.post(f"/v/{VIN}/code/{CODE}/path-repair", data={"element": hop_id, "what": "cleaned ground", "by": "t"},
                follow_redirects=False)
check("repair stored", "pt=repair" in r.headers["location"] and any(x["kind"] == "repair" for x in pt.read_all(VIN)))
page = client.get(f"/v/{VIN}/code/{CODE}")
check("hop shows repaired, not proven without reading", "repaired" in page.text and "repaired and proven" not in page.text)
r = client.post(f"/v/{VIN}/code/{CODE}/path-repair", data={"element": "bogus", "what": "x"}, follow_redirects=False)
check("repair unknown element rejected", "pt_error" in r.headers["location"])
sheet = client.get(f"/v/{VIN}/code/{CODE}/path-sheet")
check("path sheet renders, no nav, has table", sheet.status_code == 200 and "Voltage-drop table" in sheet.text
      and "Safety" in sheet.text and "<nav" not in sheet.text)
check("sheet bad code 400", client.get(f"/v/{VIN}/code/..%2fx!/path-sheet").status_code in (400, 404))

print(f"{checks - len(failures)}/{checks} checks passed")
sys.exit(1 if failures else 0)
