"""Checks for the read-only 11-bit discovery (cuore.live.discover11).

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_discover11.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-d11-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import discover11, interlock, store  # noqa: E402
from cuore.live.buses import CAN_CH, routes_for  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running",
                                "label": None}


def _ascii_hex(s: str) -> str:
    return "".join(f"{ord(c):02X}" for c in s)


def _frame(header: str, payload: str) -> str:
    return f"{header}{len(payload) // 2:02X}{payload}"


class Fake11(Stream):
    def __init__(self, nodes: dict[int, dict[str, str]]) -> None:
        self.nodes = nodes
        self.target: int | None = None
        self.sent: list[str] = []
        self._buf = bytearray()
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def _reply(self, cmd: str) -> str:
        if cmd.startswith("ATSH") and len(cmd) == 7:
            self.target = int(cmd[4:], 16)
            return "OK"
        if cmd == "ATI":
            return "ELM327 v2.3"
        if cmd == "STI":
            return "STN1170 v4.3.2"
        if cmd.startswith(("AT", "ST")):
            return "OK"
        node = self.nodes.get(self.target or -1)
        if node is None or cmd not in node:
            return "NO DATA"
        return _frame(f"{self.target + 8:03X}", node[cmd])

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").strip()
        self.sent.append(cmd)
        self._buf.extend(self._reply(cmd).encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:max(n, 1)]
        return chunk

    def reset_input_buffer(self) -> None:
        self._buf.clear()

    def in_waiting(self) -> int:
        return len(self._buf)

    @property
    def describe(self) -> str:
        return "d11-fake"


nodes = {
    0x7A0: {"3E00": "7E00", "22F192": "62F192" + _ascii_hex("MRR1evo14F")},
    0x7B0: {"3E00": "7F3E11"},
}
bus = Fake11(nodes)
lk = AdapterLink(stream_factory=lambda p, b: bus, process="check_discover11")
set_link(lk)
lk.set_cable("grey_a6")
lk.mark_verified(CAN_CH, 10)
r33 = [r for r in routes_for(CAN_CH, "grey_a6") if r.stn_protocol == "33"]
check("CAN-CH has an STP 33 route", len(r33) == 1)
before = store.confirmed_targets("ZASFAKPN5J7B88115")
with lk.session("d11-test", bus=CAN_CH, confirm=True, route=r33[0]) as sess:
    check("session uses 11-bit headers", sess.header_bits == 11, str(sess.header_bits))
    res = discover11.discover_11bit(sess, CAN_CH, candidates=[0x7A0, 0x7B0, 0x7C0, 0x7DF, 0x7E0],
                                    per_target_timeout=0.2)
hits = {h["target"]: h for h in res["hits"]}

check("(a) 7A0 answering 7E is a hit with response 7A8",
      "7A0" in hits and hits["7A0"]["response"] == "7A8"
      and hits["7A0"]["tester_present"] == "positive", str(res["hits"]))
check("(b) 7F 3E 11 is still a hit", "7B0" in hits and "7B0" in hits
      and hits["7B0"]["tester_present"] != "positive", str(res["hits"]))
check("(c) silent id is not a hit, OBD ids skipped",
      "7C0" not in hits and "7DF" not in hits and "7E0" not in hits and res["tried"] == 3,
      str(res))
check("(d) ATCP never sent", not any(c.startswith("ATCP") for c in bus.sent))
sh = [c for c in bus.sent if c.startswith("ATSH")]
cra = [c for c in bus.sent if c.startswith("ATCRA") and len(c) > 5]
check("(d) ATSH/ATCRA carry 3-digit ids",
      all(len(c) == 7 for c in sh) and all(len(c) == 8 for c in cra) and "ATCRA7A8" in cra,
      str(sh + cra))
check("(e) nothing persisted", store.confirmed_targets("ZASFAKPN5J7B88115") == before)
check("identity read for the 7A0 hit", "F192" in hits["7A0"]["identity"])
check("no write-capable service sent",
      all(c[:2] in ("3E", "22", "AT", "ST") for c in bus.sent), str(bus.sent))

# --- timing/desync checks (silent bus, adapter still waiting) ---------------
class Silent(Fake11):
    """22F190 gets no reply until a bare CR interrupts it ("STOPPED")."""
    def __init__(self) -> None:
        super().__init__({})
        self.pending = False
        self.log: list[str] = []

    def write(self, data: bytes) -> None:
        raw = data.decode("ascii", errors="replace")
        self.log.append(raw)
        if raw == "\r":
            self._buf.extend(b"STOPPED\r>" if self.pending else b"?\r>")
            self.pending = False
            return
        cmd = raw.strip()
        if self.pending:  # swallowed: a command sent mid-wait is lost
            self._buf.extend(b"STOPPED\r>")
            self.pending = False
            return
        if cmd == "22F190":
            self.pending = True
            return
        self._buf.extend(self._reply(cmd).encode("ascii") + b"\r>")


sil = Silent()
lk2 = AdapterLink(stream_factory=lambda p, b: sil, process="check_discover11_sil")
set_link(lk2)
lk2.set_cable("grey_a6")
lk2.mark_verified(CAN_CH, 10)
with lk2.session("d11-sil", bus=CAN_CH, confirm=True, route=r33[0]) as sess2:
    n0 = len(sil.log)
    r = sess2.cmd("22F190", 0.2)
    check("(a) python-side timeout is tagged and drains to the prompt",
          "TIMEOUT" in r and sil.log[n0 + 1] == "\r" and not sil._buf and not sil.pending,
          f"{r!r} {sil.log[n0:]}")
    r2 = sess2.cmd("ATCP18", 2)
    check("(b) next command after a timeout is sent intact and answered OK",
          sil.log[-1] == "ATCP18\r" and r2 == "OK", f"{r2!r} {sil.log[-3:]}")
    sess2.adapter_wait = 1.02
    t0 = __import__("time").monotonic()
    q = sess2.query("22F190", "62", 0.25)
    dt = __import__("time").monotonic() - t0
    check("(c) query deadline is never below the adapter wait", dt >= 1.2, f"{dt:.2f}s")
    seen = []
    orig = sess2.query
    sess2.query = lambda req, rb, t=0.0, _o=orig: (seen.append(t), _o(req, rb, 0.2))[1]
    discover11.discover_11bit(sess2, CAN_CH, candidates=[0x7A0], per_target_timeout=0.25)
    check("(c) discover_11bit per-target wait >= adapter wait", seen and min(seen) >= 1.2,
          str(seen))
    sess2.cmd("ATST19", 2)
    check("(c) ATSTxx updates the tracked adapter wait", abs(sess2.adapter_wait - 0.1) < 1e-6,
          str(sess2.adapter_wait))

if failures:
    print("FAILED:")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"check_discover11: {checks} checks passed")
