"""Checks for cuore.services.path_diag (network view, wiggle marks, pin data,
freeze-frame patterns) and its routes. Plain script, exit 1 on failure.

Run: .venv/Scripts/python.exe cuore/tests/check_path_diag.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mes-log-mcp"))
_TMP = tempfile.mkdtemp(prefix="cuore-check-path-diag-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_AUTOSTART"] = "0"

from cuore.services import path_diag as pd  # noqa: E402

failures: list[str] = []
n_checks = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global n_checks
    n_checks += 1
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


VIN = "ZASFAKPN5J7B88115"
OTHER = "ZASFAKPN0J7B00001"

# --- network ---------------------------------------------------------------
scan = {"scan_id": "SCAN_2610241321", "vin": VIN, "cable": "none", "coverage": [
    {"bus": "can_c", "module": "ECM", "category": "answered", "why": None},
    {"bus": "can_c", "module": "BCM", "category": "answered", "why": None},
    {"bus": "can_c", "module": "ETM", "category": "silent", "why": "no reply"},
    {"bus": "can_c", "module": "DTCM", "category": "not_reachable", "why": "no known address"},
    {"bus": "can_ihs", "module": "HVAC", "category": "not_reachable", "why": "needs blue A5 cable"},
]}
net = pd.build_network(VIN, "U1713", scan=scan,
                       description=("Engine control (NCM) - Signal/message erratic", "fixture"))
mods = {m["code"]: m for b in net["buses"] for m in b["modules"]}
check("status answered", mods["ECM"]["status"] == "answered")
check("status silent", mods["ETM"]["status"] == "silent")
check("not_reachable -> unchecked", mods["DTCM"]["status"] == "unchecked" and mods["HVAC"]["status"] == "unchecked")
check("ECM address from table", mods["ECM"]["address"] == "0x10", str(mods["ECM"]["address"]))
check("BCM address", mods["BCM"]["address"] == "0x40", str(mods["BCM"]["address"]))
check("NCM alias decodes to ECM and highlights it", net["lost"] == ["ECM"] and mods["ECM"]["lost"] and not mods["BCM"]["lost"])
check("scan time from scan id", net["scan"]["at"] == "2026-10-24 13:21", str(net["scan"]["at"]))
svg = pd.network_svg(net)
check("svg has classes, no inline colour", "pd-answered" in svg and "pd-silent" in svg and "pd-unchecked" in svg
      and "pd-lost" in svg and "fill=\"#" not in svg and "stroke=\"#" not in svg)

net2 = pd.build_network(VIN, "U1999", scan=scan, description=("Some undecodable text", "fixture"))
check("no highlight when nothing decodes", net2["lost"] == [] and not any(m["lost"] for b in net2["buses"] for m in b["modules"]))
net3 = pd.build_network(VIN, "U1999", scan=scan, description=("", ""))
check("no highlight when no description", net3["lost"] == [])
net4 = pd.build_network(VIN, "U0100", scan=scan, description=("Lost communication with ECM/PCM", "fixture"))
check("lost-communication wording decodes", net4["lost"] == ["ECM"])
nos = pd.build_network(VIN, "U1713", scan={"coverage": []}, description=("", ""))
check("no scan -> has_scan False", nos["has_scan"] is False)
evil = {"coverage": [{"bus": "can_c", "module": "<script>x</script>", "category": "answered", "why": "a&b"}]}
esvg = pd.network_svg(pd.build_network(VIN, "U1", scan=evil, description=("", "")))
check("svg text escaped", "<script>" not in esvg and "&lt;script&gt;" in esvg)
check("checklist labelled general", "not a Stelvio spec" in pd.CAN_CHECKLIST["label"])

# --- wiggle ----------------------------------------------------------------
hops = {"fuse_f1", "conn_c2"}
err = pd.add_wiggle(VIN, "U1713", "mark", "conn_c2", "lamp flickered", valid_hops=hops, live_active=False)
check("manual mark stored without live session", err is None)
check("unknown hop rejected", pd.add_wiggle(VIN, "U1713", "mark", "nope", valid_hops=hops) is not None)
check("bad action rejected", pd.add_wiggle(VIN, "U1713", "explode", "conn_c2", valid_hops=hops) is not None)
check("long note rejected", pd.add_wiggle(VIN, "U1713", "mark", "conn_c2", "x" * 500, valid_hops=hops) is not None)
check("stop stored", pd.add_wiggle(VIN, "U1713", "stop", live_active=False) is None)
lines = (Path(_TMP) / "wiggle_tests.jsonl").read_text(encoding="utf-8").splitlines()
check("jsonl has 2 lines with note", len(lines) == 2 and json.loads(lines[0])["note"] == "lamp flickered")
tl = pd.wiggle_timeline(VIN, "U1713")
check("no live -> not correlated", len(tl) == 2 and not tl[0]["correlated"] and tl[0]["events"] == [])
pd.add_wiggle(VIN, "U1713", "mark", "fuse_f1", valid_hops=hops, live_active=True, at="2026-10-25T10:00:10")
obs = [{"at": "2026-10-25T10:00:12", "kind": "live_alarm", "vin": VIN, "data": {"channel": "battery_v", "level": "warn", "value": 11.2}},
       {"at": "2026-10-25T10:05:00", "kind": "live_alarm", "vin": VIN, "data": {"channel": "x", "level": "warn", "value": 1}}]
mark = [m for m in pd.wiggle_marks(VIN, "U1713") if m["hop"] == "fuse_f1"]
tl2 = pd.wiggle_timeline(VIN, "U1713", marks=mark, observations=obs,
                         dtc_first_seen={"U1713": "2026-10-25T10:00:15", "P0": "2026-10-25T09:00:00"})
ev = tl2[0]["events"]
check("live events correlated inside window only", tl2[0]["correlated"] and len(ev) == 2
      and {e["kind"] for e in ev} == {"alarm", "dtc"}, str(ev))

# --- pin data ---------------------------------------------------------------
els = {"conn_c2"}
check("source required", pd.add_pin(VIN, "conn_c2", {"pin": "4"}, "", "joe", valid_elements=els) is not None)
check("unknown element rejected", pd.add_pin(VIN, "zzz", {"pin": "4"}, "observed on car", "joe", valid_elements=els) is not None)
check("empty fields rejected", pd.add_pin(VIN, "conn_c2", {}, "observed on car", "joe", valid_elements=els) is not None)
check("long field rejected", pd.add_pin(VIN, "conn_c2", {"pin": "x" * 200}, "observed on car", "joe", valid_elements=els) is not None)
check("pin stored", pd.add_pin(VIN, "conn_c2", {"connector": "C2", "pin": "4", "wire_colour": "VT/GR", "circuit": "CAN-H"},
                               "TechAuthority wiring diagram fig 12", "joe", valid_elements=els) is None)
rows = pd.pins_for(VIN, "conn_c2")
check("row visible, not other car", len(rows) == 1 and rows[0]["pin"] == "4" and not rows[0]["other_car"])
rid = rows[0]["row_id"]
check("amend stored", pd.add_pin(VIN, "conn_c2", {"connector": "C2", "pin": "5"}, "observed on car", "joe",
                                 valid_elements=els, amends=rid) is None)
check("amend of unknown row rejected", pd.add_pin(VIN, "conn_c2", {"pin": "5"}, "x", "joe", valid_elements=els, amends="nope") is not None)
rows = pd.pins_for(VIN, "conn_c2")
check("amend replaces fields, keeps one row", len(rows) == 1 and rows[0]["pin"] == "5" and rows[0]["amended"])
rows_o = pd.pins_for(OTHER, "conn_c2")
check("same model inherits, flagged from another car", len(rows_o) == 1 and rows_o[0]["other_car"] is True)
check("different model does not inherit", pd.pins_for("WBA00000000000000", "conn_c2") == [])
check("model key", pd.model_key(VIN) == "stelvio-2018-2.0")

# --- freeze frames -----------------------------------------------------------
def ff(ts, v, t, rpm, spd):
    return {"timestamp": ts, "dtc": "U1713-2F", "status": "stored", "file": "f",
            "freeze_frame": {"Battery voltage": f"{v} V", "Engine temperature": f"{t} °C",
                             "Engine speed": f"{rpm} rpm", "Vehicle speed": f"{spd} km/h",
                             "Startups counter": "100", "Odometer": "1000.5 km"}}


s = pd.freeze_summary(VIN, "U1713", frames=[ff("2026-01-01 10:00:00", 11.5, 20, 0, 0), ff("2026-02-01 10:00:00", 11.9, 30, 0, 0),
                                            ff("2026-03-01 10:00:00", 11.0, 35, 0, 0), ff("2026-04-01 10:00:00", 11.7, 25, 0, 0)])
check("unanimous patterns found", {"all 4 occurrences below 12.0 V", "all 4 with engine temperature < 40 °C",
                                   "all 4 at 0 rpm"} <= set(s["patterns"]), str(s["patterns"]))
check("voltage range with unit", any("11 to 11.9 V" in x["text"] for x in s["summaries"] if x["key"] == "voltage"))
s2 = pd.freeze_summary(VIN, "U1713", frames=[ff("a", 11.5, 20, 0, 0), ff("b", 13.9, 30, 800, 0)])
check("no voltage/rpm pattern when not unanimous", not any("V" in p or "rpm" in p for p in s2["patterns"]), str(s2["patterns"]))
check("speed pattern still unanimous", any("stationary" in p for p in s2["patterns"]))
s1 = pd.freeze_summary(VIN, "U1713", frames=[ff("a", 11.5, 20, 0, 0)])
check("one frame -> says so, no patterns", s1["patterns"] == [] and "Only 1" in s1["note"] and not s1["enough"])
s0 = pd.freeze_summary(VIN, "U1713", frames=[])
check("zero frames message", s0["count"] == 0 and "No freeze frame" in s0["note"])
miss = ff("c", 11.5, 20, 0, 0)
del miss["freeze_frame"]["Battery voltage"]
s3 = pd.freeze_summary(VIN, "U1713", frames=[ff("a", 11.5, 20, 0, 0), miss])
check("missing value breaks pattern, shown not recorded",
      not any("V" in p for p in s3["patterns"]) and s3["rows"][1]["voltage"] is None)

# --- routes -------------------------------------------------------------------
try:
    from fastapi.testclient import TestClient
    from cuore.app import create_app
    app = create_app()
    c = TestClient(app, follow_redirects=False)
    r = c.get(f"/v/{VIN}/network?code=U1713")
    check("network page renders", r.status_code == 200 and "CAN network" in r.text and "not a Stelvio spec" in r.text, str(r.status_code))
    r = c.post(f"/v/{VIN}/wiggle", data={"code": "U1713", "action": "mark", "hop": "bogus-hop", "redirect_to": "//evil.com"})
    check("wiggle POST redirects safely with error", r.status_code == 303 and r.headers["location"].startswith("/v/") and "error=" in r.headers["location"], r.headers.get("location", ""))
    r = c.post(f"/v/{VIN}/pins", data={"element": "bogus", "pin": "1", "source": "x", "redirect_to": "https://evil.com"})
    check("pins POST unknown element rejected, safe redirect", r.status_code == 303 and "error=" in r.headers["location"]
          and "evil" not in r.headers["location"], r.headers.get("location", ""))
    r = c.get(f"/v/{VIN}/code/U1713")
    check("code page still renders", r.status_code == 200, str(r.status_code))
except Exception as exc:  # noqa: BLE001
    check("route checks ran", False, repr(exc))

print(f"\n{n_checks} checks, {len(failures)} failed")
sys.exit(1 if failures else 0)
