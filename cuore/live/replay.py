"""Replay of recorded MES-format CSVs through the same message shape the live
SSE stream uses (``/api/live/stream``).

Two families of recording:

* cuore's own live-session recordings (:class:`cuore.live.poller.CsvRecorder`
  writes them to ``<state>/recordings/live_<timestamp>.csv``);
* MES graph-subsystem CSV recordings, found through the ``mes`` library's own
  CSV roots (``docs/format/CSV_LOG_FORMAT.md``).

Both are the identical wire format on purpose (see ``poller.CsvRecorder``'s
docstring), so one parser -- ``mes.csvlog`` -- covers both. A recording id is
``"<source>:<filename>"`` (``cuore:live_20260101-000000.csv`` or
``mes:whatever.csv``) so the two namespaces never collide.

Replay never calls :func:`cuore.live.store.record_observation`: replayed
values are explicitly not evidence about the car.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from ..services.errors import BadRequest, NotFound
from .config import state_dir

from ..services import replay_bridge as csvlog  # noqa: E402  -- the only mes access
from ..services import replay_bridge as mes_paths  # noqa: E402
from ..services.replay_bridge import MesError  # noqa: E402

_CUORE_NAME_RE = re.compile(r"^live_(\d{8})-(\d{6})\.csv$", re.IGNORECASE)


def cuore_recordings_dir() -> Path:
    d = state_dir() / "recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cuore_started(name: str) -> Optional[str]:
    m = _CUORE_NAME_RE.match(name)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return dt.isoformat(sep=" ", timespec="seconds")


def _mtime_iso(p: Path) -> Optional[str]:
    try:
        st = p.stat()
    except OSError:
        return None
    return datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ", timespec="seconds")


def _summarise(p: Path) -> dict[str, Any]:
    try:
        rec = csvlog.load_csv(p)
        return {"channels": [c.name for c in rec.columns],
               "duration_s": round(rec.duration, 3)}
    except Exception as exc:  # noqa: BLE001 -- one bad file must not sink the listing
        return {"channels": [], "duration_s": None, "parse_error": str(exc)}


def list_recordings() -> list[dict[str, Any]]:
    """Every replayable recording, cuore's own live sessions plus MES CSVs."""
    out: list[dict[str, Any]] = []
    for p in sorted(cuore_recordings_dir().glob("*.csv")):
        entry = {"id": f"cuore:{p.name}", "name": p.name, "source": "cuore",
                 "started": _cuore_started(p.name)}
        entry.update(_summarise(p))
        out.append(entry)
    for p in mes_paths.iter_csv_files():
        entry = {"id": f"mes:{p.name}", "name": p.name, "source": "mes",
                 "started": _mtime_iso(p)}
        entry.update(_summarise(p))
        out.append(entry)
    return out


def resolve_recording(recording_id: str) -> tuple[str, Path]:
    if ":" not in recording_id:
        raise BadRequest(f"recording id {recording_id!r} must be 'cuore:<file>' or "
                         "'mes:<file>'")
    source, _, name = recording_id.partition(":")
    if source == "cuore":
        p = cuore_recordings_dir() / Path(name).name
        if Path(name).name != name or not p.exists():
            raise NotFound(f"no cuore recording named {name!r}")
        return source, p
    if source == "mes":
        try:
            p = mes_paths.resolve_csv(name)
        except MesError as exc:
            raise NotFound(str(exc)) from exc
        return source, p
    raise BadRequest(f"unknown recording source {source!r}; one of 'cuore', 'mes'")


def _load(recording_id: str):
    _, path = resolve_recording(recording_id)
    try:
        return csvlog.load_csv(path)
    except MesError as exc:
        raise BadRequest(f"could not parse {recording_id!r}: {exc}") from exc


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return s or "field"


def _slug_columns(rec) -> list[tuple[str, Any]]:
    """``[(slug, column), ...]`` in column order; duplicate slugs disambiguated."""
    counts: dict[str, int] = {}
    out = []
    for c in rec.columns:
        base = _slugify(c.name)
        n = counts.get(base, 0)
        slug = base if n == 0 else f"{base}_{n + 1}"
        counts[base] = n + 1
        out.append((slug, c))
    return out


def replay_channels(recording_id: str) -> dict[str, dict[str, str]]:
    """``{slug: {"name": column name, "unit": ...}}`` for one recording."""
    rec = _load(recording_id)
    return {slug: {"name": col.name, "unit": col.unit} for slug, col in _slug_columns(rec)}


def _cell_number(text: str) -> Optional[float]:
    t = text.strip().strip('"')
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        try:
            return float(t.replace(",", "."))
        except ValueError:
            return None


def open_replay_stream(recording_id: str, speed: float = 1.0, start: float = 0.0
                       ) -> Iterator[dict[str, Any]]:
    """Validate and load eagerly; return a generator for the (now-valid) playback.

    Deliberately not a generator function itself: everything that can fail
    (bad ``speed``/``start``, an unresolvable recording, a CSV that fails to
    parse) happens synchronously when this is *called*, not on first
    iteration. That lets an HTTP route surface those as an ordinary 400/404
    response before a ``StreamingResponse`` has started -- once that response
    begins, headers are already sent and an exception can no longer become a
    clean status code.

    The returned generator yields messages shaped exactly like
    ``/api/live/stream`` (``{"t", "channel", "value", "unit"}``) plus
    ``"replay": true``, TAG rows as ``{"type": "tag", "t", "text"}``, and ends
    with ``{"type": "end"}``. ``speed=0`` emits every sample with no pacing
    delay ("as fast as possible", for tests); otherwise each inter-sample wait
    is the recording's own ``Time`` delta divided by ``speed``. Never calls
    :func:`cuore.live.store.record_observation` -- replay is not evidence.
    """
    if speed < 0 or speed > 16 or (0 < speed < 0.25):
        raise BadRequest("speed must be 0 (as fast as possible) or in 0.25..16")
    if start < 0:
        raise BadRequest("start must be >= 0")

    rec = _load(recording_id)
    slug_cols = _slug_columns(rec)
    tags_by_time: dict[float, list[str]] = {}
    for tag in rec.tags:
        tags_by_time.setdefault(tag.time, []).append(tag.text)

    def _gen() -> Iterator[dict[str, Any]]:
        prev_t: Optional[float] = None
        for t, row in zip(rec.times, rec.rows):
            if t < start:
                prev_t = t
                continue
            if speed > 0 and prev_t is not None:
                wait = (t - prev_t) / speed
                if wait > 0:
                    time.sleep(wait)
            prev_t = t
            for slug, col in slug_cols:
                raw = row[col.index] if col.index < len(row) else ""
                value = _cell_number(raw)
                yield {"t": time.time(), "channel": slug, "value": value, "unit": col.unit,
                      "replay": True}
            for text in tags_by_time.get(t, []):
                yield {"type": "tag", "t": time.time(), "text": text}
        yield {"type": "end"}

    return _gen()


__all__ = ["cuore_recordings_dir", "list_recordings", "resolve_recording",
          "replay_channels", "open_replay_stream"]
