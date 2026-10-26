"""Checks: raw-frame persistence, DBC confidence labels, validator verdicts.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_dbc_confidence.py

ALL frames below are SYNTHETIC (built here from the DBC itself). Nothing in this
file is a capture from the car.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-dbcconf-")
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401
from cuore.app import create_app  # noqa: E402
from cuore.live import chassis_decode, dbc, dbc_validate, rawframes  # noqa: E402
from cuore.live import ops as live_ops  # noqa: E402
from cuore.services import liveboard_bridge  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


db = dbc.default()
LABEL = dbc.UNVERIFIED_LABEL


def encode(fid: int, **raw: int) -> str:
    """SYNTHETIC: build a frame hex string with the given RAW signal values."""
    msg = db.get(fid, False)
    data = bytearray(msg.dlc)
    for name, value in raw.items():
        sig = msg.signals[name]
        for i, p in enumerate(sig.bit_positions()):
            bit = (value >> (sig.length - 1 - i)) & 1
            data[p // 8] = (data[p // 8] & ~(1 << (p % 8))) | (bit << (p % 8))
    return data.hex().upper()


# SYNTHETIC parked-idle capture: rpm 780, speed 0, wheel centred (raw 7168 -> 0 deg)
SYN = [{"t": i * 0.02, "id": "0FC", "data": encode(0xFC, ENGINE_RPM=780)} for i in range(10)]
SYN += [{"t": i * 0.02, "id": "11C", "data": encode(0x11C, VEHICLE_SPEED=0)} for i in range(10)]
SYN += [{"t": i * 0.02, "id": "0DE", "data": encode(0xDE, STEERING_ANGLE=7168)} for i in range(10)]
SYN += [{"t": 0.0, "id": "0F1", "data": encode(0xF1, MAYBE_VOLTAGE=700)}]

# 1. raw frames persisted with header
p = rawframes.write_capture(SYN, bus="can_c", bitrate=500000, cable="none",
                            vin="ZASFAKPN5J7B88115", state_note="parked idle, wheel centred")
check("file under bus_captures/<vin>/", p.parent.name == "ZASFAKPN5J7B88115"
      and p.parent.parent.name == "bus_captures" and p.suffix == ".jsonl", str(p))
rd = rawframes.read_capture(p)
h = rd["header"]
check("header has bus/bitrate/cable/state_note",
      (h["bus"], h["bitrate"], h["cable"], h["state_note"]) ==
      ("can_c", 500000, "none", "parked idle, wheel centred"), str(h))
f0 = rd["frames"][0]
check("frame has t,bus,bitrate,id,dlc,data",
      set(f0) == {"t", "bus", "bitrate", "id", "dlc", "data"} and f0["dlc"] == 8
      and f0["bitrate"] == 500000, str(f0))
check("all frames read back", len(rd["frames"]) == len(SYN) and rd["torn_lines"] == 0)

# 2. crash-safe: a torn last line is tolerated
with open(p, "a", encoding="utf-8") as fh:
    fh.write('{"t": 1.0, "bus": "can_c", "id": "0F')
rd2 = rawframes.read_capture(p)
check("torn final line skipped and counted", len(rd2["frames"]) == len(SYN) and rd2["torn_lines"] == 1)
check("no-vin capture goes to unknown_vin",
      rawframes.write_capture([], bus="can_c", bitrate=500000, cable="none").parent.name == "unknown_vin")

# 3. capture.listen persists (fake session), only with traffic, with state_note
from cuore.live import capture as capture_mod  # noqa: E402


class _Stream:
    def __init__(self, lines): self.buf = lines; self.sent = []
    def reset_input_buffer(self): pass
    def write(self, b): self.sent.append(b)
    def flush(self): pass
    def in_waiting(self): return len(self.buf)
    def read(self, n):
        b, self.buf = self.buf, b""
        return b


class _Bus: key, bitrate = "can_c", 500000
class _Link: is_stn, cable, vin = False, "none", "VIN123"
class _Sess:
    bus, link, passive, route = _Bus(), _Link(), True, None
    def __init__(self, n):
        self.stream = _Stream(b"".join(b"0FC 8 %s\r" % b"00 00 00 00 00 00 00 00" for _ in range(n)))
    def cmd(self, *a, **k): return "OK"


import cuore.live.capture as cm  # noqa: E402
real_parse = cm.parse_frames
cm.parse_frames = lambda text, headers_on=True: [("0FC", ["00"] * 8)]
try:
    out = capture_mod.listen(_Sess(8), seconds=0.3, persist_raw=True, state_note="note-A")
    check("listen with traffic persisted a file", bool(out.get("raw_capture_file")), str(out.get("raw_capture_file")))
    if out.get("raw_capture_file"):
        rr = rawframes.read_capture(out["raw_capture_file"])
        check("listen file header carries state_note and confirmed bitrate",
              rr["header"]["state_note"] == "note-A" and rr["header"]["bitrate"] == 500000
              and rr["header"]["bus"] == "can_c")
        check("id counts still returned", out["ids"].get("0FC") == 8 and len(rr["frames"]) == 8)
    out2 = capture_mod.listen(_Sess(2), seconds=0.3, persist_raw=True)
    check("fewer than 5 frames (rate unconfirmed): not persisted", out2.get("raw_capture_file") is None)
    out3 = capture_mod.listen(_Sess(8), seconds=0.3)
    check("persist_raw off by default", out3.get("raw_capture_file") is None)
finally:
    cm.parse_frames = real_parse

# 4. confidence label on decoded values
r = dbc.decode(0xFC, bytes.fromhex(encode(0xFC, ENGINE_RPM=780)))
check("dbc.decode result carries the unverified label", r["confidence"] == LABEL)
cap = chassis_decode.decode_capture(SYN)
check("result-level confidence + not diagnostic",
      cap["confidence"] == LABEL and cap["diagnostic_use"].startswith("none"))
check("every message and signal labelled",
      all(m["confidence"] == LABEL and all(s["confidence"] == LABEL for s in m["signals"].values())
          for m in cap["messages"].values()))
mv = cap["messages"]["0F1"]["signals"]["MAYBE_VOLTAGE"]
check("MAYBE_VOLTAGE labelled NOT battery voltage, no volt unit",
      "NOT battery voltage" in mv["label"] and mv["unit"] == "" and "V" not in mv["unit"], str(mv))
check("INTEREST comment no longer claims CAN-CH 2026-10-14 sighting",
      "seen on CAN-CH" not in open(chassis_decode.__file__, encoding="utf-8").read())

# 5. API output carries the label (available and unavailable)
calls: list = []
real_listen, real_cable = liveboard_bridge._passive_listen, live_ops.cable_state
liveboard_bridge._passive_listen = lambda seconds, state_note="": (
    calls.append(state_note) or {"frames": SYN, "seconds": 2.0, "count": len(SYN), "error": None,
                                 "raw_capture_file": "x.jsonl"})
client = TestClient(create_app())
try:
    live_ops.cable_state = lambda: {"cable": "grey_a6"}
    body = client.get("/api/live/chassis/passive", params={"state_note": "parked idle"}).json()
    check("API: confidence at top level and on a signal",
          body.get("confidence") == LABEL
          and body["messages"]["0FC"]["signals"]["ENGINE_RPM"]["confidence"] == LABEL, str(body)[:200])
    check("API: state_note passed through, raw file reported",
          calls == ["parked idle"] and body.get("raw_capture_file") == "x.jsonl")
    check("API: MAYBE_VOLTAGE not volts",
          "NOT battery voltage" in body["messages"]["0F1"]["signals"]["MAYBE_VOLTAGE"]["label"])
    live_ops.cable_state = lambda: {"cable": "none"}
    check("API unavailable answer also labelled",
          client.get("/api/live/chassis/passive").json().get("confidence") == LABEL)
finally:
    liveboard_bridge._passive_listen, live_ops.cable_state = real_listen, real_cable

# 6. validator on the SYNTHETIC capture
snap = {"rpm": 780, "speed_kmh": 0}
v = dbc_validate.validate(p, snap)
by = {(s["id"], s["signal"]): s for s in v["signals"]}
check("rpm 780 vs DID 780: PLAUSIBLE", by[("0FC", "ENGINE_RPM")]["verdict"] == "PLAUSIBLE", str(by[("0FC", "ENGINE_RPM")]))
check("0x11C speed 0 vs DID 0: PLAUSIBLE", by[("11C", "VEHICLE_SPEED")]["verdict"] == "PLAUSIBLE")
check("0x101 absent: NO DATA", by[("101", "VEHICLE_SPEED")]["verdict"] == "NO DATA")
check("steering centred per header note: PLAUSIBLE", by[("0DE", "STEERING_ANGLE")]["verdict"] == "PLAUSIBLE")
check("MAYBE_VOLTAGE: SUSPECT, never battery", by[("0F1", "MAYBE_VOLTAGE")]["verdict"] == "SUSPECT"
      and "NOT battery voltage" in by[("0F1", "MAYBE_VOLTAGE")]["label"])
check("validator output labelled", v["confidence"] == LABEL
      and all(s["confidence"] == LABEL for s in v["signals"]))
check("tolerates the torn line", v["torn_lines"] == 1)
bad = dbc_validate.validate(p, {"rpm": 1500, "speed_kmh": 40})
by2 = {(s["id"], s["signal"]): s for s in bad["signals"]}
check("rpm 780 vs DID 1500: SUSPECT", by2[("0FC", "ENGINE_RPM")]["verdict"] == "SUSPECT")
check("speed 0 vs DID 40 km/h: SUSPECT", by2[("11C", "VEHICLE_SPEED")]["verdict"] == "SUSPECT")
nosnap = dbc_validate.validate(p, {})
by3 = {(s["id"], s["signal"]): s for s in nosnap["signals"]}
check("no DID reference: NO DATA, not PLAUSIBLE", by3[("0FC", "ENGINE_RPM")]["verdict"] == "NO DATA")
empty = dbc_validate.validate({"header": {}, "frames": []}, snap)
check("empty capture: everything NO DATA", empty["counts"]["NO DATA"] == len(empty["signals"]))

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
