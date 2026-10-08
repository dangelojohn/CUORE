"""The mechanic-vs-driver timeline: codes on one axis, what was actually felt
on the other.

The dossier (``dossier_bridge``) answers "what is wrong with this car right
now". This module answers a different question a mechanic needs before ever
touching a wrench: across the whole history, which codes lined up with a
driver noticing something, and which never did? For EVAP in particular the
honest answer is almost always "nothing was ever felt" -- the fault is real,
the codes keep returning, and there is still no complaint to chase. Burying
that fact inside a code table invites a mechanic to go looking for a
drivability symptom that was never there; ``build_timeline`` makes the
absence itself the headline finding.

Like ``dossier_bridge``, this is a ``cuore/services/*_bridge.py`` module, so
it is allowed to import the ``mes`` package directly (``mes.symptoms`` and
``mes.code_feel`` are new, small, and have no existing bridge; ``mes.service``
is read the same way ``service_bridge.py`` already reads it) alongside the
``mes_bridge``/``service_bridge`` facades for everything that already has
one. Nothing here re-implements chronic/returned classification, TSB
matching or freeze-frame flagging -- it only reshapes what those already
compute, plus two new attested-report stores, into one timeline.

``build_timeline`` is the main entry point; ``add_symptom``/``symptoms``/
``hide_symptom`` and ``code_feel`` back the router in ``cuore/api/timeline.py``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import mes_bridge
from .errors import BadRequest
from ..live import store as live_store

from mes import code_feel as code_feel_mod  # noqa: E402
from mes import service as service_mod  # noqa: E402
from mes import symptoms as symptoms_mod  # noqa: E402
from mes.symptoms import CONDITIONS, SYMPTOM_TAGS  # noqa: E402

#: EVAP codes this car's corpus and TSB catalogue recognise as one system
#: fault. P0457 (fuel cap) is included here even though ``mes.knowledge``'s
#: own ``EVAP_FAMILY`` omits it -- the timeline's EVAP lane is about "any
#: EVAP leak/purge code", not the narrower TSB-cross-reference family.
_EVAP_CODES = frozenset({"P0440", "P0441", "P0455", "P0456", "P0457", "P1CEA"})

#: How close a symptom report has to sit to a code occurrence to count as
#: "near" it, in either direction.
WINDOW_DAYS = 3

_DRIVABILITY_TAGS = frozenset({"rough_idle", "hesitation", "loss_of_power", "hard_start"})

_LANE_LABELS = {
    "mil": "MIL (check-engine light)",
    "evap": "EVAP",
    "network": "Network / communication",
    "body": "Body",
    "chassis": "Chassis",
    "engine_other": "Engine (other)",
    "clears": "Clears",
    "symptoms": "Reported symptoms",
    "notes": "Technician notes",
    "work": "Work performed",
    "conditions": "Conditions at code-set",
}
_LANE_KIND = {
    "mil": "points", "evap": "bars", "network": "bars", "body": "bars",
    "chassis": "bars", "engine_other": "bars", "clears": "points",
    "symptoms": "points", "notes": "points", "work": "points",
    "conditions": "points",
}
_FAMILY_DISPLAY = {"evap": "EVAP", "network": "network", "body": "body",
                  "chassis": "chassis", "engine_other": "engine_other"}

_BASE_RE = re.compile(r"^([PBCU][0-9A-F]{4})", re.IGNORECASE)


def _base(code: str) -> str:
    m = _BASE_RE.match((code or "").strip().upper())
    return m.group(1) if m else (code or "").strip().upper()


def _num(display: Any) -> Optional[float]:
    if display is None:
        return None
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(display))
    return float(m.group(1)) if m else None


def _parse_dt(s: Any) -> Optional[datetime]:
    """Tolerant parse of the handful of timestamp shapes in play here:
    MES's ``YYYY-MM-DD HH:MM:SS``, a symptom's ISO ``...T...`` or
    ``...  ...``, or a bare date."""
    if not s:
        return None
    text = str(s).strip().replace("T", " ")
    if len(text) == 10:
        text += " 00:00:00"
    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _family_of(base: str) -> str:
    if base in _EVAP_CODES:
        return "evap"
    letter = base[:1]
    if letter == "U":
        return "network"
    if letter == "B":
        return "body"
    if letter == "C":
        return "chassis"
    return "engine_other"


# --- symptom reports (mes.symptoms) ------------------------------------------


def add_symptom(vin: str, at: str, *, odometer_km: Optional[float] = None,
                reporter: str = "driver", tags: Optional[list[str]] = None,
                conditions: Optional[list[str]] = None,
                text: str = "") -> dict[str, Any]:
    """Record what a person actually felt. Raises :class:`BadRequest` on any
    validation error -- unknown tag/condition, drives_normally combined with
    a drivability tag, missing vin/at."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    try:
        return symptoms_mod.add(vin, at, odometer_km=odometer_km, reporter=reporter,
                                tags=tags, conditions=conditions, text=text)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def symptoms(vin: str, *, include_hidden: bool = False) -> dict[str, Any]:
    """Symptom reports for this VIN, oldest first."""
    if not vin.strip():
        raise BadRequest("a VIN is required")
    return {"vin": vin, "symptoms": symptoms_mod.load(vin, include_hidden=include_hidden)}


def hide_symptom(id: str) -> dict[str, Any]:
    """Hide a symptom report (soft delete). Never rewrites history."""
    try:
        return symptoms_mod.hide(id)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


# --- "what would the driver feel" + this car's own pattern ------------------


def _pattern_for(occurrences: int, occurrence_dts: list[Optional[datetime]],
                 all_symptoms: list[dict[str, Any]],
                 *, window_days: int = WINDOW_DAYS) -> dict[str, Any]:
    """How this car's own symptom reports sit against one set of code
    occurrences -- shared by the per-code ``code_feel`` endpoint and the
    per-family ``correlation`` entries in :func:`build_timeline`.

    ``occurrences`` is the caller's own count of distinct sessions (a
    session can hold several of a family's codes at once, so it is not
    simply ``len(occurrence_dts)``); ``occurrence_dts`` is only used here to
    find symptom reports that fall within ``window_days`` of any of them.
    """
    window = timedelta(days=window_days)
    near: list[dict[str, Any]] = []
    for s in all_symptoms:
        sdt = _parse_dt(s.get("at"))
        if sdt is None:
            continue
        if any(odt is not None and abs(sdt - odt) <= window for odt in occurrence_dts):
            near.append(s)

    by_tag: dict[str, int] = {}
    drives_normally_near = 0
    for s in near:
        tags = s.get("tags") or []
        if "drives_normally" in tags:
            drives_normally_near += 1
        for t in tags:
            by_tag[t] = by_tag.get(t, 0) + 1

    return {
        "occurrences": occurrences,
        "symptom_reports_near": len(near),
        "by_tag": by_tag,
        "drives_normally_near": drives_normally_near,
    }


def _verdict_for(pattern: dict[str, Any]) -> str:
    if pattern["symptom_reports_near"] == 0:
        return "no symptom reports yet"
    other_tags = {t: c for t, c in pattern["by_tag"].items()
                  if t != "drives_normally" and c > 0}
    if not other_tags:
        return "no reported symptom"
    top = sorted(other_tags, key=lambda t: (-other_tags[t], t))
    return "co-occurs with " + ", ".join(top[:3])


def code_feel(vin: str, code: str) -> dict[str, Any]:
    """"What would the driver feel?" for one code, next to what this car's
    own symptom reports actually say near its occurrences.

    Passes ``include_siblings=True`` into ``mes.code_feel.lookup`` so a
    sourced sibling-platform (Grecale/Levante) finding would be returned
    under ``feel["siblings"]``, each labeled "from <Model> code_feel:
    verify fit" via this VIN's own model (``mes.platform.model_for_vin``).
    ``mes.code_feel`` currently tags nothing to a sibling model (every
    entry there is a physical/engineering finding, not vehicle-specific --
    see its module docstring), so ``siblings`` is always ``[]`` today.
    """
    if not vin.strip():
        raise BadRequest("a VIN is required")
    base = _base(code)
    feel = code_feel_mod.lookup(base, include_siblings=True)
    if feel is not None:
        try:
            from mes import platform as platform_mod
            model = platform_mod.model_for_vin(vin)
        except Exception:  # noqa: BLE001
            model = None
        if model and model != platform_mod.UNKNOWN:
            for sib in feel.get("siblings", []):
                sib_of = sib.get("sibling_of")
                if sib_of:
                    sib["label"] = f"from {str(sib_of).title()} code_feel: verify fit"

    occ_dts: list[Optional[datetime]] = []
    occ_files: set[str] = set()
    try:
        dossier = mes_bridge.workup(vin=vin)
    except Exception:  # noqa: BLE001 -- a code page must still render with no corpus
        dossier = {}
    history = dossier.get("history") or {}
    for bucket in ("chronic", "returned_after_clear", "seen_once"):
        for rec in history.get(bucket, []):
            if _base(rec.get("dtc", "")) != base:
                continue
            for occ in rec.get("occurrences", []):
                occ_dts.append(_parse_dt(occ.get("timestamp")))
                if occ.get("file"):
                    occ_files.add(occ["file"])

    all_symptoms = symptoms_mod.load(vin)
    occurrences = len(occ_files) if occ_files else len([d for d in occ_dts if d is not None])
    pattern = _pattern_for(occurrences, occ_dts, all_symptoms)
    return {"code": base, "feel": feel, "pattern": pattern}


# --- lane builders ------------------------------------------------------------


def _family_occurrences(dossier: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Every DTC occurrence in this car's real-log history, grouped by the
    timeline's code-family lanes. One entry per (code, session)."""
    by_family: dict[str, list[dict[str, Any]]] = {
        "evap": [], "network": [], "body": [], "chassis": [], "engine_other": [],
    }
    history = dossier.get("history") or {}
    for bucket in ("chronic", "returned_after_clear", "seen_once"):
        for rec in history.get(bucket, []):
            base = _base(rec.get("dtc", ""))
            if not base:
                continue
            family = _family_of(base)
            for occ in rec.get("occurrences", []):
                by_family[family].append({
                    "ts": occ.get("timestamp"), "code": base,
                    "status": occ.get("status"), "odo": occ.get("odometer_km"),
                    "file": occ.get("file"),
                })
    for fam in by_family:
        by_family[fam].sort(key=lambda o: o["ts"] or "")
    return by_family


def _split_runs(occs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Contiguous sightings, split wherever a session ended with the code
    cleared and not immediately returning -- a clear closes the run; a
    ``returned`` status continues it (the fault reproduced)."""
    runs: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for occ in occs:
        current.append(occ)
        if occ.get("status") == "cleared":
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def _run_event(run: list[dict[str, Any]]) -> dict[str, Any]:
    codes = sorted({o["code"] for o in run})
    files = sorted({o["file"] for o in run if o.get("file")})
    t = run[0]["ts"]
    t_end = run[-1]["ts"] if run[-1]["ts"] != t else None
    last_status = run[-1].get("status")
    if last_status == "cleared":
        severity = "cleared"
    elif last_status in ("returned", "stored", "uncleared"):
        severity = "active"
    else:
        severity = "info"
    odo_vals = [o["odo"] for o in run if o.get("odo") is not None]
    return {
        "t": t, "t_end": t_end, "odo": (odo_vals[0] if odo_vals else None),
        "label": "/".join(codes),
        "detail": f"{len(files) or len(run)} session(s): " + ", ".join(codes),
        "severity": severity, "href": None,
    }


def _family_lane(family: str, occs: list[dict[str, Any]]) -> dict[str, Any]:
    events = [_run_event(run) for run in _split_runs(occs)]
    return {"id": family, "label": _LANE_LABELS[family], "kind": _LANE_KIND[family],
           "events": events}


def _mil_lane(vin: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    try:
        obs = live_store.recent_observations(200, vin=vin, kind="readiness")
    except Exception:  # noqa: BLE001 -- the timeline must render without a live link
        obs = []
    for o in obs:
        if not live_store.is_from_car(o):
            continue
        since = (o.get("data") or {}).get("since_clear") or {}
        mil_on = since.get("mil_on")
        if mil_on is None:
            continue
        events.append({
            "t": o.get("at"), "t_end": None, "odo": None,
            "label": "MIL ON" if mil_on else "MIL OFF",
            "detail": "live readiness read" + (f" ({o['at']})" if o.get("at") else ""),
            "severity": "active" if mil_on else "info", "href": None,
        })
    if not events:
        return {"id": "mil", "label": _LANE_LABELS["mil"], "kind": _LANE_KIND["mil"],
               "events": [], "detail": "MIL state not in the logs"}
    return {"id": "mil", "label": _LANE_LABELS["mil"], "kind": _LANE_KIND["mil"],
           "events": events}


def _clears_lane(by_family: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    by_ts: dict[str, set[str]] = {}
    for occs in by_family.values():
        for o in occs:
            if o.get("status") == "cleared" and o.get("ts"):
                by_ts.setdefault(o["ts"], set()).add(o["code"])
    events = [
        {"t": ts, "t_end": None, "odo": None,
         "label": "cleared: " + ", ".join(sorted(codes)),
         "detail": ", ".join(sorted(codes)) + " cleared", "severity": "cleared",
         "href": None}
        for ts, codes in sorted(by_ts.items())
    ]
    return {"id": "clears", "label": _LANE_LABELS["clears"], "kind": _LANE_KIND["clears"],
           "events": events}


def _symptoms_lane(all_symptoms: list[dict[str, Any]]) -> dict[str, Any]:
    events = []
    for s in all_symptoms:
        tags = s.get("tags") or []
        normal = "drives_normally" in tags
        label = "drives normally" if normal else (", ".join(tags) or "symptom reported")
        events.append({
            "t": s.get("at"), "t_end": None, "odo": s.get("odometer_km"),
            "label": label, "detail": s.get("text") or label,
            "severity": "no_symptom" if normal else "symptom", "href": None,
        })
    return {"id": "symptoms", "label": _LANE_LABELS["symptoms"],
           "kind": _LANE_KIND["symptoms"], "events": events}


def _notes_lane(vin: str) -> dict[str, Any]:
    events = []
    try:
        for n in mes_bridge.notes(vin).get("notes", []):
            text = n.get("text") or ""
            events.append({
                "t": n.get("at"), "t_end": None, "odo": None,
                "label": (text[:60] + "...") if len(text) > 60 else text,
                "detail": text, "severity": "info", "href": None,
            })
    except Exception:  # noqa: BLE001
        pass
    return {"id": "notes", "label": _LANE_LABELS["notes"], "kind": _LANE_KIND["notes"],
           "events": events}


def _work_lane(vin: str) -> dict[str, Any]:
    events = []
    for rec in service_mod.load(vin):
        data = rec.get("data") or {}
        label = f"service: {rec.get('kind')}"
        detail = data.get("work_done") or data.get("category") or rec.get("kind") or ""
        events.append({
            "t": rec.get("at") or data.get("date"), "t_end": None,
            "odo": data.get("odometer_km"), "label": label, "detail": detail,
            "severity": "work", "href": None,
        })

    try:
        runs = mes_bridge.actuator_history(vin=vin).get("runs", [])
    except Exception:  # noqa: BLE001
        runs = []
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in runs:
        ts = r.get("timestamp") or ""
        day = ts[:10]
        if not day:
            continue
        by_day.setdefault(day, []).append(r)
    for day, day_runs in by_day.items():
        ops = sorted({r.get("operation") or "" for r in day_runs if r.get("operation")})
        events.append({
            "t": min(r.get("timestamp") or (day + " 00:00:00") for r in day_runs),
            "t_end": None, "odo": None,
            "label": f"{len(day_runs)} actuator test(s)/adjustment(s)",
            "detail": ", ".join(ops) or "actuator tests/adjustments",
            "severity": "work", "href": None,
        })

    try:
        dealer_results = mes_bridge.dealer_results(vin).get("results", [])
    except Exception:  # noqa: BLE001
        dealer_results = []
    for rec in dealer_results:
        events.append({
            "t": rec.get("at"), "t_end": None, "odo": None,
            "label": f"dealer: {rec.get('kind')}",
            "detail": rec.get("note") or str(rec.get("data") or ""),
            "severity": "work", "href": None,
        })

    events.sort(key=lambda e: e.get("t") or "")
    return {"id": "work", "label": _LANE_LABELS["work"], "kind": _LANE_KIND["work"],
           "events": events}


def _conditions_lane(vin: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The conditions lane, plus the raw warn-flagged rows (for ``findings``)."""
    events = []
    warnings: list[dict[str, Any]] = []
    try:
        frames = mes_bridge.freeze_frames(vin=vin).get("frames", [])
    except Exception:  # noqa: BLE001 -- NotFound when nothing has a freeze frame
        frames = []
    for f in frames:
        ff = f.get("freeze_frame") or {}
        fuel = _num(ff.get("Fuel level"))
        temp = _num(ff.get("Engine temperature"))
        cold = bool(temp is not None and temp < 40)
        parts = []
        flag = None
        if fuel is not None:
            parts.append(f"fuel {fuel:.0f}%")
            if not (15 <= fuel <= 85):
                bound = "below 15%" if fuel < 15 else "above 85%"
                flag = f"fuel {fuel:.0f}% is {bound} -- EVAP monitor cannot run"
                warnings.append({"code": _base(f.get("dtc") or ""), "fuel": fuel})
        if temp is not None:
            parts.append(f"engine temp {temp:.0f} C" + (" (cold start)" if cold else ""))
        detail = flag or (", ".join(parts) or "no fuel/engine-temperature fields captured")
        events.append({
            "t": f.get("timestamp"), "t_end": None, "odo": None,
            "label": f"{f.get('dtc')} freeze frame", "detail": detail,
            "severity": "warn" if flag else "info", "href": None,
        })
    lane = {"id": "conditions", "label": _LANE_LABELS["conditions"],
           "kind": _LANE_KIND["conditions"], "events": events}
    return lane, warnings


# --- the one entry point ------------------------------------------------------


def build_timeline(vin: str) -> dict[str, Any]:
    """Everything the mechanic-vs-driver timeline page needs, in one call.

    Only real data: every lane is built from the real-log corpus (simulation
    excluded by ``mes.catalog``'s own default), the live link's own
    observations, and the technician-entered stores -- nothing here
    synthesises a code occurrence or a symptom that was not actually
    recorded.
    """
    if not vin.strip():
        raise BadRequest("a VIN is required")

    dossier = mes_bridge.workup(vin=vin)
    identity = dossier.get("identity") or {}
    all_symptoms = symptoms_mod.load(vin)

    by_family = _family_occurrences(dossier)

    lanes = [
        _mil_lane(vin),
        _family_lane("evap", by_family["evap"]),
        _family_lane("network", by_family["network"]),
        _family_lane("body", by_family["body"]),
        _family_lane("chassis", by_family["chassis"]),
        _family_lane("engine_other", by_family["engine_other"]),
        _clears_lane(by_family),
        _symptoms_lane(all_symptoms),
        _notes_lane(vin),
        _work_lane(vin),
    ]
    conditions_lane, fuel_warnings = _conditions_lane(vin)
    lanes.append(conditions_lane)

    correlation: list[dict[str, Any]] = []
    findings: list[str] = []
    for family, occs in by_family.items():
        if not occs:
            continue
        occ_dts = [_parse_dt(o["ts"]) for o in occs]
        occurrences = len({o["file"] for o in occs if o.get("file")}) or len(occs)
        pattern = _pattern_for(occurrences, occ_dts, all_symptoms)
        if pattern["occurrences"] == 0:
            continue
        verdict = _verdict_for(pattern)
        codes = sorted({o["code"] for o in occs})
        display = _FAMILY_DISPLAY[family]
        correlation.append({
            "family": display, "codes": codes, "occurrences": pattern["occurrences"],
            "symptom_reports_near": pattern["symptom_reports_near"],
            "by_tag": pattern["by_tag"], "drives_normally_near": pattern["drives_normally_near"],
            "window_days": WINDOW_DAYS, "verdict": verdict,
        })
        if verdict == "no symptom reports yet":
            findings.append(
                f"{display} codes appeared in {pattern['occurrences']} session(s); "
                f"no driver symptom has been reported yet.")
        elif verdict == "no reported symptom":
            findings.append(
                f"{display} codes appeared in {pattern['occurrences']} session(s); "
                f"no driver symptom was reported within {WINDOW_DAYS} days of any of them.")
        elif verdict.startswith("co-occurs"):
            findings.append(f"{display} codes {verdict} within {WINDOW_DAYS} days.")

    if fuel_warnings:
        codes = []
        for w in fuel_warnings:
            if w["code"] not in codes:
                codes.append(w["code"])
        fuels = sorted(w["fuel"] for w in fuel_warnings)
        findings.append(
            f"{' and '.join(codes)} were set with the tank "
            f"{fuels[0]:.0f}-{fuels[-1]:.0f} % full.")

    return {
        "vin": vin,
        "range": {
            "start": identity.get("first_log"), "end": identity.get("last_log"),
            "odo_start": identity.get("odometer_first_km"),
            "odo_end": identity.get("odometer_last_km"),
        },
        "lanes": lanes,
        "correlation": correlation,
        "findings": findings,
        "symptom_tags": list(SYMPTOM_TAGS),
        "conditions": list(CONDITIONS),
    }


__all__ = ["WINDOW_DAYS", "add_symptom", "symptoms", "hide_symptom", "code_feel",
          "build_timeline"]
