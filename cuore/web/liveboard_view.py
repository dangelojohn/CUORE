"""Mechanic view of the Live board: what the page shows before any session runs.

Pure functions over ``liveboard_bridge.board()`` plus the open job's own words (codes, unresolved symptoms,
hypotheses), read the way ``fuse_direct`` reads the job. Builds, for the template:

* the one-line call (not connected / connected), with the cable for this job's modules;
* a "For this job" group of key readings, each with the reason it is there;
* one row per measured quantity (best source first, the rest folded as "other sources");
* the raw rows (bitmaps, formulas, "pids supported") kept out of the mechanic view;
* page-only search (labels, channel ids, units, groups), matches first.

Nothing here talks to the car. Every loader degrades to empty rather than failing the page.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from . import page_search as ps

HINT = "Try a reading (coolant, fuel level, rpm), a channel id, a unit (kPa) or a group (temperatures)."
CONF_WORD = {
    "CORROBORATED": "confirmed by 2+ sources",
    "SINGLE-SOURCE": "one source only",
}
_MODULE_PREFIX = re.compile(r"^(ecm|bcm|tcm|ipc|rfhub|esim)_")
_RAW_NAME = re.compile(r"\(\(|\)\)|\*\s*256|/\s*800|pids? supported|bitmap|\bformula\b", re.I)
_RAW_UNITS = {"bitmap", "enum", "code"}
_RAW_IDS = re.compile(r"^(pids_supported|monitor_status|o2_sensors_present|obd_standard|esim_status)")

# (quantity key, regex on "id | name", label) -- first match wins; anything else is its own quantity.
QUANTITIES: tuple[tuple[str, str, str], ...] = (
    ("rpm", r"^(engine_rpm|ecm_1000)\b|^engine rpm$", "Engine speed"),
    ("speed", r"^(vehicle_speed|ecm_1002)\b|^vehicle speed$", "Vehicle speed"),
    ("coolant", r"coolant", "Coolant temperature"),
    ("oil_temp", r"oil temp", "Engine oil temperature"),
    ("iat", r"^(intake_air_temp|ecm_1935|ecm_3a58)\b|intake air temp(?!.*sensors)", "Intake air temperature"),
    ("battery", r"^(battery_voltage|ecm_1955|bcm_1004|control_module_voltage)\b|battery voltage", "Battery voltage"),
    ("fuel_level", r"^(fuel_level|ecm_1001)\b|fuel (tank )?level", "Fuel level"),
    ("rail", r"^fuel_rail_pressure", "Fuel rail pressure"),
    ("evap_p", r"^evap_vapor_pressure", "Evap vapour pressure"),
    ("throttle", r"^(throttle_position|ecm_1924)$|^throttle position(, sensor 1)?$", "Throttle position"),
    ("baro", r"^(barometric_pressure|ecm_1956)\b", "Barometric pressure"),
    ("boost", r"^(boost|ecm_195a)$|^boost \(", "Boost pressure"),
    ("run_time", r"^(engine_run_time|runtime_since_start|ecm_1009)\b", "Time since start"),
)
_QRE = [(k, re.compile(rx, re.I), lab) for k, rx, lab in QUANTITIES]

# Job words -> key readings. (rule label, regex over the job's words, channel ids in the order to show them)
JOB_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("EVAP", r"evap|\bp04(?:[3-5]\d)\b|purge|vapou?r|fuel cap|smoke test|\bp0496\b|esim",
     ("fuel_level", "evap_vapor_pressure", "commanded_evap_purge", "esim_switch_state")),
    ("cooling", r"coolant|overheat|thermostat|\bp0(?:11[5-9]|12[5-8]|217)\b",
     ("engine_coolant_temp", "engine_oil_temp")),
    ("fuel trim / misfire", r"misfire|shudder|rough idle|lean|rich|fuel trim|\bp03\d\d\b|\bp01[67]\d\b",
     ("short_fuel_trim_b1", "long_fuel_trim_b1", "engine_rpm", "throttle_position")),
    ("charging / battery", r"battery|charging|alternator|\bibs\b|no start|\bp056\d\b|\bu?0?1\d\d\d\b.*volt",
     ("battery_voltage",)),
    ("gearbox", r"gearbox|transmission|shift|\bp07\d\d\b|\btcm\b", ("tcm_04fe", "tcm_1018")),
    ("boost", r"boost|turbo|wastegate|\bp0(?:234|299|243)\b", ("intake_map", "boost", "boost_pressure_control")),
    ("EGR", r"\begr\b|\bp040\d\b", ("commanded_egr", "egr_error", "egr_temperature")),
    ("oxygen sensor / catalyst", r"o2 sensor|oxygen|catalyst|\bp013\d\b|\bp042\d\b",
     ("o2_b1s1_voltage", "catalyst_temp_b1s1")),
)
_RULES = [(lab, re.compile(rx, re.I), ids) for lab, rx, ids in JOB_RULES]


# --- channels ---------------------------------------------------------------

_UNIT_MAP = {"c": "°C", "degc": "°C", "deg c": "°C", "celsius": "°C", "°c": "°C",
             "f": "°F", "degf": "°F", "°f": "°F",
             "kpa": "kPa", "bar": "bar", "psi": "psi", "v": "V", "mv": "mV", "a": "A", "%": "%", "pct": "%",
             "percent": "%", "rpm": "rpm", "km/h": "km/h", "kph": "km/h", "kmh": "km/h", "mph": "mph",
             "s": "s", "ms": "ms", "g/s": "g/s", "l/h": "L/h"}


def fmt_unit(unit: Any) -> str:
    """One unit formatter for the whole board: "C" -> "°C", "kpa" -> "kPa", "KPH" -> "km/h" ..."""
    u = str(unit or "").strip()
    return _UNIT_MAP.get(u.lower(), u)


def plain_name(ch: dict[str, Any]) -> str:
    name = str(ch.get("name") or ch.get("id") or "").strip().replace("vapor", "vapour")
    return (name[:1].upper() + name[1:]) if name else str(ch.get("id") or "")


def conf_of(ch: dict[str, Any]) -> str:
    return str(((ch.get("band") or {}).get("confidence")) or "").upper().replace("_", "-").replace(" ", "-")


def conf_word(ch: dict[str, Any]) -> str:
    return CONF_WORD.get(conf_of(ch), "")


def is_raw(ch: dict[str, Any]) -> bool:
    return bool(_RAW_IDS.match(str(ch.get("id") or "")) or _RAW_NAME.search(str(ch.get("name") or ""))
                or str(ch.get("unit") or "").lower() in _RAW_UNITS)


def quantity(ch: dict[str, Any]) -> tuple[str, str]:
    """(key, label) -- the measured quantity this channel reports."""
    cid, name = str(ch.get("id") or ""), str(ch.get("name") or "")
    for key, rx, lab in _QRE:
        if rx.search(cid) or rx.search(name):
            return key, lab
    return "id:" + cid, plain_name(ch)


def _rank(ch: dict[str, Any], order: int) -> tuple[int, int, int]:
    c = {"CORROBORATED": 0, "SINGLE-SOURCE": 1}.get(conf_of(ch), 2)
    return (c, 1 if _MODULE_PREFIX.match(str(ch.get("id") or "")) else 0, order)


def band_note(ch: dict[str, Any]) -> str:
    """"88-105 C normal, >130 alarm" -- the numbers only; how sure is a separate chip."""
    b = ch.get("band") or {}
    unit = fmt_unit(ch.get("unit"))
    bits = []
    n = b.get("normal")
    if isinstance(n, (list, tuple)) and len(n) == 2 and n[0] is not None and n[1] is not None:
        bits.append(f"{n[0]:g}-{n[1]:g} {unit} normal".replace("  ", " "))
    a = b.get("alarm") or [None, None]
    d = b.get("direction") or "both"
    al = []
    if d in ("below", "both") and a[0] is not None:
        al.append(f"<{a[0]:g}")
    if d in ("above", "both") and a[1] is not None:
        al.append(f">{a[1]:g}")
    if al:
        bits.append(" or ".join(al) + " alarm")
    return ", ".join(bits)


def _row_text(ch: dict[str, Any], group_label: str) -> str:
    return ps.haystack([ch.get("id"), ch.get("name"), plain_name(ch), ch.get("unit"), group_label,
                        quantity(ch)[1]])


def _item(chs: list[tuple[int, dict[str, Any]]], group_label: str) -> dict[str, Any]:
    """One quantity: best source first, the rest as ``others``."""
    chs = sorted(chs, key=lambda p: _rank(p[1], p[0]))
    best = chs[0][1]
    key, lab = quantity(best)
    return {"key": key, "label": lab if not key.startswith("id:") else plain_name(best), "ch": best,
            "others": [c for _, c in chs[1:]], "group": group_label}


def view_channel(ch: dict[str, Any]) -> dict[str, Any]:
    return {"id": ch.get("id"), "name": plain_name(ch), "unit": fmt_unit(ch.get("unit")), "note": band_note(ch),
            "conf": conf_word(ch)}


# --- the job ----------------------------------------------------------------

def job_words(codes: list[str], symptoms: list[dict[str, Any]], jobs: list[dict[str, Any]]) -> str:
    """Everything the open job says, as one lower-case string. Resolved symptoms are already excluded
    (``fuse_direct.job_inputs``); refuted and deleted hypotheses are left out here."""
    parts = [str(c) for c in codes or []] + [str(s.get("text") or "") for s in symptoms or []]
    for j in jobs or []:
        parts.append(str(j.get("complaint") or ""))
        for h in j.get("hypotheses") or []:
            if h.get("deleted") or h.get("status") == "refuted":
                continue
            parts += [str(h.get("system") or ""), str(h.get("text") or "")[:400]]
    return " | ".join(parts).lower()


def load_job(vin: str, dossier: dict[str, Any]) -> dict[str, Any]:
    """{"codes", "symptoms", "jobs"} from the car's own records. Never raises."""
    out: dict[str, Any] = {"codes": [], "symptoms": [], "jobs": []}
    try:
        from ..services import fuse_direct as fd, mes_bridge
        out["codes"] = mes_bridge.open_codes_for(dossier)
        out["symptoms"], _ = fd.job_inputs(vin, out["codes"], dossier)
    except Exception:  # noqa: BLE001
        pass
    try:
        from mes import jobs
        out["jobs"] = jobs.open_jobs(vin)
    except Exception:  # noqa: BLE001
        pass
    return out


def job_picks(job: dict[str, Any], available: set[str]) -> list[dict[str, str]]:
    """[{"id", "why"}] key readings for the open job, in rule order, only channels this board has."""
    text = job_words(job.get("codes") or [], job.get("symptoms") or [], job.get("jobs") or [])
    codes = [str(c).split("-")[0] for c in job.get("codes") or []]
    picks: list[dict[str, str]] = []
    seen: set[str] = set()
    for lab, rx, ids in _RULES:
        if not rx.search(text):
            continue
        hit = [c for c in codes if rx.search(c.lower())]
        why = f"{lab} job" + (f" (open code {', '.join(hit[:3])})" if hit else "")
        for cid in ids:
            if cid in available and cid not in seen:
                seen.add(cid)
                picks.append({"id": cid, "why": why})
    return picks


def cable_line(ids: list[str]) -> str:
    """Which lead this job's modules need. The board only lists the OBD-II (engine CAN) channels and the ESIM probe."""
    obd = [i for i in ids if not i.startswith("esim_")]
    probe = [i for i in ids if i.startswith("esim_")]
    bits = []
    if obd or not ids:
        bits.append("the OBD-II lead in the car's port (engine ECM readings)")
    if probe:
        bits.append("the ESIM probe on its serial lead")
    return "Cable for this job: " + " and ".join(bits) + "."


# --- the page ---------------------------------------------------------------

def build(board: dict[str, Any], job: Optional[dict[str, Any]] = None, q: str = "") -> dict[str, Any]:
    q = ps.clean_q(q)
    groups_in = board.get("groups") or []
    by_id = {c["id"]: (g, c) for g in groups_in for c in g.get("channels") or []}
    picks = job_picks(job or {}, set(by_id))
    pick_ids = {p["id"] for p in picks}

    # one list of (order, group label, channel) -> quantity buckets, a bucket living in its best source's group
    buckets: dict[str, list[tuple[int, dict[str, Any], str]]] = {}
    raw: list[dict[str, Any]] = []
    order = 0
    for g in groups_in:
        for c in g.get("channels") or []:
            order += 1
            if is_raw(c):
                raw.append(c)
                continue
            buckets.setdefault(quantity(c)[0], []).append((order, c, g.get("label") or g.get("id") or ""))
    items_by_group: dict[str, list[dict[str, Any]]] = {}
    group_order = [g.get("label") or g.get("id") or "" for g in groups_in]
    item_of_id: dict[str, dict[str, Any]] = {}
    for key, lst in buckets.items():
        ranked = sorted(lst, key=lambda p: _rank(p[1], p[0]))
        it = _item([(o, c) for o, c, _ in lst], ranked[0][2])
        for _, c, _ in lst:
            item_of_id[c["id"]] = it
        items_by_group.setdefault(it["group"], []).append(it)

    def vi(it: dict[str, Any], why: str = "") -> dict[str, Any]:
        gl = it["group"]
        d = view_channel(it["ch"])
        d.update({"label": it["label"], "others": [view_channel(o) for o in it["others"]], "why": why,
                  "text": " | ".join([_row_text(it["ch"], gl)] + [_row_text(o, gl) for o in it["others"]])})
        return d

    # job group: the item holding each picked channel (a pick that is an "other" source still shows its quantity)
    job_items: list[dict[str, Any]] = []
    used: set[int] = set()
    for p in picks:
        it = item_of_id.get(p["id"])
        if it is None:
            continue   # a hidden raw channel is never a key reading
        if id(it) in used:
            continue
        used.add(id(it))
        job_items.append(vi(it, p["why"]))

    rest: dict[str, list[dict[str, Any]]] = {}
    for gl in group_order:
        for it in items_by_group.get(gl, []):
            if id(it) not in used:
                rest.setdefault(gl, []).append(vi(it))

    matches: list[dict[str, Any]] = []
    if q:
        flat = [(gl, r) for gl, rows in rest.items() for r in rows]
        job_hit = [r for r in job_items if ps.matches(q, r["text"], ())]
        job_items = [r for r in job_items if r not in job_hit]
        matches = job_hit + [r for gl, r in flat if ps.matches(q, r["text"] + " | " + gl, ())]
        mset = {id(r) for r in matches}
        rest = {gl: [r for r in rows if id(r) not in mset] for gl, rows in rest.items()}
    groups = [{"label": gl, "rows": rest[gl], "open": False} for gl in group_order if rest.get(gl)]
    # a group is listed once even when two board groups share a label
    seen_l: set[str] = set()
    groups = [g for g in groups if not (g["label"] in seen_l or seen_l.add(g["label"]))]

    raw_rows = [view_channel(c) for c in raw
                if not q or ps.matches(q, _row_text(c, ""), ())]
    watch = [r["label"] for r in job_items]
    call_off = "Connect the car, then Start."
    call_on = ("Watching live. For this job, watch: " + ", ".join(w.lower() for w in watch) + "."
               if watch else "Watching live. Open a group below, or search for a reading.")
    return {
        "q": q, "hint": HINT, "job_rows": job_items, "job_why": sorted({p["why"] for p in picks}),
        "matches": matches, "groups": groups, "raw": raw_rows,
        "n_rows": len(job_items) + len(matches) + sum(len(g["rows"]) for g in groups),
        "call_off": call_off, "call_on": call_on,
        "cable": cable_line([p["id"] for p in picks]) if picks else cable_line([]),
        "has_job": bool(picks),
    }


__all__ = ["build", "load_job", "job_picks", "quantity", "is_raw", "plain_name", "band_note", "cable_line"]
