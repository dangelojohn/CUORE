"""Check the live new-code alert (code watch): baseline, new events, re-appearance,
ack, observation, read-only requests. Driven through LivePoller._poll_dtcs on a
fake stream (no adapter). Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_code_watch.py"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-code-watch-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "mes-log-mcp"))

from cuore.live import channels as channels_mod  # noqa: E402
from cuore.live import ops, store  # noqa: E402
from cuore.live import poller as poller_mod  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

bad: list[str] = []


def check(label: str, cond: bool) -> None:
    if not cond:
        bad.append(label)


def _frames(payload: str) -> str:
    return f"7E8{len(payload) // 2:02X}{payload}"


def _dtc(resp: str, codes: set[str]) -> str:
    body = resp + f"{len(codes):02X}"
    for c in sorted(codes):
        hi = ("PCBU".index(c[0]) << 2) | int(c[1], 16)
        body += f"{hi:X}{c[2]}{c[3:5]}".upper()
    return _frames(body)


class Fake(Stream):
    def __init__(self) -> None:
        self.stored: set[str] = set()
        self.pending: set[str] = set()
        self.sent: list[str] = []
        self._buf = bytearray()

    def open(self) -> None: pass
    def close(self) -> None: pass
    def is_open(self) -> bool: return True
    def reset_input_buffer(self) -> None: self._buf.clear()
    def in_waiting(self) -> int: return len(self._buf)

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii").strip()
        self.sent.append(cmd)
        r = {"ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2", "ATRV": "12.6V"}.get(cmd)
        if cmd == "03":
            r = _dtc("43", self.stored)
        elif cmd == "07":
            r = _dtc("47", self.pending)
        self._buf.extend((r or ("OK" if cmd[:2] in ("AT", "ST") else "NO DATA")).encode() + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:max(n, 1)]
        return chunk

    @property
    def describe(self) -> str: return "cw-fake"


fake = Fake()
lk = AdapterLink(stream_factory=lambda p, b: fake, process="check_code_watch")
set_link(lk)
lk.mark_verified(CAN_C, 10)
p = poller_mod.LivePoller()
poller_mod.set_poller(p)
p._channels = {c.id: c for c in channels_mod.resolve_channels(["engine_rpm"])}
p._pid_route, p._did_route, p._mode = ops._obd_route(), None, "did"
p._cw_enabled, p._cw_vin, p._cw_session_id = True, "ZASTESTVIN0000001", "live-test"
fake.stored = {"P0100"}

with lk.session("check_code_watch", bus=CAN_C) as sess:
    p._poll_dtcs(sess)
    cw = p.status()["code_watch"]
    check("first read is baseline only", cw["baseline"] == ["P0100"] and cw["count_new"] == 0)
    p._poll_dtcs(sess)
    check("unchanged read raises nothing", p.status()["code_watch"]["count_new"] == 0)
    fake.pending = {"P0456"}
    p._poll_dtcs(sess)
    cw = p.status()["code_watch"]
    check("new pending code is one new event", cw["count_new"] == 1 and
          cw["new"][0]["code"] == "P0456" and cw["new"][0]["kind"] == "pending")
    check("last_read_at set, no error", bool(cw["last_read_at"]) and cw["last_error"] is None)
    obs = store.recent_observations(50, vin="ZASTESTVIN0000001", kind="live_new_code")
    check("event persisted as observation with session id and kind",
          len(obs) == 1 and obs[0]["data"]["session_id"] == "live-test"
          and obs[0]["data"]["kind"] == "pending")
    ack = ops.live_code_watch_ack()
    check("ack clears new, keeps event in seen", ack["count_new"] == 0 and len(ack["seen"]) == 1)
    fake.pending = set()
    p._poll_dtcs(sess)
    fake.pending = {"P0456"}
    p._poll_dtcs(sess)
    check("a code that disappears and returns is a new event again",
          p.status()["code_watch"]["count_new"] == 1)
    fake.stored = {"P0100", "P0300"}
    p._poll_dtcs(sess)
    check("baseline code does not alert; a new stored one does",
          [e["code"] for e in p.status()["code_watch"]["new"]] == ["P0456", "P0300"])

check("only read requests were sent (Mode 03/07, AT/ST)",
      all(c[:2] in ("03", "07", "AT", "ST") for c in fake.sent))
print("FAIL: " + "; ".join(bad) if bad else "all green")
sys.exit(1 if bad else 0)
