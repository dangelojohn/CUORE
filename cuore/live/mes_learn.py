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
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import audit
from . import capture as capture_mod
from . import interlock
from . import procedure_capture
from . import learn as learn_mod
from . import learned as learned_mod
from .addressing import MODULES
from .buses import CAN_C
from .config import mes_registry, state_dir
from .errors import BadCommand, Refused
from .transport import declared_rate, link

#: One capture window inside the background thread's loop -- same posture as
#: ``cuore.live.buscapture._WINDOW_S``.
_WINDOW_S = 1.0
#: Cap on frames kept IN MEMORY (a recent tail, for status). Every frame is
#: streamed to disk as it arrives, so the cap never loses data.
_MAX_FRAMES = 20000
#: The listener opens ONLY at this bus's confirmed bitrate.
_BUS = CAN_C

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

def _configured_rate() -> int:
    """The bitrate CUORE's bus table configures for CAN-C under the declared cable.
    Refuses anything but CAN-C's own confirmed rate (500000)."""
    if _BUS.key != "can_c" or _BUS.bitrate_confidence != "confirmed":
        raise Refused(f"{_BUS.key} bitrate is not confirmed; the listener will not open")
    rate = int(declared_rate(_BUS, link().cable))
    if rate != _BUS.bitrate:
        raise Refused(f"configured rate {rate} != confirmed {_BUS.bitrate} for {_BUS.key}; "
                      f"the listener opens only at the confirmed bitrate and refuses any other")
    return rate


def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "") or "unknown-vin"


def _capture_path(vin: str, stamp: str) -> Path:
    return state_dir() / "mes_learn" / _sanitize(vin) / f"{stamp}.jsonl"


def _header(state: dict[str, Any], stopped_at: Optional[str]) -> dict[str, Any]:
    return {"type": "header", "port": state["port"], "bitrate": state["bitrate"],
            "bus": _BUS.key, "mes_port": state["mes_port"], "vin": state["vin"],
            "started_at": state["started_at"], "stopped_at": stopped_at}


def _open_file(state: dict[str, Any]) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = _capture_path(state["vin"], stamp)
    n = 1
    while path.exists():  # never overwrite an earlier capture
        path = _capture_path(state["vin"], f"{stamp}-{n}")
        n += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    state["file"] = str(path)
    with path.open("w", encoding="utf-8") as fh:  # header first: a crash leaves a labelled file
        fh.write(json.dumps(_header(state, None)) + "\n")


def _record(state: dict[str, Any], frames: list[dict[str, Any]]) -> None:
    """Append frames to the capture file (flushed + fsynced: a crash keeps them)
    and to the bounded in-memory tail."""
    if not frames:
        return
    if state.get("file"):
        with open(state["file"], "a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps({"t": f["t"], "id": f["id"], "data": f["data"]}) + "\n"
                             for f in frames))
            fh.flush()
            os.fsync(fh.fileno())
    state["frame_count"] += len(frames)
    state["frames"].extend(frames)
    if len(state["frames"]) > _MAX_FRAMES:
        del state["frames"][:len(state["frames"]) - _MAX_FRAMES]


def load_capture(path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(header, frames) from a saved capture; tolerates a torn last line."""
    header: dict[str, Any] = {}
    frames: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") == "header":
                header = row
            elif "id" in row and "data" in row:
                frames.append(row)
    return header, frames


def _finalize_file(state: dict[str, Any]) -> None:
    """Rewrite the header with the stop time (streaming, atomic replace)."""
    path = state.get("file")
    if not path or not os.path.exists(path):
        return
    tmp = path + ".tmp"
    with open(path, encoding="utf-8") as src, open(tmp, "w", encoding="utf-8") as dst:
        next(src, None)
        dst.write(json.dumps(_header(state, state["finished_at"])) + "\n")
        for line in src:
            dst.write(line)
    os.replace(tmp, path)


def _new_state(port: str, vin: str, rate: int = 0) -> dict[str, Any]:
    return {
        "bitrate": rate, "mes_port": _mes_port(), "file": None, "review_file": None,
        "review": None, "verdict": None, "frame_count": 0,
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
            used = sess.route.bitrate_override or sess.bus.bitrate
            if int(used) != state["bitrate"]:  # belt and braces: never listen at another rate
                raise Refused(f"session opened at {used}, not the confirmed {state['bitrate']}")
            while not state["_stop"].is_set():
                window_t0 = time.monotonic() - session_start
                cap = capture_mod.listen(sess, seconds=_WINDOW_S, max_frames=2000)
                err = cap.get("error")
                if err and err not in ("DATA ERROR", "STOPPED"):
                    state["error"] = err
                state["last_rate_hz"] = cap.get("rate_hz", 0.0)
                _record(state, [{"t": round(window_t0 + f["t"], 4), "id": f["id"],
                                 "data": f["data"]} for f in cap.get("frames", [])])
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
    rate = _configured_rate()
    with _LOCK:
        if _STATE is not None and _STATE["status"] == "running":
            raise Refused("a MES-learn capture is already running; stop it first")
        state = _new_state(port, vin, rate)
        _open_file(state)
        _STATE = state
    thread = threading.Thread(target=_run, args=(state["port"], state), daemon=True,
                              name="cuore-mes-learn")
    state["_thread"] = thread
    thread.start()
    audit.record("mes_learn_start", port=state["port"], bitrate=rate, file=state["file"])
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
        "frame_count": state["frame_count"], "bitrate": state["bitrate"], "bus": _BUS.key,
        "file": state["file"], "review_file": state["review_file"], "review": state["review"],
        "verdict": state["verdict"],
        "rate_hz": state["last_rate_hz"],
        "error": state["error"], "csv": state["csv_name"], "aligned": state["aligned"],
        "candidate_count": len(state["candidates"]),
    }


def status() -> dict[str, Any]:
    return _public(_require_state())


def stop(csv: str = "", *, pre: Optional[dict[str, Any]] = None,
         post: Optional[dict[str, Any]] = None, name: str = "",
         max_seconds: Optional[float] = None, mes_function: str = "") -> dict[str, Any]:
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
    try:
        _finalize_file(state)
    except OSError as e:   # the frames are already on disk; do not lose the alignment over a header rewrite
        state["error"] = state["error"] or f"could not rewrite the capture header: {e}"
    frames = _all_frames(state)
    _align(state, csv, frames)
    _auto_review(state, frames, pre=pre, post=post, name=name, max_seconds=max_seconds,
                 mes_function=mes_function)
    audit.record("mes_learn_stop", frame_count=state["frame_count"], file=state["file"],
                 review_file=state["review_file"], candidates=len(state["candidates"]))
    return _public(state)


def _all_frames(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Every captured frame, from disk (memory holds only a tail)."""
    if state.get("file") and os.path.exists(state["file"]):
        return load_capture(state["file"])[1]
    return list(state["frames"])


def _auto_review(state: dict[str, Any], frames: list[dict[str, Any]], **gate_kw: Any) -> None:
    """Run procedure_capture.review + gate on the saved frames and store the report
    beside them. Read-only: nothing is replayed. The gate is fed the RECORDED
    bitrate, never a caller value."""
    rep = procedure_capture.review_frames(
        frames, path=state.get("file") or "", listen_bitrate=state["bitrate"], **gate_kw)
    state["review_file"] = rep.get("review_file")
    state["verdict"] = rep["verdict"]
    if rep.get("error"):
        state["review"] = {"error": f"review failed: {rep['error']}"}
    else:
        state["review"] = {"text": rep["text"], "gates": rep["gates"],
                           "recorded_bitrate": rep["recorded_bitrate"]}


def latest_review(vin: str = "") -> dict[str, Any]:
    """Newest stored review report for ``vin`` (read-only; survives restarts)."""
    base = state_dir() / "mes_learn"
    dirs = [base / _sanitize(vin)] if vin else [d for d in base.glob("*") if d.is_dir()]
    files = sorted((f for d in dirs for f in d.glob("*.review.json")), key=lambda f: f.name)
    if not files:
        return {"found": False, "message": "no MES-learn review stored yet"}
    rep = json.loads(files[-1].read_text(encoding="utf-8"))
    return {"found": True, "file": str(files[-1]), "text": rep.get("text"),
            "gates": rep.get("gates", []), "recorded_bitrate": rep.get("recorded_bitrate"),
            "capture_file": rep.get("capture_file"), "reviewed_at": rep.get("reviewed_at")}


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


def _align(state: dict[str, Any], csv: str, frames: list[dict[str, Any]]) -> None:
    rec = _load_recording(csv, state.get("_t0", 0.0))
    if rec is None:
        if not state["error"]:
            state["error"] = ("no MES CSV recording found to align against; pass csv= "
                              "explicitly or let MES finish writing its export first")
        return
    state["csv_name"] = rec.name
    today = datetime.now().strftime("%Y-%m-%d")
    fitted = align(frames, rec)
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


__all__ = ["start", "stop", "status", "candidates", "accept", "reject", "align",
           "latest_review", "load_capture"]
