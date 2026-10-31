"""Checks for learning module DIDs by listening to MES over a second adapter.

Same posture as ``check_buscapture.py``/``check_learn.py``: plain script,
``check()``, exit 1 on failure, no pytest, no mocking framework. Nothing
here ever opens a real serial port -- a ``FakeBus`` stream answers STM/STP/
AT the way ``check_buscapture.py``'s does, and ``mes_learn._comports``/
``_mes_port`` are monkeypatched so the two-adapter guard never touches real
hardware either.

Checks:
  1. The two-adapter guard: refuses with no port, with only one adapter
     detected, and with the same port MES is configured to use; passes with
     a genuinely different second port.
  2. ``align()`` against a synthetic capture (two modules -- ECM target
     0x10, TCM target 0x18 -- three DIDs: a 2-byte signed temperature
     scaled 0.1 offset -40 on ECM, a 1-byte unrelated "decoy" byte also on
     ECM, and a 1-byte gear position on TCM) and a synthetic MES CSV with
     two named columns ("Oil temperature", "Gear position"): the
     temperature column finds the right module/DID/field/scale/offset at
     R² >= 0.98; the gear column (only 9 distinct raw values) is reported
     "no confident match", never guessed; the decoy DID never wins either
     column.
  3. The full ``start`` -> ``stop`` -> ``candidates`` -> ``accept``/
     ``reject`` lifecycle over a ``FakeBus``: never transmits anything but
     AT/ST adapter commands (and the blank monitor-interrupt byte); accept
     saves through ``cuore.live.learned`` with confidence
     ``SINGLE-SOURCE (learned)`` and makes a Live board channel via
     ``cuore.live.learned.learned_mes_channels`` whose formula reproduces
     the original physical values; reject keeps the DID unscaled; a
     candidate with no confident fit cannot be accepted.

Run:
    .venv/Scripts/python.exe cuore/tests/check_mes_learn.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-mes-learn-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cuore import bootstrap  # noqa: E402,F401 -- side effect: mes on sys.path
from cuore.live import interlock, learned, mes_learn  # noqa: E402
from cuore.live.errors import BadCommand, Refused  # noqa: E402
from cuore.live.readall import eval_formula  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

from mes import csvlog  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def frame(t: float, can_id: str, byte_list: list[str]) -> dict:
    return {"t": t, "id": can_id, "data": "".join(byte_list)}


def sf(byte_values: list[int]) -> list[str]:
    """Single-frame ISO-TP bytes: PCI 0N + N data bytes."""
    n = len(byte_values)
    assert n <= 7
    return [f"0{n:X}"] + [f"{v:02X}" for v in byte_values]


# ===========================================================================
# 1. the two-adapter guard
# ===========================================================================

mes_learn._comports = lambda: []
mes_learn._mes_port = lambda: None

try:
    mes_learn._check_two_adapters("")
    check("guard refuses an empty port", False)
except BadCommand as e:
    check("guard refuses an empty port", True)
    check("the refusal names the missing hardware", "Y-splitter" in str(e), str(e))

mes_learn._comports = lambda: ["COM5"]
try:
    mes_learn._check_two_adapters("COM5")
    check("guard refuses a lone adapter", False)
except Refused as e:
    check("guard refuses a lone adapter", True)
    check("the lone-adapter refusal names the missing hardware", "second adapter" in str(e), str(e))

mes_learn._comports = lambda: ["COM5", "COM3"]
mes_learn._mes_port = lambda: "COM5"
try:
    mes_learn._check_two_adapters("com5")  # case-insensitive
    check("guard refuses MES's own port", False)
except Refused as e:
    check("guard refuses MES's own port", True)
    check("the same-port refusal names MES", "MultiEcuScan" in str(e), str(e))

mes_learn._mes_port = lambda: "COM3"
try:
    mes_learn._check_two_adapters("COM5")
    check("guard passes a genuinely different second adapter", True)
except Exception as e:  # noqa: BLE001
    check("guard passes a genuinely different second adapter", False, str(e))


# ===========================================================================
# 2. align(): synthetic capture + synthetic MES CSV
# ===========================================================================

N = 25
RAW_TEMP = [-150 + 12 * i for i in range(N)]            # 25 distinct, spans negative/positive
PHYS_TEMP = [r * 0.1 - 40.0 for r in RAW_TEMP]
GEAR = [i % 9 for i in range(N)]                        # only 9 distinct raw values
DECOY = [(53 * i + 7) % 256 for i in range(N)]           # unrelated to either column

align_frames: list[dict] = []
for i in range(N):
    t0 = float(i)
    raw16 = RAW_TEMP[i] if RAW_TEMP[i] >= 0 else RAW_TEMP[i] + 65536
    hi, lo = (raw16 >> 8) & 0xFF, raw16 & 0xFF
    align_frames.append(frame(t0 + 0.00, "18DA10F1", sf([0x22, 0x11, 0x11])))
    align_frames.append(frame(t0 + 0.01, "18DAF110", sf([0x62, 0x11, 0x11, hi, lo])))
    align_frames.append(frame(t0 + 0.02, "18DA10F1", sf([0x22, 0x99, 0x99])))
    align_frames.append(frame(t0 + 0.03, "18DAF110", sf([0x62, 0x99, 0x99, DECOY[i]])))
    align_frames.append(frame(t0 + 0.04, "18DA18F1", sf([0x22, 0x22, 0x22])))
    align_frames.append(frame(t0 + 0.05, "18DAF118", sf([0x62, 0x22, 0x22, GEAR[i]])))

_csv_lines = ['"Time"\t"Oil temperature"\t"Gear position"\t"TAG"',
             '"sec"\t"degC"\t"gear"\t" "']
for i in range(N):
    _csv_lines.append(f'{float(i):.2f}\t{PHYS_TEMP[i]:.4f}\t{float(GEAR[i]):.1f}\t""')
_csv_path = Path(_TMP) / "mes_learn_fixture.csv"
_csv_path.write_text("\n".join(_csv_lines) + "\n", encoding="utf-8")

_rec = csvlog.load_csv(_csv_path)
_fitted = mes_learn.align(align_frames, _rec, bus="can_c")
check("align: one result per named column", len(_fitted) == 2, str(_fitted))
_by_col = {r["column"]: r for r in _fitted}

_temp = _by_col.get("Oil temperature", {})
check("temperature: status candidate", _temp.get("status") == "candidate", str(_temp))
check("temperature: module ECM", _temp.get("module") == "ECM", str(_temp))
check("temperature: did 1111", _temp.get("did") == "1111", str(_temp))
check("temperature: field is a signed u16 at offset 0",
     _temp.get("field") == {"offset": 0, "width": "u16", "signed": True}, str(_temp))
check("temperature: scale ~0.1", abs(_temp.get("scale", 0.0) - 0.1) < 1e-6, repr(_temp.get("scale")))
check("temperature: offset ~-40", abs(_temp.get("offset", 0.0) - (-40.0)) < 1e-6,
     repr(_temp.get("offset")))
check("temperature: r2 >= 0.98", _temp.get("r2", 0.0) >= 0.98, repr(_temp.get("r2")))
check("temperature: distinct >= 20", _temp.get("distinct", 0) >= 20, repr(_temp.get("distinct")))

_gear = _by_col.get("Gear position", {})
check("gear: no confident match (only 9 distinct raw values)",
     _gear.get("status") == "no confident match", str(_gear))
check("gear: its own true DID (2222, only 9 distinct values) is never reported confident",
     not (_gear.get("did") == "2222" and _gear.get("status") == "candidate"), str(_gear))

check("the decoy DID (9999) never wins a confident column",
     not any(r.get("status") == "candidate" and r.get("did") == "9999" for r in _fitted),
     str(_fitted))


# ===========================================================================
# 3. full lifecycle: Start -> Stop -> candidates -> accept/reject
# ===========================================================================

class FakeBus(Stream):
    """Same shape as ``check_buscapture.py``'s ``FakeBus``."""

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
    def describe(self) -> str: return "serial COM5@115200 (fake second adapter)"

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
        if cmd in ("STM", "STMA"):
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


_orig_mes_status = interlock.mes_status
interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}

mes_learn._WINDOW_S = 0.2
mes_learn._comports = lambda: ["COM5", "COM3"]
mes_learn._mes_port = lambda: "COM3"

_car = FakeBus(["0DE00"])
_lk = AdapterLink(stream_factory=lambda p, b: _car, process="check_mes_learn")
set_link(_lk)

_started = mes_learn.start("COM5", vin=VIN)
check("start reports running", _started["status"] == "running", str(_started))

try:
    mes_learn.start("COM5", vin=VIN)
    check("starting twice while running is refused", False)
except Refused:
    check("starting twice while running is refused", True)

time.sleep(0.5)  # let at least one capture window run

_state = mes_learn._STATE
_state["_stop"].set()
_state["_thread"].join(timeout=5.0)
check("the background thread stopped", _state["status"] == "stopped", str(_state["status"]))

_bad_cmds = [c for c in _car.sent if c and not c.upper().startswith(("AT", "ST"))]
check("mes_learn never transmits a non-AT/ST command", not _bad_cmds, str(_car.sent))
check("the session was opened passive (STCMM 0 sent)", "STCMM 0" in _car.sent, str(_car.sent))

# Inject the richer synthetic capture built in part 2 -- the thread has
# already fully stopped, so there is no race with this assignment.
_pre_count = _state["frame_count"]
mes_learn._record(_state, align_frames)  # streams to disk like the live thread does

_stopped = mes_learn.stop(csv=str(_csv_path))
check("stop reports stopped", _stopped["status"] == "stopped", str(_stopped))
check("stop aligned against the given csv", _stopped["aligned"] is True, str(_stopped))
check("stop reports the csv basename", _stopped["csv"] == _csv_path.name, str(_stopped))

# --- saved frames, header, automatic review, recorded bitrate ---------------
import json  # noqa: E402
from cuore.live import procedure_capture as _pc  # noqa: E402

_f = Path(_stopped["file"])
check("frames file is under <state dir>/mes_learn/<vin>/",
      _f.parent == Path(_TMP) / "mes_learn" / VIN and _f.suffix == ".jsonl", str(_f))
_hdr, _saved = mes_learn.load_capture(str(_f))
check("every frame is saved (incl. >_MAX_FRAMES-independent streaming)",
      len(_saved) >= len(align_frames) and _stopped["frame_count"] == _pre_count + len(align_frames),
      f"{len(_saved)} saved, status {_stopped['frame_count']}")
check("saved frames carry t/id/data", all({"t", "id", "data"} <= set(f) for f in _saved))
check("header: port, bitrate, bus, mes_port, start and stop time",
      _hdr.get("port") == "COM5" and _hdr.get("bitrate") == 500000 and _hdr.get("bus") == "can_c"
      and _hdr.get("mes_port") == "COM3" and _hdr.get("started_at") and _hdr.get("stopped_at"),
      str(_hdr))
check("status exposes file and recorded bitrate",
      _stopped["file"] == str(_f) and _stopped["bitrate"] == 500000, str(_stopped))
check("review report stored next to the frames",
      _stopped["review_file"] and Path(_stopped["review_file"]).parent == _f.parent
      and Path(_stopped["review_file"]).exists(), str(_stopped.get("review_file")))
_rv = json.loads(Path(_stopped["review_file"]).read_text(encoding="utf-8"))
check("stored review has text, modules and gates", _rv.get("text") and "gates" in _rv, str(_rv)[:200])
check("status carries the review", bool(_stopped["review"] and _stopped["review"].get("text")))
check("gate is fed the RECORDED rate, not a caller value (no bitrate-mismatch failure)",
      _rv["recorded_bitrate"] == 500000
      and not any("capture bitrate" in r for g in _rv["gates"] for r in g["reasons"]),
      str(_rv["gates"]))
check("stop returns a one-line verdict", str(_stopped.get("verdict", "")).startswith("replayable:"),
      str(_stopped.get("verdict")))
check("stored review carries the same verdict", _rv.get("verdict") == _stopped["verdict"])
print("VERDICT stop:", _stopped["verdict"])
_lr = mes_learn.latest_review(VIN)
check("latest_review reads the stored report", _lr["found"] and _lr["recorded_bitrate"] == 500000,
      str(_lr)[:200])
check("latest_review for an unknown VIN is a clean not-found",
      mes_learn.latest_review("NOSUCHVIN")["found"] is False)

# crash safety: frames written by _record survive without stop() ever running
_crash = {"port": "COM5", "bitrate": 500000, "mes_port": "COM3", "vin": "CRASHVIN",
          "started_at": "t0", "file": None, "frames": [], "frame_count": 0}
mes_learn._open_file(_crash)
mes_learn._record(_crash, [{"t": 0.1, "id": "18DA10F1", "data": "0322DE0000000000"}])
_h2, _f2 = mes_learn.load_capture(_crash["file"])
check("crash-safe: frames on disk before any stop", len(_f2) == 1 and _h2.get("stopped_at") is None)
with open(_crash["file"], "a", encoding="utf-8") as _fh:
    _fh.write('{"t": 0.2, "id": "18DA')  # torn last line from a crash
check("crash-safe: a torn last line is tolerated", len(mes_learn.load_capture(_crash["file"])[1]) == 1)
_big = [{"t": i / 1000, "id": "18DA10F1", "data": "0322DE0000000000"} for i in range(mes_learn._MAX_FRAMES + 500)]
_crash = dict(_crash, file=None, frames=[], frame_count=0)
mes_learn._open_file(_crash)
mes_learn._record(_crash, _big)
check("memory is bounded but disk keeps every frame",
      len(_crash["frames"]) == mes_learn._MAX_FRAMES
      and len(mes_learn.load_capture(_crash["file"])[1]) == len(_big))

# bitrate: refuse any rate but CAN-C's confirmed one
_orig_rate = mes_learn.declared_rate
mes_learn.declared_rate = lambda bus, cable: 125000
try:
    mes_learn._configured_rate()
    check("a non-confirmed configured rate is refused", False)
except Refused as e:
    check("a non-confirmed configured rate is refused", "confirmed" in str(e), str(e))
_s_before = mes_learn._STATE
try:
    mes_learn.start("COM5", vin=VIN)  # previous state stopped, so only the rate guard can refuse
    check("start refuses before opening at a wrong rate", False)
except Refused:
    check("start refuses before opening at a wrong rate", mes_learn._STATE is _s_before)
mes_learn.declared_rate = _orig_rate
check("configured rate for CAN-C is 500000", mes_learn._configured_rate() == 500000)

_cands = mes_learn.candidates()
check("candidates: two entries (one per named column)", len(_cands["candidates"]) == 2,
     str(_cands))
_by_col2 = {c["column"]: c for c in _cands["candidates"]}
_temp_cand = _by_col2["Oil temperature"]
_gear_cand = _by_col2["Gear position"]
check("candidates: temperature carries an id", bool(_temp_cand.get("id")), str(_temp_cand))
check("candidates: temperature carries the MES-learned source sentence",
     _temp_cand.get("source", "").startswith(f"learned from MES {_csv_path.name} "),
     str(_temp_cand))

# A candidate with no confident fit cannot be accepted.
try:
    mes_learn.accept(_gear_cand["id"], VIN, "gear")
    check("a no-confident-match candidate cannot be accepted", False)
except BadCommand:
    check("a no-confident-match candidate cannot be accepted", True)

# accept() validates vin/name.
try:
    mes_learn.accept(_temp_cand["id"], "", "trans fluid temp")
    check("accept requires a VIN", False)
except BadCommand:
    check("accept requires a VIN", True)
try:
    mes_learn.accept(_temp_cand["id"], VIN, "")
    check("accept requires a name", False)
except BadCommand:
    check("accept requires a name", True)

_entry = mes_learn.accept(_temp_cand["id"], VIN, "trans fluid temp")
check("accept: confidence stamped", _entry["confidence"] == learned.CONFIDENCE_MES, str(_entry))
check("accept: kind mes", _entry["kind"] == "mes", str(_entry))
check("accept: never overwrites a catalogue DID (kept in its own kind)",
     _entry.get("kind") == "mes" and _entry.get("confidence") != "confirmed")

_mes_entries = learned.learned_mes(VIN)
check("learned_mes: one accepted entry", len(_mes_entries.get(VIN, [])) == 1, str(_mes_entries))

# accept makes a Live board channel (via channels/learned).
_channels = learned.learned_mes_channels(VIN)
check("learned_mes_channels: exactly one channel", len(_channels) == 1, str(_channels))
_ch = _channels[0]
check("channel: kind did", _ch.kind == "did", str(_ch))
check("channel: confidence SINGLE-SOURCE (learned)", _ch.confidence == learned.CONFIDENCE_MES)
check("channel: module/DID carried through", _ch.module == "ECM" and _ch.did == 0x1111, str(_ch))

# The channel's formula, evaluated the same way the live poller evaluates any
# other kind="did" channel (cuore.live.readall.eval_formula), reproduces the
# original physical values from the raw bytes.
for k in (0, 12, 24):
    raw16 = RAW_TEMP[k] if RAW_TEMP[k] >= 0 else RAW_TEMP[k] + 65536
    data_bytes = [(raw16 >> 8) & 0xFF, raw16 & 0xFF]
    got = eval_formula(_ch.formula, data_bytes)
    check(f"channel formula reproduces sample {k}", abs(got - PHYS_TEMP[k]) < 1e-3,
         f"formula={_ch.formula!r} got={got} want={PHYS_TEMP[k]}")

# Re-accepting replaces, does not duplicate.
mes_learn.accept(_temp_cand["id"], VIN, "trans fluid temp (renamed)")
check("accept: replace not duplicate", len(learned.learned_mes(VIN)[VIN]) == 1,
     str(learned.learned_mes(VIN)))

# reject() works regardless of confidence and keeps the DID unscaled.
try:
    mes_learn.reject(_gear_cand["id"], "")
    check("reject requires a VIN", False)
except BadCommand:
    check("reject requires a VIN", True)

_rej = mes_learn.reject(_gear_cand["id"], VIN, reason="only 9 distinct values -- no confident fit")
check("reject: kind mes", _rej["kind"] == "mes", str(_rej))
check("reject: status rejected", _rej["status"] == "rejected", str(_rej))
check("reject: kept unscaled", _rej["scale"] == learned.UNSCALED, str(_rej))

_mes_entries2 = learned.learned_mes(VIN)
check("learned_mes: accepted + rejected both present", len(_mes_entries2[VIN]) == 2,
     str(_mes_entries2))
statuses = sorted(e["status"] for e in _mes_entries2[VIN])
check("learned_mes: one accepted one rejected", statuses == ["accepted", "rejected"], str(statuses))

interlock.mes_status = _orig_mes_status


# ===========================================================================
# 4. HTTP + page surface
# ===========================================================================

from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402

client = TestClient(create_app())

_page_resp = client.get(f"/v/{VIN}/learn-mes")
check("the learn-mes page responds 200", _page_resp.status_code == 200, str(_page_resp.status_code))
check("the learn-mes page renders the panel", 'id="lm-panel"' in _page_resp.text)

_rev_resp = client.get(f"/api/mes-learn/review?vin={VIN}")
check("GET /api/mes-learn/review returns the stored review",
      _rev_resp.status_code == 200 and _rev_resp.json().get("found") is True, _rev_resp.text[:200])
check("the learn-mes page shows the latest review", 'id="lm-review-text"' in _page_resp.text)

_status_resp = client.get("/api/mes-learn/status")
check("GET /api/mes-learn/status responds 200", _status_resp.status_code == 200,
     str(_status_resp.status_code))

_cand_resp = client.get("/api/mes-learn/candidates")
check("GET /api/mes-learn/candidates responds 200", _cand_resp.status_code == 200,
     str(_cand_resp.status_code))
check("GET /api/mes-learn/candidates returns the same two columns",
     len(_cand_resp.json().get("candidates", [])) == 2, str(_cand_resp.json()))


print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
