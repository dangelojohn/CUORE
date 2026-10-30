"""Checks for the wiTECH listen-only recording (cuore/live/witech_recording.py + /witech-recording).

Fakes only: no COM port is ever opened. Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_witech_recording.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-witech-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from cuore import bootstrap  # noqa: E402,F401
from cuore.live import buscapture, interlock, procedure_sources, store  # noqa: E402
from cuore.live import witech_recording as wr  # noqa: E402
from cuore.live.buses import BUSES, CAN_C, route_for  # noqa: E402
from cuore.live.errors import BadCommand, Refused  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, declared_rate, set_link  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


class FakeBus(Stream):
    def __init__(self, stm_reply: str) -> None:
        self.stm_reply = stm_reply
        self._buf = bytearray()
        self._open = False
        self.sent: list[str] = []

    def open(self) -> None: self._open = True
    def close(self) -> None: self._open = False
    def is_open(self) -> bool: return self._open

    @property
    def describe(self) -> str: return "serial COM99@115200 (fake bus)"

    def _reply(self, cmd: str) -> str:
        if not cmd:
            return ""
        if cmd == "ATI": return "ELM327 v2.3"
        if cmd == "STI": return "STN1170 v4.3.2"
        if cmd in ("AT@1", "STDI", "STMFR", "STSN"): return "?"
        if cmd == "ATRV": return "12.4V"
        if cmd in ("STM", "STMA"): return self.stm_reply
        return "OK"

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").strip()
        self.sent.append(cmd)
        self._buf.extend((self._reply(cmd)).encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:max(n, 1)]
        return chunk

    def reset_input_buffer(self) -> None: self._buf.clear()
    def in_waiting(self) -> int: return len(self._buf)


def use(car: FakeBus) -> AdapterLink:
    lk = AdapterLink(stream_factory=lambda p, b: car, process="check_witech")
    lk.auto_verify_seconds = 0.1
    set_link(lk)
    return lk


buscapture._WINDOW_S = 0.2

# The sample wiTECH exchange with the ECM (0x10) from tester F1, as raw frames.
REQ, RESP = "18DA10F1", "18DAF110"
SAMPLE = [
    (0.10, REQ, "021003"), (0.11, RESP, "025003"),
    (0.20, REQ, "022701"), (0.21, RESP, "066701AABBCCDD"),
    (0.30, REQ, "06270211223344"), (0.31, RESP, "026702"),
    (0.40, REQ, "0431010203"), (0.41, RESP, "0471010203"),
    (0.50, REQ, "032EF190"), (0.51, RESP, "037F2E33"),
]
FRAMES = [{"t": t, "id": i, "data": d} for t, i, d in SAMPLE]

# ===== 1. refusals =====================================================================
car = FakeBus("18DA10F1021003\r18DAF110025003")
lk = use(car)
for cable in ("none", "blue_a5", "grey_a6"):
    lk.set_cable(cable)
    try:
        wr.start("Oil service reset")
        check(f"can_c recording refused with cable {cable}", False)
    except Refused as e:
        check(f"can_c recording refused with cable {cable}", "witech_splitter" in str(e), str(e))
lk.set_cable("witech_splitter")
try:
    wr.start("   ")
    check("a function tag is required", False)
except BadCommand:
    check("a function tag is required", True)

check("splitter reaches can_c at 500000, no override",
      route_for(CAN_C, "witech_splitter") is not None
      and declared_rate(CAN_C, "witech_splitter") == 500000
      and CAN_C.bitrate_confidence == "confirmed"
      and route_for(CAN_C, "witech_splitter").bitrate_override is None)
check("splitter reaches no other bus",
      all(route_for(b, "witech_splitter") is None for k, b in BUSES.items() if k != "can_c"))
for other in ("can_ihs", "can_ch"):
    try:
        buscapture.capture_start(other)
        check(f"splitter does not open {other}", False)
    except Refused:
        check(f"splitter does not open {other}", True)
try:
    with lk.session("tx_attempt", bus=CAN_C, passive=False):
        pass
    check("a transmitting session is refused under the splitter", False)
except Refused:
    check("a transmitting session is refused under the splitter", True)

_real_blocked = interlock.blocked_by
interlock.blocked_by = lambda: "MES is running"
try:
    wr.start("Oil service reset")
    check("adapter held by MES/poller -> refused", False)
except Refused as e:
    check("adapter held by MES/poller -> refused", "held" in str(e), str(e))
interlock.blocked_by = _real_blocked

# ===== 2. record: passive, no transmit, saved ==========================================
modes: list = []
_orig_session = lk.session


def _spy(*a, **kw):
    modes.append(kw.get("passive"))
    kb = kw.get("bus")
    modes.append(kb.key if kb else None)
    return _orig_session(*a, **kw)


lk.session = _spy

st = wr.start("Oil service reset")
check("recording starts", st["status"] == "running", str(st))
time.sleep(0.6)
wr.stop()
saved = wr.save(VIN)
check("passive=True on can_c only", len(modes) >= 2 and modes[0] is True and modes[1] == "can_c", str(modes))
check("nothing hex-shaped was ever written to the adapter (no transmit)",
      not any(re.fullmatch(r"[0-9A-Fa-f]{4,}", c) for c in car.sent), str(car.sent))
check("no STCMM 1 (ACKing) mode", "STCMM 1" not in car.sent, str(car.sent))
check("saved with an id and CSV", Path(saved["saved_path"]).exists() and saved["id"].startswith("witech_"), str(saved))
rec = wr.load_recording(saved["id"])
check("raw frames JSON saved with the function tag",
      rec["function"] == "Oil service reset" and bool(rec["frames"]), str(rec)[:200])
check("recorded bitrate is CAN-C's 500000", rec["bitrate"] == 500000 and rec["cable"] == "witech_splitter")
obs = store.recent_observations(n=100, vin=VIN, kind="witech_recording")
check("a witech_recording observation was logged", len(obs) == 1, str(obs))
check("save twice is a no-op", wr.save(VIN).get("already_saved") is True)

# ===== 3. transcript ===================================================================
sample_rec = {"id": "witech_sample", "function": "Key learning", "bus": "can_c",
              "bitrate": 500000, "frames": FRAMES}
rows = wr.transcript(sample_rec)
check("5 exchanges decoded in time order",
      [r["service"] for r in rows] == ["10", "27", "27", "31", "2E"], str([r["service"] for r in rows]))
check("module resolved from addressing", all(r["module"] == "ECM" for r in rows), str(rows[:1]))
check("service names", rows[0]["service_name"] == "DiagnosticSessionControl"
      and rows[3]["service_name"] == "RoutineControl")
check("positive and negative responses", rows[0]["result"] == "positive" and rows[4]["result"] == "negative")
check("NRC name decoded", rows[4]["nrc"] == "33" and rows[4]["nrc_name"] == "securityAccessDenied", str(rows[4]))
check("request hex shown", rows[1]["request"] == "2701" and rows[2]["request"] == "270211223344", str(rows[1:3]))
check("every 0x27 exchange is flagged as an unlock",
      [bool(r["flag"]) for r in rows] == [False, True, True, False, False]
      and "does not give the algorithm" in rows[1]["flag"])

# ===== 4. draft procedure ==============================================================
(Path(_TMP) / "witech_recordings" / "witech_sample.json").write_text(json.dumps(sample_rec), encoding="utf-8")
drafts = wr.make_draft("witech_sample")
check("one draft for the one module", len(drafts) == 1, str(len(drafts)))
d = drafts[0]
files = list((Path(_TMP) / "procedure_drafts").glob("witech_sample__*.json"))
check("draft saved under <state>/procedure_drafts/", len(files) == 1, str(files))
check("source is witech_observed with recording and function",
      d["source"]["kind"] == "witech_observed" and d["source"]["recording"] == "witech_sample"
      and d["source"]["function"] == "Key learning", str(d["source"]))
check("status and acceptance", d["status"] == "draft from wiTECH recording"
      and d["accepted_by_owner"] is False and d["executable"] is False)
flags = [s["needs_algorithm"] for s in d["steps"]]
check("needs_algorithm from the first 0x27 on", flags == [False, True, True, True, True], str(flags))
check("gate result stored, and it does not pass",
      d["gate"]["passed"] is False and any("0x27" in x for x in d["gate"]["reasons"]), str(d["gate"]))
check("not written into cuore/data/procedures", not list(Path(procedure_sources.DATA_DIR).glob("witech*")))
check("not listed as a procedure", all(not p["name"].startswith("witech") for p in procedure_sources.list()))
try:
    procedure_sources.load(d["name"])
    loadable = True
except Exception:  # noqa: BLE001
    loadable = False
check("not loadable as an executable procedure", not loadable)

# ===== 5. web page, no write route =====================================================
from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402

app = create_app()
client = TestClient(app, follow_redirects=False)
r = client.get(f"/v/{VIN}/witech-recording")
check("page responds 200", r.status_code == 200, str(r.status_code))
for text in ("Dealer session checklist", "Key learning", "Battery registration", "Oil / service reset",
             "Paddle-shifter market", "Listen-only", "Oil service reset", "witech_sample",
             "does not give the algorithm"):
    check(f"page shows {text!r}", text in r.text)
adj = client.get(f"/v/{VIN}/adjustments")
check("Adjustments links to the page", f"/v/{VIN}/witech-recording" in adj.text)
lk.set_cable("none")
r2 = client.post(f"/v/{VIN}/witech-recording/start", data={"function": "x"})
check("start without splitter is a redirect carrying the refusal",
      r2.status_code == 303 and "kind=err" in r2.headers["location"], str(r2.headers))

from cuore.web import witech_routes  # noqa: E402

routes = [(sorted(rt.methods - {"HEAD"}), rt.path) for rt in witech_routes.router.routes]
posts = sorted(p for m, p in routes if "POST" in m)
check("only the four expected POST routes",
      posts == sorted(f"/v/{{vin}}/witech-recording/{s}" for s in ("declare-splitter", "start", "stop", "draft")),
      str(posts))
src = Path(wr.__file__).read_text(encoding="utf-8") + (ROOT / "cuore" / "web" / "witech_routes.py").read_text(encoding="utf-8")
check("no transmit/write code paths in the new modules",
      not re.search(r"run_actuator|send_raw|\.send\(|uds\.(request|write)|passive\s*=\s*False", src),
      "found a transmit-ish call")

if failures:
    print(f"FAILED {len(failures)}/{checks}")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print(f"OK {checks} checks")
