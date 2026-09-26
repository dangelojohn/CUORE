"""Checks for per-module DTC clearing (UDS 0x14) and its guards.

Plain script, check(), exit 1 on failure. State goes to a temp directory.

Run:
    .venv/Scripts/python.exe cuore/tests/check_clear.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-clear-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import interlock, ops, store  # noqa: E402
from cuore.live.errors import Refused  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0
interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def raises(exc, fn):
    try:
        fn()
    except exc as e:
        return str(e)
    return None


def _frames(header: str, payload: str) -> str:
    n = len(payload) // 2
    if n <= 7:
        return f"{header}{n:02X}{payload}"
    out = [f"{header}1{n:03X}{payload[:12]}"]
    rest, seq = payload[12:], 1
    while rest:
        out.append(f"{header}2{seq % 16:X}{rest[:14]}")
        rest, seq = rest[14:], seq + 1
    return "\r".join(out)


class FakeCar(Stream):
    """An ECM with P0456-00 and P0455-00 failing; after a clear P0455 comes straight back."""

    def __init__(self, speed_kmh: int = 0, clear_reply: str = "54") -> None:
        self.speed = speed_kmh
        self.clear_reply = clear_reply
        self.cleared = False
        self.proto = ""
        self.sent: list[str] = []
        self._buf = bytearray()
        self._open = False

    def open(self): self._open = True
    def close(self): self._open = False
    def is_open(self): return self._open
    @property
    def describe(self): return "serial COM99@115200 (fake)"

    def _reply(self, cmd: str) -> str:
        if cmd.startswith("STP "):
            self.proto = cmd[4:]
            return "OK"
        if cmd == "STM":
            return "1E36000100112233\r1E36000B00112233"
        if cmd.startswith(("AT", "ST")):
            return {"ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2", "ATRV": "12.4V"}.get(cmd, "OK")
        if cmd == "010D":
            return f"7E803410D{self.speed:02X}" if self.proto == "33" else "NO DATA"
        hdr = "18DAF110"
        if cmd == "1902FF":
            recs = "04550008" if self.cleared else "0456004D" + "0455004D"
            return _frames(hdr, "5902FF" + recs + ("" if self.cleared else "01370040"))
        if cmd.startswith(("1904", "1906")):
            return _frames(hdr, "7F1931")
        if cmd == "14FFFFFF":
            if self.clear_reply == "54":
                self.cleared = True
            return _frames(hdr, self.clear_reply)
        return "NO DATA"

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").strip()
        self.sent.append(cmd)
        self._buf.extend(self._reply(cmd).encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:max(n, 1)]
        return chunk

    def reset_input_buffer(self): self._buf.clear()
    def in_waiting(self): return len(self._buf)


def use(car: FakeCar) -> None:
    lk = AdapterLink(stream_factory=lambda p, b: car, process="check_clear")
    lk.auto_verify_seconds = 0.2
    set_link(lk)


# 1. consent is mandatory and checked before any traffic
car = FakeCar()
use(car)
msg = raises(Refused, lambda: ops.clear_module_dtcs("ECM", "yes please", vin=VIN))
check("wrong consent phrase is refused", msg is not None and "CLEAR ECM" in msg, str(msg))
check("nothing was sent to the car without consent", car.sent == [], str(car.sent))

# 2. refuses while moving
car = FakeCar(speed_kmh=30)
use(car)
msg = raises(Refused, lambda: ops.clear_module_dtcs("ECM", "CLEAR ECM", vin=VIN))
check("moving car is refused", msg is not None and "moving" in msg, str(msg))
check("no clear request sent while moving", "14FFFFFF" not in car.sent)

# 3. a good clear: evidence first, acknowledged, immediate return flagged
car = FakeCar()
use(car)
out = ops.clear_module_dtcs("ECM", "CLEAR ECM", vin=VIN)
check("clear acknowledged", out.get("acknowledged") is True, str(out))
check("cleared reported", out.get("cleared") is True, str(out))
check("active codes before are recorded", out.get("active_before") == ["P0455-00", "P0456-00"],
      str(out.get("active_before")))
check("a code back within seconds is flagged as live", out.get("returned_immediately") == ["P0455-00"],
      str(out.get("returned_immediately")))
ev = Path(out.get("evidence_file", ""))
check("evidence file written in the state dir", ev.exists() and str(ev).startswith(_TMP), str(ev))
if ev.exists():
    data = json.loads(ev.read_text(encoding="utf-8"))
    check("evidence holds all tracked records", len(data.get("records", [])) == 3, str(len(data.get("records", []))))
    check("evidence holds the vehicle speed", data.get("vehicle_speed_kmh") == 0.0)
    check("evidence holds the result after the clear", data.get("result", {}).get("acknowledged") is True)
order = [c for c in car.sent if c in ("1902FF", "14FFFFFF")]
check("codes were read before the clear request",
      "14FFFFFF" in order and order.index("1902FF") < order.index("14FFFFFF"), str(order))
check("codes were read back after the clear request",
      order[-1] == "1902FF" and order.index("14FFFFFF") < len(order) - 1, str(order))
obs = [o for o in store.recent_observations(50, kind="clear_evidence")]
check("clear evidence recorded as an observation from the car",
      bool(obs) and store.is_from_car(obs[-1]), str(obs[-1] if obs else None))

# 4. a module refusing the clear (security gateway) is reported, not claimed
car = FakeCar(clear_reply="7F1433")
use(car)
out = ops.clear_module_dtcs("ECM", "CLEAR ECM", vin=VIN)
check("NRC 0x33 is reported as a refusal", "securityAccessDenied" in (out.get("refused_by_module") or ""),
      str(out))
check("a refused clear is not reported as cleared", out.get("cleared") is False)

# 5. there is still no clear route over HTTP
from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402
paths = list(create_app().openapi().get("paths", {}))
check("no HTTP route can clear module codes",
      not any("clear" in p and "live" in p and "vehicle" not in p for p in paths),
      str([p for p in paths if "clear" in p]))

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
