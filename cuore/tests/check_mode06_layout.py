"""Checks for cuore.live.mode06_layout (assumed Mode $06 record layout vs a raw reply).

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_mode06_layout.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-m06layout-")
os.environ["CUORE_STATE_DIR"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import mode06_layout as ml  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def frame(payload_hex: str, hdr: str = "7E8") -> str:
    """ISO-TP, headers on, 11-bit."""
    n = len(payload_hex) // 2
    if n <= 7:
        return f"{hdr}{n:02X}{payload_hex}"
    out = [f"{hdr}1{n:03X}{payload_hex[:12]}"]
    rest, seq = payload_hex[12:], 1
    while rest:
        out.append(f"{hdr}2{seq % 16:X}{rest[:14]}")
        rest, seq = rest[14:], seq + 1
    return "\r".join(out)


# SYNTHETIC bytes in the assumed layout (not from the car). UASID 01 = raw count.
MID_3C = "46" + "3C0101" + "00640000012C" + "3C0201" + "00010000000A" + "3C0301" + "0005 0000 0020".replace(" ", "")
MID_3D = "46" + "3D0101" + "00220000003C" + "3D0201" + "000A00000014"
SUP_00 = "46" + "00" + "00000001"
SUP_20 = "46" + "20" + "00000018"          # bits for MIDs 3C and 3D

raw = {"supported_00": frame(SUP_00), "supported_20": frame(SUP_20),
       "3C": frame(MID_3C), "3D": frame(MID_3D)}

v = ml.mode06_layout_check(raw)
check("assumed layout: ok", v["ok"], str(v["anomalies"]))
check("assumed layout: 5 records", len(v["records"]) == 5, str(len(v["records"])))
check("assumed layout: no anomalies", v["anomalies"] == [])
check("bitmap consistent", isinstance(v["bitmap_check"], dict) and not v["bitmap_check"]["records_not_in_bitmap"],
      str(v["bitmap_check"]))
check("three alternatives tried", len(v["alternative_layouts_tried"]) == 3)
check("assumed layout described", v["assumed_layout"]["stride"] == 9)

# plain list of frames (no keys) still works, bitmap check reported as not run for lack of frames
v2 = ml.mode06_layout_check([frame(MID_3C)])
check("list input: ok, bitmap not run", v2["ok"] and isinstance(v2["bitmap_check"], str), str(v2["anomalies"]))

# same bytes shifted by one: an extra leading byte after 46 (length no longer whole)
raw_ins = {"3C": frame("46" + "5A" + MID_3C[2:]), "3D": frame("46" + "5A" + MID_3D[2:])}
vi = ml.mode06_layout_check(raw_ins)
check("shifted (inserted byte): not ok", not vi["ok"])
check("shifted (inserted byte): length anomaly flagged",
      any("whole number" in a for a in vi["anomalies"]), str(vi["anomalies"]))

raw_ins0 = {"3C": frame("46" + "00" + MID_3C[2:])}   # extra byte reads like a bad bitmap reply
check("shifted (00 inserted): not ok", not ml.mode06_layout_check(raw_ins0)["ok"])

# same length, bytes rotated left by one: ids and ranges go wrong
def rot(h: str) -> str:
    body = h[2:]
    return "46" + body[2:] + body[:2]


raw_rot = {"3C": frame(rot(MID_3C)), "3D": frame(rot(MID_3D)), "supported_00": frame(SUP_00),
           "supported_20": frame(SUP_20)}
vr = ml.mode06_layout_check(raw_rot)
check("shifted (rotated): not ok", not vr["ok"])
check("shifted (rotated): anomalies flagged", len(vr["anomalies"]) >= 1, str(vr["anomalies"]))

# bitmap says only 3D; a 3C record is flagged
raw_bm = dict(raw, supported_20=frame("46" + "20" + "00000008"))
vb = ml.mode06_layout_check(raw_bm)
check("record MID outside bitmap flagged", not vb["ok"] and any("supported-MID bitmap" in a for a in vb["anomalies"]),
      str(vb["anomalies"]))

# nothing to check
check("empty input: not ok", not ml.mode06_layout_check({"3C": "NO DATA"})["ok"])

# save + hook helper
res = ml.check_and_save(raw)
saved = Path(res["saved_to"])
check("check_and_save writes under mode06_layout_check", saved.exists() and saved.parent.name == "mode06_layout_check")
body = json.loads(saved.read_text(encoding="utf-8"))
check("saved file carries raw and verdict", body["raw"]["3C"] == raw["3C"] and body["verdict"]["ok"] is True)

if failures:
    print(f"FAIL: {len(failures)} of {checks} checks failed")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"PASS: {checks} mode06 layout checks")
