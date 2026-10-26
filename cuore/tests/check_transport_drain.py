"""Stale-input drain + opt-in Session.hard_reset (transport.py).

Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_transport_drain.py
Fake stream only; never touches COM3.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-drain-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("CUORE_RESET_BEFORE_LEGISLATED", None)
os.environ["CUORE_AUTOSTART"] = "0"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "obd2-mcp"))

from cuore.live import audit  # noqa: E402
from cuore.live.addressing import by_code  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


_SCRIPT = {
    "ATE0": "OK", "ATL0": "OK", "ATS0": "OK", "ATH1": "OK", "ATAT1": "OK",
    "ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2", "ATCAF1": "OK",
    "STP 33": "OK", "STP 34": "OK", "STCMM 0": "OK", "STCMM 1": "OK",
    "ATSH7DF": "OK", "ATCRA": "OK", "STCFCPC": "OK",
    "ATP": "OK", "ATWS": "ELM327 v2.3", "0100": "7E8064100BE3FA813",
}


class Fake(Stream):
    def __init__(self):
        self.script = dict(_SCRIPT)
        self._buf = bytearray()
        self.sent: list[str] = []

    def open(self): pass
    def close(self): pass
    def is_open(self): return True

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").rstrip("\r\n")
        self.sent.append(cmd)
        self._buf.extend(self.script.get(cmd, "OK").encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:len(chunk)]
        return chunk

    def reset_input_buffer(self): self._buf.clear()
    def in_waiting(self): return len(self._buf)

    @property
    def describe(self): return "fake"


def _link(reset: bool = False):
    st = Fake()
    lk = AdapterLink(stream_factory=lambda p, b: st, process="check_transport_drain")
    lk.reset_before_legislated = reset
    set_link(lk)
    lk.mark_verified(CAN_C, 10)
    return lk, st


def _events(name: str) -> list[dict]:
    return [e for e in audit.read_recent(400) if e.get("event") == name]


# 1. stale reply is drained (not read as the next answer) and audited
lk, st = _link()
with lk.session("drain", bus=CAN_C) as sess:
    st._buf.extend(b"7E8 04 62 F1 90 AA\r>")
    r = sess.cmd("0100", 2)
check("stale reply drained, not returned as the answer",
      "62F190" not in r.replace(" ", "") and "7E8064100" in r.replace(" ", ""), r)
ev = _events("stale_input")
check("stale reply audited with the request it preceded",
      len(ev) == 1 and ev[0].get("before") == "0100" and "62 F1 90" in ev[0].get("bytes", ""), str(ev))

# 2. hard_reset: ATWS first, then init restated, targeting cleared
lk, st = _link()
with lk.session("hr", bus=CAN_C) as sess:
    st.sent.clear()
    sess.hard_reset()
sent = st.sent
i = sent.index("ATWS") if "ATWS" in sent else -1
tail = sent[i + 1:] if i >= 0 else []
check("hard_reset sends ATWS then restates init and clears targeting",
      i == 0 and tail[:6] == ["ATE0", "ATL0", "ATS0", "ATH1", "ATAT1", "ATCAF1"]
      and any(c.startswith("STP ") for c in tail) and "STCMM 1" in tail
      and "ATCRA" in tail and "STCFCPC" in tail and len(_events("hard_reset")) == 1, str(sent))

# 3. flag off: physical -> functional never resets
lk, st = _link(False)
with lk.session("off", bus=CAN_C) as sess:
    sess.target(by_code("ECM"))
    sess.untarget()
check("flag off: no ATWS on physical -> functional", "ATWS" not in st.sent, str(st.sent))

# 4. flag on: exactly one reset, before the functional restate
lk, st = _link(True)
with lk.session("on", bus=CAN_C) as sess:
    sess.target(by_code("ECM"))
    sess.untarget()
    sess.target(by_code("TCM"))
    sess.untarget()
check("flag on: one ATWS per session, before the functional header",
      st.sent.count("ATWS") == 1 and any(
          c in ("ATSH7DF", "ATSHDB33F1") for c in st.sent[st.sent.index("ATWS"):]),
      str(st.sent))

# 5. flag on but never physical: no reset
lk, st = _link(True)
with lk.session("fresh", bus=CAN_C) as sess:
    sess.untarget()
check("flag on, no physical target before: no reset", "ATWS" not in st.sent, str(st.sent))

# 6. a second caller waits a bounded time for a long-held session, then is told the adapter is busy
import threading  # noqa: E402
import time  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.live.errors import LinkUnavailable  # noqa: E402

os.environ["CUORE_OBD_PORT"] = "COM99"
lk, st = _link()
lk.lock_wait_s = 0.3
inside, release = threading.Event(), threading.Event()


def _hold():
    with lk.session("long capture", bus=CAN_C, passive=True):
        inside.set()
        release.wait(5)


th = threading.Thread(target=_hold, daemon=True)
th.start()
inside.wait(5)
t0 = time.monotonic()
msg = None
try:
    with lk.session("second", bus=CAN_C):
        pass
except LinkUnavailable as e:
    msg = str(e)
check("a second caller is refused after a bounded wait, naming the holder",
      msg is not None and "long capture" in msg and time.monotonic() - t0 < 3.0, str(msg))
release.set()
th.join(5)
with lk.session("after", bus=CAN_C):
    pass
check("the adapter is usable again once the holder finishes", lk.current is None)

# 7. a stream factory that raises must release the lock file and the adapter lock
def _boom(p, b):
    raise OSError("no such device")


lk = AdapterLink(stream_factory=_boom, process="check_transport_drain")
lk.mark_verified(CAN_C, 10)
msg = None
try:
    with lk.session("boom", bus=CAN_C):
        pass
except LinkUnavailable as e:
    msg = str(e)
check("a failing stream factory surfaces as LinkUnavailable", msg is not None, str(msg))
check("and leaves no advisory lock file behind", interlock.read_lock() is None, str(interlock.read_lock()))
got = []
th = threading.Thread(target=lambda: got.append(lk.lock.acquire(timeout=1)), daemon=True)
th.start()
th.join(3)
check("and does not leave the adapter lock held", got == [True], str(got))

# 8. untarget() on a cable route re-selects the protocol AND restates the route's bit rate
from cuore.live.buses import CAN_IHS  # noqa: E402

lk, st = _link()
lk.set_cable("blue_a5")
with lk.session("ihs-untarget", bus=CAN_IHS, passive=True) as sess:
    st.sent.clear()
    sess.untarget()
stp = [i for i, c in enumerate(st.sent) if c.startswith("STP ")]
check("untarget on the 125k cable route restates STPBR 125000 after STP",
      bool(stp) and "STPBR 125000" in st.sent[stp[-1]:], str(st.sent))

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
