"""Checks for the live-data engine: channels, poller, alarms, recording, HTTP/SSE.

Same posture as ``check_live.py``/``check_coverage.py``: plain script,
``check(label, cond, detail)``, exit 1 on failure, a hand-written fake
``Stream`` instead of a mocking framework. Runs against a temporary state
directory so it never touches the bench's real evidence.

Run:
    .venv/Scripts/python.exe cuore/tests/check_live_data.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

# Before any cuore import: state must go to a throwaway directory.
_TMP = tempfile.mkdtemp(prefix="cuore-check-live-data-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "mes-log-mcp"))

from cuore.live import channels as channels_mod  # noqa: E402
from cuore.live import interlock, ops, store  # noqa: E402
from cuore.live import poller as poller_mod  # noqa: E402
from cuore.live import ui_store as ui_store_mod  # noqa: E402
from cuore.live.buses import CAN_C  # noqa: E402
from cuore.live.errors import BadCommand, LinkUnavailable, Refused  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402
from cuore.services.errors import BadRequest  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want) -> None:
    check(label, got == want, f"got {got!r} want {want!r}")


def raises(exc, fn) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running",
                                "label": None}


def wait_until(pred, timeout: float = 5.0, step: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(step)
    return pred()


# ===========================================================================
# fake adapter: legislated PIDs (single + multi), ATRV, one UDS DID
# ===========================================================================

def _encode_dtc(code: str) -> tuple[str, str]:
    """Inverse of :func:`cuore.live.obd.dtc_from_two_bytes`: ``"P0456" -> ("04", "56")``."""
    prefix_index = "PCBU".index(code[0])
    high = (prefix_index << 2) | int(code[1], 16)
    return f"{high:X}{code[2]}".upper(), code[3:5].upper()


def _frames(header: str, payload: str) -> str:
    """Single/multi-frame ISO-TP framing, as an STN prints it with headers on."""
    n = len(payload) // 2
    if n <= 7:
        return f"{header}{n:02X}{payload}"
    out = [f"{header}1{n:03X}{payload[:12]}"]
    rest, seq = payload[12:], 1
    while rest:
        out.append(f"{header}2{seq % 16:X}{rest[:14]}")
        rest, seq = rest[14:], seq + 1
    return "\r".join(out)


#: RPM 0x1F40/4 = 2000.0 rpm; speed 0x3C = 60 km/h; coolant 0x50-40 = 40 C;
#: framed with the 11-bit legislated header (7E8) and a real ISO-TP PCI byte,
#: exactly as an STN prints an ATH1 reply -- a bare "41 0C ..." with no
#: header/PCI is not what ``reassemble()`` expects and silently parses empty.
PID_REPLIES: dict[str, str] = {
    "010C": _frames("7E8", "410C1F40"),
    "010D": _frames("7E8", "410D3C"),
    "0105": _frames("7E8", "410550"),
    "010B": _frames("7E8", "410B64"),
    "0133": _frames("7E8", "413365"),
    "010C0D05": _frames("7E8", "410C1F40" + "410D3C" + "410550"),
}


class LiveFakeStream(Stream):
    """Answers legislated PIDs (single and the one multi-PID request this
    project's poller is expected to send), ATRV, and a UDS DID on TCM (0x18)."""

    def __init__(self, pid_replies: dict[str, str] | None = None) -> None:
        self.pid_replies = dict(pid_replies or PID_REPLIES)
        self.target: int | None = None
        self.sent: list[str] = []
        self.opens = 0
        self._buf = bytearray()
        self._open = False
        #: TCM DID 04FE (gearbox oil temp, "A-40"): byte 0x7D -> 85.0 C.
        self.did_nodes: dict[int, dict[str, str]] = {
            0x18: {"2204FE": _frames("18DAF118", "6204FE7D")},
        }
        #: Mode 03/07 DTC state -- mutable, so a test can change what the "car"
        #: reports mid-poll and check that "Monitor DTCs" notices the diff.
        self.stored_dtcs: set[str] = set()
        self.pending_dtcs: set[str] = set()

    def _dtc_reply(self, response_byte: str, codes: set[str]) -> str:
        ordered = sorted(codes)
        body = response_byte + f"{len(ordered):02X}"
        for code in ordered:
            a, b = _encode_dtc(code)
            body += a + b
        return _frames("7E8", body)

    def open(self) -> None:
        self.opens += 1
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def _reply(self, cmd: str) -> str:
        if cmd == "ATI":
            return "ELM327 v2.3"
        if cmd == "STI":
            return "STN1170 v4.3.2"
        if cmd == "ATRV":
            return "12.6V"
        if cmd.startswith("ATSH18DA") and len(cmd) == 12:
            self.target = int(cmd[8:10], 16)
            return "OK"
        if cmd.startswith(("AT", "ST")):
            return "OK"
        if cmd == "03":
            return self._dtc_reply("43", self.stored_dtcs)
        if cmd == "07":
            return self._dtc_reply("47", self.pending_dtcs)
        if cmd in self.pid_replies:
            return self.pid_replies[cmd]
        if cmd.startswith("22"):
            node = self.did_nodes.get(self.target if self.target is not None else -1, {})
            return node.get(cmd, "NO DATA")
        return "NO DATA"

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
        return "live-fake"


# ===========================================================================
# 1. channel registry and presets
# ===========================================================================

reg = channels_mod.registry()
check("registry includes the legislated PIDs", "engine_rpm" in reg and "vehicle_speed" in reg)
check("registry includes catalogued DIDs for every named module",
      all(any(c.module == m for c in reg.values()) for m in channels_mod.DID_MODULES),
      str(sorted({c.module for c in reg.values() if c.kind == "did"})))
check("registry includes the battery channel", "battery_voltage" in reg)
check("registry includes the computed boost channel", "boost" in reg)
check_eq("boost depends on MAP and baro", reg["boost"].depends_on,
         ("intake_map", "barometric_pressure"))
check("RFHUB tire DIDs expand into pressure/temp sub-channels",
      "rfhub_40b1_pressure" in reg and "rfhub_40b1_temp" in reg)
check_eq("ecm_195a (unverified boost DID) is present and unverified",
         reg["ecm_195a"].confidence, "unverified")

pr = channels_mod.presets()
for name in ("engine_basics", "boost", "evap_job", "transmission", "tpms"):
    check(f"preset {name!r} is non-empty", bool(pr.get(name)), str(pr.get(name)))
check_eq("tpms preset has all four wheels x2 fields", len(pr["tpms"]), 8)

resolved = channels_mod.resolve_channels(preset="boost")
check("resolving the boost preset pulls in its computed dependencies",
      {"intake_map", "barometric_pressure"} <= {c.id for c in resolved},
      str([c.id for c in resolved]))
check("unknown channel id raises BadCommand",
      raises(BadCommand, lambda: channels_mod.by_id("no_such_channel")))
check("unknown preset raises BadCommand",
      raises(BadCommand, lambda: channels_mod.resolve_channels(preset="no_such_preset")))
check("no channels and no preset raises BadCommand",
      raises(BadCommand, lambda: channels_mod.resolve_channels()))


# ===========================================================================
# 2. computed-channel math (safe evaluator, no eval())
# ===========================================================================

check_eq("boost = MAP - baro", channels_mod.eval_expr(
    "intake_map - barometric_pressure", {"intake_map": 100.0, "barometric_pressure": 101.0}),
    -1.0)
check_eq("parentheses and precedence", channels_mod.eval_expr(
    "(a + b) * 2", {"a": 1.0, "b": 2.0}), 6.0)
check("missing dependency raises ComputedError",
      raises(channels_mod.ComputedError,
            lambda: channels_mod.eval_expr("missing_channel * 2", {})))
check("a stray character raises ComputedError",
      raises(channels_mod.ComputedError, lambda: channels_mod.eval_expr("a & b", {"a": 1, "b": 1})))
check("no eval() is reachable: 'import' is just an unresolved identifier",
      raises(channels_mod.ComputedError,
            lambda: channels_mod.eval_expr("__import__('os')", {})))


# ===========================================================================
# 3 & 4. multi-PID batching, single-PID fallback, DID reads, the poller
# ===========================================================================

fake1 = LiveFakeStream()
lk1 = AdapterLink(stream_factory=lambda p, b: fake1, process="check_live_data")
set_link(lk1)
lk1.mark_verified(CAN_C, 10)

p = poller_mod.LivePoller()
poller_mod.set_poller(p)

chans = channels_mod.resolve_channels(["engine_rpm", "vehicle_speed", "engine_coolant_temp",
                                       "tcm_04fe"])
started = p.start(chans, rates={"engine_rpm": 5.0, "vehicle_speed": 5.0,
                                "engine_coolant_temp": 0.5, "tcm_04fe": 1.0})
check("session start reports active", started.get("active") is True, str(started))

check("the first poll tick sent the 3-way multi-PID request",
      wait_until(lambda: "010C0D05" in fake1.sent), str(fake1.sent[:10]))

snap = wait_until(lambda: p.snapshot()["channels"]["engine_rpm"]["value"] is not None)
check("engine_rpm decoded from the multi-PID reply", snap)
s = p.snapshot()["channels"]
check_eq("engine_rpm value", s["engine_rpm"]["value"], 2000.0)
check_eq("vehicle_speed value", s["vehicle_speed"]["value"], 60.0)
check_eq("engine_coolant_temp value", s["engine_coolant_temp"]["value"], 40.0)

check("DID mode grouped under one retarget to TCM (0x18)",
      wait_until(lambda: "2204FE" in fake1.sent), str(fake1.sent))
tcm_snap = wait_until(lambda: p.snapshot()["channels"]["tcm_04fe"]["value"] is not None)
check("tcm_04fe (gearbox oil temp) decoded", tcm_snap)
check_eq("tcm_04fe value (0x7D - 40)", p.snapshot()["channels"]["tcm_04fe"]["value"], 85.0)

check_eq("multi-PID stays supported when the ECU answers every PID asked",
         p.status()["multi_pid_supported"], True)
check("the session held one port open (opens==1) despite many poll ticks",
      wait_until(lambda: fake1.opens == 1) and fake1.opens == 1, str(fake1.opens))

p.stop()
check("stop releases the adapter lock", interlock.read_lock() is None, str(interlock.read_lock()))
check("stop leaves the link with no current session", lk1.current is None)

# -- fallback: an ECU that only answers part of a multi-PID request ---------

partial_replies = dict(PID_REPLIES)
# Coolant missing from the multi reply -- only two of the three groups answered.
partial_replies["010C0D05"] = _frames("7E8", "410C1F40" + "410D3C")
fake2 = LiveFakeStream(partial_replies)
lk2 = AdapterLink(stream_factory=lambda p, b: fake2, process="check_live_data")
set_link(lk2)
lk2.mark_verified(CAN_C, 10)

p2 = poller_mod.LivePoller()
poller_mod.set_poller(p2)
chans2 = channels_mod.resolve_channels(["engine_rpm", "vehicle_speed", "engine_coolant_temp"])
p2.start(chans2, rates={"engine_rpm": 5.0, "vehicle_speed": 5.0, "engine_coolant_temp": 5.0})
check("the multi-PID request is tried once",
      wait_until(lambda: "010C0D05" in fake2.sent), str(fake2.sent[:10]))
check("an ECU answering fewer PIDs than asked turns multi-PID support off",
      wait_until(lambda: p2.status()["multi_pid_supported"] is False))
check("after falling back, coolant is polled as its own single-PID request",
      wait_until(lambda: "0105" in fake2.sent), str(fake2.sent))
check("coolant still eventually decodes via the single-PID fallback",
      wait_until(lambda: p2.snapshot()["channels"]["engine_coolant_temp"]["value"] == 40.0))
p2.stop()


# ===========================================================================
# 5. rate scheduling: a fast channel samples more often than a slow one
# ===========================================================================

fake3 = LiveFakeStream()
lk3 = AdapterLink(stream_factory=lambda p, b: fake3, process="check_live_data")
set_link(lk3)
lk3.mark_verified(CAN_C, 10)
p3 = poller_mod.LivePoller()
poller_mod.set_poller(p3)
chans3 = channels_mod.resolve_channels(["engine_rpm", "engine_coolant_temp"])
p3.start(chans3, rates={"engine_rpm": 5.0, "engine_coolant_temp": 0.5})
time.sleep(1.3)
st3 = p3.status()
fast_n = st3["achieved_hz"].get("engine_rpm", 0) * (st3["elapsed_s"] or 1)
slow_n = st3["achieved_hz"].get("engine_coolant_temp", 0) * (st3["elapsed_s"] or 1)
check("a 5 Hz channel is sampled noticeably more than a 0.5 Hz channel over 1.3s",
      fast_n > slow_n and fast_n >= 3, f"fast~{fast_n:.1f} slow~{slow_n:.1f}")
p3.stop()


# ===========================================================================
# 6. alarm with hysteresis fires once while sustained
# ===========================================================================

p4 = poller_mod.LivePoller()
ch = channels_mod.by_id("engine_coolant_temp")
p4._channels = {"engine_coolant_temp": ch}
p4._ring = {"engine_coolant_temp": deque(maxlen=100)}
p4._sample_counts = {"engine_coolant_temp": 0}
p4.set_alarm("engine_coolant_temp", warn=90.0, alarm=105.0, direction="above", hysteresis=5.0)

before = len(store.recent_observations(1000, kind="live_alarm"))
for v in (80.0, 95.0, 110.0, 108.0, 106.0, 102.0, 98.0, 80.0):
    p4._publish("engine_coolant_temp", v, "C")
events = store.recent_observations(1000, kind="live_alarm")[before:]
levels = [e["data"]["level"] for e in events]
check_eq("alarm-hysteresis transition sequence", levels, ["warn", "alarm", "warn"])
check_eq("the sustained alarm (110, 108, 106) fires exactly once",
         sum(1 for lv in levels if lv == "alarm"), 1)
check_eq("final state settles back to ok",
         p4.snapshot()["channels"]["engine_coolant_temp"]["alarm"], "ok")


# ===========================================================================
# 7. CSV recording readable by mes.csvlog
# ===========================================================================

from mes import csvlog  # noqa: E402

fake4 = LiveFakeStream()
lk4 = AdapterLink(stream_factory=lambda p, b: fake4, process="check_live_data")
set_link(lk4)
lk4.mark_verified(CAN_C, 10)
p5 = poller_mod.LivePoller()
poller_mod.set_poller(p5)
chans5 = channels_mod.resolve_channels(["engine_rpm", "vehicle_speed"])
p5.start(chans5, rates={"engine_rpm": 10.0, "vehicle_speed": 10.0})
rec_info = p5.start_recording()
check("recording reports a path under state_dir/recordings",
      "recordings" in rec_info["recording"], str(rec_info))
check("engine_rpm reaches the recorder before it is stopped",
      wait_until(lambda: p5.snapshot()["channels"]["engine_rpm"]["value"] is not None))
time.sleep(0.5)
stop_info = p5.stop_recording()
check("recording wrote at least one row", stop_info.get("rows", 0) > 0, str(stop_info))
p5.stop()

recording = csvlog.load_csv(Path(rec_info["recording"]))
check("mes.csvlog parses the recorded CSV", len(recording.times) > 0, str(recording.times[:5]))
names = [c.name for c in recording.columns]
check("recorded columns include the polled channels' names",
      "engine rpm" in names and "vehicle speed" in names, str(names))
rpm_col = recording.find_column("engine rpm")
numeric = recording.numbers("engine rpm")
check("the recorded engine rpm values decode to 2000",
      bool(numeric) and all(v == 2000.0 for _t, v in numeric), str(numeric[:5]))


# ===========================================================================
# 8. SSE stream yields events (bounded read)
# ===========================================================================
#
# httpx's ASGITransport (which FastAPI's own TestClient.stream() also uses in
# this environment) drains an ASGI response to completion before yielding
# anything to the caller -- confirmed against a minimal reproduction with a
# bare Starlette app and no cuore code involved. A route whose stream never
# ends (by design: it runs until the client disconnects) therefore hangs
# forever under that TestClient, regardless of the route's own correctness.
# The route is exercised two other ways instead: the route is confirmed
# registered on the real app, and the exact generator the route wraps
# (``ops.live_stream_events``, independent of FastAPI/ASGI) is read directly
# with a bound.

from cuore.api import live as live_api  # noqa: E402
from cuore.app import create_app  # noqa: E402

stream_route = next((r for r in live_api.router.routes if getattr(r, "path", None) == "/live/stream"),
                    None)
check("GET /live/stream is registered on the live router",
      bool(stream_route) and "GET" in getattr(stream_route, "methods", set()), str(stream_route))
create_app()  # still exercised: the app must build with the new routes present

fake5 = LiveFakeStream()
lk5 = AdapterLink(stream_factory=lambda p, b: fake5, process="check_live_data")
set_link(lk5)
lk5.mark_verified(CAN_C, 10)
p6 = poller_mod.LivePoller()
poller_mod.set_poller(p6)
chans6 = channels_mod.resolve_channels(["engine_rpm"])
p6.start(chans6, rates={"engine_rpm": 20.0})

wait_until(lambda: p6.snapshot()["channels"]["engine_rpm"]["value"] is not None)
events = list(ops.live_stream_events(max_messages=3))
check_eq("live_stream_events yields the number of messages asked for", len(events), 3)
check("every message is either a sample dict or a keepalive placeholder",
      all(e is None or {"t", "channel", "value", "unit"} <= set(e) for e in events), str(events))
check("a sample message names the polled channel",
      any(e and e["channel"] == "engine_rpm" for e in events), str(events))
check("the SSE route only unsubscribes once its generator is exhausted",
      len(p6._subscribers) == 0, str(p6._subscribers))

p6.stop()


# ===========================================================================
# 9. the poller-active guard refuses other live ops while it runs
# ===========================================================================

fake6 = LiveFakeStream()
lk6 = AdapterLink(stream_factory=lambda p, b: fake6, process="check_live_data")
set_link(lk6)
lk6.mark_verified(CAN_C, 10)
p7 = poller_mod.LivePoller()
poller_mod.set_poller(p7)
chans7 = channels_mod.resolve_channels(["engine_rpm"])
p7.start(chans7)

check("obd_pid is refused while a live-data session holds the adapter",
      raises(Refused, lambda: ops.obd_pid("0C")))
check("verify_bus is refused while a live-data session holds the adapter",
      raises(Refused, lambda: ops.verify_bus("can_c")))
check("starting a second session is refused",
      raises(Refused, lambda: p7.start(chans7)))

p7.stop()
check("after stop, ordinary ops are no longer refused for that reason",
      not raises(Refused, lambda: ops.obd_pid("0C")))
check("stop releases the adapter lock (again)", interlock.read_lock() is None)


# ===========================================================================
# 10. "Monitor DTCs": Mode 03/07 diffing, SSE dtc event, TAG row, observation
# ===========================================================================
#
# Driven directly through LivePoller._poll_dtcs on a manually-opened session
# rather than through the real background-thread scheduler, so the test does
# not have to wait out MIN_DTC_INTERVAL_S (5s minimum) twice over.

fake8 = LiveFakeStream()
lk8 = AdapterLink(stream_factory=lambda p, b: fake8, process="check_live_data")
set_link(lk8)
lk8.mark_verified(CAN_C, 10)

p8 = poller_mod.LivePoller()
poller_mod.set_poller(p8)
chans8 = channels_mod.resolve_channels(["engine_rpm"])
p8._channels = {c.id: c for c in chans8}
p8._pid_route = ops._obd_route()
p8._did_route = None
p8._mode = "did"   # _poll_dtcs must switch itself into "pid" mode

with lk8.session("check_dtc_monitor", bus=CAN_C) as sess8:
    sub8 = p8.subscribe()
    dtc_csv_path = Path(_TMP) / "dtc_monitor_test.csv"
    rec8 = poller_mod.CsvRecorder(dtc_csv_path, chans8)
    rec8.start()
    p8._recorder = rec8

    before_obs = len(store.recent_observations(1000, kind="live_dtc_change"))

    p8._poll_dtcs(sess8)   # cycle 1: empty baseline -- must not report a "change"
    check("the first Monitor-DTCs cycle only establishes a baseline", sub8.empty())
    check_eq("baseline dtc state is (empty, empty)", p8._dtc_state, (set(), set()))

    p8._poll_dtcs(sess8)   # cycle 2: no change -- still nothing published
    check("a cycle with no DTC change publishes nothing", sub8.empty())

    fake8.pending_dtcs = {"P0456"}
    p8._poll_dtcs(sess8)   # cycle 3: a pending code sets
    check("a new pending code publishes a dtc SSE message", not sub8.empty())
    msg = sub8.get_nowait()
    check_eq("dtc message type", msg.get("type"), "dtc")
    check_eq("dtc message reports the added pending code", msg.get("added"), ["P0456 pending"])
    check_eq("dtc message reports no removed codes on a set", msg.get("removed"), [])
    check_eq("dtc message's stored list stays empty", msg.get("stored"), [])
    check_eq("dtc message's pending list names the new code", msg.get("pending"), ["P0456"])
    check("dtc message carries a numeric timestamp", isinstance(msg.get("t"), float), str(msg))

    check_eq("a live_dtc_change observation was recorded",
            len(store.recent_observations(1000, kind="live_dtc_change")), before_obs + 1)
    latest_obs = store.recent_observations(1000, kind="live_dtc_change")[-1]
    # The observation carries the session's own stream label, so a real
    # adapter session ("serial COM3@...") counts as evidence and this fake
    # session does not (fixed 2026-09-26: it was hardcoded to "serial").
    check_eq("the dtc observation carries the session's own stream label",
            latest_obs.get("stream"), fake8.describe)
    check("a fake-session dtc observation is NOT counted as real-car evidence",
          not store.is_from_car(latest_obs), str(latest_obs))
    check("a serial-stream dtc observation IS counted as real-car evidence",
          store.is_from_car({**latest_obs, "stream": "serial COM3@115200"}))

    fake8.pending_dtcs = set()
    p8._poll_dtcs(sess8)   # cycle 4: the code clears -- a "DTC-" transition
    check("a cleared code publishes a dtc SSE message", not sub8.empty())
    msg2 = sub8.get_nowait()
    check_eq("dtc message reports the removed pending code", msg2.get("removed"), ["P0456 pending"])
    check_eq("dtc message reports no added codes on a clear", msg2.get("added"), [])

    rec8.stop()

dtc_csv_text = dtc_csv_path.read_text(encoding="utf-8")
check("the TAG column recorded the DTC+ transition (MES convention)",
      "DTC+ P0456 pending" in dtc_csv_text, dtc_csv_text)
check("the TAG column recorded the DTC- transition (MES convention)",
      "DTC- P0456 pending" in dtc_csv_text, dtc_csv_text)


# ===========================================================================
# 11. safety: every request the poller ever sent is on the read-only allowlist
# ===========================================================================
#
# Mode 01 (PIDs), Mode 03/07 (DTCs) and UDS 0x22 (ReadDataByIdentifier) only --
# never Mode 04, never 0x14/0x2F/0x31/0x10. AT/ST-prefixed lines are the
# adapter's own local configuration (addressing, protocol, filters), not a
# request transmitted to a module, so they are not part of this allowlist.

def _is_allowed_poller_request(cmd: str) -> bool:
    if cmd.startswith(("AT", "ST")):
        return True
    return cmd[:2] in ("01", "03", "07") or cmd.startswith("22")


for _label, _sent in (("multi/single-PID + DID session", fake1.sent),
                      ("Monitor-DTCs session", fake8.sent)):
    _bad = [c for c in _sent if not _is_allowed_poller_request(c)]
    check(f"every request in the {_label} is Mode 01/03/07 or a UDS 0x22 read",
          not _bad, str(_bad))
    check(f"the {_label} actually exercised at least one real request", bool(_sent))


# ===========================================================================
# 12. custom channels: registry refresh (no restart) and real DID polling
# ===========================================================================

check("custom_trans_temp is not yet in the registry",
      "custom_trans_temp" not in channels_mod.registry())

ui_store_mod.save_custom_channels([
    {"id": "custom_trans_temp", "name": "Custom trans temp", "unit": "C", "kind": "did",
     "module": "TCM", "did": "04FE", "formula": "A-40"},
])
check("saving a custom channel refreshes the registry without a restart",
      "custom_trans_temp" in channels_mod.registry())
check_eq("the custom channel's confidence marks it user-defined",
        channels_mod.by_id("custom_trans_temp").confidence, "USER-DEFINED")

check("a custom DID channel on a non-can_c module (ABS, CAN-CH) is refused",
      raises(BadRequest, lambda: ui_store_mod.save_custom_channels([
          {"id": "custom_abs_bad", "name": "bad", "unit": "", "kind": "did",
           "module": "ABS", "did": "F190", "formula": "A"},
      ])))

fake9 = LiveFakeStream()
lk9 = AdapterLink(stream_factory=lambda p, b: fake9, process="check_live_data")
set_link(lk9)
lk9.mark_verified(CAN_C, 10)
p9 = poller_mod.LivePoller()
poller_mod.set_poller(p9)
chans9 = channels_mod.resolve_channels(["custom_trans_temp"])
p9.start(chans9, rates={"custom_trans_temp": 5.0})
check("the custom DID channel is polled for real and decoded via 0x22 + its formula",
      wait_until(lambda: p9.snapshot()["channels"]["custom_trans_temp"]["value"] == 85.0))
p9.stop()

# re-saving the same custom channel (an edit) must not collide with itself
r_resave = ui_store_mod.save_custom_channels([
    {"id": "custom_trans_temp", "name": "Custom trans temp (renamed)", "unit": "C",
     "kind": "did", "module": "TCM", "did": "04FE", "formula": "A-40"},
])
check_eq("re-saving (editing) an existing custom channel is not a collision",
        r_resave["channels"][0]["name"], "Custom trans temp (renamed)")


# ===========================================================================
# report
# ===========================================================================

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
