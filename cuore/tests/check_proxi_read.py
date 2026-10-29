"""Checks for the read-only PROXI read (cuore.live.proxi_read) and the Configuration page.
Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_proxi_read.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-proxi-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import configuration_routes  # noqa: E402
from cuore.live import interlock, ops, proxi_read as pr, uds as uds_mod  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0
interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- fake lowest layer: records every request as the UDS bytes it would send ----------------
REQUESTS: list[str] = []
BLOCK = [f"{(i * 7) % 256:02X}" for i in range(120)]
BIG = [f"{(i * 7) % 256:02X}" for i in range(160)]
BIG[63], BIG[156] = "8B", "10"
FIX = {"2010": BLOCK, "2011": ["01", "02", "03"], "F190": [f"{ord(c):02X}" for c in VIN]}


def fake_discover(code, vin="", ranges=None, max_dids=2000, confirm=False, **kw):
    pos, tried = [], 0
    for r in ranges:
        a, _, b = r.partition("-")
        for did in range(int(a, 16), int(b or a, 16) + 1):
            if tried >= max_dids:
                break
            tried += 1
            REQUESTS.append(f"22{did:04X}")
            if f"{did:04X}" in FIX:
                pos.append({"did": f"{did:04X}", "bytes": FIX[f"{did:04X}"], "ascii": None})
    return {"tried": tried, "positive": pos, "stopped_early": None}


ops.module_discover_dids = fake_discover
pr.RANGES[:] = [(0x2008, 0x2012, "t"), (0xF18F, 0xF191, "t")]   # small sweep for the test
client = TestClient(create_app(), follow_redirects=False)

# --- refusal when the BCM address is not confirmed ------------------------------------------
_orig = uds_mod.resolve_module


def _none(code, vin=None):
    from cuore.live.errors import BadCommand
    raise BadCommand("module BCM has no confirmed address on this car")


uds_mod.resolve_module = _none
try:
    pr.discover(VIN)
    refused = None
except pr.ProxiRefused as e:
    refused = str(e)
uds_mod.resolve_module = _orig
check("refuses clearly when BCM unconfirmed, sends nothing", refused and "no confirmed" in refused and not REQUESTS, str(refused))

# --- page state 1: nothing yet --------------------------------------------------------------
h = client.get(f"/v/{VIN}/configuration").text
check("page none: run discovery + needs + MES confirm", "Run discovery" in h and "MES closed" in h
      and "screenshot" in h and "Read only. CUORE never writes configuration" in h)
check("nothing accepted at start", pr.accepted(VIN) is None)

# --- discover ranks and flags ---------------------------------------------------------------
res = pr.discover(VIN)
check("only 0x22 requests sent", REQUESTS and all(q.startswith("22") for q in REQUESTS), str(REQUESTS[:3]))
c0 = res["candidates"][0]
check("120-byte response ranked first and flagged", c0["did"] == "2010" and c0["length"] == 120
      and c0["likely_configuration"] is True)
check("short ones not flagged", all(not c["likely_configuration"] for c in res["candidates"][1:]))
check("saved under proxi/<vin>/", any((Path(_TMP) / "proxi" / VIN).glob("2*.json")))
check("nothing accepted by discovery", pr.accepted(VIN) is None and pr.view(VIN)["state"] == "candidates")

# --- page state 2 ---------------------------------------------------------------------------
h = client.get(f"/v/{VIN}/configuration").text
check("page candidates: table, accept form with required reason", "Candidates, longest first" in h
      and "2010" in h and "likely configuration" in h and re.search(r'name="reason" required', h) is not None)
client.post(f"/v/{VIN}/configuration/accept", data={"did": "2010", "reason": ""})
check("accept without reason refused", pr.accepted(VIN) is None)
try:
    pr.accept_candidate(VIN, "9999", "x")
    bad = False
except pr.ProxiRefused:
    bad = True
check("accept of a non-candidate refused", bad)
a = pr.accept_candidate(VIN, "2010", "matches MES CAN Setup screenshot of 2026-10-30")
check("accept writes accepted.json with reason", pr.accepted(VIN)["reason"].startswith("matches MES") and a["did"] == "2010")

# --- read + diff ----------------------------------------------------------------------------
n_before = len(REQUESTS)
r1 = pr.read(VIN)
check("read is a single 0x22 of the accepted DID", REQUESTS[n_before:] == ["222010"], str(REQUESTS[n_before:]))
check("first read: no diff", r1["changed"] is None and r1["length"] == 120)
FIX["2010"] = BLOCK[:]
FIX["2010"][5] = "FF"
r2 = pr.read(VIN)
check("second read: diff names byte 5", [d["index"] for d in r2["changed"]] == [5]
      and r2["changed"][0]["before"] == BLOCK[5] and r2["changed"][0]["after"] == "FF", str(r2["changed"]))
h = client.get(f"/v/{VIN}/configuration").text
check("page accepted: grid, options, diff, read-only line", "Block, byte by byte" in h and "Known options" in h
      and "Change since the previous read" in h and "00000000" in h
      and "Read only. CUORE never writes configuration" in h
      and "<script" not in h.split('class="cfg"')[1].rsplit("</table>", 1)[0])

# --- known options decode from the sourced map ----------------------------------------------
blk = ["00"] * 160
blk[63], blk[156] = "8B", "10"
ko = {o["byte"]: o for o in pr.known_options(blk)}
check("battery byte decodes H8 AGM from proxi_map_949.json", "AGM" in ko[63]["label"] and ko[63]["source_kind"] == "forum", str(ko[63]))
check("paddle byte decodes North America", "North America" in ko[156]["label"])
mp = json.loads((Path(pr.__file__).resolve().parents[1] / "data" / "proxi_map_949.json").read_text(encoding="utf-8"))
check("map: each entry has source_kind, source, reference-only flag",
      all(o["source"] and o["source_kind"] in pr.KIND_RANK and "reference only" in o["flag"] for o in mp["options"]))
check("short block says so", pr.known_options(["00"] * 10)[0]["present"] is False)

# --- MES-display names: agree / disagree / no same-day, precedence ---------------------------
FIX["2010"] = BIG[:]
pr.read(VIN)
today = pr.reads(VIN)[-1]["read_at"][:10]
out = pr.add_names(VIN, [{"byte": 63, "mask": "0x0F", "name": "Battery type (MES)", "value": "0x0B"},
                         {"byte": 63, "mask": "whole byte", "name": "Whole 63", "value": "8B"},
                         {"byte": 156, "mask": "xx01xxxx", "name": "Paddle (MES)", "value": "xx00xxxx"}],
                   "C:/shots/can_setup.png", today)["added"]
check("agrees on matching masked value", out[0]["agreement"] == "agrees", str(out[0]))
check("whole byte agrees", out[1]["agreement"] == "agrees")
check("disagrees when MES pattern differs", out[2]["agreement"] == "disagrees", str(out[2]))
old = pr.add_names(VIN, [{"byte": 63, "mask": "0x0F", "name": "x", "value": "0B"}], "s.png", "2020-01-01")["added"]
check("no same-day read", old[0]["agreement"] == "no same-day read")
check("source_kind mes_display with screenshot and date", out[0]["source_kind"] == "mes_display"
      and "can_setup.png" in out[0]["source"] and today in out[0]["source"])
try:
    pr.add_names(VIN, [{"byte": 500, "mask": "", "name": "n", "value": "1"}], "s.png", today)
    ok = False
except pr.ProxiRefused:
    ok = True
check("refused: byte beyond the accepted read", ok)
try:
    pr.add_names(VIN, [{"byte": 1, "mask": "", "name": "n", "value": "1"}], "", today)
    ok = False
except pr.ProxiRefused:
    ok = True
check("screenshot required", ok)
check("bulk parse", pr.parse_bulk("63;0x0F;Battery;0B\n\n156;0x30;Paddle;00")[1]["name"] == "Paddle")
ko = {(o["byte"], o["mask_hex"]): o for o in pr.known_options(BIG, VIN)}
w = ko[(63, "0x0F")]
check("precedence: MES display beats forum on same byte+bits, forum listed as also",
      w["source_kind"] == "mes_display" and any("forum" in a for a in w["also"]), str(w))
check("source kind shown on page", "MES display" in client.get(f"/v/{VIN}/configuration").text)
n_before = len(REQUESTS)
r = client.post(f"/v/{VIN}/configuration/names",
                data={"screenshot": "p.png", "mes_date": today, "bulk": "10;whole byte;Test;00"})
check("names POST sends nothing to the car", r.status_code == 303 and len(REQUESTS) == n_before)

# --- no write path ---------------------------------------------------------------------------
src = Path(pr.__file__).read_text(encoding="utf-8")
check("module has no send/write primitives", not re.search(r"uds_mod\.request|\.send\(|send_raw|0x2E\)", src))
check("names.json appears only in names()/add_names, never passed to ops",
      src.count('"names.json"') == 2 and not re.search(r"ops\.\w+\([^)]*names", src))
check("every request in the whole run was 0x22", all(q.startswith("22") for q in REQUESTS))
paths = {(m, rt.path) for rt in configuration_routes.router.routes if "/configuration" in getattr(rt, "path", "")
         for m in getattr(rt, "methods", ())}
allowed = {("POST", f"/v/{{vin}}/configuration/{x}") for x in ("discover", "accept", "read", "names")}
check("only discover/accept/read/names POST routes", {p for p in paths if p[0] == "POST"} == allowed, str(paths))

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
