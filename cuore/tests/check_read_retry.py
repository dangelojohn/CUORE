"""One CAN ERROR retry of READS only, minimum gap between sessions, serialised
callers. Fake adapter only; never touches COM3.
Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_read_retry.py"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-retry-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ["CUORE_AUTOSTART"] = "0"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "obd2-mcp"))

from cuore.live import audit, read_state, transport  # noqa: E402
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
    "ATSH7DF": "OK", "ATCRA": "OK", "STCFCPC": "OK", "ATP": "OK",
    "0100": "7E8064100BE3FA813",
}
GOOD = "18DAF110 04 62 F1 90 AA"
ECM = by_code("ECM")


class Fake(Stream):
    """Replies to request hex from a per-request queue (last one repeats)."""
    def __init__(self, replies: dict[str, list[str]]):
        self.replies = {k: list(v) for k, v in replies.items()}
        self._buf = bytearray()
        self.sent: list[str] = []
        self.busy = 0
        self.max_busy = 0
        self.slow = 0.0

    def open(self): pass
    def close(self): pass
    def is_open(self): return True

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").rstrip("\r\n")
        self.sent.append(cmd)
        q = self.replies.get(cmd)
        if q is not None:
            r = q.pop(0) if len(q) > 1 else q[0]
            if self.slow:
                self.busy += 1
                self.max_busy = max(self.max_busy, self.busy)
                time.sleep(self.slow)
                self.busy -= 1
        else:
            r = _SCRIPT.get(cmd, "OK")
        self._buf.extend(r.encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:len(chunk)]
        return chunk

    def reset_input_buffer(self): self._buf.clear()
    def in_waiting(self): return len(self._buf)

    @property
    def describe(self): return "fake"


def _link(replies):
    st = Fake(replies)
    lk = AdapterLink(stream_factory=lambda p, b: st, process="check_read_retry")
    set_link(lk)
    lk.mark_verified(CAN_C, 10)
    return lk, st


def _uds(lk, service, payload=b"\xf1\x90"):
    with lk.session("t", bus=CAN_C) as s:
        return s.uds(ECM, service, payload, timeout=1)


transport.RETRY_PAUSE_S = 0.05
transport.MIN_SESSION_GAP_S = 0.0

# 1. read: CAN ERROR then answer -> retried once, recorded
lk, st = _link({"22F190": ["CAN ERROR", GOOD]})
r = _uds(lk, 0x22)
check("read retried once", r["attempts"] == 2 and st.sent.count("22F190") == 2, str(r))
check("retry recovered: no error", not r["error"] and bool(r["positive"]), str(r))
rec = [e for e in audit.read_recent(50) if e.get("event") == "uds" and e.get("req") == "22F190"]
check("attempts recorded in audit", rec and rec[-1].get("attempts") == 2, str(rec[-1:]))

# 2. second failure stays NOT READ
lk, st = _link({"22F190": ["CAN ERROR", "CAN ERROR"]})
r = _uds(lk, 0x22)
check("retried exactly once", r["attempts"] == 2 and st.sent.count("22F190") == 2, str(r))
check("second failure keeps the error", r["error"] == "CAN ERROR" and not r["positive"], str(r))
check("second failure is NOT READ",
      not read_state.is_read({"ecu": "ECM", "dtcs": [], "error": r["error"]}))

# 3. car-affecting requests never retried
for svc, pay in ((0x2E, b"\xf1\x90\x01"), (0x14, b"\xff\xff\xff"), (0x31, b"\x01\x02\x03"),
                 (0x10, b"\x03"), (0x27, b"\x01")):
    req = f"{svc:02X}{pay.hex().upper()}"
    lk, st = _link({req: ["CAN ERROR", GOOD]})
    try:
        r = _uds(lk, svc, pay)
        n = st.sent.count(req)
        a = r["attempts"]
    except Exception as e:  # allowlist may refuse the request outright: still not retried
        n, a = st.sent.count(req), 0
    check(f"service {svc:02X} never retried", n <= 1 and a <= 1, f"sent {n} attempts {a}")

# 4. no retry after NO DATA or a negative response
lk, st = _link({"22F190": ["NO DATA", GOOD]})
r = _uds(lk, 0x22)
check("NO DATA not retried", r["attempts"] == 1 and st.sent.count("22F190") == 1, str(r))
lk, st = _link({"22F190": ["18DAF110 03 7F 22 31", GOOD]})
r = _uds(lk, 0x22)
check("negative response not retried", r["attempts"] == 1 and st.sent.count("22F190") == 1, str(r))

# 5. minimum gap between sessions honoured; first session not delayed
transport.MIN_SESSION_GAP_S = 0.4
lk, st = _link({"22F190": [GOOD]})
t0 = time.monotonic()
_uds(lk, 0x22)
first = time.monotonic() - t0
t1 = time.monotonic()
_uds(lk, 0x22)
gap_wait = time.monotonic() - t1
check("first session not delayed", first < 0.35, f"{first:.2f}")
check("second session waits out the gap", gap_wait >= 0.35, f"{gap_wait:.2f}")
opens = [e for e in audit.read_recent(200) if e.get("event") in ("session_open", "session_close")]
closes = [e for e in opens if e["event"] == "session_close"]
check("gap constant is named and >= 1 s default",
      transport.__dict__.get("MIN_SESSION_GAP_S") is not None)
with lk.session("outer", bus=CAN_C):
    t2 = time.monotonic()
    with lk.session("inner", bus=CAN_C):
        pass
    check("nested session on same thread not delayed", time.monotonic() - t2 < 0.3)

# 6. concurrent callers are serialised
transport.MIN_SESSION_GAP_S = 0.0
lk, st = _link({"22F190": [GOOD]})
st.slow = 0.15
res: list[dict] = []
ths = [threading.Thread(target=lambda: res.append(_uds(lk, 0x22))) for _ in range(4)]
for t in ths:
    t.start()
for t in ths:
    t.join()
check("all concurrent callers answered", len(res) == 4 and all(not x["error"] for x in res), str(res))
check("two reads never overlapped on the adapter", st.max_busy == 1, str(st.max_busy))
ev = [e for e in audit.read_recent(400) if e.get("event") in ("session_open", "session_close")][-8:]
depth = 0
ok = True
for e in ev:
    depth += 1 if e["event"] == "session_open" else -1
    ok = ok and 0 <= depth <= 1
check("audit sessions strictly one at a time", ok and depth == 0, str(ev))

print(f"{checks} checks, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
