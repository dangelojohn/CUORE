"""Drive recordings: sample the RUNNING live session, store, graph, export.

Safety contract (read before changing anything):

* This module never opens an adapter, never builds a request, never touches
  a bus. It only reads the poller's in-memory last-value cache through
  ``cuore.live.ops.live_snapshot()`` / ``live_session_status()``. Those
  functions are cache reads; the poller keeps polling at the channels' own
  rates (and refuses to start while MultiEcuScan holds the adapter). A
  recording therefore adds zero bus traffic, and cannot exist without a live
  session: ``start`` refuses when none is running, and the sampler stops the
  moment the session does.
* Each sample is stamped with wall-clock time (MES's own FES logs carry no
  per-sample time).

Storage: ``<state dir>/recordings/<vin>/<id>.jsonl`` -- one header line, one
``row`` line per sample, one ``end`` line (reason + row count) when stopped.
The pre-existing flat ``recordings/*.csv`` files (poller / MES-format) are
untouched; this is a subdirectory per VIN.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_RATE_HZ = 2.0
MAX_RATE_HZ = 10.0
DEFAULT_MAX_S = 60 * 60
_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_lock = threading.RLock()
_active: Optional["_Rec"] = None


class RecordingError(Exception):
    """Refused or invalid; the message is shown to the mechanic as-is."""


# --- the only two touch points with the live layer (tests replace these) --------

def _status() -> dict[str, Any]:
    from ..live import ops
    return ops.live_session_status()


def _snapshot() -> dict[str, Any]:
    from ..live import ops
    return ops.live_snapshot()


def _state_dir() -> Path:
    from ..live.config import state_dir
    return Path(state_dir())


# --- paths -----------------------------------------------------------------------

def _check_vin(vin: str) -> str:
    if not _SAFE.match(vin or ""):
        raise RecordingError("bad VIN")
    return vin


def _check_id(rec_id: str) -> str:
    if not _SAFE.match(rec_id or ""):
        raise RecordingError("bad recording id")
    return rec_id


def _dir(vin: str) -> Path:
    return _state_dir() / "recordings" / _check_vin(vin)


def _slug(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", label or "").strip("-")[:24]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds")


# --- recording -------------------------------------------------------------------

class _Rec:
    def __init__(self, vin: str, rec_id: str, path: Path, channels: "list[str]", rate_hz: float,
                 max_s: float) -> None:
        self.vin, self.id, self.path = vin, rec_id, path
        self.channels, self.rate_hz, self.max_s = channels, rate_hz, max_s
        self.t0 = time.time()
        self.m0 = time.monotonic()
        self.rows = 0
        self.reason: Optional[str] = None
        self.stop_evt = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.fh: Any = None


def _write(rec: _Rec, obj: "dict[str, Any]") -> None:
    rec.fh.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    rec.fh.flush()


def _finish(rec: _Rec, reason: str) -> None:
    global _active
    with _lock:
        if rec.reason is not None:
            return
        rec.reason = reason
        try:
            _write(rec, {"type": "end", "reason": reason, "rows": rec.rows,
                         "duration_s": round(time.monotonic() - rec.m0, 3), "end": _iso(time.time())})
        except (OSError, ValueError):
            pass  # disk full / closed file: still release the recorder below
        finally:
            try:
                rec.fh.close()
            except OSError:
                pass
        if _active is rec:
            _active = None
        rec.stop_evt.set()


def sample_once(rec: _Rec) -> Optional[str]:
    """One sample from the live cache. Returns a stop reason, or None to go on."""
    try:
        if not _status().get("active"):
            return "session_stopped"
        snap = _snapshot()
    except Exception as e:  # noqa: BLE001 -- any failure ends the recording, honestly
        return f"error: {type(e).__name__}: {e}"[:200]
    if not snap.get("active"):
        return "session_stopped"
    chans = snap.get("channels") or {}
    vals = {c: (chans.get(c) or {}).get("value") for c in rec.channels}
    with _lock:
        if rec.reason is not None:
            return rec.reason
        try:
            _write(rec, {"type": "row", "t": round(time.monotonic() - rec.m0, 3), "at": _iso(time.time()),
                         "v": vals})
        except (OSError, ValueError, TypeError) as e:
            return f"error: write failed: {type(e).__name__}: {e}"[:200]
        rec.rows += 1
    return None


def _loop(rec: _Rec) -> None:
    period = 1.0 / rec.rate_hz
    nxt = time.monotonic()
    while not rec.stop_evt.is_set():
        if time.monotonic() - rec.m0 >= rec.max_s:
            _finish(rec, "max_duration")
            return
        reason = sample_once(rec)
        if reason:
            _finish(rec, reason)
            return
        nxt += period
        rec.stop_evt.wait(max(0.0, nxt - time.monotonic()))


def start(vin: str, channels: Optional["list[str]"] = None, label: str = "",
          rate_hz: float = DEFAULT_RATE_HZ, max_s: float = DEFAULT_MAX_S) -> "dict[str, Any]":
    global _active
    _check_vin(vin)
    with _lock:
        if _active is not None:
            raise RecordingError("a recording is already running; stop it first")
        try:
            active = bool(_status().get("active"))
        except Exception as e:  # noqa: BLE001
            raise RecordingError(f"cannot read the live session: {e}") from e
        if not active:
            raise RecordingError("No live session is running. Start one on the Live board first; "
                                 "a recording only reads what the live session already collects.")
        avail = _snapshot().get("channels") or {}
        chosen = [c for c in (channels or []) if c] or [c for c in avail]
        unknown = [c for c in chosen if c not in avail]
        if unknown:
            raise RecordingError("not in the running live session: " + ", ".join(unknown[:5]))
        if not chosen:
            raise RecordingError("the live session has no channels")
        rate = min(MAX_RATE_HZ, max(0.1, float(rate_hz)))
        rec_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        sl = _slug(label)
        if sl:
            rec_id += "-" + sl
        d = _dir(vin)
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{rec_id}.jsonl"
        n = 2
        while path.exists():
            path = d / f"{rec_id}-{n}.jsonl"
            n += 1
        rec = _Rec(vin, path.stem, path, chosen, rate, float(max_s))
        rec.fh = path.open("w", encoding="utf-8", newline="\n")
        _write(rec, {"type": "header", "id": rec.id, "vin": vin, "label": (label or "")[:80],
                     "start": _iso(rec.t0), "channels": chosen,
                     "units": {c: (avail[c] or {}).get("unit", "") for c in chosen},
                     "rate_hz": rate, "max_s": rec.max_s})
        _active = rec
        rec.thread = threading.Thread(target=_loop, args=(rec,), name="cuore-recording", daemon=True)
        rec.thread.start()
    return {"id": rec.id, "vin": vin, "channels": chosen, "rate_hz": rate}


def stop(reason: str = "stopped") -> "dict[str, Any]":
    with _lock:
        rec = _active
    if rec is None:
        return {"stopped": False, "detail": "no recording is running"}
    _finish(rec, reason)
    if rec.thread is not None and rec.thread is not threading.current_thread():
        rec.thread.join(timeout=2.0)
    return {"stopped": True, "id": rec.id, "rows": rec.rows, "reason": rec.reason}


def add_tag(key: str, label: str) -> Optional["dict[str, Any]"]:
    """Insert a keyed tag (0-9) into the running drive recording; None when none is running."""
    with _lock:
        rec = _active
        if rec is None or rec.reason is not None:
            return None
        ev = {"type": "tag", "t": round(time.monotonic() - rec.m0, 3), "at": _iso(time.time()),
              "key": str(key), "label": str(label), "row": rec.rows}
        try:
            _write(rec, ev)
        except (OSError, ValueError):
            return None
        return {k: v for k, v in ev.items() if k != "type"}


def current() -> Optional["dict[str, Any]"]:
    with _lock:
        rec = _active
        if rec is None:
            return None
        return {"id": rec.id, "vin": rec.vin, "channels": rec.channels[:], "rate_hz": rec.rate_hz,
                "elapsed_s": round(time.monotonic() - rec.m0, 1), "rows": rec.rows}


def live_state() -> "dict[str, Any]":
    """What the pages need: is a live session running (and why not), what records now."""
    try:
        st = _status()
        active = bool(st.get("active"))
        names = [c.get("id") or c.get("name") for c in (st.get("channels") or [])] if active else []
    except Exception as e:  # noqa: BLE001
        return {"live": False, "reason": f"Live session unavailable: {e}", "channels": [],
                "recording": current()}
    return {"live": active, "channels": [n for n in names if n],
            "reason": "" if active else "No live session - start one on the Live board",
            "recording": current()}


# --- reading ---------------------------------------------------------------------

def _read(path: Path) -> "dict[str, Any]":
    header: dict[str, Any] = {}
    rows: "list[dict[str, Any]]" = []
    tags: "list[dict[str, Any]]" = []
    end: dict[str, Any] = {}
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue  # a torn last line from a crash
            t = o.get("type")
            if t == "header":
                header = o
            elif t == "row":
                rows.append(o)
            elif t == "tag":
                tags.append({k: o.get(k) for k in ("key", "label", "at", "t", "row")})
            elif t == "end":
                end = o
    dur = end.get("duration_s")
    if dur is None:
        dur = rows[-1]["t"] if rows else 0.0
    return {**header, "rows": rows, "tags": tags, "n_rows": len(rows), "duration_s": dur,
            "end_reason": end.get("reason") or ("interrupted" if header else ""), "ended": bool(end)}


def load(vin: str, rec_id: str) -> Optional["dict[str, Any]"]:
    p = _dir(vin) / f"{_check_id(rec_id)}.jsonl"
    if not p.is_file():
        return None
    r = _read(p)
    return r if r.get("id") else None


def list_recordings(vin: str) -> "dict[str, Any]":
    d = _dir(vin)
    out: "list[dict[str, Any]]" = []
    if d.is_dir():
        for p in d.glob("*.jsonl"):
            try:
                r = _read(p)
            except OSError:
                continue
            if r.get("id"):
                r.pop("rows", None)
                out.append(r)
    out.sort(key=lambda r: r.get("start", ""), reverse=True)
    return out  # type: ignore[return-value]


#: Public name requested by the spec. Defined after every internal use of the
#: builtin ``list`` so those keep working.
list = list_recordings  # noqa: A001
