"""Checks for bus capture, learn-a-signal, and the per-bus presets built
from the blue A5 (CAN-IHS) and grey A6 (CAN-CH) bypass cables.

Same posture as ``check_actuate.py``/``check_learn.py``: plain script,
``check()``, exit 1 on failure, no pytest, no mocking framework. A
``FakeBus`` stream answers STM/STP/AT the way check_actuate.py's FakeECU
does, but with scripted broadcast frame lines instead of UDS replies.

Checks:
  1. ``rank_changed_bytes`` ranks a byte that flips during a synthetic
     capture above a byte that never changes.
  2. ``learn_accept`` saves a learned broadcast signal with scale
     "unknown", filed under kind "broadcast".
  3. ``bus_capture_preset("chassis_a6")`` contains only catalogue/learned
     items -- known wheel-speed/steering/yaw signals, brake pressure
     "unknown_did" -- and refuses to start without grey_a6 declared.
  4. Capture on can_ihs with blue_a5 declared: Start, Stop, Save writes a
     CSV recording and a from-car "bus_capture" observation.
  5. Capture is refused with no cable declared (cable "none").
  6. Live board renders the cable header and bus-capture panel; the learn
     page and the liveboard page both respond 200.

Run:
    .venv/Scripts/python.exe cuore/tests/check_buscapture.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-buscapture-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from cuore import bootstrap  # noqa: E402,F401 -- side effect: mes on sys.path
from cuore.live import buscapture, channels, learned, store  # noqa: E402
from cuore.live.errors import BadCommand, Refused  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def frame(t: float, can_id: str, data: str) -> dict:
    return {"t": t, "id": can_id, "data": data}


# ===========================================================================
# 1-2. rank_changed_bytes / learn_accept
# ===========================================================================

# Id "0DE" byte 0 flips 0x00 -> 0x01 partway through a 5-sample window;
# id "0EE" byte 0 is constant noise.
_frames = [
    frame(0.0, "0DE", "00"), frame(0.2, "0DE", "00"),
    frame(0.4, "0DE", "01"), frame(0.6, "0DE", "01"), frame(0.8, "0DE", "01"),
    frame(0.0, "0EE", "55"), frame(0.2, "0EE", "55"),
    frame(0.4, "0EE", "55"), frame(0.6, "0EE", "55"), frame(0.8, "0EE", "55"),
]
ranked = buscapture.rank_changed_bytes(_frames)
check("ranking finds exactly one changed (id, offset)", len(ranked) == 1, str(ranked))
check("the changed candidate is id 0DE offset 0",
      bool(ranked) and ranked[0]["id"] == "0DE" and ranked[0]["offset"] == 0, str(ranked))
check("the noise id (0EE) never appears", all(c["id"] != "0EE" for c in ranked), str(ranked))

_accepted = buscapture.learn_accept(VIN, "can_ch", "0DE", 0, "brake pedal switch")
check("learn_accept stamps kind broadcast", _accepted["kind"] == "broadcast", str(_accepted))
check("learn_accept stamps scale unknown", _accepted["scale"] == "unknown", str(_accepted))
check("learn_accept records the field offset", _accepted["field"]["offset"] == 0, str(_accepted))

_lb = learned.learned_broadcast(VIN, bus="can_ch")
check("learned_broadcast surfaces the accepted entry",
      len(_lb.get(VIN, [])) == 1 and _lb[VIN][0]["name"] == "brake pedal switch", str(_lb))

try:
    buscapture.learn_accept("", "can_ch", "0DE", 0, "x")
    check("learn_accept refuses an empty VIN", False)
except BadCommand:
    check("learn_accept refuses an empty VIN", True)


# ===========================================================================
# 3. chassis_a6 preset: catalogue-only, cable-gated
# ===========================================================================

_preset = channels.bus_capture_preset("chassis_a6", vin=VIN)
check("chassis_a6 needs grey_a6", _preset["cable_required"] == "grey_a6", str(_preset))
_by_label = {i["label"]: i for i in _preset["items"]}
for _label in ("Wheel speed FL", "Wheel speed FR", "Wheel speed RL", "Wheel speed RR",
              "Steering angle", "Yaw rate"):
    check(f"chassis_a6: {_label} is known from the catalogue",
          _by_label.get(_label, {}).get("status") == "known", str(_by_label.get(_label)))
check("chassis_a6: brake pressure has no catalogued DID -> unknown_did",
      _by_label.get("Brake pressure", {}).get("status") == "unknown_did",
      str(_by_label.get("Brake pressure")))
check("chassis_a6: the brake-pedal switch I just learned is not claimed as a wheel-speed "
     "item (learned entries only surface under their own exact label)",
     _by_label.get("Brake pressure", {}).get("status") != "learned")

try:
    channels.bus_capture_preset("not_a_real_preset")
    check("an unknown preset name is refused", False)
except BadCommand:
    check("an unknown preset name is refused", True)


# ===========================================================================
# Fake bus stream: STM returns scripted broadcast frame lines.
#
# Header width follows line parity (cuore.live.framing.parse_frames):
# an odd total length is an 11-bit, 3-char header. "0DE" + "00" is 5 chars
# (odd) -> header "0DE", one data byte "00".
# ===========================================================================

class FakeBus(Stream):
    def __init__(self, stm_replies: list[str]) -> None:
        self.stm_replies = stm_replies
        self._stm_i = 0
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
            return ""  # the monitor-interrupt byte: no reply needed, just the prompt
        if cmd == "ATI":
            return "ELM327 v2.3"
        if cmd == "STI":
            return "STN1170 v4.3.2"
        if cmd in ("AT@1", "STDI", "STMFR", "STSN"):
            return "?"
        if cmd == "ATRV":
            return "12.4V"
        if cmd == "STM":
            i = min(self._stm_i, len(self.stm_replies) - 1)
            self._stm_i += 1
            return self.stm_replies[i]
        return "OK"

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", errors="replace").strip()
        self.sent.append(cmd)
        reply = self._reply(cmd)
        self._buf.extend(reply.encode("ascii") + b"\r>")

    def read(self, n: int) -> bytes:
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:max(n, 1)]
        return chunk

    def reset_input_buffer(self) -> None: self._buf.clear()
    def in_waiting(self) -> int: return len(self._buf)


def use(car: FakeBus) -> AdapterLink:
    lk = AdapterLink(stream_factory=lambda p, b: car, process="check_buscapture")
    lk.auto_verify_seconds = 0.1
    set_link(lk)
    return lk


# capture.listen() clamps a window to a 0.2s floor regardless of what is
# asked for, so this is the shortest a window actually runs; sleeps below
# are sized in multiples of it.
buscapture._WINDOW_S = 0.2


# ===========================================================================
# 4. capture Start / Stop / Save on can_ihs with blue_a5 declared
# ===========================================================================

_car = FakeBus(["0DE00\r0EE55"])
_lk = use(_car)
_lk.set_cable("blue_a5")

_started = buscapture.capture_start("can_ihs")
check("capture starts running", _started["status"] == "running", str(_started))
time.sleep(0.5)
_status = buscapture.capture_status("can_ihs")
check("capture status shows frames while running", _status["frame_count"] > 0, str(_status))

_stopped = buscapture.capture_stop("can_ihs")
check("capture stops", _stopped["status"] == "stopped", str(_stopped))
check("capture saw both ids", _stopped["distinct_ids"] == 2, str(_stopped))

_before = len(store.recent_observations(n=1000, vin=VIN, kind="bus_capture"))
_saved = buscapture.capture_save("can_ihs", vin=VIN)
check("save reports a recording name", bool(_saved.get("saved_name")), str(_saved))
check("the recording file exists", Path(_saved["saved_path"]).exists(), str(_saved))
_obs = store.recent_observations(n=1000, vin=VIN, kind="bus_capture")
check("save logs exactly one new bus_capture observation", len(_obs) == _before + 1,
     f"before={_before} after={len(_obs)}")
_last_obs = _obs[-1]
check("the observation is from-car (serial stream)", store.is_from_car(_last_obs), str(_last_obs))
check("the observation carries the cable and recording path",
     _last_obs["data"]["cable"] == "blue_a5" and _last_obs["data"]["recording"] == _saved["saved_name"],
     str(_last_obs))

# Saving again is a no-op, not a second observation.
_saved2 = buscapture.capture_save("can_ihs", vin=VIN)
check("saving twice is a no-op", _saved2.get("already_saved") is True, str(_saved2))
check("saving twice does not add a second observation",
     len(store.recent_observations(n=1000, vin=VIN, kind="bus_capture")) == _before + 1)


# ===========================================================================
# 5. refused with no cable declared
# ===========================================================================

_car2 = FakeBus(["0DE00"])
_lk2 = use(_car2)
_lk2.set_cable("none")
try:
    # can_ch has no "none" route at all -- only the grey A6 bypass reaches
    # it (buses.py CAN_CH.routes); can_ihs still has a native MS-CAN route
    # with no cable fitted, so it is not the right bus for this refusal.
    buscapture.capture_start("can_ch")
    check("capture on can_ch with cable none is refused", False)
except Refused as e:
    check("capture on can_ch with cable none is refused", True)
    check("the refusal names the missing cable", "cable" in str(e).lower(), str(e))

try:
    buscapture.preset_capture_start("chassis_a6", vin=VIN)
    check("chassis_a6 preset refuses to start without grey_a6", False)
except Refused as e:
    check("chassis_a6 preset refuses to start without grey_a6", True)
    check("the preset refusal names grey_a6", "grey_a6" in str(e), str(e))


# ===========================================================================
# 6. learn flow end-to-end (Start -> Stop -> ranked candidates), via a
# capture whose STM reply changes partway through the window.
# ===========================================================================

_car3 = FakeBus(["0DE00", "0DE00", "0DE01", "0DE01", "0DE01", "0DE01"])
_lk3 = use(_car3)
_lk3.set_cable("grey_a6")

buscapture.learn_start("can_ch", "press the brake pedal")
time.sleep(1.3)  # several 0.2s windows, enough to see the STM reply flip
_learned_stop = buscapture.learn_stop("can_ch")
check("learn_stop returns candidates", len(_learned_stop.get("candidates", [])) >= 1,
     str(_learned_stop))
check("learn_stop's top candidate is id 0DE",
     _learned_stop["candidates"] and _learned_stop["candidates"][0]["id"] == "0DE",
     str(_learned_stop))


# ===========================================================================
# 7. cable header + web pages
# ===========================================================================

_header = buscapture.cable_header()
check("cable_header reports the declared cable", _header["cable"] == "grey_a6", str(_header))
check("cable_header lists both bus-capture presets",
     {p["preset"] for p in _header["presets"]} == {"chassis_a6", "body_a5"}, str(_header))

from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402

client = TestClient(create_app())

_lp = client.get(f"/v/{VIN}/learn")
check("the learn page responds 200", _lp.status_code == 200, str(_lp.status_code))
check("the learn page renders the panel", 'id="lrn-panel"' in _lp.text)
check("the learn page renders both learnable buses",
     'value="can_ihs"' in _lp.text and 'value="can_ch"' in _lp.text)

_bp = client.get(f"/v/{VIN}/liveboard")
check("the liveboard page responds 200", _bp.status_code == 200, str(_bp.status_code))
check("the liveboard page renders the cable header", 'id="bc-cable-header"' in _bp.text)
check("the liveboard page renders the bus-capture panel", 'id="bc-panel"' in _bp.text)

_cable_resp = client.get("/api/buscapture/cable")
check("GET /api/buscapture/cable responds 200", _cable_resp.status_code == 200,
     str(_cable_resp.status_code))


print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
