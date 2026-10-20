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
        self.cra: int | None = None
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
        if cmd.startswith("ATSH") and len(cmd) in (7, 12):
            self.target = int(cmd[4:], 16)
            return "OK"
        if cmd.startswith("ATCRA"):
            self.cra = int(cmd[5:], 16) if len(cmd) > 5 else None
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
        rx = node.get("_rx", self.target + 8)
        if self.cra is not None and self.cra != rx:
            return "NO DATA"
        return _frame(f"{rx:03X}" if rx < 0x800 else f"{rx:08X}", node[cmd])

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

# --- rx_mode / probe_dids (FCA leads) ----------------------------------------
from cuore.live import uds  # noqa: E402
from cuore.live.addressing import address_pair  # noqa: E402


def _run11(nodes_: dict, **kw):
    fb = Fake11(nodes_)
    l = AdapterLink(stream_factory=lambda p, b: fb, process="check_d11_rx")
    set_link(l)
    l.set_cable("grey_a6")
    l.mark_verified(CAN_CH, 10)
    with l.session("d11-rx", bus=CAN_CH, confirm=True, route=r33[0]) as s_:
        return fb, discover11.discover_11bit(s_, CAN_CH, per_target_timeout=0.2, **kw)


fca = {0x7A0: {"_rx": 0x7A0 - 0x280, "3E00": "7E00"}, 0x7B0: {"3E00": "7E00"}}
fb1, r_p8 = _run11(fca, candidates=[0x7A0, 0x7B0])
fb2, r_m = _run11(fca, candidates=[0x7A0, 0x7B0], rx_mode="minus280")
fb3, r_b = _run11(fca, candidates=[0x7A0, 0x7B0], rx_mode="both")
t_p8, t_m, t_b = ({h["target"]: h for h in r["hits"]} for r in (r_p8, r_m, r_b))
check("(rx) default plus8 finds 7B0 only; minus280 finds 7A0 (rx 520) only",
      set(t_p8) == {"7B0"} and set(t_m) == {"7A0"} and t_m["7A0"]["response"] == "520",
      str((t_p8, t_m)))
check("(rx) both finds each node on its own convention",
      set(t_b) == {"7A0", "7B0"} and t_b["7A0"]["response"] == "520"
      and t_b["7B0"]["response"] == "7B8", str(t_b))
check("(rx) minus280 skips ids whose reply id would be < 0x100",
      _run11(fca, candidates=[0x300], rx_mode="minus280")[1]["tried"] == 0)

# 29-bit discover: node refuses F190 (silent) but answers F194
req29, rsp29 = address_pair(0x40)
node29 = {int(req29, 16): {"_rx": int(rsp29, 16), "22F194": "62F194" + _ascii_hex("SW123")}}


def _run29(**kw):
    fb = Fake11(node29)
    l = AdapterLink(stream_factory=lambda p, b: fb, process="check_d11_29")
    set_link(l)
    l.set_cable("grey_a6")
    l.mark_verified(CAN_CH, 10)
    with l.session("d29", bus=CAN_CH, confirm=True) as s_:
        return fb, uds.discover(s_, CAN_CH, candidates=[0x40, 0x41], per_target_timeout=0.2, **kw)


fb29a, r29a = _run29()
fb29b, r29b = _run29(probe_dids=("F190", "F132", "F194"))
h29 = {h["target"]: h for h in r29b["hits"]}
check("(probe) F194-only node: missed by default, found with probe_dids",
      r29a["hits"] == [] and set(h29) == {"40"} and h29["40"]["probe_did"] == "F194"
      and h29["40"]["probe_value"] == "SW123", str((r29a["hits"], r29b["hits"])))
check("(probe/rx) only 22/3E services ever sent",
      all(c[:2] in ("3E", "22", "AT", "ST") for fb_ in (fb1, fb2, fb3, fb29a, fb29b)
          for c in fb_.sent), "non read-only service")

# --- broadcast-id exclusion (DBC + passive capture) and flow-control restore --
bcast = {0x73E: {"3E00": "7E00"}, 0x749: {"3E00": "7E00"}, 0x7A0: {"3E00": "7E00"}}
fbd, rd = _run11(bcast)  # default 0x700-0x7FF sweep
tx_ids = {c[4:] for c in fbd.sent if c.startswith("ATSH")} - {"7DF"}
sk = {d["id"]: d["reason"] for d in rd["skipped"]}
check("(safety) default sweep never transmits on 73E/749 and lists them as skipped",
      not ({"73E", "749"} & tx_ids) and {"73E", "749"} <= set(sk)
      and "7A0" in tx_ids and "dbc" in sk["73E"].lower(), str((sorted(tx_ids)[:8], rd["skipped"])))
store.record_observation("bus_capture", {"ids": {"7C4": 9, "0x7C5": 3}}, bus="can_ch")
fbc, rc = _run11(bcast, candidates=[0x73E, 0x7A0, 0x7C4, 0x7C5, 0x72A],
                 rx_mode="both")
txc = {c[4:] for c in fbc.sent if c.startswith("ATSH")} - {"7DF"}
skc = {d["id"] for d in rc["skipped"]}
check("(safety) caller candidates: DBC id and captured ids filtered, 7A0 still sent",
      txc == {"7A0", "72A"} and {"73E", "7C4", "7C5"} <= skc, str((txc, rc["skipped"])))
check("(safety) response id landing on a DBC id (72A -> 4AA, minus280) is skipped, never sent",
      "4AA" in skc and not any(c == "ATCRA4AA" for c in fbc.sent), str(rc["skipped"]))

fbf = Fake11(node29)
lf = AdapterLink(stream_factory=lambda p, b: fbf, process="check_d11_fc")
set_link(lf)
lf.set_cable("grey_a6")
lf.mark_verified(CAN_CH, 10)
with lf.session("fc", bus=CAN_CH, confirm=True) as sf:
    sf.target_raw(req29, rsp29)
    n_fc = len(fbf.sent)
    sf.untarget()
    after = fbf.sent[n_fc:]
check("(fc) untarget restores ATFCSM0 (and default FC header/data) after target_raw",
      "ATFCSM0" in after and "ATFCSM1" not in after and "ATFCSD300000" in after, str(after))

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
