"""Learn module DIDs by listening to MES over a second adapter.

With a Y-splitter fitted on CAN-C (pins 6/14), MES's own adapter still does
all the talking -- its UDS requests and the modules' responses are exactly
what this module listens for, through a SECOND adapter (another STN/vLinker
on its own COM port, or a USB-CAN interface) wired to the same splitter,
opened ``passive=True`` (receive-only, ``STCMM 0`` -- see
:func:`cuore.live.capture.listen`). Nothing here ever transmits a byte onto
the bus, and :func:`start` refuses outright unless the given port is a
genuinely different, second adapter from MES's own (see
:func:`_check_two_adapters`).

Pipeline, once a capture is stopped:

1. :func:`cuore.live.learn.uds_transactions` reassembles ISO-TP and pairs
   every ``0x22``/``0x62`` (and ``0x21``/``0x2A``, via
   :data:`cuore.live.learn.REQUEST_SERVICES`) request/response seen on the
   wire -- 29-bit ``18DAxxF1``/``18DAF1xx`` and the 11-bit pair alike.
2. :func:`cuore.live.learn.did_series` groups those into one time series per
   ``(target, DID)``.
3. :func:`align` fits each named column of the MES CSV recording (loaded
   through ``mes.csvlog``) against every ``(target, DID, byte offset, width,
   signedness)`` this session saw, by ordinary least squares over the whole
   session -- nearest-time-matched, never interpolated. A column only
   becomes a confident candidate at R² >= :data:`_MIN_R2` over
   >= :data:`_MIN_DISTINCT` distinct raw values; anything short of that is
   reported ``"no confident match"`` rather than guessed.

Accepting a candidate (:func:`accept`) saves it through
:mod:`cuore.live.learned` as a MES-learned entry (never a catalogue DID) and
hands back a ready :class:`~cuore.live.channels.Channel` via
:func:`cuore.live.learned.learned_mes_channels` for whoever wires the Live
board's registry (the same hand-off :func:`cuore.live.ui_store.
load_custom_channels` already uses for custom channels). Rejecting
(:func:`reject`) keeps the DID observed-but-unscaled, same posture as
:func:`cuore.live.learned.reject`.
"""

from __future__ import annotations

import bisect
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import audit
from . import capture as capture_mod
from . import interlock
from . import learn as learn_mod
from . import learned as learned_mod
from .addressing import MODULES
from .buses import CAN_C
from .config import mes_registry
from .errors import BadCommand, Refused
from .transport import link

#: One capture window inside the background thread's loop -- same posture as
#: ``cuore.live.buscapture._WINDOW_S``.
_WINDOW_S = 1.0
#: Safety cap on frames retained in memory.
_MAX_FRAMES = 20000

#: A column only becomes a confident candidate at this R² or better, over at
#: least this many distinct raw values -- a session with a sensor that never
#: moved (or a low-cardinality signal like a 9-position gear indicator) is
#: correctly reported "no confident match" rather than guessed.
_MIN_R2 = 0.98
_MIN_DISTINCT = 20

_LOCK = threading.Lock()
_STATE: Optional[dict[str, Any]] = None


# ===========================================================================
# the two-adapter guard
# ===========================================================================

def _comports() -> list[Any]:
    """Serial ports on this machine. A thin wrapper so tests can fake it
    without ever touching real hardware."""
    import serial.tools.list_ports
    return list(serial.tools.list_ports.comports())


def _mes_port() -> Optional[str]:
    """MES's own configured adapter port (``Interface 0 Port``), or ``None``.

    Same registry key :func:`cuore.live.ops.ports` reads for ``mes_port``.
    A thin wrapper, same reason as :func:`_comports`.
    """
    port = mes_registry().get("Interface 0 Port")
    return str(port).strip().upper() if port else None


_SECOND_ADAPTER_HINT = (
    "Learning module parameters from MES needs a Y-splitter on CAN-C (pins 6/14) "
    "plus a SECOND adapter (another STN/vLinker on its own COM port, or a USB-CAN "
    "interface) listening passively alongside MES's own adapter."
)


def _check_two_adapters(port: str) -> None:
    """Refuse before a thread ever starts: no port, a lone adapter, or the
    same port MES already holds. All three name exactly what is missing."""
    port = (port or "").strip()
    if not port:
        raise BadCommand(f"a port is required for the second adapter. {_SECOND_ADAPTER_HINT}")
    ports = _comports()
    if len(ports) < 2:
        raise Refused(
            f"only {len(ports)} serial port(s) detected on this machine. "
            f"{_SECOND_ADAPTER_HINT} Fit the splitter and the second adapter first.")
    mp = _mes_port()
    if mp and port.upper() == mp.upper():
        raise Refused(
            f"port {port!r} is MultiEcuScan's own adapter port ({mp}). The listener must be "
            f"a different, second adapter on its own port -- it never shares MES's adapter. "
            f"{_SECOND_ADAPTER_HINT}")


# ===========================================================================
# capture lifecycle: Start / Stop
# ===========================================================================

def _new_state(port: str, vin: str) -> dict[str, Any]:
    return {
        "port": port.strip().upper(), "vin": (vin or "").strip(), "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"), "finished_at": None,
        "stream": "", "frames": [], "error": None, "last_rate_hz": 0.0,
        "csv_name": None, "candidates": [], "aligned": False,
        "_t0": time.monotonic(), "_stop": threading.Event(), "_thread": None,
    }


def _run(port: str, state: dict[str, Any]) -> None:
    lk = link()
    session_start = time.monotonic()
    try:
        with lk.session("mes_learn", bus=CAN_C, port=port, passive=True,
                        allow_while_mes_connected=True) as sess:
            state["stream"] = sess.stream.describe
            while not state["_stop"].is_set():
                window_t0 = time.monotonic() - session_start
                cap = capture_mod.listen(sess, seconds=_WINDOW_S, max_frames=2000)
                err = cap.get("error")
                if err and err not in ("DATA ERROR", "STOPPED"):
                    state["error"] = err
                state["last_rate_hz"] = cap.get("rate_hz", 0.0)
                for f in cap.get("frames", []):
                    if len(state["frames"]) < _MAX_FRAMES:
                        state["frames"].append(
                            {"t": round(window_t0 + f["t"], 4), "id": f["id"], "data": f["data"]})
    except Exception as e:  # noqa: BLE001 -- the thread must never die silently
        state["error"] = str(e)
    finally:
        state["status"] = "stopped"
        state["finished_at"] = datetime.now().isoformat(timespec="seconds")


def start(port: str, vin: str = "") -> dict[str, Any]:
    """Start the passive listener on ``port`` -- a different, second adapter
    from MES's own (see :func:`_check_two_adapters`). Refuses if a session
    is already running."""
    global _STATE
    _check_two_adapters(port)
    with _LOCK:
        if _STATE is not None and _STATE["status"] == "running":
            raise Refused("a MES-learn capture is already running; stop it first")
        state = _new_state(port, vin)
        _STATE = state
    thread = threading.Thread(target=_run, args=(state["port"], state), daemon=True,
                              name="cuore-mes-learn")
    state["_thread"] = thread
    thread.start()
    audit.record("mes_learn_start", port=state["port"])
    return _public(state)


def _require_state() -> dict[str, Any]:
    if _STATE is None:
        raise BadCommand("no MES-learn session; start one first")
    return _STATE


def _public(state: dict[str, Any]) -> dict[str, Any]:
    elapsed = round(time.monotonic() - state["_t0"], 2)
    return {
        "port": state["port"], "status": state["status"], "started_at": state["started_at"],
        "finished_at": state["finished_at"], "elapsed_s": elapsed,
        "frame_count": len(state["frames"]), "rate_hz": state["last_rate_hz"],
        "error": state["error"], "csv": state["csv_name"], "aligned": state["aligned"],
        "candidate_count": len(state["candidates"]),
    }


def status() -> dict[str, Any]:
    return _public(_require_state())


def stop(csv: str = "") -> dict[str, Any]:
    """Stop the listener, then align every captured transaction against
    ``csv`` (an MES CSV recording -- an absolute path, or a bare filename
    resolved through ``mes.csvlog``'s own CSV roots). With no ``csv`` given,
    the newest CSV recording modified since this capture started is used, if
    one is found."""
    state = _require_state()
    state["_stop"].set()
    thread = state.get("_thread")
    if thread is not None:
        thread.join(timeout=5.0)
    if state["status"] != "stopped":
        state["status"] = "stopped"
        state["finished_at"] = datetime.now().isoformat(timespec="seconds")
    _align(state, csv)
    audit.record("mes_learn_stop", frame_count=len(state["frames"]),
                 candidates=len(state["candidates"]))
    return _public(state)


def _load_recording(csv: str, since_s: float) -> Optional[Any]:
    from .. import bootstrap  # noqa: F401 -- side effect: mes on sys.path
    from mes import csvlog  # noqa: E402

    name = (csv or "").strip()
    if name:
        p = Path(name)
        if p.is_absolute() and p.exists():
            return csvlog.load_csv(p)
        return csvlog.load_named(name)

    # No CSV given: fall back to the newest CSV recording modified since the
    # capture started -- never a recording that predates this session.
    from mes import paths as mes_paths  # noqa: E402
    newest, newest_mtime = None, -1.0
    for p in mes_paths.iter_csv_files():
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime >= since_s - 2.0 and mtime > newest_mtime:
            newest, newest_mtime = p, mtime
    return csvlog.load_csv(newest) if newest is not None else None


def _align(state: dict[str, Any], csv: str) -> None:
    rec = _load_recording(csv, state.get("_t0", 0.0))
    if rec is None:
        if not state["error"]:
            state["error"] = ("no MES CSV recording found to align against; pass csv= "
                              "explicitly or let MES finish writing its export first")
        return
    state["csv_name"] = rec.name
    today = datetime.now().strftime("%Y-%m-%d")
    fitted = align(state["frames"], rec)
    out: list[dict[str, Any]] = []
    for i, c in enumerate(fitted, start=1):
        c = dict(c)
        c["id"] = f"c{i}"
        c["review_status"] = "pending"
        if c["status"] == "candidate":
            c["source"] = f"learned from MES {rec.name} {today}, fit R² {round(c['r2'], 4)}"
        out.append(c)
    state["candidates"] = out
    state["aligned"] = True


def candidates() -> dict[str, Any]:
    state = _require_state()
    return {"csv": state["csv_name"], "aligned": state["aligned"],
           "candidates": [{k: v for k, v in c.items() if not k.startswith("_")}
                          for c in state["candidates"]]}


def _find_candidate(state: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for c in state["candidates"]:
        if c["id"] == candidate_id:
            return c
    raise BadCommand(f"unknown candidate id {candidate_id!r}")


def accept(candidate_id: str, vin: str, name: str) -> dict[str, Any]:
    """Accept a candidate: saves it through :mod:`cuore.live.learned` as a
    MES-learned, scaled DID mapping -- usable by the Live board as a named
    channel via :func:`cuore.live.learned.learned_mes_channels`."""
    if not (vin or "").strip():
        raise BadCommand("a VIN is required to save a learned DID mapping")
    if not (name or "").strip():
        raise BadCommand("a name is required for the learned DID mapping")
    state = _require_state()
    cand = _find_candidate(state, candidate_id)
    if cand.get("status") != "candidate":
        raise BadCommand(
            f"candidate {candidate_id!r} has no confident fit (R² >= {_MIN_R2} and "
            f">= {_MIN_DISTINCT} distinct values required); it cannot be accepted")
    entry = learned_mod.accept_mes(
        vin.strip(), cand["module"], cand["did"], name.strip(), cand["field"],
        scale=cand["scale"], offset=cand["offset"], unit=cand.get("unit") or "",
        r2=cand["r2"], source=cand["source"], evidence=cand.get("evidence"))
    cand["review_status"] = "accepted"
    audit.record("mes_learn_accept", vin=vin.strip(), module=cand["module"], did=cand["did"])
    return entry


def reject(candidate_id: str, vin: str, reason: str = "") -> dict[str, Any]:
    """Reject a candidate: kept as observed-but-unscaled, never guessed."""
    if not (vin or "").strip():
        raise BadCommand("a VIN is required to record a rejected MES-learn candidate")
    state = _require_state()
    cand = _find_candidate(state, candidate_id)
    module, did = cand.get("module") or "UNKNOWN", cand.get("did") or "0000"
    entry = learned_mod.reject_mes(vin.strip(), module, did, cand.get("field"), reason=reason)
    cand["review_status"] = "rejected"
    audit.record("mes_learn_reject", vin=vin.strip(), module=module, did=did)
    return entry


# ===========================================================================
# alignment: byte series -> MES CSV named columns
# ===========================================================================

def _decode(raw_bytes: list[str], offset: int, width: int, signed: bool) -> Optional[int]:
    if offset < 0 or offset + width > len(raw_bytes):
        return None
    val = 0
    for b in raw_bytes[offset:offset + width]:
        val = (val << 8) | int(b, 16)
    if signed:
        bits = width * 8
        if val >= (1 << (bits - 1)):
            val -= (1 << bits)
    return val


def _field_candidates(max_len: int) -> list[tuple[int, int, bool]]:
    out: list[tuple[int, int, bool]] = []
    for off in range(max_len):
        out.append((off, 1, False))
        out.append((off, 1, True))
    for off in range(max_len - 1):
        out.append((off, 2, False))
        out.append((off, 2, True))
    return out


def _nearest(times: list[float], values: list[float], t: float) -> Optional[float]:
    if not times:
        return None
    i = bisect.bisect_left(times, t)
    if i == 0:
        return values[0]
    if i == len(times):
        return values[-1]
    before, after = times[i - 1], times[i]
    return values[i - 1] if (t - before) <= (after - t) else values[i]


def _linreg(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, 0.0
    scale = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    offset = my - scale * mx
    ss_res = sum((y - (scale * x + offset)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    if ss_tot == 0:
        return scale, offset, 1.0 if ss_res == 0 else 0.0
    return scale, offset, 1 - ss_res / ss_tot


def _module_for_target(target_hex: str) -> str:
    try:
        t = int(target_hex, 16)
    except ValueError:
        return target_hex.upper()
    for m in MODULES:
        if m.target == t:
            return m.code
    return target_hex.upper()


def _width_name(width: int) -> str:
    return "byte" if width == 1 else "u16"


def align(frames: list[dict[str, Any]], recording: Any) -> list[dict[str, Any]]:
    """Fit every named numeric column of ``recording`` against every
    ``(target, DID, offset, width, signedness)`` seen in ``frames``.

    One entry per column (``Time``/``TAG`` excluded): ``status`` is either
    ``"candidate"`` (``>= _MIN_R2`` R² over ``>= _MIN_DISTINCT`` distinct raw
    values -- the best such fit across every module/DID this session saw) or
    ``"no confident match"``. Pure function: no I/O, no state.
    """
    tx = learn_mod.uds_transactions(frames)
    series = learn_mod.did_series(tx)
    results: list[dict[str, Any]] = []

    for col in recording.columns:
        if col.name.strip().lower() in ("time", "tag"):
            continue
        pairs = recording.numbers(col.name)
        if len(pairs) < _MIN_DISTINCT:
            results.append({
                "column": col.name, "unit": col.unit, "status": "no confident match",
                "best_r2": None,
                "reason": f"fewer than {_MIN_DISTINCT} numeric samples in the recording",
            })
            continue
        times = [t for t, _ in pairs]
        values = [v for _, v in pairs]

        best: Optional[dict[str, Any]] = None
        for (target, did), pts in series.items():
            if not pts:
                continue
            max_len = max(len(p["bytes"]) for p in pts)
            for off, width, signed in _field_candidates(max_len):
                triples: list[tuple[float, int, float]] = []
                for p in pts:
                    raw = _decode(p["bytes"], off, width, signed)
                    if raw is None:
                        continue
                    v = _nearest(times, values, p["t"])
                    if v is None:
                        continue
                    triples.append((p["t"], raw, v))
                xs = [r for _, r, _ in triples]
                distinct = len(set(xs))
                if distinct < _MIN_DISTINCT:
                    continue
                ys = [v for _, _, v in triples]
                scale, offset, r2 = _linreg(xs, ys)
                if best is None or r2 > best["r2"]:
                    best = {
                        "target": target, "did": did, "module": _module_for_target(target),
                        "field": {"offset": off, "width": _width_name(width), "signed": signed},
                        "scale": scale, "offset": offset, "r2": r2,
                        "n": len(xs), "distinct": distinct,
                        "evidence": [{"t": t, "raw": r, "value": v} for t, r, v in triples[:10]],
                    }

        if best is None:
            results.append({"column": col.name, "unit": col.unit,
                           "status": "no confident match", "best_r2": None})
        else:
            entry = {"column": col.name, "unit": col.unit, **best}
            entry["status"] = "candidate" if best["r2"] >= _MIN_R2 else "no confident match"
            results.append(entry)
    return results


__all__ = ["start", "stop", "status", "candidates", "accept", "reject", "align"]
