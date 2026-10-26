"""Intermittent-fault correlator: line up every recorded occasion a code SET
(or a symptom happened) against the conditions at that moment, and report what
those occasions have in common.

Example line this module produces::

    U0100: 4 of 5 set events: battery below 12.0 V

Rules that shape every function here:

* Conclusions cite CUORE's own records. Each event carries its source and a
  source id (a log file name, an observation time, a symptom id, a wiggle
  mark id) so a line can be traced back to the record behind it.
* "Not recorded" is never 0. A condition's denominator ("of M") counts only
  the events that actually recorded that condition; the rest are reported as
  not recorded.
* Counts are counts ("4 of 5"). No percentages, p-values or invented
  statistics. Wording such as "all", "most" and "some" is derived from the
  counts alone (see ``emphasis`` in ``cuore/data/intermittent_bands.json``).
* Only this car (VIN equality) and only readings from the car: simulated MES
  logs are excluded by the catalog, and live observations must pass
  ``live.store.is_from_car``. An event with an empty or different VIN is never
  used.
* A log's file time is NOT the time a code set, so it is never used for
  time-of-day. Only an event's own recorded clock time is.

Event sources used, in the order they are gathered:

``freeze_frame``   MES FES freeze-frame blocks (``mes_bridge.freeze_frames``)
``dtc_snapshot``   CUORE live UDS 19 04 snapshot records (``dtc_detail``
                   observations); only DIDs the decoder rates medium/high
``live_freeze``    CUORE live OBD Mode 02 freeze-frame reads
``wiggle``         wiggle-test marks whose live window saw the code set
``symptom``        symptom reports (hidden and "resolved"-noted ones excluded)
                   that carry the tag, or (for a code) name the code in text
``owner_event``    owner events that name the code
``first_seen``     the earliest read that showed the code, used only when no
                   other event exists (it records presence, not conditions)

Thresholds live in ``cuore/data/intermittent_bands.json``; each band carries a
``basis``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import cache, mes_bridge
from .errors import BadRequest, NotFound
from ..live import store as live_store

BANDS_PATH = Path(__file__).resolve().parents[1] / "data" / "intermittent_bands.json"

_CODE_RE = re.compile(r"^[A-Za-z][0-9A-Za-z]{3,6}(-[0-9A-Fa-f]{2})?$")
_NUM_RE = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*(.*)$")

SOURCE_LABELS = {
    "freeze_frame": "MES freeze frame",
    "dtc_snapshot": "Live DTC snapshot (UDS 19 04)",
    "live_freeze": "Live freeze frame (Mode 02)",
    "wiggle": "Wiggle-test mark",
    "symptom": "Symptom report",
    "owner_event": "Owner event",
    "first_seen": "First read that showed it",
}


# ---------------------------------------------------------------------------
# Bands
# ---------------------------------------------------------------------------

_bands_memo: dict[str, Any] = {}


def load_bands() -> dict[str, Any]:
    """The band file, re-read when it changes on disk."""
    try:
        stamp = BANDS_PATH.stat().st_mtime_ns
    except OSError as exc:
        raise NotFound(f"band file missing: {BANDS_PATH.name}") from exc
    if _bands_memo.get("stamp") != stamp:
        data = json.loads(BANDS_PATH.read_text(encoding="utf-8"))
        for c in data.get("conditions", []):
            c["_rx"] = [re.compile(p, re.I) for p in c.get("fields", [])]
            c["_ex"] = [re.compile(p, re.I) for p in c.get("exclude_fields", [])]
        _bands_memo.update(stamp=stamp, data=data)
    return _bands_memo["data"]


def _cond_def(bands: dict[str, Any], key: str) -> Optional[dict[str, Any]]:
    return next((c for c in bands["conditions"] if c["key"] == key), None)


def band_of(cond: dict[str, Any], value: float) -> Optional[dict[str, Any]]:
    """The band holding ``value`` (``lo`` inclusive, ``hi`` exclusive), or None."""
    for b in cond.get("bands", []):
        lo, hi = b.get("lo"), b.get("hi")
        if (lo is None or value >= lo) and (hi is None or value < hi):
            return b
    return None


# ---------------------------------------------------------------------------
# Small parsing helpers
# ---------------------------------------------------------------------------

def _base(code: str) -> str:
    return (code or "").strip().upper().split("-")[0]


def _num(v: Any) -> tuple[Optional[float], str]:
    if isinstance(v, bool):
        return None, ""
    if isinstance(v, (int, float)):
        return float(v), ""
    m = _NUM_RE.match(str(v or ""))
    if not m:
        return None, ""
    try:
        return float(m.group(1).replace(",", ".")), m.group(2).strip()
    except ValueError:
        return None, ""


def _parse_dt(s: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(s))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _precise(at: Any) -> Optional[datetime]:
    """A datetime only when ``at`` carries a real clock time. A date alone, or
    a midnight stamp (the symptom form's "time not given" placeholder), is
    treated as no time at all."""
    s = str(at or "")
    if "T" not in s and " " not in s.strip():
        return None
    dt = _parse_dt(s.replace(" ", "T", 1))
    if dt is None or (dt.hour == 0 and dt.minute == 0 and dt.second == 0):
        return None
    return dt


def _cv(text: str, value: Any, field: str, **extra: Any) -> dict[str, Any]:
    return {"value": value, "text": text, "field": field, **extra}


def condition_values(bands: dict[str, Any], fields: list[tuple[str, Any, str]]
                     ) -> dict[str, dict[str, Any]]:
    """Map raw labelled fields ``[(label, value, unit)]`` onto the band file's
    condition keys. Numbers for ``band`` conditions, exact text for
    ``same_value`` conditions. The first matching field wins; no match means
    the key is simply absent (= not recorded)."""
    out: dict[str, dict[str, Any]] = {}
    for c in bands["conditions"]:
        kind = c.get("kind")
        if kind not in ("band", "same_value") or not c.get("_rx"):
            continue
        for label, val, unit in fields:
            if not any(rx.search(label) for rx in c["_rx"]) or any(rx.search(label) for rx in c["_ex"]):
                continue
            if kind == "band":
                n, u = _num(val)
                if n is None:
                    continue
                u = unit or u
                out[c["key"]] = _cv(f"{n:g} {u}".strip(), n, label)
                break
            text = str(val if val is not None else "").strip()
            if not text or text.lower() in ("none", "null"):
                continue
            if c["key"] == "startups":
                n, _ = _num(val)
                if n is None:
                    continue
                text = str(int(n))
            out[c["key"]] = _cv(text, text, label)
            break
    return out


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def _event(source: str, ref: str, code: str, at: str, conditions: dict[str, Any], *,
           odometer_km: Optional[float] = None, note: str = "", precise: bool = False,
           confidence: str = "", href: str = "") -> dict[str, Any]:
    return {"source": source, "source_label": SOURCE_LABELS[source], "ref": ref, "code": code,
            "at": at or "", "precise_time": precise, "odometer_km": odometer_km,
            "conditions": conditions, "note": note, "confidence": confidence, "href": href,
            "also_in": []}


def _all_frames(vin: str) -> list[dict[str, Any]]:
    """Every real freeze frame for this VIN, memoised on the corpus freshness
    (parsing each FES log is the expensive part)."""
    def build() -> list[dict[str, Any]]:
        try:
            return list(mes_bridge.freeze_frames(vin=vin).get("frames") or [])
        except NotFound:
            return []
    return cache.get_or_build(("intermittent.frames", vin, mes_bridge.newest_mtime(vin)), build)


def _freeze_events(bands: dict[str, Any], vin: str, base: Optional[str]) -> list[dict[str, Any]]:
    out = []
    for f in _all_frames(vin):
        if f.get("vin") and f["vin"] != vin:
            continue
        if base and _base(f.get("dtc", "")) != base:
            continue
        ff = f.get("freeze_frame") or {}
        fields = [(k, v, "") for k, v in ff.items()]
        conds = condition_values(bands, fields)
        odo, _ = _num(next((v for k, v in ff.items() if k.lower() == "odometer"), None))
        opt, _ = _num(next((v for k, v in ff.items() if k.lower() == "operating time"), None))
        ev = _event("freeze_frame", f.get("file", ""), f.get("dtc", ""), f.get("timestamp", ""),
                    conds, odometer_km=odo,
                    note="The time shown is the log's time; it is not the time the code set.")
        ev["_opt"] = opt
        out.append(ev)
    return out


def _obs_for(vin: str, kind: str) -> list[dict[str, Any]]:
    rows = cache.recent_observations(1_000_000, vin=vin, kind=kind)
    return [o for o in rows if o.get("vin") == vin and live_store.is_from_car(o)]


def _snapshot_events(bands: dict[str, Any], vin: str, base: Optional[str]) -> tuple[list[dict[str, Any]], int]:
    """Live 19 04 snapshots. Returns (events, snapshots read that decoded nothing)."""
    out, undecoded = [], 0
    for o in _obs_for(vin, "dtc_detail"):
        d = o.get("data") or {}
        code = str(d.get("dtc") or "")
        if base and _base(code) != base:
            continue
        fields, confs = [], set()
        for rec in (d.get("snapshot") or {}).get("records") or []:
            for i in rec.get("identifiers") or []:
                if i.get("value") is None or i.get("confidence") not in ("medium", "high"):
                    continue
                fields.append((str(i.get("name") or ""), i["value"], str(i.get("unit") or "")))
                confs.add(i.get("confidence"))
        if not fields:
            undecoded += 1
            continue
        conds = condition_values(bands, fields)
        odo = next((v for k, v, _ in fields if k.lower() == "odometer"), None)
        opt = next((v for k, v, _ in fields if k.lower() == "operating time"), None)
        ev = _event("dtc_snapshot", f"observation {o.get('at')}", code, str(o.get("at") or ""),
                    conds, odometer_km=odo,
                    note="Read time shown; the snapshot's own set time is not decoded.",
                    confidence="medium" if "medium" in confs else "high")
        ev["_opt"] = opt
        out.append(ev)
    return out, undecoded


def _live_freeze_events(bands: dict[str, Any], vin: str, base: str) -> list[dict[str, Any]]:
    """Mode 02: PID 02 names the code the frame belongs to; PIDs read in the
    next two minutes from the same ECU are that frame's values."""
    obs = _obs_for(vin, "freeze_frame")
    out = []
    for i, o in enumerate(obs):
        by = (o.get("data") or {}).get("by_ecu") or {}
        owner = next((e for e, v in by.items() if _base(str(v.get("dtc") or "")) == base
                      and (o.get("data") or {}).get("pid") == "02"), None)
        if owner is None:
            continue
        t0 = _parse_dt(o.get("at"))
        fields = []
        for o2 in obs[i + 1:]:
            t1 = _parse_dt(o2.get("at"))
            if t0 and t1 and (t1 - t0).total_seconds() > 120:
                break
            v = ((o2.get("data") or {}).get("by_ecu") or {}).get(owner) or {}
            if v.get("value") is not None and v.get("name"):
                fields.append((str(v["name"]).replace("_", " "), v["value"], str(v.get("unit") or "")))
        out.append(_event("live_freeze", f"observation {o.get('at')}", base, str(o.get("at") or ""),
                          condition_values(bands, fields),
                          note="Read time shown; not the time the code set."))
    return out


def _closed_symptom_ids(vin: str) -> set[str]:
    """Symptom ids named by a visible note tagged "resolved" (the symptom store
    has no status field, so that note is the record that closes one)."""
    out: set[str] = set()
    try:
        for n in mes_bridge.notes(vin)["notes"]:
            if n.get("hidden") or "resolved" not in [str(t).lower() for t in n.get("tags") or []]:
                continue
            out.update(re.findall(r"\b[0-9a-f]{12}\b", n.get("text") or ""))
    except Exception:  # noqa: BLE001
        pass
    return out


def _symptom_rows(vin: str) -> list[dict[str, Any]]:
    from mes import symptoms as symptoms_mod            # noqa: E402
    closed = _closed_symptom_ids(vin)
    out = []
    for s in symptoms_mod.load(vin):
        sid = str(s.get("id") or "")
        if s.get("hidden") or s.get("vin") != vin:
            continue
        if s.get("resolved") or s.get("closed") or str(s.get("status") or "").lower() in (
                "resolved", "closed", "fixed", "done"):
            continue
        if sid and any(sid.startswith(c) or c.startswith(sid) for c in closed):
            continue
        out.append(s)
    return out


def _symptom_event(s: dict[str, Any], code: str) -> dict[str, Any]:
    at = str(s.get("at") or "")
    p = _precise(at)
    conds: dict[str, Any] = {}
    tags = [str(t) for t in s.get("conditions") or []]
    if tags:
        conds["reported_conditions"] = _cv(", ".join(tags), tags, "conditions")
    ev = _event("symptom", str(s.get("id") or ""), code, at, conds,
                odometer_km=s.get("odometer_km"), precise=p is not None,
                note=str(s.get("text") or "")[:300], href="")
    return ev


def _owner_events(vin: str, base: str) -> list[dict[str, Any]]:
    try:
        from ..live import owner_events
        rows = owner_events.load(vin)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in rows:
        if r.get("vin") != vin:
            continue
        blob = " ".join([str(r.get("note") or "")] + [str(v) for v in (r.get("fields") or {}).values()]).upper()
        if base not in blob:
            continue
        at = str(r.get("at") or "")
        out.append(_event("owner_event", str(r.get("id") or ""), base, at, {},
                          odometer_km=r.get("odometer_km"), precise=_precise(at) is not None,
                          note=f"{r.get('category')}/{r.get('kind')}"))
    return out


def _wiggle_marks(vin: str, base: str) -> list[dict[str, Any]]:
    from . import path_diag
    return [m for m in path_diag.wiggle_marks(vin, base) if m.get("action") == "mark"]


def _wiggle_events(bands: dict[str, Any], vin: str, base: str, marks: list[dict[str, Any]]
                   ) -> list[dict[str, Any]]:
    """A mark is a set event when its live window recorded the code setting."""
    if not marks:
        return []
    from . import path_diag
    out = []
    try:
        timeline = path_diag.wiggle_timeline(vin, base, marks=marks)
    except Exception:  # noqa: BLE001
        return []
    for m in timeline:
        if not m.get("correlated"):
            continue
        saw = [e for e in m.get("events") or [] if e.get("kind") == "dtc" and base in str(e.get("text", "")).upper()]
        if not saw:
            continue
        conds: dict[str, Any] = {"wiggle_near": _cv("yes", True, "wiggle mark"),
                                 "wiggle_hop": _cv(str(m.get("hop") or ""), str(m.get("hop") or ""), "hop")}
        for e in m.get("events") or []:                      # a voltage alarm inside the window
            mm = re.search(r"\(([-\d.]+)\)\s*$", str(e.get("text", "")))
            if e.get("kind") == "alarm" and "volt" in str(e.get("text", "")).lower() and mm:
                v = float(mm.group(1))
                conds["battery_v"] = _cv(f"{v:g} V", v, "live alarm")
        out.append(_event("wiggle", str(m.get("id") or ""), base, str(m.get("at") or ""), conds,
                          precise=True, note=str(m.get("note") or "")))
    return out


def _first_seen_event(vin: str, base: str) -> Optional[dict[str, Any]]:
    """The earliest read that showed the code (presence only, no conditions)."""
    best: Optional[tuple[str, str]] = None
    try:
        hist = mes_bridge.dtc_history(base, vin=vin)
        for rec in hist["matches"]:
            for o in rec.get("occurrences") or []:
                ts = str(o.get("timestamp") or "")
                if ts and (best is None or ts.replace(" ", "T") < best[0]):
                    best = (ts.replace(" ", "T"), f"log {o.get('file')}")
    except Exception:  # noqa: BLE001
        pass
    for o in _obs_for(vin, "module_dtcs"):
        if any(_base(str(x.get("code") or "")) == base for x in (o.get("data") or {}).get("dtcs") or []):
            ts = str(o.get("at") or "")
            if best is None or ts < best[0]:
                best = (ts, f"live read {ts}")
    if best is None:
        return None
    return _event("first_seen", best[1], base, best[0], {},
                  note="First read that showed the code. A read shows the code is present, not when it set, and records no conditions.")


def _sightings(vin: str, base: str) -> int:
    n = 0
    try:
        for rec in mes_bridge.dtc_history(base, vin=vin)["matches"]:
            n += len({o.get("file") for o in rec.get("occurrences") or []})
    except Exception:  # noqa: BLE001
        pass
    for o in _obs_for(vin, "module_dtcs"):
        if any(_base(str(x.get("code") or "")) == base for x in (o.get("data") or {}).get("dtcs") or []):
            n += 1
    return n


# --- native per-VIN drive recordings (conditions at an event's own time) ---------

def _recording_index(vin: str) -> list[dict[str, Any]]:
    try:
        from . import recordings
        out = []
        for r in recordings.list_recordings(vin):
            s = _parse_dt(r.get("start"))
            if s is not None and r.get("id"):
                out.append({"id": r["id"], "start": s, "dur": float(r.get("duration_s") or 0),
                            "units": r.get("units") or {}})
        return out
    except Exception:  # noqa: BLE001
        return []


def _recording_conditions(bands: dict[str, Any], vin: str, index: list[dict[str, Any]],
                          at: datetime) -> dict[str, dict[str, Any]]:
    from . import recordings
    tol = float(bands.get("nearest_recording_row_s", 2))
    for r in index:
        off = (at - r["start"]).total_seconds()
        if off < -tol or off > r["dur"] + tol:
            continue
        full = recordings.load(vin, r["id"])
        best, gap = None, None
        for row in (full or {}).get("rows") or []:
            t = _parse_dt(row.get("at"))
            if t is None:
                continue
            g = abs((t - at).total_seconds())
            if gap is None or g < gap:
                best, gap = row, g
        if best is None or gap is None or gap > tol:
            continue
        fields = [(str(k).replace("_", " "), v, str(r["units"].get(k) or ""))
                  for k, v in (best.get("v") or {}).items() if v is not None]
        out = condition_values(bands, fields)
        for c in out.values():
            c["from_recording"] = r["id"]
        return out
    return {}


# ---------------------------------------------------------------------------
# Subject, collection, analysis
# ---------------------------------------------------------------------------

def subject_of(key: str) -> dict[str, str]:
    """``{"kind": "code"|"symptom", "key": ...}`` for a path parameter."""
    from mes.symptoms import SYMPTOM_TAGS
    k = (key or "").strip()
    if k in SYMPTOM_TAGS:
        return {"kind": "symptom", "key": k}
    if _CODE_RE.match(k) and any(ch.isdigit() for ch in k):
        return {"kind": "code", "key": k.upper()}
    raise BadRequest(f"'{key}' is neither a DTC (like U0100) nor a symptom tag (like noise)")


def _dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One real occurrence read twice (same code, startups counter and
    operating time) is one event; the later copies are listed as ``also_in``."""
    seen: dict[tuple, dict[str, Any]] = {}
    out = []
    for ev in events:
        st = (ev["conditions"].get("startups") or {}).get("value")
        opt = ev.get("_opt")
        if st is not None and opt is not None:
            key = (_base(ev["code"]), st, opt)
            if key in seen:
                seen[key]["also_in"].append(f"{ev['source_label']}: {ev['ref']}")
                continue
            seen[key] = ev
        out.append(ev)
    return out


def _wiggle_flag(events: list[dict[str, Any]], marks: list[dict[str, Any]], bands: dict[str, Any]) -> None:
    """With marks on file for this code, an event that has a real clock time
    gets wiggle_near = yes/no; without marks or without a time it stays
    not recorded."""
    if not marks:
        return
    w = bands.get("wiggle_window_s") or {}
    before, after = float(w.get("before", 5)), float(w.get("after", 20))
    mts = [t for t in (_parse_dt(m.get("at")) for m in marks) if t]
    for ev in events:
        if "wiggle_near" in ev["conditions"] or not ev["precise_time"]:
            continue
        t = _parse_dt(ev["at"].replace(" ", "T", 1))
        if t is None:
            continue
        near = any(-before <= (t - m).total_seconds() <= after for m in mts)
        ev["conditions"]["wiggle_near"] = _cv("yes" if near else "no", near, "wiggle marks on file")


def _time_of_day(events: list[dict[str, Any]], bands: dict[str, Any]) -> None:
    cond = _cond_def(bands, "time_of_day")
    for ev in events:
        if not ev["precise_time"] or "time_of_day" in ev["conditions"]:
            continue
        t = _precise(ev["at"])
        if t is None or cond is None:
            continue
        h = t.hour + t.minute / 60
        ev["conditions"]["time_of_day"] = _cv(t.strftime("%H:%M"), h, "event time")


def _recording_fill(events: list[dict[str, Any]], bands: dict[str, Any], vin: str) -> None:
    precise = [e for e in events if e["precise_time"]]
    if not precise:
        return
    index = _recording_index(vin)
    if not index:
        return
    for ev in precise:
        t = _precise(ev["at"])
        if t is None:
            continue
        for k, c in _recording_conditions(bands, vin, index, t).items():
            ev["conditions"].setdefault(k, c)


def collect(vin: str, subject: dict[str, str]) -> dict[str, Any]:
    """Events for one code or symptom, plus the source inventory."""
    bands = load_bands()
    sources: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    marks: list[dict[str, Any]] = []
    sightings = 0

    def note(sid: str, found: int, text: str = "") -> None:
        sources.append({"id": sid, "label": SOURCE_LABELS.get(sid, sid), "found": found, "note": text})

    if subject["kind"] == "code":
        base = _base(subject["key"])
        ff = _freeze_events(bands, vin, base)
        events += ff
        note("freeze_frame", len(ff), "from real MES FES logs for this VIN; simulated logs are excluded")
        sn, undecoded = _snapshot_events(bands, vin, base)
        events += sn
        note("dtc_snapshot", len(sn), (f"{undecoded} snapshot read(s) decoded no usable value and are not counted"
                                        if undecoded else ""))
        lf = _live_freeze_events(bands, vin, base)
        events += lf
        note("live_freeze", len(lf))
        marks = _wiggle_marks(vin, base)
        wg = _wiggle_events(bands, vin, base, marks)
        events += wg
        note("wiggle", len(wg), f"{len(marks)} wiggle mark(s) on file for {base}; an event only when a live "
                                f"session saw the code set inside the mark's window")
        mention = re.compile(re.escape(base), re.I)
        sy = [_symptom_event(s, base) for s in _symptom_rows(vin) if mention.search(str(s.get("text") or ""))]
        events += sy
        note("symptom", len(sy), "open symptom reports whose text names this code; resolved ones are excluded")
        oe = _owner_events(vin, base)
        events += oe
        note("owner_event", len(oe), "owner events that name this code")
        sightings = _sightings(vin, base)
        if not events:
            fs = _first_seen_event(vin, base)
            if fs:
                events.append(fs)
                note("first_seen", 1, "used because no other event exists")
        label = base
    else:
        tag = subject["key"]
        sy = [_symptom_event(s, tag) for s in _symptom_rows(vin) if tag in (s.get("tags") or [])]
        events += sy
        note("symptom", len(sy), f"open symptom reports tagged '{tag}'; resolved ones are excluded")
        label = tag

    events = _dedupe(events)
    _wiggle_flag(events, marks, bands)
    _recording_fill(events, bands, vin)
    _time_of_day(events, bands)
    events.sort(key=lambda e: (e["at"].replace(" ", "T"), e["source"], e["ref"]))
    for i, e in enumerate(events, 1):
        e["id"] = f"E{i}"
        e.pop("_opt", None)
    return {"label": label, "events": events, "sources": sources, "sightings": sightings, "marks": len(marks)}


def _baseline(vin: str, base: Optional[str]) -> list[dict[str, Any]]:
    """Every OTHER code's freeze-frame / snapshot events on this car, to show
    how common a condition is on this car generally (counts only)."""
    bands = load_bands()
    evs = _freeze_events(bands, vin, None) + _snapshot_events(bands, vin, None)[0]
    evs = [e for e in evs if not base or _base(e["code"]) != base]
    return _dedupe(evs)


def _emphasis(n: int, m: int, bands: dict[str, Any]) -> str:
    e = bands.get("emphasis") or {}
    if n == m:
        return "all"
    if n / m >= float(e.get("most", 0.75)):
        return "most"
    if n / m >= float(e.get("half", 0.5)):
        return "about half or more"
    return "some"


def _tally(cond: dict[str, Any], events: list[dict[str, Any]]) -> tuple[int, dict[str, list[str]]]:
    """(M, {group id: [event ids]}) for one condition over ``events``; M counts
    only events that recorded the condition."""
    kind = cond.get("kind")
    m = 0
    groups: dict[str, list[str]] = {}
    for ev in events:
        c = ev["conditions"].get(cond["key"])
        if c is None:
            continue
        m += 1
        v = c["value"]
        if kind == "tags":
            for t in v:
                groups.setdefault(str(t), []).append(ev["id"])
        elif kind == "same_value":
            groups.setdefault(str(v), []).append(ev["id"])
        elif kind == "wiggle":
            if v is True:
                groups.setdefault("yes", []).append(ev["id"])
        else:
            b = band_of(cond, float(v))
            if b:
                groups.setdefault(b["id"], []).append(ev["id"])
            else:
                m -= 1
    return m, groups


def _lines(bands: dict[str, Any], events: list[dict[str, Any]], baseline: list[dict[str, Any]],
           noun: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    min_hits = int(bands.get("min_hits", 2))
    min_events = int(bands.get("min_events", 3))
    for i, e in enumerate(baseline, 1):
        e["id"] = f"B{i}"
    lines, never, missing = [], [], []
    total = len(events)
    for cond in bands["conditions"]:
        m, groups = _tally(cond, events)
        bm, bgroups = _tally(cond, baseline) if baseline else (0, {})
        if m < total:
            missing.append({"condition": cond["key"], "label": cond["label"],
                            "recorded": m, "of": total, "not_recorded": total - m})
        if m == 0:
            continue
        kind = cond.get("kind")
        if kind in ("band", "time_of_day", "wiggle"):
            band_by_id = {b["id"]: b for b in cond["bands"]}
            candidates = [(b["id"], b) for b in cond["bands"]]
        else:
            band_by_id = {}
            candidates = [(g, None) for g in groups]
        for gid, b in candidates:
            ids = groups.get(gid, [])
            n = len(ids)
            if kind == "same_value":
                phrase = cond["phrase_template"].format(value=gid)
                short = cond["short_template"]
                basis, nxt = cond.get("basis", ""), cond.get("next_test", "")
            elif kind == "tags":
                phrase = cond["phrase_template"].format(value=gid)
                short = gid.replace("_", " ")
                basis, nxt = cond.get("basis", ""), ""
            else:
                phrase, short = b["phrase"], b["short"]
                basis, nxt = b.get("basis", ""), b.get("next_test", "")
            row = {"condition": cond["key"], "label": cond["label"], "band": gid, "phrase": phrase,
                   "short": short, "n": n, "m": m, "of_total": total,
                   "not_recorded": total - m, "event_ids": ids, "basis": basis, "next_test": nxt,
                   "baseline": ({"n": len(bgroups.get(gid, [])), "m": bm} if bm else None)}
            if n >= min_hits:
                row["emphasis"] = _emphasis(n, m, bands)
                row["text"] = f"{n} of {m} {noun}: {phrase}"
                if m < total:
                    row["text"] += f" ({total - m} of {total} did not record {cond['label']})"
                lines.append(row)
            elif n == 0 and m >= min_events and kind in ("band", "time_of_day"):
                row["text"] = f"0 of {m} {noun}: {phrase}"
                never.append(row)

    def bfrac(r: dict[str, Any]) -> float:
        b = r["baseline"]
        return (b["n"] / b["m"]) if b and b["m"] else 0.5

    lines.sort(key=lambda r: (-(r["n"] / r["m"]), -r["n"], bfrac(r), r["label"], r["phrase"]))
    never.sort(key=lambda r: (-r["m"], r["label"], r["phrase"]))
    return lines, never, missing


def _hint(bands: dict[str, Any], subject: dict[str, str], lines: list[dict[str, Any]], noun: str
          ) -> Optional[dict[str, Any]]:
    """The one-line directing call, worded as a pattern in the records."""
    strong = [r for r in lines if r["n"] / r["m"] >= float((bands.get("emphasis") or {}).get("half", 0.5))]
    if not strong:
        return None

    def distinctive(r: dict[str, Any]) -> bool:
        b = r["baseline"]
        return not b or not b["m"] or (b["n"] / b["m"]) < (r["n"] / r["m"])

    def next_test(r: dict[str, Any]) -> tuple[str, str]:
        if subject["kind"] == "code":
            for h in bands.get("hints", []):
                if not any(subject["key"].startswith(p) for p in h.get("code_prefix", [])):
                    continue
                if h.get("condition") == r["condition"] and h.get("band") in (None, r["band"]):
                    return h["next_test"], h.get("source", "")
        return r.get("next_test", ""), r.get("basis", "")

    pool = [r for r in strong if distinctive(r)] or strong
    pick = next((r for r in pool if next_test(r)[0]), pool[0])
    test, src = next_test(pick)
    lead = f"{subject['key']}: {pick['short']} in {pick['n']} of {pick['m']} {noun}"
    text = lead + (f" — {test}" if test else "")
    return {"text": text, "lead": lead, "next_test": test, "next_test_source": src,
            "condition": pick["condition"], "band": pick["band"], "n": pick["n"], "m": pick["m"],
            "caveat": "A pattern in CUORE's records, not a proven cause."}


def analyze(vin: str, key: str) -> dict[str, Any]:
    """The full result for one code or symptom tag on one VIN."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    subject = subject_of(key)
    bands = load_bands()
    got = collect(vin, subject)
    return _finish(vin, subject, bands, got)


def _finish(vin: str, subject: dict[str, str], bands: dict[str, Any], got: dict[str, Any]) -> dict[str, Any]:
    events = got["events"]
    noun = "set events" if subject["kind"] == "code" else "occurrences"
    n = len(events)
    min_events = int(bands.get("min_events", 3))
    enough = n >= min_events
    base = _base(subject["key"]) if subject["kind"] == "code" else None
    lines: list[dict[str, Any]] = []
    never: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    hint = None
    baseline = _baseline(vin, base) if (enough and subject["kind"] == "code") else []
    if enough:
        lines, never, missing = _lines(bands, events, baseline, noun)
        hint = _hint(bands, subject, lines, noun)
    by_id = {e["id"]: e for e in events}
    for r in lines + never:
        r["events"] = [by_id[i] for i in r["event_ids"] if i in by_id]
    if not enough:
        headline = f"too few events to correlate ({n})"
    elif lines:
        headline = lines[0]["text"]
    else:
        headline = f"{n} {noun}; no condition is shared by {int(bands.get('min_hits', 2))} or more of them"
    return {
        "vin": vin, "subject": {**subject, "label": got["label"]},
        "n_events": n, "min_events": min_events, "enough": enough, "noun": noun,
        "headline": headline, "hint": hint, "lines": lines, "never": never, "not_recorded": missing,
        "events": events, "sources": got["sources"], "sightings": got["sightings"],
        "baseline_events": len(baseline),
        "basis_file": "cuore/data/intermittent_bands.json",
        "note": ("Counts of CUORE's own records only. A shared condition is a pattern to test, not a cause."),
    }


def panel(vin: str, code: str) -> dict[str, Any]:
    """Context for ``_intermittent_panel.html``. Never raises: a failure
    comes back as ``{"error": ...}`` so an embedded panel cannot sink its page."""
    try:
        return analyze(vin, code)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "vin": vin,
                "subject": {"kind": "code", "key": code, "label": code},
                "events": [], "lines": [], "never": [], "not_recorded": [], "sources": [],
                "n_events": 0, "enough": False, "hint": None, "headline": ""}


def overview(vin: str) -> dict[str, Any]:
    """One row per code (and per open symptom tag) that has any event."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    bands = load_bands()
    codes: dict[str, str] = {}
    for ev in _freeze_events(bands, vin, None) + _snapshot_events(bands, vin, None)[0]:
        codes.setdefault(_base(ev["code"]), "")
    try:
        for rec in mes_bridge.extract_dtcs(vin=vin).get("dtcs") or []:
            codes.setdefault(_base(rec["dtc"]), "; ".join(rec.get("descriptions") or [])[:90])
    except Exception:  # noqa: BLE001
        pass
    rows = []
    for c in sorted(codes):
        try:
            r = analyze(vin, c)
        except Exception:  # noqa: BLE001
            continue
        if not r["n_events"]:
            continue
        rows.append({"key": c, "kind": "code", "description": codes[c], "n_events": r["n_events"],
                     "enough": r["enough"], "headline": r["headline"],
                     "hint": (r["hint"] or {}).get("text", ""), "n_lines": len(r["lines"]),
                     "sightings": r["sightings"]})
    tags = sorted({t for s in _symptom_rows(vin) for t in (s.get("tags") or [])})
    for t in tags:
        try:
            r = analyze(vin, t)
        except Exception:  # noqa: BLE001
            continue
        rows.append({"key": t, "kind": "symptom", "description": "", "n_events": r["n_events"],
                     "enough": r["enough"], "headline": r["headline"],
                     "hint": (r["hint"] or {}).get("text", ""), "n_lines": len(r["lines"]), "sightings": 0})
    rows.sort(key=lambda r: (not r["n_lines"], -r["n_events"], r["key"]))
    return {"vin": vin, "rows": rows,
            "note": "Only codes and symptoms with at least one recorded event are listed."}


__all__ = ["analyze", "panel", "overview", "collect", "subject_of", "load_bands", "band_of",
           "condition_values"]
