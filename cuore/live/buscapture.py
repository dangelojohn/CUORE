"""Bus capture and broadcast-signal learning on a declared bypass cable.

Two mechanic-facing flows, both built on the existing passive listen
(:func:`cuore.live.capture.listen`) and read-only by construction -- every
session this module opens is ``passive=True``, so nothing here ever
transmits a byte onto CAN-IHS or CAN-CH:

* **bus capture** -- Start/Stop a passive listen on one bus, watch the live
  frame rate and distinct-ID count while it runs, Stop, then Save to a CSV
  recording in the same wire format cuore's own live sessions already write
  (:class:`cuore.live.poller.CsvRecorder`), tagged with the bus, the
  declared cable and the time, and logged as a from-car observation (kind
  ``"bus_capture"``) so the Scans area can show it.
* **learn a signal** -- the identical Start/Stop capture, kept as raw
  frames so :func:`rank_changed_bytes` can rank every ``(CAN id, byte
  offset)`` by how much it changed during the window a mechanic held a
  named physical action (brake pedal, door, HVAC fan...). The mechanic
  names the best candidate and :func:`learn_accept` saves it through
  :mod:`cuore.live.learned` as a ``"broadcast"`` entry with
  ``scale="unknown"`` -- never a guessed scale.

Both refuse (:class:`Refused`) with no cable declared for the target bus,
or with the adapter held by the poller/MES -- :func:`cuore.live.transport.
AdapterLink.session`'s own interlock still applies once the background
thread opens the adapter, but the check here gives a clear refusal before
a thread is even started.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from . import capture as capture_mod
from . import interlock
from . import replay
from . import store
from .buses import BUSES, Bus, route_for
from .channels import Channel
from .errors import BadCommand, Refused
from .poller import CsvRecorder
from .transport import link

#: One capture window inside the background thread's loop. Short enough
#: that Stop takes effect within about a second, long enough not to thrash
#: the adapter's monitor start/interrupt cycle.
_WINDOW_S = 1.0
#: Safety cap on frames retained in memory / written to a recording. A
#: busy bus held open for minutes would otherwise grow without bound.
_MAX_FRAMES = 20000

_LOCK = threading.Lock()
#: One session per bus -- starting a second capture/learn on the same bus
#: while one is running is refused, not queued.
_SESSIONS: dict[str, dict[str, Any]] = {}


def _bus(key: str) -> Bus:
    b = BUSES.get((key or "").lower())
    if b is None:
        raise BadCommand(f"unknown bus {key!r}; one of {list(BUSES)}")
    return b


def _check_ready(bus: Bus) -> None:
    """Refuse before a thread starts: no cable, or the adapter is held."""
    lk = link()
    if route_for(bus, lk.cable) is None:
        raise Refused(
            f"no cable declared for {bus.key}: cable is {lk.cable!r}. Declare the bypass "
            f"cable that reaches {bus.key} first (set_cable).")
    held = interlock.blocked_by()
    if held:
        raise Refused(f"adapter is held: {held}")


def _new_state(bus: Bus, purpose: str, action: str = "") -> dict[str, Any]:
    return {
        "bus": bus.key, "purpose": purpose, "action": action, "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"), "finished_at": None,
        "cable": link().cable, "stream": "", "frames": [], "ids": Counter(),
        "last_rate_hz": 0.0, "error": None, "saved_path": None, "saved_name": None,
        "_t0": time.monotonic(), "_stop": threading.Event(), "_thread": None,
    }


def _run(bus: Bus, state: dict[str, Any]) -> None:
    lk = link()
    session_start = time.monotonic()
    try:
        with lk.session(f"bus_{state['purpose']}", bus=bus, passive=True) as sess:
            state["stream"] = sess.stream.describe
            while not state["_stop"].is_set():
                window_t0 = time.monotonic() - session_start
                cap = capture_mod.listen(sess, seconds=_WINDOW_S, max_frames=2000)
                err = cap.get("error")
                if err and err not in ("DATA ERROR", "STOPPED"):
                    state["error"] = err
                state["last_rate_hz"] = cap.get("rate_hz", 0.0)
                for f in cap.get("frames", []):
                    state["ids"][f["id"]] += 1
                    if len(state["frames"]) < _MAX_FRAMES:
                        state["frames"].append(
                            {"t": round(window_t0 + f["t"], 4), "id": f["id"], "data": f["data"]})
    except Exception as e:  # noqa: BLE001 -- the thread must never die silently
        state["error"] = str(e)
    finally:
        state["status"] = "stopped"
        state["finished_at"] = datetime.now().isoformat(timespec="seconds")


def _public(state: dict[str, Any]) -> dict[str, Any]:
    elapsed = round(time.monotonic() - state["_t0"], 2)
    frame_count = sum(state["ids"].values())
    return {
        "bus": state["bus"], "purpose": state["purpose"], "action": state["action"],
        "status": state["status"], "cable": state["cable"],
        "started_at": state["started_at"], "finished_at": state["finished_at"],
        "elapsed_s": elapsed, "frame_count": frame_count, "distinct_ids": len(state["ids"]),
        "ids": dict(state["ids"].most_common(20)),
        "rate_hz": round(frame_count / elapsed, 1) if elapsed > 0 else 0.0,
        "error": state["error"], "saved_path": state["saved_path"],
        "saved_name": state["saved_name"],
    }


def _start(bus_key: str, purpose: str, action: str = "") -> dict[str, Any]:
    b = _bus(bus_key)
    with _LOCK:
        existing = _SESSIONS.get(b.key)
        if existing is not None and existing["status"] == "running":
            raise Refused(f"a {existing['purpose']} session is already running on {b.key}; "
                          f"stop it first")
        _check_ready(b)
        state = _new_state(b, purpose, action)
        _SESSIONS[b.key] = state
    thread = threading.Thread(target=_run, args=(b, state), daemon=True,
                              name=f"cuore-buscapture-{b.key}")
    state["_thread"] = thread
    thread.start()
    return _public(state)


def _get(bus_key: str) -> dict[str, Any]:
    b = _bus(bus_key)
    state = _SESSIONS.get(b.key)
    if state is None:
        raise BadCommand(f"no capture/learn session on {b.key}; start one first")
    return state


def _stop(bus_key: str) -> dict[str, Any]:
    state = _get(bus_key)
    state["_stop"].set()
    thread = state.get("_thread")
    if thread is not None:
        thread.join(timeout=5.0)
    return _public(state)


# ===========================================================================
# bus capture: Start / Stop / Save
# ===========================================================================

def capture_start(bus: str) -> dict[str, Any]:
    """Start a passive capture on ``bus``. Refuses with no cable declared
    for that bus, the adapter held, or a session already running on it."""
    return _start(bus, "capture")


def capture_status(bus: str) -> dict[str, Any]:
    """Live frame rate and distinct-ID counts of a running (or just-stopped)
    capture."""
    return _public(_get(bus))


def capture_stop(bus: str) -> dict[str, Any]:
    """Stop a running capture; frames already read are kept for Save."""
    state = _stop(bus)
    return state


def capture_save(bus: str, vin: str = "") -> dict[str, Any]:
    """Write the stopped capture to a CSV recording and log a from-car
    ``"bus_capture"`` observation. A capture must be stopped first. Saving
    twice is a no-op that returns the same recording."""
    b = _bus(bus)
    state = _get(b.key)
    if state["status"] == "running":
        raise BadCommand("this capture is still running; stop it first")
    if state.get("saved_path"):
        out = _public(state)
        out["already_saved"] = True
        return out

    ids = sorted(state["ids"])
    channels = [Channel(id=f"raw_{h}", name=f"CAN {h}", unit="hex", kind="broadcast",
                        bus=b.key, confidence="raw_capture", default_rate_hz=0.0)
               for h in ids]
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"buscapture_{b.key}_{state['cable']}_{ts}.csv"
    path = replay.cuore_recordings_dir() / name
    rec = CsvRecorder(path, channels)
    rec.start()
    for f in sorted(state["frames"], key=lambda x: x["t"]):
        rec.update(f"raw_{f['id']}", f["data"])
        rec.write_row()
    rec.stop()

    state["saved_path"] = str(path)
    state["saved_name"] = name
    frame_count = sum(state["ids"].values())
    store.record_observation(
        "bus_capture",
        {"bus": b.key, "cable": state["cable"], "recording": name, "path": str(path),
         "frame_count": frame_count, "distinct_ids": len(state["ids"]),
         "ids": dict(state["ids"])},
        vin=vin, bus=b.key, cable=state["cable"], stream=state["stream"] or "")
    out = _public(state)
    out["already_saved"] = False
    return out


# ===========================================================================
# learn a signal: Start / Stop, then rank and accept
# ===========================================================================

def learn_start(bus: str, action: str) -> dict[str, Any]:
    """Start the same passive capture, tagged with the physical action the
    mechanic is about to perform (e.g. "press the brake pedal")."""
    if not (action or "").strip():
        raise BadCommand("an action description is required (what the mechanic is doing)")
    return _start(bus, "learn", action.strip())


def learn_status(bus: str) -> dict[str, Any]:
    return _public(_get(bus))


def rank_changed_bytes(frames: list[dict[str, Any]], top: int = 15) -> list[dict[str, Any]]:
    """Rank every ``(CAN id, byte offset)`` by how much it changed across
    ``frames`` -- no marks needed, because the whole Start-to-Stop window is
    "while the action was held". Scored by the number of distinct values
    seen (a byte that never changes scores 0 and is dropped); ties broken by
    more transitions first, since a clean step (idle -> pressed) has fewer
    distinct values than a noisy one but is still the signal. Ignores a
    CAN id's last byte beyond the shortest frame seen for it, so it is
    never scored past data every frame on that id actually carried.
    """
    by_id: dict[str, list[dict[str, Any]]] = {}
    for f in sorted(frames, key=lambda x: x["t"]):
        by_id.setdefault(f["id"], []).append(f)

    candidates: list[dict[str, Any]] = []
    for can_id, fs in by_id.items():
        min_len = min(len(f["data"]) // 2 for f in fs)
        for off in range(min_len):
            values = [int(f["data"][2 * off:2 * off + 2], 16) for f in fs]
            distinct = sorted(set(values))
            if len(distinct) < 2:
                continue
            transitions = sum(1 for a, b in zip(values, values[1:]) if a != b)
            candidates.append({
                "id": can_id, "offset": off, "width": "byte",
                "score": len(distinct), "transitions": transitions,
                "values_seen": distinct,
                "evidence": [{"t": f["t"], "raw": v} for f, v in zip(fs, values)][:20],
            })
    candidates.sort(key=lambda c: (c["score"], c["transitions"]))
    return candidates[:top]


def learn_stop(bus: str) -> dict[str, Any]:
    """Stop a running learn capture and rank the candidates it saw."""
    state = _stop(bus)
    full = _get(bus)
    candidates = rank_changed_bytes(full["frames"])
    out = _public(full)
    out["candidates"] = candidates
    return out


def learn_accept(vin: str, bus: str, can_id: str, offset: int, name: str) -> dict[str, Any]:
    """Name the ranked candidate and save it as a learned broadcast signal.

    ``scale`` is always ``"unknown"`` here (see :mod:`cuore.live.learned`):
    a raw byte's physical units are never guessed from one capture.
    """
    from . import learned as learned_mod
    if not (vin or "").strip():
        raise BadCommand("a VIN is required to save a learned signal")
    if not (name or "").strip():
        raise BadCommand("a name is required for the learned signal")
    b = _bus(bus)
    field = {"offset": int(offset), "width": "byte"}
    return learned_mod.accept_broadcast(vin.strip(), b.key, can_id, name.strip(), field)


# ===========================================================================
# per-bus presets and the cable header
# ===========================================================================

def preset_info(name: str, vin: str = "") -> dict[str, Any]:
    """One bus-capture preset's items, resolved against the catalogue and
    this VIN's learned broadcast signals. See :func:`cuore.live.channels.
    bus_capture_preset`."""
    from . import channels as channels_mod
    return channels_mod.bus_capture_preset(name, vin)


def preset_capture_start(name: str, vin: str = "") -> dict[str, Any]:
    """Start a bus capture scoped to one preset's bus. Refuses
    (:class:`Refused`) unless the preset's required cable is declared --
    before :func:`capture_start`'s own cable/interlock check even runs."""
    from . import channels as channels_mod
    spec = channels_mod.BUS_CAPTURE_PRESETS.get(name)
    if spec is None:
        raise BadCommand(f"unknown bus-capture preset {name!r}; one of "
                         f"{sorted(channels_mod.BUS_CAPTURE_PRESETS)}")
    lk = link()
    if lk.cable != spec["cable"]:
        raise Refused(
            f"preset {name!r} ({spec['name']}) needs cable {spec['cable']!r} declared; "
            f"the declared cable is {lk.cable!r}. Fit the cable and set_cable({spec['cable']!r}) "
            f"first.")
    return capture_start(spec["bus"])


def cable_header(vin: str = "") -> dict[str, Any]:
    """What the Live board's header shows: the declared cable, which buses
    it reaches, and which bus-capture presets it unlocks."""
    from . import channels as channels_mod
    lk = link()
    state = lk.cable_state()
    presets = []
    for pname, spec in channels_mod.BUS_CAPTURE_PRESETS.items():
        presets.append({"preset": pname, "name": spec["name"], "bus": spec["bus"],
                        "cable_required": spec["cable"], "enabled": lk.cable == spec["cable"]})
    return {**state, "presets": presets}


def set_cable(cable: str) -> dict[str, Any]:
    """Declare the fitted cable (or ``"none"``). Clears stale bus
    verifications when the cable actually changes -- see
    :meth:`cuore.live.transport.AdapterLink.set_cable`. Returns the same
    shape as :func:`cable_header` so a "Change cable" confirmation can list
    what the new declaration enables in one call."""
    link().set_cable(cable)
    return cable_header()


__all__ = ["capture_start", "capture_status", "capture_stop", "capture_save",
          "learn_start", "learn_status", "learn_stop", "learn_accept",
          "rank_changed_bytes", "preset_info", "preset_capture_start",
          "cable_header", "set_cable"]
