"""The live-data poller: one background thread, one adapter session, many channels.

:class:`LivePoller` owns exactly one :class:`~cuore.live.transport.Session`
for the whole run -- opened once in :meth:`LivePoller.start`'s worker thread
and held until :meth:`LivePoller.stop`. It round-robins the requested
channels at their configured rate, batching Mode 01 PIDs (up to 6 per
request) and grouping UDS DID reads per module, publishes every sample to
subscribers (the SSE route), keeps a per-channel ring buffer, evaluates
alarm thresholds with hysteresis, and can mirror the session to an MES-format
CSV recording.

Only read services (Mode 01, UDS 0x22, ``ATRV``) are ever sent -- nothing
here writes to the vehicle. A session refuses to start while MultiEcuScan is
connected (the ordinary interlock in :meth:`AdapterLink.session`); other live
operations refuse while a poll session is active (see the guard appended to
``ops.py``).
"""

from __future__ import annotations

import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import audit, store
from . import uds as uds_mod
from .buses import CAN_C, header_bits_for_protocol, route_for
from .channels import Channel, ComputedError, eval_expr
from .config import state_dir
from .errors import BadCommand, LinkUnavailable, Refused
from .obd import PIDS_BY_HEX, decode_pid
from .transport import Session, link

MIN_TICK = 0.02
DEFAULT_RING_MINUTES = 5.0
_MAX_MULTI_PID = 6


def _parse_multi_pid(data: list[str], pids: list[str]) -> dict[str, list[str]]:
    """Split a ``41 <pid> <data> 41 <pid> <data> ...`` payload by the PIDs asked.

    A multi-PID Mode 01 reply repeats the ``41`` response byte before each
    PID's own group. Stops at the first group that does not match the next
    PID asked -- the ECU answered fewer than requested, which is how a
    caller learns multi-PID does not fully work here and should fall back
    to single requests.
    """
    out: dict[str, list[str]] = {}
    i = 0
    for pid in pids:
        if i + 1 >= len(data) or data[i] != "41" or data[i + 1] != pid:
            break
        spec = PIDS_BY_HEX.get(pid)
        n = spec.n_bytes if spec else 1
        if i + 2 + n > len(data):
            break
        out[pid] = data[i + 2:i + 2 + n]
        i += 2 + n
    return out


# ===========================================================================
# alarms
# ===========================================================================

@dataclass
class AlarmSpec:
    channel_id: str
    warn: Optional[float] = None
    alarm: Optional[float] = None
    direction: str = "above"       # "above" | "below"
    hysteresis: float = 0.0

    def level_for(self, value: float, current: str) -> str:
        """The alarm level ``value`` implies, given the level it is already at.

        Crossing INTO a stricter level uses the raw threshold; leaving one
        requires clearing it by ``hysteresis`` first, so a value dithering
        right at the line does not re-fire on every sample.
        """
        sign = 1.0 if self.direction == "above" else -1.0
        v = sign * value
        alarm = None if self.alarm is None else sign * self.alarm
        warn = None if self.warn is None else sign * self.warn
        h = abs(self.hysteresis)

        def is_alarm() -> bool:
            if alarm is None:
                return False
            if v >= alarm:
                return True
            return current == "alarm" and v >= alarm - h

        def is_warn() -> bool:
            if warn is None:
                return False
            if v >= warn:
                return True
            return current in ("warn", "alarm") and v >= warn - h

        if is_alarm():
            return "alarm"
        if is_warn():
            return "warn"
        return "ok"

    def to_dict(self) -> dict[str, Any]:
        return {"channel": self.channel_id, "warn": self.warn, "alarm": self.alarm,
                "direction": self.direction, "hysteresis": self.hysteresis}


# ===========================================================================
# CSV recording, in the MES graph-CSV shape mes.csvlog parses
# ===========================================================================

class CsvRecorder:
    """Mirrors a live session to a CSV in the shape ``mes.csvlog.load_csv`` reads:
    ``Time`` first, ``TAG`` last, row 1 names, row 2 units, tab-separated."""

    def __init__(self, path: Path, channels: list[Channel]) -> None:
        self.path = path
        self.channels = channels
        self._fh = None
        self._last: dict[str, Any] = {}
        self._start: Optional[float] = None
        self._rows = 0

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8", newline="")
        names = ["Time"] + [c.name for c in self.channels] + ["TAG"]
        units = ["sec"] + [c.unit for c in self.channels] + [" "]
        self._fh.write("\t".join(f'"{n}"' for n in names) + "\n")
        self._fh.write("\t".join(f'"{u}"' for u in units) + "\n")
        self._fh.flush()
        self._start = time.monotonic()

    def update(self, channel_id: str, value: Any) -> None:
        self._last[channel_id] = value

    def write_row(self, tag: str = "") -> None:
        if self._fh is None or self._start is None:
            return
        t = time.monotonic() - self._start
        cells = [f"{t:.3f}"]
        for c in self.channels:
            v = self._last.get(c.id)
            if v is None:
                cells.append("")
            elif isinstance(v, float):
                cells.append(f"{v:.4f}")
            else:
                cells.append(str(v))
        cells.append(f'"{tag}"' if tag else '""')
        self._fh.write("\t".join(cells) + "\n")
        self._fh.flush()
        self._rows += 1

    def stop(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            finally:
                self._fh = None


# ===========================================================================
# the poller
# ===========================================================================

class LivePoller:
    """One process-wide live-data session. Create one; use :func:`poller`."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._channels: dict[str, Channel] = {}
        self._rates: dict[str, float] = {}
        self._ring_minutes = DEFAULT_RING_MINUTES
        self._ring: dict[str, deque] = {}
        self._last_value: dict[str, Any] = {}
        self._last_unit: dict[str, str] = {}
        self._sample_counts: dict[str, int] = {}
        self._subscribers: list[queue.Queue] = []
        self._alarms: dict[str, AlarmSpec] = {}
        self._alarm_level: dict[str, str] = {}
        self._started_at: Optional[float] = None
        self._error: Optional[str] = None
        self._recorder: Optional[CsvRecorder] = None
        self._pid_multi_ok = True
        self._opens = 0
        self._mode = "did"
        self._pid_route = None
        self._did_route = None
        self._holding = False

    # --- lifecycle -----------------------------------------------------

    def is_active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def holds_adapter(self) -> bool:
        """True only once the session is actually open and polling.

        Distinct from :meth:`is_active` (thread spawned) so the poller's own
        startup -- which opens its session through the ordinary
        :meth:`AdapterLink.session` path and may auto-verify the bus via
        ``ops.verify_bus`` -- is never refused by its own guard.
        """
        with self._lock:
            return self._holding

    def start(self, channels: list[Channel], rates: Optional[dict[str, float]] = None
             ) -> dict[str, Any]:
        with self._lock:
            if self.is_active():
                raise Refused("a live-data poll session is already running; stop it first")
            if not channels:
                raise BadCommand("no channels to poll")
            for c in channels:
                if c.bus != "can_c" and c.kind != "computed":
                    raise BadCommand(f"channel {c.id!r} is on bus {c.bus!r}; the live-data "
                                     f"poller currently serves can_c channels only")
            self._channels = {c.id: c for c in channels}
            self._rates = {c.id: max(0.05, float((rates or {}).get(c.id, c.default_rate_hz)))
                          for c in channels}
            self._ring = {c.id: deque(maxlen=self._ring_len(self._rates[c.id])) for c in channels}
            self._last_value = {}
            self._last_unit = {}
            self._sample_counts = {c.id: 0 for c in channels}
            self._alarm_level = {}
            self._error = None
            self._pid_multi_ok = True
            self._started_at = None
            self._mode = "did"
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="cuore-live-poller",
                                            daemon=True)
            self._thread.start()
        # Give the worker a moment to open the session so a refusal (MES
        # connected, no port, adapter fault) surfaces to this call rather
        # than only showing up later in status().
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            with self._lock:
                if self._started_at is not None or self._error is not None:
                    break
                if self._thread is None or not self._thread.is_alive():
                    break
            time.sleep(0.02)
        with self._lock:
            if self._error is not None:
                err, self._thread = self._error, None
                raise LinkUnavailable(err)
            return self._status_locked()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self.is_active():
                return {"stopped": False, "note": "no live-data session running"}
            self._stop_event.set()
            t = self._thread
        if t is not None:
            t.join(timeout=10)
        with self._lock:
            self._thread = None
            self._holding = False
            recorder, self._recorder = self._recorder, None
        if recorder is not None:
            recorder.stop()
        return {"stopped": True}

    def _ring_len(self, rate_hz: float) -> int:
        return max(60, int(rate_hz * 60 * self._ring_minutes))

    # --- status ----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict[str, Any]:
        active = self._thread is not None and self._thread.is_alive()
        elapsed = (time.monotonic() - self._started_at) if (self._started_at and active) else None
        achieved = {}
        if elapsed and elapsed > 0:
            achieved = {cid: round(n / elapsed, 3) for cid, n in self._sample_counts.items()}
        return {
            "active": active,
            "channels": [c.to_dict() for c in self._channels.values()],
            "rates_hz": dict(self._rates),
            "achieved_hz": achieved,
            "elapsed_s": round(elapsed, 1) if elapsed else None,
            "recording": str(self._recorder.path) if self._recorder else None,
            "error": self._error,
            "multi_pid_supported": self._pid_multi_ok,
            "alarms": {cid: a.to_dict() for cid, a in self._alarms.items()},
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            channels = {
                cid: {"value": self._last_value.get(cid), "unit": self._last_unit.get(cid, ""),
                     "alarm": self._alarm_level.get(cid, "ok")}
                for cid in self._channels
            }
            return {"active": self.is_active(), "channels": channels}

    # --- alarms ------------------------------------------------------------

    def set_alarm(self, channel_id: str, warn: Optional[float] = None,
                 alarm: Optional[float] = None, direction: str = "above",
                 hysteresis: float = 0.0) -> dict[str, Any]:
        if direction not in ("above", "below"):
            raise BadCommand("direction must be 'above' or 'below'")
        with self._lock:
            spec = AlarmSpec(channel_id, warn, alarm, direction, hysteresis)
            self._alarms[channel_id] = spec
            self._alarm_level.pop(channel_id, None)
            return spec.to_dict()

    def clear_alarm(self, channel_id: str) -> dict[str, Any]:
        with self._lock:
            self._alarms.pop(channel_id, None)
            self._alarm_level.pop(channel_id, None)
            return {"channel": channel_id, "cleared": True}

    # --- subscribers (SSE) -------------------------------------------------

    def subscribe(self) -> "queue.Queue[dict[str, Any]]":
        q: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=2000)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[dict[str, Any]]") -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _broadcast(self, msg: dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

    # --- recording -----------------------------------------------------

    def start_recording(self) -> dict[str, Any]:
        with self._lock:
            if not self.is_active():
                raise Refused("no live-data session running; start one first")
            if self._recorder is not None:
                return {"recording": str(self._recorder.path), "already_recording": True}
            d = state_dir() / "recordings"
            path = d / f"live_{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
            rec = CsvRecorder(path, list(self._channels.values()))
            rec.start()
            self._recorder = rec
            return {"recording": str(path)}

    def stop_recording(self) -> dict[str, Any]:
        with self._lock:
            rec, self._recorder = self._recorder, None
        if rec is None:
            return {"stopped": False, "note": "not recording"}
        rec.stop()
        return {"stopped": True, "path": str(rec.path), "rows": rec._rows}

    # --- the worker thread -----------------------------------------------

    def _run(self) -> None:
        from . import ops as ops_mod  # local: ops imports poller lazily; avoid a cycle at import time
        lk = link()
        try:
            did_route = route_for(CAN_C, lk.cable)
            pid_route = ops_mod._obd_route()
            if pid_route is None:
                raise LinkUnavailable("no 11-bit legislated route on can_c for cable "
                                      f"{lk.cable!r}; Mode 01 PIDs need it")
            self._pid_route, self._did_route = pid_route, did_route
            with lk.session("live_session", bus=CAN_C) as sess:
                self._opens += 1
                self._mode = "did"
                with self._lock:
                    self._started_at = time.monotonic()
                    self._holding = True
                try:
                    next_due = {cid: 0.0 for cid in self._channels}
                    while not self._stop_event.is_set():
                        now = time.monotonic()
                        due = [cid for cid, t in next_due.items() if t <= now]
                        if not due:
                            time.sleep(MIN_TICK)
                            continue
                        pid_due = [c for c in due if self._channels[c].kind == "pid"]
                        did_due = [c for c in due if self._channels[c].kind == "did"]
                        batt_due = [c for c in due if self._channels[c].kind == "battery"]
                        comp_due = [c for c in due if self._channels[c].kind == "computed"]
                        touched: set[str] = set()
                        if pid_due:
                            self._switch_mode(sess, "pid")
                            touched |= self._poll_pids(sess, pid_due)
                        if did_due:
                            self._switch_mode(sess, "did")
                            touched |= self._poll_dids(sess, did_due)
                        if batt_due:
                            touched |= self._poll_battery(sess, batt_due)
                        if comp_due:
                            touched |= self._poll_computed(comp_due)
                        later = time.monotonic()
                        for cid in due:
                            next_due[cid] = later + 1.0 / self._rates.get(cid, 1.0)
                        if touched:
                            with self._lock:
                                rec = self._recorder
                            if rec is not None:
                                rec.write_row()
                        time.sleep(MIN_TICK)
                finally:
                    with self._lock:
                        self._holding = False
        except Exception as e:  # noqa: BLE001 -- reported through status()/start()'s wait
            with self._lock:
                self._error = str(e)
                self._holding = False

    def _switch_mode(self, sess: Session, want: str) -> None:
        if self._mode == want:
            return
        route = self._pid_route if want == "pid" else self._did_route
        if route is None:
            raise LinkUnavailable(f"no route available for {want} mode")
        if not sess.link.is_stn:
            raise LinkUnavailable("live-data polling of both PIDs and DIDs needs an STN adapter")
        if sess.route.stn_protocol != route.stn_protocol:
            sess.cmd(f"STP {route.stn_protocol}", 2)
            if route.bitrate_override:
                sess.cmd(f"STPBR {route.bitrate_override}", 2)
            sess.route = route
            sess.header_bits = header_bits_for_protocol(route.stn_protocol)
            sess._target = None
        if want == "pid":
            sess.untarget()
        self._mode = want

    # --- per-kind polling ---------------------------------------------------

    def _poll_pids(self, sess: Session, due_ids: list[str]) -> set[str]:
        sess.untarget()
        # The up-to-6 cap only matters for a multi-PID batch; once multi-PID
        # is known unsupported every due channel is polled individually this
        # same tick, not just the first (each is its own request either way).
        ids = due_ids[:_MAX_MULTI_PID] if self._pid_multi_ok else due_ids
        pid_by_id: dict[str, str] = {cid: self._channels[cid].pid for cid in ids}
        pids = list(dict.fromkeys(pid_by_id.values()))
        touched: set[str] = set()
        if self._pid_multi_ok and len(pids) > 1:
            q = sess.query("01" + "".join(pids), "41")
            data = next(iter(q["ecus"].values()), None)
            if q["error"] or not data:
                self._pid_multi_ok = False
                return touched
            parsed = _parse_multi_pid(data, pids)
            if len(parsed) < len(pids):
                self._pid_multi_ok = False
            for cid in ids:
                pid = pid_by_id[cid]
                if pid in parsed:
                    self._record_pid(cid, pid, parsed[pid])
                    touched.add(cid)
        else:
            for cid in ids:
                pid = pid_by_id[cid]
                q = sess.query(f"01{pid}", "41")
                data = next(iter(q["ecus"].values()), None)
                if data and len(data) >= 2 and data[1] == pid:
                    self._record_pid(cid, pid, data[2:])
                    touched.add(cid)
        return touched

    def _record_pid(self, cid: str, pid: str, raw: list[str]) -> None:
        spec = PIDS_BY_HEX.get(pid)
        decoded = decode_pid(pid, spec, raw)
        if "value" in decoded:
            self._publish(cid, decoded["value"], decoded.get("unit", ""))

    def _poll_dids(self, sess: Session, due_ids: list[str]) -> set[str]:
        from .readall import FormulaError, eval_formula
        touched: set[str] = set()
        by_module: dict[str, list[str]] = {}
        for cid in due_ids:
            by_module.setdefault(self._channels[cid].module, []).append(cid)
        for module, cids in by_module.items():
            try:
                ecu = uds_mod.resolve_module(module)
            except BadCommand:
                continue
            sess.target(ecu)
            for cid in cids:
                ch = self._channels[cid]
                r = uds_mod.read_did(sess, ecu, ch.did, timeout=1.5)
                data = r.get("bytes")
                if r.get("error") or not data or not ch.formula:
                    continue
                try:
                    val = eval_formula(ch.formula, [int(b, 16) for b in data])
                except FormulaError:
                    continue
                if isinstance(val, dict):
                    val = val.get(ch.field)
                if val is None:
                    continue
                self._publish(cid, float(val), ch.unit)
                touched.add(cid)
        return touched

    def _poll_battery(self, sess: Session, due_ids: list[str]) -> set[str]:
        raw = sess.cmd("ATRV", 2)
        m = re.search(r"(\d+\.\d+)V", raw)
        touched: set[str] = set()
        if m:
            v = float(m.group(1))
            for cid in due_ids:
                self._publish(cid, v, "V")
                touched.add(cid)
        return touched

    def _poll_computed(self, due_ids: list[str]) -> set[str]:
        touched: set[str] = set()
        for cid in due_ids:
            ch = self._channels[cid]
            with self._lock:
                values = {dep: self._last_value.get(dep) for dep in ch.depends_on}
            if any(v is None for v in values.values()):
                continue
            try:
                val = eval_expr(ch.expr, values)
            except ComputedError:
                continue
            self._publish(cid, val, ch.unit)
            touched.add(cid)
        return touched

    # --- publish: ring buffer, alarms, subscribers, recorder --------------

    def _publish(self, cid: str, value: Any, unit: str) -> None:
        t = time.time()
        alarm_level: Optional[str] = None
        spec = self._alarms.get(cid)
        if spec is not None and value is not None:
            current = self._alarm_level.get(cid, "ok")
            new_level = spec.level_for(float(value), current)
            if new_level != current:
                self._alarm_level[cid] = new_level
                if new_level != "ok":
                    self._record_alarm_event(cid, new_level, value)
            if new_level != "ok":
                alarm_level = new_level
        with self._lock:
            self._last_value[cid] = value
            self._last_unit[cid] = unit
            self._sample_counts[cid] = self._sample_counts.get(cid, 0) + 1
            ring = self._ring.get(cid)
            if ring is not None:
                ring.append((t, value))
            if self._recorder is not None:
                self._recorder.update(cid, value)
        msg: dict[str, Any] = {"t": t, "channel": cid, "value": value, "unit": unit}
        if alarm_level:
            msg["alarm"] = alarm_level
        self._broadcast(msg)

    def _record_alarm_event(self, cid: str, level: str, value: Any) -> None:
        store.record_observation("live_alarm", {"channel": cid, "level": level, "value": value},
                                 stream="live_poller")
        audit.record("live_alarm", channel=cid, level=level, value=value)


_POLLER: Optional[LivePoller] = None
_POLLER_LOCK = threading.Lock()


def poller() -> LivePoller:
    """The process-wide live-data poller, created on first use."""
    global _POLLER
    with _POLLER_LOCK:
        if _POLLER is None:
            _POLLER = LivePoller()
        return _POLLER


def set_poller(new: LivePoller) -> None:
    """Replace the process-wide poller (tests only)."""
    global _POLLER
    with _POLLER_LOCK:
        _POLLER = new


__all__ = ["Channel", "AlarmSpec", "CsvRecorder", "LivePoller", "poller", "set_poller"]
