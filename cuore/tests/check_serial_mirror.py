"""Checks for cuore.live.serial_mirror (+ the listener's refusals).

ALL FIXTURES BELOW ARE SYNTHETIC: invented DIDs/values shaped like an ELM/STN
mirror log. No serial port is opened, nothing is written under ProgramData.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_serial_mirror.py
"""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import procedure_capture as pc  # noqa: E402
from cuore.live import serial_mirror as sm  # noqa: E402
from cuore.live import serial_mirror_listen as sml  # noqa: E402
from cuore.live.errors import Refused  # noqa: E402
from cuore.live.mes_learn import load_capture  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# Echo ON (ELM default), headers OFF, spaces ON: how a plain MES session looks.
LOG_A = """\
# synthetic mirror log
[0.000] TX: ATZ
[0.010] RX: ATZ
[0.020] RX: ELM327 v1.5
[0.030] RX: >
[0.100] TX: STP 34
[0.110] RX: STP 34
[0.120] RX: OK
[0.130] RX: >
[0.200] TX: ATSH DA10F1
[0.210] RX: ATSH DA10F1
[0.220] RX: OK
[0.230] RX: >
[0.300] TX: 1003
[0.310] RX: 1003
[0.320] RX: SEARCHING...
[0.340] RX: BUS INIT: OK
[0.350] RX: 50 03 00 32 01 F4
[0.360] RX: >
[0.400] TX: 22DE00
[0.410] RX: 22DE00
[0.420] RX: 00E
[0.421] RX: 0: 62 DE 00 01 02 03
[0.422] RX: 1: 04 05 06 07 08 09
[0.423] RX: 2: 0A 0B
[0.430] RX: >
[0.500] TX: 2F DE 01 03 01
[0.510] RX: 2F DE 01 03 01
[0.520] RX: 7F 2F 78
[0.700] RX: 6F DE 01 03 01
[0.710] RX: >
[1.500] TX: 2F DE 01 00
[1.510] RX: 2F DE 01 00
[1.520] RX: 6F DE 01 00
[1.530] RX: >
[1.600] TX: 2210AA
[1.610] RX: 2210AA
[1.620] RX: NO DATA
[1.630] RX: >
[1.700] RX: GARBAGE%%
[1.800] TX: ATSH DA18F1
[1.810] RX: ATSH DA18F1
[1.820] RX: OK
[1.830] RX: >
[1.900] TX: ATH1
[1.910] RX: ATH1
[1.920] RX: OK
[1.930] RX: >
[2.000] TX: 22F190
[2.010] RX: 22F190
[2.020] RX: 18DAF118 10 0A 62 F1 90 31 32 33
[2.025] RX: 18DAF118 21 34 35 36 37
[2.030] RX: >
[2.100] TX: STPX H:18DA18F1, D:22F191, R:1
[2.110] RX: STPX H:18DA18F1, D:22F191, R:1
[2.120] RX: 18DAF11805 62F19141 42
[2.130] RX: >
"""

LOG_27 = LOG_A + """\
[2.900] TX: ATH0
[2.910] RX: OK
[2.920] RX: >
[3.000] TX: ATSH DA10F1
[3.010] RX: OK
[3.020] RX: >
[3.100] TX: 2701
[3.110] RX: 2701
[3.120] RX: 67 01 AA BB
[3.130] RX: >
[3.200] TX: 27 02 11 22
[3.210] RX: 27 02 11 22
[3.220] RX: 67 02
[3.230] RX: >
"""

# --- parse the main log ---
a = sm.parse_lines(LOG_A.splitlines())
cap = sm.to_capture(a, bitrate=500000, vin="SYNTHETIC")
ex = {e["n"]: e for e in cap["exchanges"]}
check("7 requests", len(cap["exchanges"]) == 7, str([(e["n"], e["service"]) for e in cap["exchanges"]]))
check("targets follow ATSH (10 then 18)",
      [e["target"] for e in cap["exchanges"]] == ["10"] * 5 + ["18"] * 2,
      str([e["target"] for e in cap["exchanges"]]))
check("tester address F1", all(e["tester"] == "F1" for e in cap["exchanges"]))
check("29-bit ids", all(e["id_bits"] == 29 for e in cap["exchanges"]))
check("protocol recorded after STP 34", ex[1]["protocol"] == "STP34" and ex[1]["protocol_id_bits"] == 29,
      str(ex[1]["protocol"]))
check("session answered", ex[1]["status"] == "ok" and ex[1]["responses"][0]["payload"] == "5003003201F4",
      str(ex[1]))
check("multi-frame headerless reply reassembled (14 bytes)",
      ex[2]["responses"][0]["payload"] == "62DE00" + "010203040506" + "0708090A0B"[:10]
      and len(ex[2]["responses"][0]["payload"]) == 28, str(ex[2]["responses"]))
check("0x78 pending not kept as the answer", ex[3]["pending_78"] == 1 and ex[3]["nrc"] is None
      and ex[3]["responses"][0]["payload"] == "6FDE010301", str(ex[3]))
check("stop step captured", ex[4]["request"] == "2FDE0100" and ex[4]["status"] == "ok")
check("NO DATA recorded", ex[5]["status"] == "no_data" and a.stats.get("no_data") == 1, str(ex[5]))
check("headers-on multi-frame (with PCI) reassembled",
      ex[6]["responses"][0]["payload"] == "62F19031323334353637" or ex[6]["responses"][0]["payload"] == "62F19031323334353637", str(ex[6]["responses"]))
check("STPX sent under its own header", ex[7]["via"] == "STPX" and ex[7]["target"] == "18"
      and ex[7]["responses"][0]["payload"] == "62F1914142", str(ex[7]))
check("SEARCHING / BUS INIT / prompts / echo counted, not unparsed",
      a.stats.get("searching") == 1 and a.stats.get("bus_init") == 1
      and a.stats.get("prompts", 0) >= 10 and a.stats.get("echo_lines", 0) >= 8, str(a.stats))
check("stray line goes to unparsed with a count",
      cap["unparsed_count"] == 1 and cap["unparsed"][0]["text"] == "GARBAGE%%"
      and a.stats.get("unparsed") == 1, str(cap["unparsed"]))
check("config commands (ATZ, STP, ATSH, ATH) logged in order",
      [c["cmd"] for c in cap["config_log"]][:3] == ["ATZ", "STP34", "ATSHDA10F1"],
      str(cap["config_log"][:4]))
check("no 0x27 in the main log", not cap["flags"]["security_access"])

# --- frames are the mes_learn shape and accepted by review / gate ---
check("frame shape", all(set(f) == {"t", "id", "data"} for f in cap["frames"]))
ids = {f["id"] for f in cap["frames"]}
check("request and reply CAN ids synthesised", {"18DA10F1", "18DAF110", "18DA18F1", "18DAF118"} <= ids, str(ids))
rep = pc.review(cap["frames"])
mods = {m["target"]: m for m in rep["modules"]}
check("review sees ECM and target 18", "10" in mods and "18" in mods and mods["10"]["module"] == "ECM",
      str(list(mods)))
seq = mods["10"]["sequence"]
check("ECM sequence from the mirror", seq == ["10", "22", "2F", "2F", "22"], str(seq))
check("multi-frame reply survives the round trip",
      len(mods["10"]["procedure"]["steps"][1]["response"]) == 14, str(mods["10"]["procedure"]["steps"][1]))
check("NRC-free", mods["10"]["negative_responses"] == [])

# 0x2F with its stop step, alone: gate under neutral engine-off conditions
f2f = [f for f in cap["frames"] if f["t"] < 1.6 and f["t"] >= 0.4]
v2f = pc.review(f2f)["modules"][0]
neutral = dict(listen_bitrate=500000, pre={"engine_state": "off", "voltage_v": 12.6},
               post={"engine_state": "off", "voltage_v": 12.6}, name="bench widget test")
g2f = pc.gate(v2f, **neutral)
check("0x2F + stop captured via mirror: review replay allowed", v2f["replay_allowed"], str(v2f["replay_reasons"]))
check("0x2F + stop: gate passes under engine-off conditions (verdict recorded)", g2f["passed"], str(g2f))

# --- 0x27 captured and flagged, gate refuses ---
b = sm.parse_lines(LOG_27.splitlines())
cap27 = sm.to_capture(b, bitrate=500000, vin="SYNTHETIC")
check("0x27 flagged on the exchanges", cap27["flags"]["security_access"]
      and len(cap27["flags"]["security_access_exchanges"]) == 2, str(cap27["flags"]))
check("seed/key bytes captured", [e["responses"][0]["payload"] for e in cap27["exchanges"]
                                  if e["service"] == "27"] == ["6701AABB", "6702"])
m27 = [m for m in pc.review(cap27["frames"])["modules"] if m["target"] == "10"][0]
check("review: 0x27 present", m27["has_security_access"])
g27 = pc.gate(m27, **neutral)
check("gate refuses 0x27", not g27["passed"] and any("0x27" in r for r in g27["reasons"]), str(g27["reasons"]))
check("replay refused", not m27["replay_allowed"])

# --- two separate streams give the same result ---
p2 = sm.MirrorParser()
for line in LOG_A.splitlines():
    if line.startswith("#"):
        continue
    ts, rest = line[1:6], line[8:]
    d, text = rest[:2], rest[4:]
    p2.feed(d, text + "\r" if d == "TX" else text + "\r", float(ts))
p2.close()
check("raw two-stream feed matches (requests, frames)",
      [e["request"] for e in p2.exchanges] == [e["request"] for e in a.exchanges]
      and sm.to_capture(p2)["frames"] == cap["frames"])

# --- chunked bytes, '>' prompt without newline ---
p3 = sm.MirrorParser()
p3.feed("TX", b"ATSH DA10F1\r", 0.0)
p3.feed("RX", b"OK\r\r>", 0.05)
p3.feed("TX", b"2210", 0.1)
p3.feed("TX", b"DE\r", 0.11)
p3.feed("RX", b"62 10 DE 01\r\r>", 0.2)
p3.close()
check("chunked bytes + bare prompts", len(p3.exchanges) == 1 and p3.exchanges[0]["target"] == "10"
      and p3.exchanges[0]["responses"][0]["payload"] == "6210DE01", str(p3.exchanges))

# --- saved file round trip into the mes_learn loader ---
with tempfile.TemporaryDirectory() as td:
    lp = Path(td) / "mirror.log"
    lp.write_text(LOG_A, encoding="utf-8")
    pf = sm.parse_file(lp)
    cf = sm.to_capture(pf, vin="SYNTHETIC")
    check("parse_file == parse_lines", cf["frames"] == cap["frames"])
    out = sm.write_capture(cf, Path(td) / "cap" / "x.jsonl")
    hdr, frames = load_capture(str(out))
    check("mes_learn.load_capture reads the written file",
          hdr.get("bus") == "can_c" and hdr.get("source") == "serial_mirror" and frames == cap["frames"])
    try:
        sm.write_capture(cf, out)
        check("never overwrites", False)
    except FileExistsError:
        check("never overwrites", True)

# --- listener refusals (no port is ever opened) ---
def refuses(env: dict, **kw) -> bool:
    try:
        sml.check_guard(env, **kw)
    except Refused:
        return True
    return False


check("listener refuses without the env var", refuses({}))
check("listener refuses without the TX port", refuses({sml.ENV_PORT: "COM21"}))
check("listener refuses COM3 (RX)", refuses({sml.ENV_PORT: "COM3", sml.ENV_PORT_TX: "COM22"}))
check("listener refuses COM3 (TX, odd spelling)", refuses({sml.ENV_PORT: "COM21", sml.ENV_PORT_TX: "\\\\.\\com3"}))
check("listener refuses the same port twice", refuses({sml.ENV_PORT: "COM21", sml.ENV_PORT_TX: "COM21"}))
check("listener refuses MES's own port", refuses({sml.ENV_PORT: "COM21", sml.ENV_PORT_TX: "COM22"}, mes_port="com22"))
check("listener refuses extra real ports", refuses({sml.ENV_PORT: "COM21", sml.ENV_PORT_TX: "COM22",
                                                    sml.ENV_REAL: "COM5,COM21"}))
check("listener accepts two distinct virtual ports",
      sml.check_guard({sml.ENV_PORT: "COM21", sml.ENV_PORT_TX: "COM22"}) == ("COM21", "COM22"))
def _raises(fn, *a, **k) -> bool:
    try:
        fn(*a, **k)
    except Refused:
        return True
    return False


check("run() refuses without the env var", _raises(sml.run, threading.Event(), env={}, out_dir=Path(".")))
check("run() refuses COM3", _raises(sml.run, threading.Event(), env={sml.ENV_PORT: "COM3", sml.ENV_PORT_TX: "COM9"},
                                    out_dir=Path(".")))


class FakeSer:
    opened: list = []

    def __init__(self, port, baud, **kw):
        self.port, self.kw, self.out_waiting = port, kw, 0
        self.xonxoff, self.rtscts, self.dsrdtr = kw["xonxoff"], kw["rtscts"], kw["dsrdtr"]
        self.closed = False
        FakeSer.opened.append(self)

    def read(self, n):
        return b""

    def close(self):
        self.closed = True


rp = sml.open_rx_only("COM21", serial_factory=FakeSer)
s = FakeSer.opened[-1]
check("opened with no flow control and no write timeout use",
      not (s.xonxoff or s.rtscts or s.dsrdtr) and s.kw["write_timeout"] == 0)
check("wrapper exposes no write path",
      not any(hasattr(rp, n) for n in ("write", "flush", "send_break", "setDTR", "setRTS", "_ser_write")))
s.out_waiting = 3
try:
    rp.read()
    check("queued TX bytes stop the listener", False)
except Refused:
    check("queued TX bytes stop the listener", True)
try:
    sml.open_rx_only("com3", serial_factory=FakeSer)
    check("open_rx_only refuses COM3", False)
except Refused:
    check("open_rx_only refuses COM3", True)
check("COM3 never reached the factory", all(x.port != "com3" for x in FakeSer.opened))

# a full fake run: both ports quiet, stop immediately, scratch output dir
with tempfile.TemporaryDirectory() as td:
    ev = threading.Event()
    ev.set()
    cap_run = sml.run(ev, env={sml.ENV_PORT: "COM21", sml.ENV_PORT_TX: "COM22"}, out_dir=Path(td),
                      serial_factory=FakeSer, vin="SYNTHETIC")
    check("fake run saves an (empty) capture and closes both ports",
          Path(cap_run["file"]).exists() and all(x.closed for x in FakeSer.opened[-2:]))

print(f"{checks - len(failures)}/{checks} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
