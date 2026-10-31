"""Checks for value groups (cuore/data/value_groups.json, services/value_groups.py, the Live board group panel).
Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_value_groups.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-value-groups-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import channels as channels_mod, interlock  # noqa: E402
from cuore.services import value_groups as vg  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


TOKEN = "vg-token-123"
Path(_TMP, "web_token.txt").write_text(TOKEN, encoding="utf-8")
c = TestClient(create_app(), follow_redirects=False, raise_server_exceptions=False)
c.get(f"/login?token={TOKEN}")

raw = (ROOT / "cuore" / "data" / "value_groups.json").read_text(encoding="utf-8")
groups = vg.groups()
reg = channels_mod.registry()
from mes import systems as systems_mod  # noqa: E402

# 1. the eight starting groups exist and every channel id is a real channel
want = {"battery_charging", "engine_temps", "boost_intake", "fuel", "evap", "gearbox_transfer", "brakes_wheels",
        "body_lighting"}
check("starting groups all present", want <= {g["id"] for g in groups}, str(want - {g["id"] for g in groups}))
for g in groups:
    ids = vg.group_channel_ids(g)
    check(f"{g['id']}: has channels", bool(ids))
    for cid in ids:
        check(f"{g['id']}: channel {cid} exists", cid in reg)
        check(f"{g['id']}: channel {cid} is not untrusted", cid not in reg or not reg[cid].untrusted)
    for sk in g.get("systems") or []:
        check(f"{g['id']}: system {sk} exists", sk in systems_mod.SYSTEMS)
    for n in g.get("not_read_yet") or []:
        check(f"{g['id']}: not-read row names value, module, source", all(n.get(k) for k in ("name", "module", "source")))
        check(f"{g['id']}: {n['name']!r} is not a channel CUORE already reads",
              not any(ch.name.lower() == n["name"].lower() for ch in reg.values()))
    for r in g.get("related") or []:
        check(f"{g['id']}: related {r['group']} exists", vg.get(r["group"]) is not None)

# 2. the data holds no numbers a source should own (no limits, scales, bands)
check("no band or scale keys stored", not re.search(r'"(normal|warn|alarm|min|max|scale|formula|limit|band)"', raw))

# 3. marque neutral: no marque or model in the data
check("data file is marque neutral", not re.search(r"stelvio|giulia|alfa|maserati|ferrari|fiat|jeep|dodge", raw, re.I))

# 4. relationships: battery shows engine state beside voltage; IBS and the 19bd field are in the group
bat = vg.get("battery_charging")
secs = {s["title"]: s for s in bat["sections"]}
check("battery: engine state section exists", "Engine state" in secs and "engine_rpm" in secs["Engine state"]["channels"])
check("battery: voltage from four sources", len(secs["Voltage, four sources"]["channels"]) == 4)
check("battery: ecm_19bd and bcm_1005 present", {"ecm_19bd", "bcm_1005"} <= set(vg.group_channel_ids(bat)))
check("battery: no alternator channel invented",
      not any("alternator" in reg[i].name.lower() for i in vg.group_channel_ids(bat)))

# 5. the Live board renders each group, with source module, status and band per row
for g in groups:
    r = c.get(f"/v/{VIN}/liveboard", params={"group": g["id"]})
    check(f"{g['id']}: page 200", r.status_code == 200, str(r.status_code))
    t = r.text
    check(f"{g['id']}: group panel", f'data-group="{g["id"]}"' in t)
    check(f"{g['id']}: picker has every group", all(f'>{x["label"]}</a>' in t for x in groups))
    check(f"{g['id']}: session scoped to the group", "data-group-channels=" in t)
    check(f"{g['id']}: full list not duplicated", 'id="lb-groups"' not in t)
    rows = re.findall(r'id="lb-chan-([A-Za-z0-9_]+)"', t)
    check(f"{g['id']}: no duplicate row ids", len(rows) == len(set(rows)))
    check(f"{g['id']}: rows render", len(rows) >= 1, str(len(rows)))
    for st in re.findall(r'<div class="lb-chan lb-vrow[^>]*data-status="([^"]*)"', t):
        check(f"{g['id']}: status is a known word", st in ("confirmed", "unconfirmed", "no reading"), st)
    check(f"{g['id']}: every row shows source and status", t.count('class="lb-vstat ') == len(rows))
    check(f"{g['id']}: unknowns labelled", ("Not read yet" in t) == bool(g.get("not_read_yet")))
    check(f"{g['id']}: every row says band or no sourced band", len(re.findall(r'class="lb-chan-band"', t)) == len(rows))

# 6. the plain Live board still shows the full list and the picker
r = c.get(f"/v/{VIN}/liveboard")
check("plain board: 200 with picker and full list",
      r.status_code == 200 and 'id="lb-groups"' in r.text and "lb-vpick" in r.text)
r = c.get(f"/v/{VIN}/liveboard", params={"group": "nope"})
check("unknown group: page renders and says so", r.status_code == 200 and "not known" in r.text)

# 7. a sourced band comes through the existing band code
r = c.get(f"/v/{VIN}/liveboard", params={"group": "engine_temps"})
check("engine temps: a row carries a band note", " normal" in r.text)

# 8. unknowns: a composite DID with no decode reads 'no reading', not a number
r = c.get(f"/v/{VIN}/liveboard", params={"group": "battery_charging"})
m = re.search(r'id="lb-chan-bcm_1005"[^>]*data-status="([^"]*)"', r.text)
check("undecoded IBS composite is no reading", bool(m) and m.group(1) == "no reading", str(m and m.group(1)))

# 9. other platform: DID channels are not shown on a Maserati VIN, standard readings still are
MVIN = "ZN661XUA9JX000001"
from cuore.services import liveboard_bridge  # noqa: E402
from cuore.web import liveboard_view as lbv  # noqa: E402
mv = lbv.group_view(liveboard_bridge.board(MVIN), MVIN, "battery_charging")
mids = {r["id"] for s in mv["sections"] for r in s["rows"]}
check("other marque: no catalogue DID rows", not ({"ecm_1955", "bcm_1004", "ecm_19bd"} & mids), str(mids))
check("other marque: standard readings remain", {"battery_voltage", "engine_rpm"} <= mids)
check("other marque: skipped rows are named", bool(mv["other_platform"]))

# 10. links from the other screens
check("system -> group", [g["id"] for g in vg.groups_for_system("evap")] == ["evap"])
mod = {x["id"]: x for x in vg.groups_for_module("BCM")}
check("module -> whole group", "battery_charging" in mod and "ECM" in mod["battery_charging"]["others"], str(list(mod)))
r = c.get(f"/v/{VIN}/modules/BCM")
check("module workspace links the group", r.status_code == 200 and "group=battery_charging" in r.text, str(r.status_code))
r = c.get(f"/v/{VIN}/systems", params={"system": "evap"})
check("systems map card links the group", r.status_code == 200 and "Values together: EVAP" in r.text)
r = c.get("/find", params={"q": "battery", "vin": VIN})
mm = re.search(r'class="find-best" href="([^"]+)">Go to: ([^<]*)', r.text)
check("find: battery goes to the group", bool(mm) and "group=battery_charging" in mm.group(1), str(mm and mm.group(1)))
from cuore.services import find as find_mod  # noqa: E402
check("find without a car offers no group link", not any(
    "group=" in x["href"] for g in find_mod.search("battery")["groups"] for x in g["rows"]))

check("picker lists all groups", len(vg.picker(VIN)) == len(groups))

print(f"{checks} checks, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
