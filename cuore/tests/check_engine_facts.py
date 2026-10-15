"""Checks for the 2026-10-15 engine-side facts: run-time PID decoders, untrusted
PID 6B, per-VIN capability records, deposit-risk trend group."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-facts-")
os.environ.pop("MES_LIVE_OBSERVATIONS", None)
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "mes-log-mcp"))

from cuore.live import capabilities, channels  # noqa: E402
from cuore.live.obd import decode_pid, resolve_pid  # noqa: E402

FAILS = 0


def check(label, cond, detail=""):
    global FAILS
    print(("ok   " if cond else "FAIL ") + label + (f"  {detail}" if not cond else ""))
    if not cond:
        FAILS += 1


def dec(pid, data):
    hx, spec = resolve_pid(pid)
    return decode_pid(hx, spec, data)


check("4D minutes with MIL", dec("4D", ["01", "2C"]).get("value") == 300)
check("4E minutes since clear", dec("4E", ["00", "3C"]).get("value") == 60)
r = dec("7F", ["00", "00", "00", "0E", "10", "00", "00", "01", "2C", "00", "00", "00", "05"]).get("value")
check("7F total/idle/pto", r == {"info": 0, "total_s": 3600, "idle_s": 300, "pto_s": 5}, str(r))
c = channels.by_id("egr_temperature")
check("6B untrusted", c.untrusted and c.to_dict().get("untrusted") is True and c.confidence == "untrusted")
VIN = "ZASFAKPN5J7B88115"
check("seed: engine hours unavailable", capabilities.capabilities(VIN)["engine_hours_available"]["value"] is False)
capabilities.record_capability("TESTVIN0000000001", "x_key", ["a"], evidence="e")
back = capabilities.capabilities("TESTVIN0000000001")
check("capability round-trip", back.get("x_key", {}).get("value") == ["a"], str(back))
rows = {r["key"]: r for r in capabilities.capability_rows(VIN)}
check("rows list IBS DIDs", "BCM 1005" in rows["ibs_dids_to_verify"]["value"])
g = channels.channel_groups()["deposit_risk_trend"]
mids = [m for i in g["items"] for m in i.get("obdmids", [])]
check("trend group lists misfire OBDMIDs A2-AD", mids[0] == "A2" and mids[-1] == "AD" and len(mids) == 12)
check("trend items tagged", {i["evidence"] for i in g["items"]} == {"evidence", "weak"})
print("FAILED" if FAILS else "ALL OK")
sys.exit(1 if FAILS else 0)
