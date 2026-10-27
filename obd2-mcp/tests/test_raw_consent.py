"""Consent gates on server.send_raw (vehicle writes) and server.clear_dtcs (Mode 04).

Plain script, fake adapter only (no COM port is ever opened). State goes to a temp dir.
Run: .venv/Scripts/python.exe -X utf8 obd2-mcp/tests/test_raw_consent.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-test-raw-consent-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "obd2-mcp"))

from cuore.live import interlock  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
import server  # noqa: E402

failures = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        failures.append(f"{label} -- {detail}")


class Fake(Stream):
    def __init__(self):
        self.sent, self._buf, self._open = [], bytearray(), False

    def open(self): self._open = True
    def close(self): self._open = False
    def is_open(self): return self._open
    @property
    def describe(self): return "serial COM99@115200 (fake)"

    def write(self, data):
        cmd = data.decode("ascii", "replace").strip()
        self.sent.append(cmd)
        if cmd.startswith("STP "):
            r = "OK"
        elif cmd in ("STM", "STMA"):
            r = "1E36000100112233\r1E36000B00112233"
        elif cmd == "0100":
            r = "7E806410098180001"
        elif cmd == "010D":
            r = "7E803410D00"
        elif cmd == "04":
            r = "7E80144"
        elif cmd.startswith(("AT", "ST")):
            r = "OK"
        else:
            r = "NO DATA"
        self._buf.extend(r.encode() + b"\r>")

    def read(self, n):
        c = bytes(self._buf[:max(n, 1)]); del self._buf[:max(n, 1)]; return c

    def reset_input_buffer(self): self._buf.clear()
    def in_waiting(self): return len(self._buf)


def fresh():
    car = Fake()
    lk = AdapterLink(stream_factory=lambda p, b: car, process="test_raw_consent")
    lk.auto_verify_seconds = 0.2
    set_link(lk)
    return car


def raw(cmd, **kw):
    return json.loads(server.send_raw(cmd, **kw))


FLAG = dict(i_understand_this_writes_to_the_vehicle=True)

print("send_raw vehicle writes")
car = fresh()
r = raw("2F123456", module="ECM", **FLAG)
check("write with flag but no consent is refused", "refused" in r and "SEND RAW 2F TO ECM" in r["refused"], str(r))
r = raw("2F123456", module="ECM", consent="yes", **FLAG)
check("wrong phrase is refused", "refused" in r, str(r))
r = raw("2F123456", module="ECM", consent="SEND RAW 11 TO ECM", **FLAG)
check("phrase for another service is refused", "refused" in r, str(r))
r = raw("2F123456", consent="SEND RAW 2F TO ", **FLAG)
check("no module is refused", "refused" in r, str(r))
r = raw("1101", module="ORC", consent="SEND RAW 11 TO ORC", **FLAG)
check("right phrase on blocked module (ORC) is refused", "refused" in r and "ORC" in r["refused"], str(r))
r = raw("1101", module="IPC", consent="SEND RAW 11 TO IPC", **FLAG)
check("right phrase on cluster (IPC) is refused", "refused" in r, str(r))
r = raw("2E123456", module="ECM", consent="SEND RAW 2E TO ECM", **FLAG)
check("blocked service stays blocked despite consent", "refused" in r, str(r))
r = raw("ATSH7E0", consent="x", **FLAG)
check("ATSH as a write is refused", "refused" in r, str(r))
r = raw("04", module="ECM", consent="SEND RAW 04 TO ECM", **FLAG)
check("Mode 04 via send_raw is refused (use clear_dtcs)", "refused" in r and "clear_dtcs" in r["refused"], str(r))
check("nothing reached the car on any refusal", car.sent == [], str(car.sent))
audit_txt = ""
for p in Path(_TMP).rglob("*"):
    if p.is_file() and "audit" in p.name.lower():
        audit_txt += p.read_text(encoding="utf-8", errors="replace")
check("refusals are audited with a reason", audit_txt.count("send_raw_refused") >= 8, audit_txt[-300:])

car = fresh()
r = raw("1101", module="ECM", consent="send raw 11 to ecm", **FLAG)
check("right phrase on allowed module proceeds on the fake", "refused" not in r and r.get("command") == "1101", str(r))
check("the request reached the fake", "1101" in car.sent, str(car.sent))

print("send_raw reads unaffected")
car = fresh()
r = raw("010D")
check("read via send_raw needs no consent", "refused" not in r and r.get("kind") == "read", str(r))
r = raw("ATRV")
check("adapter read still works", "refused" not in r, str(r))

print("clear_dtcs")
car = fresh()
r = json.loads(server.clear_dtcs(confirm=True))
check("no phrase is refused", "refused" in r and "CLEAR ALL EMISSIONS CODES" in r["refused"], str(r))
r = json.loads(server.clear_dtcs(confirm=True, consent="CLEAR ECM"))
check("wrong phrase is refused", "refused" in r, str(r))
r = json.loads(server.clear_dtcs(confirm=False, consent="CLEAR ALL EMISSIONS CODES"))
check("phrase without confirm is refused", "refused" in r, str(r))
check("no clear request sent on any refusal", "04" not in car.sent, str(car.sent))
car = fresh()
r = json.loads(server.clear_dtcs(confirm=True, consent="CLEAR ALL EMISSIONS CODES"))
check("phrase + confirm proceeds on the fake", "refused" not in r and "04" in car.sent, str(r))

print("\nALL PASS" if not failures else "\nFAILURES PRESENT")
for f in failures:
    print("  -", f)
sys.exit(1 if failures else 0)
