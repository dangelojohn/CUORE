"""ZF 8HP transmission parameters read from MES graph-subsystem CSV
recordings (:mod:`mes.csvlog`), surfaced as read-only Live board channels.

These are never from the live serial stream the poller
(:mod:`cuore.live.poller`) reads -- a CSV recording is a file someone made
in MES at some point in the past, possibly long before the car is next on
the bench. Every entry :func:`transmission_recording_channels` returns
carries ``kind: "recording"``, ``source: "MES"`` and the recording's own
filename/date (``mtime`` -- see ``mes.csvlog.list_recordings``'s own
docstring on why that, not a filename stamp, is the only timestamp a CSV
recording has) so nothing downstream can mistake one for a live reading.
:mod:`cuore.services.liveboard_bridge` keeps these in their own section,
separate from ``board()``'s polled ``can_c`` channel list -- see that
module's own note at the top of :func:`cuore.services.liveboard_bridge.
board` for why a recording channel must never land in ``all_channel_ids``/
``rates`` (the poller would try, and fail, to poll it).

Column matching is case-insensitive substring matching against each
recording's own column names (:data:`RECORDING_CHANNELS`'s ``aliases``) --
the same rule :mod:`mes.known_good`'s ``observed_ranges()`` pipeline uses
for FES/CSV parameter matching (``_best_match``, private to that module's
own pipeline and small enough to duplicate here rather than reach into it).

Grading reuses the one sourced band this project already has for this
quantity: ATF temperature shares :mod:`mes.known_good`'s ``tcm_04fe`` row
(a sourced ZF-8HP-generic normal/alarm band) rather than inventing a second
band for the same physical quantity under a new id. Every other ZF 8HP
recording parameter here (gear, torque-converter slip/lock-up, line
pressure, input/output speed) has no sourced band in ``mes.known_good`` and
always grades ``"unknown"`` -- never invented.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import known_good_bridge

try:
    from mes import csvlog as csvlog_mod  # noqa: E402
except Exception:  # noqa: BLE001 -- a recording-less install must still work
    csvlog_mod = None  # type: ignore[assignment]

#: The ``mes.systems`` key every recording channel below maps onto.
SYSTEM = "transmission_driveline"

#: recording channel id -> {name, unit, aliases, known_good_id}.
#: ``aliases`` are matched against a recording's own column names
#: (:func:`_best_match`). ``known_good_id`` names the ``mes.known_good`` row
#: (if any) this parameter is graded against -- only ATF temperature
#: (``tcm_04fe``) has one today; every other row is graded "unknown" by
#: design (see module docstring), not from a gap in this table.
RECORDING_CHANNELS: dict[str, dict[str, Any]] = {
    "rec_atf_temp": {
        "name": "ATF temperature (MES recording)", "unit": "C",
        "aliases": ("gearbox oil temp", "transmission oil temp",
                    "transmission fluid temp", "atf temp"),
        "known_good_id": "tcm_04fe",
    },
    "rec_gear_engaged": {
        "name": "Gear engaged (MES recording)", "unit": "",
        "aliases": ("gear engaged", "selected gear", "current gear", "actual gear"),
        "known_good_id": None,
    },
    "rec_tc_slip": {
        "name": "Torque converter slip (MES recording)", "unit": "rpm",
        "aliases": ("converter slip", "torque converter slip", "tc slip"),
        "known_good_id": None,
    },
    "rec_tc_lockup": {
        "name": "Torque converter lock-up (MES recording)", "unit": "",
        "aliases": ("converter lock-up", "converter lockup", "lock-up clutch",
                    "converter clutch"),
        "known_good_id": None,
    },
    "rec_line_pressure": {
        "name": "Line pressure (MES recording)", "unit": "bar",
        "aliases": ("line pressure",),
        "known_good_id": None,
    },
    "rec_input_speed": {
        "name": "Input shaft speed (MES recording)", "unit": "rpm",
        "aliases": ("input speed", "turbine speed"),
        "known_good_id": None,
    },
    "rec_output_speed": {
        "name": "Output shaft speed (MES recording)", "unit": "rpm",
        "aliases": ("output speed",),
        "known_good_id": None,
    },
}


def _best_match(names: list[str], alias: str) -> Optional[str]:
    """Shortest case-insensitive substring match of ``alias`` among
    ``names`` -- small, deliberate duplicate of ``mes.known_good._best_
    match`` (private to that module's own observed-ranges pipeline)."""
    candidates = [n for n in names if alias in n.lower()]
    if not candidates:
        return None
    for n in candidates:
        if n.lower() == alias:
            return n
    return min(candidates, key=len)


def _grade(value: float, normal: Optional[list[float]], alarm: Optional[list[float]],
          direction: str) -> str:
    """Small, deliberate duplicate of ``liveboard_bridge._grade`` -- kept
    separate rather than imported so this module never has to import
    ``liveboard_bridge`` (which imports this one, to add recording
    channels to the board; importing back would make the two modules
    mutually dependent for no real benefit, just to grade one number)."""
    if not normal:
        return "unknown"
    lo, hi = normal
    a_lo, a_hi = (alarm or (None, None))
    if direction == "above":
        if value <= hi:
            return "ok"
        return "excessive" if (a_hi is not None and value > a_hi) else "moderate"
    if direction == "below":
        if value >= lo:
            return "ok"
        return "excessive" if (a_lo is not None and value < a_lo) else "moderate"
    if lo <= value <= hi:
        return "ok"
    if value < lo:
        return "excessive" if (a_lo is not None and value < a_lo) else "moderate"
    return "excessive" if (a_hi is not None and value > a_hi) else "moderate"


def _scan_recordings() -> list[dict[str, Any]]:
    if csvlog_mod is None:
        return []
    try:
        return csvlog_mod.list_recordings()
    except Exception:  # noqa: BLE001 -- recording discovery must never raise
        return []


def _latest_value(aliases: tuple[str, ...]) -> Optional[dict[str, Any]]:
    """The newest recording (by mtime) with a column matching one of
    ``aliases``, and that column's last numeric sample -- ``None`` if no
    recording on this install has a matching column, or none has ever
    been made here at all."""
    if csvlog_mod is None:
        return None
    recs = sorted(_scan_recordings(), key=lambda r: r.get("_mtime", 0), reverse=True)
    for rec_info in recs:
        name = rec_info.get("file")
        if not name or rec_info.get("parse_error"):
            continue
        try:
            rec = csvlog_mod.load_named(name)
        except Exception:  # noqa: BLE001 -- one bad recording must not block the rest
            continue
        col_names = [c.name for c in rec.columns]
        for alias in aliases:
            match = _best_match(col_names, alias)
            if not match:
                continue
            col = rec.find_column(match)
            nums = rec.numbers(str(col.index))
            if not nums:
                continue
            _, value = nums[-1]
            return {"value": value, "unit": col.unit, "recording": name,
                   "recorded_at": rec_info.get("mtime")}
    return None


def transmission_recording_channels() -> list[dict[str, Any]]:
    """One entry per :data:`RECORDING_CHANNELS` row this install's MES
    recordings actually have a matching column for -- ``[]`` if no CSV
    recording has ever been made here (the common case today; see
    ``mes.csvlog``'s own docstring) or none mentions a ZF 8HP parameter.
    """
    out: list[dict[str, Any]] = []
    for cid, spec in RECORDING_CHANNELS.items():
        found = _latest_value(spec["aliases"])
        if found is None:
            continue
        kg_id = spec["known_good_id"]
        band = known_good_bridge.sourced_band(kg_id) if kg_id else None
        grade = "unknown"
        if band is not None:
            row = known_good_bridge.known_good_for(kg_id) or {}
            grade = _grade(float(found["value"]), row.get("normal"), row.get("alarm"),
                          row.get("direction") or "both")
        out.append({
            "id": cid, "name": spec["name"], "unit": found.get("unit") or spec["unit"],
            "value": found["value"], "kind": "recording", "source": "MES",
            "system": SYSTEM, "grade": grade, "band": band,
            "recording": found["recording"], "recorded_at": found["recorded_at"],
            "note": (f"from MES recording {found['recorded_at']} "
                    f"({found['recording']}) -- not the live serial stream"),
        })
    return out


def latest_atf_temp() -> Optional[dict[str, Any]]:
    """Just the newest recorded ATF-temperature sample, for the health
    report's transmission row (``"from MES recording <date>"``) -- ``None``
    if no recording on this install has one."""
    found = _latest_value(RECORDING_CHANNELS["rec_atf_temp"]["aliases"])
    if found is None:
        return None
    return {"value_c": found["value"], "recorded_at": found["recorded_at"],
           "recording": found["recording"]}


__all__ = ["SYSTEM", "RECORDING_CHANNELS", "transmission_recording_channels",
          "latest_atf_temp"]
