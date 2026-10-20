"""Checks for the DBC parser, CAN-CH passive decode and its API.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_chassis_decode.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-chassis-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401
from cuore.app import create_app  # noqa: E402
from cuore.live import chassis_decode, dbc  # noqa: E402
from cuore.live import ops as live_ops  # noqa: E402
from cuore.services import liveboard_bridge  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def close(a, b, tol=1e-6) -> bool:
    return abs(a - b) <= tol


# 1. the shipped DBC loads and finds the messages of interest
db = dbc.load()
for name, fid in (("EPS_1", 0xDE), ("ABS_1", 0xEE), ("ENGINE_1", 0xFC)):
    m = db.by_name.get(name)
    check(f"DBC has {name} at 0x{fid:X}", m is not None and m.frame_id == fid)
check("EPS_1 STEERING_ANGLE parsed (5|14 Motorola, 0.1, -716.8)",
      (s := db.by_name["EPS_1"].signals.get("STEERING_ANGLE")) is not None
      and (s.start, s.length, s.little_endian, s.signed) == (5, 14, False, False)
      and close(s.factor, 0.1) and close(s.offset, -716.8) and s.unit == "deg")
check("29-bit message keyed as extended", (506855454, True) in db.messages)
check("VAL_ table attached", db.by_name["EPS_2"].signals["LKA_STATUS"].choices.get(1) == "lka_active")

# 2. little-endian and Motorola signals on hand-made frames
mini = dbc.parse('''
BO_ 100 LE_MSG: 4 X
 SG_ A : 0|8@1+ (1,0) [0|255] "" X
 SG_ B : 8|16@1- (0.5,0) [-100|100] "u" X
BO_ 200 BE_MSG: 4 X
 SG_ S : 7|8@0- (1,0) [-128|127] "" X
 SG_ W : 11|12@0+ (1,0) [0|4095] "" X
''')
r = mini.decode(100, bytes([0x12, 0xFC, 0xFF, 0x00]))
check("little-endian unsigned A = 0x12", r["signals"]["A"] == (18, ""))
check("little-endian signed 16-bit B = -4 * 0.5", r["signals"]["B"] == (-2, "u"), str(r["signals"]["B"]))
r = mini.decode(200, bytes([0xFE, 0x00, 0x00, 0x00]))
check("Motorola signed 8-bit S = -2", r["signals"]["S"][0] == -2, str(r["signals"]))
# W: start bit 11 = byte1 bit3 (MSB), runs byte1 bits3..0 then byte2 bits7..0 -> 0xABC
r = mini.decode(200, bytes([0x00, 0x0A, 0xBC, 0x00]))
check("Motorola 12-bit crossing a byte W = 0xABC", r["signals"]["W"][0] == 0xABC, str(r["signals"]))
# real DBC, hand computed: STEERING_ANGLE raw 7168+10 = 0x1C0A -> bytes 1C 0A; angle = 1.0 deg
r = dbc.decode(0xDE, bytes([0x1C, 0x0A, 0, 0, 0, 0]))
check("EPS_1 STEERING_ANGLE raw 7178 -> 1.0 deg",
      r["message"] == "EPS_1" and close(r["signals"]["STEERING_ANGLE"][0], 1.0)
      and r["signals"]["STEERING_ANGLE"][1] == "deg", str(r))
# VEHICLE_SPEED 47|12: byte5 + high nibble of byte6; raw 0x123 -> 291 * 0.017
r = dbc.decode(0x11C, bytes([0, 0, 0, 0, 0, 0x12, 0x30, 0]))
check("0x11C VEHICLE_SPEED raw 291 -> 4.947 m/s", close(r["signals"]["VEHICLE_SPEED"][0], 4.947, 1e-6),
      str(r["signals"]["VEHICLE_SPEED"]))
check("short frame skips signals that do not fit", dbc.decode(0xDE, b"\x1c")["signals"] == {}
      or "CHECKSUM" not in dbc.decode(0xDE, b"\x1c")["signals"])
check("unknown id decodes to None", dbc.decode(0x7FF, b"\x00" * 8) is None)

# 3. decode_capture handles unknown ids and bad frames
frames = [
    {"t": 0.00, "id": "0DE", "data": "1C0A00000000"},
    {"t": 0.01, "id": "0DE", "data": "1C0B00000000"},
    {"t": 0.51, "id": "0DE", "data": "1C0C00000000"},
    {"t": 0.02, "id": "7FF", "data": "0011223344556677"},
    {"t": 0.03, "id": "ZZZ", "data": "00"},
    {"t": 0.04, "id": "0EE", "data": "XYZ"},
]
cap = chassis_decode.decode_capture(frames)
eps = cap["messages"].get("0DE", {})
check("latest EPS_1 frame wins (raw 7180 -> 1.2 deg)",
      close(eps["signals"]["STEERING_ANGLE"]["value"], 1.2, 1e-6), str(eps.get("signals")))
check("EPS_1 count and rate", eps["count"] == 3 and eps["rate_hz"] == 3.9, str((eps["count"], eps["rate_hz"])))
check("unknown id tallied, not decoded", cap["unknown_ids"] == {"7FF": 1} and "7FF" not in cap["messages"])
check("bad frames counted", cap["bad_frames"] == 2 and cap["frames"] == 6, str(cap))
check("empty capture is fine", chassis_decode.decode_capture([])["messages"] == {})

# 4. API returns 200 with a fake capture (and refuses to listen without grey A6)
calls: list[float] = []


def fake_listen(seconds: float) -> dict:
    calls.append(seconds)
    return {"frames": frames, "seconds": 2.0, "count": len(frames), "error": None}


real_listen, real_cable = liveboard_bridge._passive_listen, live_ops.cable_state
liveboard_bridge._passive_listen = fake_listen
client = TestClient(create_app())
try:
    live_ops.cable_state = lambda: {"cable": "grey_a6"}
    resp = client.get("/api/live/chassis/passive")
    body = resp.json() if resp.status_code == 200 else {}
    check("GET /api/live/chassis/passive 200 with grey_a6", resp.status_code == 200, str(resp.status_code))
    check("API carries decoded EPS_1 signals",
          close(body.get("messages", {}).get("0DE", {}).get("signals", {})
                .get("STEERING_ANGLE", {}).get("value", 0), 1.2, 1e-6), str(body)[:200])
    check("API marks passive + listened", body.get("available") is True and body.get("passive") is True
          and calls == [2.0])
    live_ops.cable_state = lambda: {"cable": "blue_a5"}
    calls.clear()
    resp = client.get("/api/live/chassis/passive")
    check("without grey_a6: 200, unavailable, no listen",
          resp.status_code == 200 and resp.json().get("available") is False and not calls)
finally:
    liveboard_bridge._passive_listen, live_ops.cable_state = real_listen, real_cable

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
