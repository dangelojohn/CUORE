"""abs_connect_test (cuore/live/abs_connect.py): gates, ranked routes, bounds, logging.

Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_abs_connect.py
Fake stream only; never touches COM3.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-absconn-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ["CUORE_AUTOSTART"] = "0"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "obd2-mcp"))

from cuore.live import abs_connect, audit  # noqa: E402
from cuore.live.addressing import by_code  # noqa: E402
from cuore.live.buses import CAN_CH  # noqa: E402
from cuore.live.errors import BadCommand, Refused  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


HEX_REQUESTS = ("22F190", "3E00", "1001")


class Fake(Stream):
    """An adapter that tracks the settings a route changes and answers by rule."""

    def __init__(self, rule=None):
        self.rule = rule or (lambda req, st: None)
        self.state = {"fcm": 1, "atcra": "", "ash": ""}
        self._buf = bytearray()
        self.sent: list[str] = []
        self.writes = 0

    def open(self): pass
    def close(self): pass
    def is_open(self): return True

    def write(self, data: bytes) -> None:
        self.writes += 1
        cmd = data.decode("ascii", errors="replace").rstrip("\r\n")
        self.sent.append(cmd)
        if cmd.startswith("ATFCSM"):
            self.state["fcm"] = int(cmd[-1])
        if cmd.startswith("ATCRA"):
            self.state["atcra"] = cmd[5:]
        if cmd.startswith("ATSH"):
            self.state["ash"] = cmd[4:]
        if cmd in HEX_REQUESTS:
            reply = self.rule(cmd, self.state) or "NO DATA"
        else:
            reply = {"ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2"}.get(cmd, "OK")
        self._buf.extend(reply.encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:len(chunk)]
        return chunk

    def reset_input_buffer(self): self._buf.clear()
    def in_waiting(self): return len(self._buf)

    @property
    def describe(self): return "fake"


def _link(rule=None, cable="grey_a6", verified=True):
    st = Fake(rule)
    lk = AdapterLink(stream_factory=lambda p, b: st, process="check_abs_connect")
    lk.auto_verify = False
    set_link(lk)
    lk.set_cable(cable)
    if verified:
        lk.mark_verified(CAN_CH, 22)
    return lk, st


def _hex_sent(st: Fake) -> list[str]:
    return [c for c in st.sent if c in HEX_REQUESTS]


def _refused(fn, exc=Refused):
    try:
        fn()
    except exc as e:
        return str(e)
    return None


# --- gates: nothing leaves the adapter ----------------------------------------------------
lk, st = _link(cable="none")
msg = _refused(lambda: abs_connect.abs_connect_test("ABS", confirm=True))
check("refused unless the grey cable is declared", bool(msg) and "grey A6" in msg, str(msg))
check("... and the adapter was never opened", st.writes == 0)

lk, st = _link(cable="blue_a5")
check("refused with the blue cable", _refused(lambda: abs_connect.abs_connect_test("ABS", confirm=True)) is not None)

lk, st = _link(verified=False)
msg = _refused(lambda: abs_connect.abs_connect_test("ABS", confirm=True))
check("refused when CAN-CH is not verified", bool(msg) and "verify_bus" in msg, str(msg))
check("... and nothing was sent", st.writes == 0)

lk, st = _link()
lk.verified[CAN_CH.key]["ts"] -= 10_000
check("refused when the verification is stale",
      _refused(lambda: abs_connect.abs_connect_test("ABS", confirm=True)) is not None and st.writes == 0)

lk, st = _link()
msg = _refused(lambda: abs_connect.abs_connect_test("ABS", confirm=False))
check("refused without confirm=True", bool(msg) and "confirm" in msg, str(msg))
check("... and nothing was sent", st.writes == 0)

lk, st = _link()
check("refused for a module that is not on CAN-CH",
      _refused(lambda: abs_connect.abs_connect_test("ECM", confirm=True), BadCommand) is not None
      and st.writes == 0)

# --- silent car: every route tried once, bounded, protocol and rate untouched ----------------
lk, st = _link()
out = abs_connect.abs_connect_test("ABS", confirm=True)
check("silent: five routes, five requests", out["requests_sent"] == 5 and len(out["steps"]) == 5
      and len(_hex_sent(st)) == 5, str(_hex_sent(st)))
check("silent: nobody answered", out["answered_by"] is None and "silent" in out["conclusion"])
check("silent: only read-only requests left the adapter",
      set(_hex_sent(st)) <= set(HEX_REQUESTS) and _hex_sent(st) == ["22F190", "3E00", "22F190", "22F190", "1001"],
      str(_hex_sent(st)))
check("the only protocol ever selected is STP 34 (init, and untarget's own re-select)",
      {c for c in st.sent if c.startswith("STP ")} == {"STP 34"}, str(st.sent))
check("no bit-rate, monitor, filter-table or FEPS command",
      not any(c.startswith(("STPBR", "STFAP", "STFPA", "STFAC", "STPO")) or c in ("STM", "STMA")
              for c in st.sent), str(st.sent))
check("protocol reported: 29-bit 500k", out["protocol"]["header_bits"] == 29
      and out["protocol"]["bitrate"] == 500000 and out["protocol"]["stn_protocol"] == "34")
check("every set-up step records the commands sent and the adapter's replies",
      all(s["commands"] and all("sent" in c and "got" in c for c in s["commands"])
          for s in (out["steps"][0], out["steps"][2], out["steps"][3])), str(out["steps"][0]))
check("every step records the request and the raw reply",
      all(s["request"] and s["raw"] == "NO DATA" for s in out["steps"]))
check("route 1 shows the production commands incl. ATSH 18DA2AF1 and ATFCSM1",
      [c["sent"] for c in out["steps"][0]["commands"]][:2] == ["ATSH18DA2AF1", "ATCRA18DAF12A"]
      and "ATFCSM1" in [c["sent"] for c in out["steps"][0]["commands"]])
check("route 4 clears the receive filter and uses the 6-digit header",
      ["ATCP18", "ATSHDA2AF1", "ATCRA"] == [c["sent"] for c in out["steps"][3]["commands"]])
check("the adapter was put back to functional addressing afterwards",
      "ATSHDB33F1" in st.sent[-12:] and out["read_only"] is True, str(st.sent[-12:]))
ev = [e for e in audit.read_recent(400) if e.get("event") == "abs_connect_step"]
check("each step is audited", len(ev) >= 5)

# --- stops at the first answer -----------------------------------------------------------------
vin_reply = "18DAF12A0462F190AA"
lk, st = _link(lambda req, s: vin_reply if req == "22F190" else None)
out = abs_connect.abs_connect_test("ABS", confirm=True)
check("answers on route 1: stops after one request", out["answered_by"] == "1_production_22F190"
      and out["requests_sent"] == 1 and len(_hex_sent(st)) == 1, str(out["steps"]))
check("... outcome positive", out["steps"][0]["outcome"] == "positive")

lk, st = _link(lambda req, s: "18DAF12A027E00" if req == "3E00" else None)
out = abs_connect.abs_connect_test("ABS", confirm=True)
check("only 3E 00 answers: stops at route 2", out["answered_by"] == "2_tester_present_3E00"
      and out["requests_sent"] == 2, str(out["answered_by"]))

lk, st = _link(lambda req, s: vin_reply if req == "22F190" and s["fcm"] == 0 else None)
out = abs_connect.abs_connect_test("ABS", confirm=True)
check("answers only with default flow control: stops at route 3",
      out["answered_by"] == "3_default_flow_control_22F190" and out["requests_sent"] == 3
      and len(_hex_sent(st)) == 3, str(out["answered_by"]))

lk, st = _link(lambda req, s: "18DAF1290462F190AA" if req == "22F190" and s["atcra"] == "" else None)
out = abs_connect.abs_connect_test("ABS", confirm=True)
check("a reply from another id on the open-filter route is reported as such",
      out["answered_by"] == "4_six_digit_header_open_filter_22F190"
      and out["steps"][3]["outcome"] == "positive_from_other_id"
      and out["steps"][3]["headers_seen"] == ["18DAF129"], str(out["steps"][3]))

lk, st = _link(lambda req, s: "18DAF12A037F2278" if req == "22F190" else None)
out = abs_connect.abs_connect_test("ABS", confirm=True)
check("a negative response counts as an answer and carries its NRC",
      out["answered_by"] == "1_production_22F190" and out["steps"][0]["outcome"] == "negative"
      and out["steps"][0]["nrc"] == "78", str(out["steps"][0]))

lk, st = _link(lambda req, s: "CAN ERROR")
out = abs_connect.abs_connect_test("ABS", confirm=True)
check("a CAN ERROR ends the test at once", out["requests_sent"] == 1 and out["stopped"]
      and "CAN ERROR" in out["stopped"], str(out["stopped"]))

# --- the set-up allowlist refuses anything that could change protocol or rate ---------------------
for bad in ("STP 36", "STPBR 125000", "STFAC", "ATSP6", "ATZ", "STPX", "2E0101"):
    check(f"setup allowlist rejects {bad}", abs_connect._ALLOWED_SETUP.match(bad) is None)
check("setup allowlist accepts the route commands",
      all(abs_connect._ALLOWED_SETUP.match(c) for c in
          ("ATAT0", "ATSTFF", "STCFCPC", "ATFCSM0", "ATCP18", "ATSHDA2AF1", "ATSH18DA2AF1",
           "ATCRA", "ATCRA18DAF12A")))

# --- the production path now keeps the adapter's replies to its addressing commands ----------------
lk, st = _link()
with lk.session("t", bus=CAN_CH, confirm=True) as sess:
    sess.uds(by_code("ABS"), 0x22, bytes.fromhex("F190"))
    check("target_raw keeps the adapter's replies until the request is audited",
          sess.last_setup == [])
ev = [e for e in audit.read_recent(50) if e.get("event") == "uds" and e.get("ecu") == "ABS"]
check("the uds audit entry carries the addressing commands and replies",
      bool(ev) and ev[-1].get("setup") and ev[-1]["setup"][0][0] == "ATSH18DA2AF1", str(ev[-1:] ))

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
