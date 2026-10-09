"""``build_system_view(vin, key)`` -- the per-system dive-in page's whole
view model (``GET /v/{vin}/systems/{key}``, phase 1 of the Systems
dive-in; the existing one-page map stays ``cuore/web/templates/
systems.html`` + ``cuore/services/systems_bridge.py``).

This module invents nothing. Every field is a pass-through (or a thin
merge) of other bridges that already carry their own sourcing:

* ``systems_bridge`` -- the system record and this VIN's correlation
  (codes-by-system, co-occurrence, chains).
* ``dossier_bridge`` -- per-code ACTIVE/CLEARED_UNVERIFIED/STALE state
  (``build_view``'s ``codes`` rows -- see that module's ``_code_status``,
  the only place in ``cuore.services`` that computes this vocabulary) and
  readiness-monitor state.
* ``bench_bridge`` -- the car's one active blocker, if any.
* ``known_good_bridge`` / ``liveboard_bridge`` -- sourced bands and the
  live-board grading helper for this system's channels.
* ``electrical_bridge`` -- layout elements, per-code wiring paths and
  inspection records (the electrical layout's own system vocabulary does
  not match the 25-key systems graph 1:1 -- see ``_ELEMENT_TAGS_FOR``).
* ``parts_bridge`` -- catalogue entries for this system's part keys.
* ``jobs_bridge`` -- suggested and job-attached hypotheses, filtered to
  this system.
* ``cases_bridge`` -- case-memory matches for this system's open codes.
* ``experience_bridge`` -- others' experience links for this family.

Nothing here raises for a data gap -- a missing bridge, a code with no
systems mapping, an element with no sourced location all degrade to the
page's own UNKNOWN marker (see ``UNKNOWN_MARKER``) rather than a 500 or an
invented value. ``build_system_view`` returns ``None`` for a key that is
not in ``systems_bridge.systems()`` -- the route turns that into a 404.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401 -- side effect: puts `mes` on sys.path
from ..live import attested as attested_store
from ..live import learned as learned_store

from . import (
    bench_bridge,
    cases_bridge,
    dossier_bridge,
    electrical_bridge,
    experience_bridge,
    jobs_bridge,
    known_good_bridge,
    liveboard_bridge,
    mes_bridge,
    parts_bridge,
    systems_bridge,
)

#: The one marker every sourcing gap renders as -- never a guess, never a
#: blank. Matches the wording already used across maintenance.html /
#: torque.html / drivetrain_section.html / _code_brief.html.
UNKNOWN_MARKER = "Unknown — use the service manual (TechAuthority)"

#: dependency confidence -> a 0..1 weight, used only for ranking "what
#: else should I look at" (section 8) -- never shown as a number on its
#: own, always alongside the sourced confidence word.
_CONFIDENCE_WEIGHT = {"CONFIRMED": 1.0, "CORROBORATED": 0.8,
                     "SINGLE-SOURCE": 0.5, "UNKNOWN": 0.2}

#: cuore.services.electrical_bridge's elements carry their own
#: ``part_of_systems`` vocabulary (``mes.electrical.CANONICAL_SYSTEMS``),
#: built independently of the 25-key systems graph and not a 1:1 match.
#: This is the documented overlap -- a systems-graph key with no entry
#: here simply has no electrical-layout elements merged in (its
#: ``components`` list, from the systems record itself, still shows).
_ELEMENT_TAGS_FOR: dict[str, list[str]] = {
    "evap": ["evap"], "network": ["network"], "lighting": ["lighting"],
    "brakes_abs": ["chassis"], "adas_sensors": ["adas"],
    "body_comfort": ["body"], "starting_charging": ["charging", "cranking"],
    "engine_management": ["misfire"], "wheels_tpms": ["tpms"],
}

#: Standard OBD-II monitor categories (SAE J1979 continuous/non-continuous
#: monitor taxonomy -- factual, not vehicle-specific) a systems-graph key
#: can plausibly carry. A key not listed here has no OBD monitor at all,
#: which is itself a fact worth stating plainly rather than as a gap.
_MONITOR_KEYWORDS: dict[str, list[str]] = {
    "evap": ["evap"],
    "exhaust_emissions": ["catalyst", "secondary air", "heated catalyst"],
    "engine_management": ["misfire", "comprehensive component"],
    "fuel": ["fuel system"],
    "air_intake_boost": ["secondary air"],
}


# --- small helpers -----------------------------------------------------------

def _all_systems() -> dict[str, dict[str, Any]]:
    try:
        raw = systems_bridge.systems()
    except Exception:  # noqa: BLE001 -- a knowledge-table miss must never 500
        raw = {}
    if isinstance(raw, dict):
        return raw
    return {s.get("key"): s for s in (raw or []) if s.get("key")}


def _correlate(vin: str) -> dict[str, Any]:
    try:
        return systems_bridge.correlate(vin) or {}
    except Exception:  # noqa: BLE001
        return {}


def _base_code(full: str) -> str:
    return (full or "").split("-")[0].strip().upper()


def _edge_kind(dep: dict[str, Any]) -> str:
    """"electrical supply" vs "functional" vs "UNKNOWN", from whatever the
    edge's own ``technical.carries`` note says -- never a guess beyond
    that note's own words."""
    if dep.get("system") == "electrical_supply":
        return "electrical supply"
    carries = ((dep.get("technical") or {}).get("carries") or "").lower()
    if any(w in carries for w in ("volt", "supply", "ground", "current", "12 v", "amp")):
        return "electrical supply"
    if carries or dep.get("why"):
        return "functional"
    return "UNKNOWN"


def _dossier_codes_map(vin: str) -> dict[str, dict[str, Any]]:
    try:
        dossier = mes_bridge.workup(vin=vin)
        view = dossier_bridge.build_view(vin, dossier, None)
    except Exception:  # noqa: BLE001
        return {}
    return {r.get("code"): r for r in (view.get("codes") or [])}


def _live_value_for(channel_id: str, dview_freeze: list[dict[str, Any]]
                    ) -> Optional[dict[str, Any]]:
    """The most recent sourced value CUORE has for ``channel_id`` -- a
    freeze-frame snapshot carried from a real DTC event on this VIN (no
    live-session store of "latest reading per channel" exists yet, so a
    freeze frame is the closest sourced value there is), graded through
    ``liveboard_bridge.evaluate`` exactly as the Live board grades it."""
    try:
        name = known_good_bridge.known_good_for(channel_id) or {}
        chan_name = name.get("name") or channel_id.replace("_", " ")
    except Exception:  # noqa: BLE001
        chan_name = channel_id.replace("_", " ")
    for ff in dview_freeze or []:
        for row in (ff.get("key") or []) + (ff.get("all") or []):
            if (row.get("name") or "").strip().lower() != chan_name.strip().lower():
                continue
            raw = str(row.get("value") or "")
            num = ""
            for ch in raw:
                if ch.isdigit() or ch in ".-":
                    num += ch
                elif num:
                    break
            try:
                value = float(num)
            except ValueError:
                continue
            try:
                grade = liveboard_bridge.evaluate(channel_id, value)
            except Exception:  # noqa: BLE001
                grade = {"level": "unknown", "text": UNKNOWN_MARKER}
            return {"value": raw, "level": grade.get("level"), "text": grade.get("text"),
                    "source": f"freeze frame, {ff.get('code')}"}
    return None


def _fact(attested_map: dict[str, dict[str, Any]], fact_key: str, raw_value: Optional[str]
          ) -> dict[str, Any]:
    """One open-square UNKNOWN marker's full state: the sourced text (or
    the marker itself), the key a mechanic's input against it is filed
    under, and the most recent attested input on file for it (``None`` if
    none). Never upgrades ``raw_value`` -- an attested row is shown
    *alongside* the marker, never in place of it (see ``cuore.live.
    attested``'s module docstring for why)."""
    text = raw_value or UNKNOWN_MARKER
    return {
        "text": text, "fact_key": fact_key, "is_unknown": text == UNKNOWN_MARKER,
        "attested": attested_map.get(fact_key),
    }


def _channel_display_names(rec: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for ch in rec.get("live_channels") or []:
        try:
            cg = known_good_bridge.known_good_for(ch) or {}
        except Exception:  # noqa: BLE001
            cg = {}
        names.add((cg.get("name") or ch.replace("_", " ")).strip().lower())
    return names


# --- the view model -----------------------------------------------------------

def build_system_view(vin: str, key: str) -> Optional[dict[str, Any]]:
    """Everything ``/v/{vin}/systems/{key}`` needs, or ``None`` if ``key``
    is not one of ``systems_bridge.systems()``'s keys (the route 404s)."""
    all_systems = _all_systems()
    rec = all_systems.get(key)
    if rec is None:
        return None
    labels = {k: (s.get("label") or k) for k, s in all_systems.items()}
    label = labels.get(key, key)

    corr = _correlate(vin)
    by_system = {r.get("system"): r for r in (corr.get("by_system") or [])}
    this_row = by_system.get(key) or {}
    dossier_codes = _dossier_codes_map(vin)

    try:
        attested_map = attested_store.latest_by_fact(vin, key)
    except Exception:  # noqa: BLE001 -- a bad/missing store must never 500 the page
        attested_map = {}

    # --- 1. status strip -----------------------------------------------------
    codes_status: list[dict[str, Any]] = []
    for full in this_row.get("codes") or []:
        base = _base_code(full)
        drow = dossier_codes.get(base)
        codes_status.append({
            "code": base, "dtc": full,
            "status": (drow or {}).get("status") or "STALE",
            "status_label": (drow or {}).get("status_label") or "Stale",
            "description": (drow or {}).get("description") or "",
            "href": f"/v/{vin}/code/{base}",
        })

    monitor_keywords = _MONITOR_KEYWORDS.get(key)
    if not monitor_keywords:
        monitor = {"has_monitor": False}
    else:
        try:
            dossier = mes_bridge.workup(vin=vin)
            rp = dossier_bridge.readiness_panel(vin, dossier)
        except Exception:  # noqa: BLE001
            rp = {"monitors": [], "at": None, "note": None}
        match = next((m for m in (rp.get("monitors") or [])
                     if any(kw in (m.get("name") or "").lower() for kw in monitor_keywords)),
                    None)
        note_raw = None if match else (rp.get("note") or "no readiness read on file yet")
        monitor = {"has_monitor": True, "at": rp.get("at"),
                  "name": (match or {}).get("name") or monitor_keywords[0].title(),
                  "status": (match or {}).get("status") if match else None,
                  "note": note_raw,
                  "note_fact": _fact(attested_map, f"monitor:{key}", note_raw) if note_raw is not None else None}

    try:
        dossier = mes_bridge.workup(vin=vin)
        dview_freeze = dossier_bridge.build_view(vin, dossier, None).get("freeze_frames") or []
    except Exception:  # noqa: BLE001
        dview_freeze = []
    live_values = []
    for ch in rec.get("live_channels") or []:
        try:
            cg = known_good_bridge.known_good_for(ch) or {}
            band = known_good_bridge.sourced_band(ch) or {}
        except Exception:  # noqa: BLE001
            cg, band = {}, {}
        band_note_raw = band.get("note") or None
        live_values.append({
            "id": ch, "name": cg.get("name") or ch.replace("_", " ").title(),
            "band_note": band_note_raw or UNKNOWN_MARKER,
            "band_fact": _fact(attested_map, f"live:{ch}", band_note_raw),
            "band_confidence": band.get("confidence") or "UNKNOWN",
            "latest": _live_value_for(ch, dview_freeze),
        })

    try:
        bench = bench_bridge.build_bench(vin)
        banner = bench.get("blocker_banner") or {}
    except Exception:  # noqa: BLE001
        banner = {}
    # bench_bridge._blocker_banner carries {icon, is_blocker, action, why,
    # basis} -- only the car's own *active* blocker (is_blocker true)
    # counts as a blocker here; a clean/no-data banner is not one.
    blocker = {"text": banner.get("action"), "why": banner.get("why")} if banner.get("is_blocker") else None

    last_evidence = this_row.get("last")

    status_strip = {
        "codes": codes_status, "monitor": monitor, "live_values": live_values,
        "blocker": blocker, "last_evidence": last_evidence,
        "system_status": this_row.get("status") or "stale",
    }

    # --- 2. relationship ring --------------------------------------------------
    co_occ = {}
    for row in corr.get("co_occurrence") or []:
        a, b = row.get("a"), row.get("b")
        other = b if a == key else (a if b == key else None)
        if other and (row.get("sessions_together") or 0) > 0:
            co_occ[other] = row

    def _dep_entry(dep: dict[str, Any], other_key: str) -> dict[str, Any]:
        hot = co_occ.get(other_key)
        why_raw = dep.get("why") or None
        source_raw = dep.get("source") or None
        return {
            "system": other_key, "label": labels.get(other_key, other_key),
            "why": why_raw or UNKNOWN_MARKER,
            "why_fact": _fact(attested_map, f"rel:{other_key}:why", why_raw),
            "confidence": (dep.get("confidence") or "UNKNOWN").upper(),
            "source": source_raw or UNKNOWN_MARKER,
            "source_fact": _fact(attested_map, f"rel:{other_key}:source", source_raw),
            "kind": _edge_kind(dep),
            "hot": bool(hot),
            "lift": hot.get("lift") if hot else None,
            "href": f"/v/{vin}/systems/{other_key}",
        }

    upstream = [_dep_entry(dep, dep.get("system")) for dep in (rec.get("depends_on") or [])
               if dep.get("system")]
    downstream = []
    for other_key, other_rec in all_systems.items():
        if other_key == key:
            continue
        for dep in other_rec.get("depends_on") or []:
            if dep.get("system") == key:
                downstream.append(_dep_entry(dep, other_key))

    related_keys = {e["system"] for e in upstream} | {e["system"] for e in downstream}
    hot_only = [{
        "system": other, "label": labels.get(other, other),
        "lift": row.get("lift"), "sessions_together": row.get("sessions_together"),
        "reading": row.get("reading") or "",
        "href": f"/v/{vin}/systems/{other}",
    } for other, row in co_occ.items() if other not in related_keys]

    relationship = {"upstream": upstream, "downstream": downstream, "hot_only": hot_only}

    # --- 3. components, placed ---------------------------------------------
    parts = []
    for pkey in rec.get("parts") or []:
        try:
            p = parts_bridge.part(pkey)
        except Exception:  # noqa: BLE001
            p = None
        images = (p or {}).get("images") or []
        image_url = images[0].get("url") if images and isinstance(images[0], dict) else None
        image_fact = None if image_url else _fact(attested_map, f"part:{pkey}:image", None)
        if p:
            parts.append({"key": pkey, "name": p.get("name") or pkey,
                         "href": f"/v/{vin}/parts#{pkey}",
                         "image_url": image_url, "image_fact": image_fact})
        else:
            parts.append({"key": pkey, "name": pkey.replace("_", " "), "href": None,
                         "image_url": None, "image_fact": image_fact})

    try:
        all_elements = electrical_bridge.list_elements()
    except Exception:  # noqa: BLE001
        all_elements = []
    tags = set(_ELEMENT_TAGS_FOR.get(key, []))
    elements = [e for e in all_elements if tags & set(e.get("part_of_systems") or [])]

    try:
        all_inspections = electrical_bridge.list_inspections(vin)
    except Exception:  # noqa: BLE001
        all_inspections = []
    latest_inspection: dict[str, dict[str, Any]] = {}
    for row in all_inspections:
        eid = row.get("element")
        if eid in {e.get("id") for e in elements}:
            if eid not in latest_inspection or (row.get("at") or "") > (latest_inspection[eid].get("at") or ""):
                latest_inspection[eid] = row

    placed_components = []
    for e in elements:
        eid = e.get("id")
        loc = e.get("location") or {}
        location_note_raw = loc.get("description") or None
        latest_insp = latest_inspection.get(eid)
        placed_components.append({
            "id": eid, "label": e.get("label") or eid,
            "zone": loc.get("zone") or UNKNOWN_MARKER,
            "location_note": location_note_raw or UNKNOWN_MARKER,
            "location_fact": _fact(attested_map, f"element:{eid}:location", location_note_raw),
            "location_confidence": loc.get("confidence") or "UNKNOWN",
            "inspection_hint": e.get("inspection_hint") or UNKNOWN_MARKER,
            "latest_inspection": ({
                "condition": latest_insp.get("condition"), "at": latest_insp.get("at"),
                "by": latest_insp.get("by"), "note": latest_insp.get("note") or "",
                "photo_count": len(latest_insp.get("media_ids") or []),
            } if latest_insp else None),
            # pre-filled with element id (anchor) and system (query param) --
            # electrical.html's own per-element "Record inspection" details/
            # form (electrical_routes.py) already hides the element id, so
            # jumping to its anchor is the whole pre-fill this page owes it.
            "inspect_href": f"/v/{vin}/electrical?system={(tags and sorted(tags)[0]) or ''}#el-{eid}",
        })

    wiring_paths = []
    for row in codes_status:
        if row["status"] not in ("ACTIVE", "CLEARED_UNVERIFIED"):
            continue
        try:
            path = electrical_bridge.path_for_code(row["code"])
        except Exception:  # noqa: BLE001
            path = None
        if path and path.get("path"):
            wiring_paths.append({"code": row["code"], "path": path.get("path"),
                                 "note": path.get("note")})

    components = {"parts": parts, "elements": placed_components, "wiring_paths": wiring_paths}

    # --- 4. how it fails here ------------------------------------------------
    open_codes = [r["code"] for r in codes_status if r["status"] in ("ACTIVE", "CLEARED_UNVERIFIED")]
    fault_tree = None
    if open_codes:
        try:
            fault_tree = mes_bridge.fault_tree(",".join(open_codes), vin=vin)
        except Exception:  # noqa: BLE001
            fault_tree = None

    do_it_now_href = f"/v/{vin}/job?step=6"
    next_test_label = None
    try:
        from mes import mechanic_tests as _mech  # noqa: PLC0415 -- being built in parallel
    except Exception:  # noqa: BLE001
        _mech = None
    if _mech is not None and open_codes:
        try:
            finder = getattr(_mech, "tests_for_code", None) or getattr(_mech, "find_test", None)
            match = finder(open_codes[0]) if finder else None
            test_id = None
            if isinstance(match, dict):
                test_id = match.get("id") or match.get("test_id")
                next_test_label = match.get("label") or match.get("name")
            elif isinstance(match, (list, tuple)) and match:
                first = match[0]
                test_id = first.get("id") if isinstance(first, dict) else None
                next_test_label = first.get("label") if isinstance(first, dict) else None
            if test_id:
                do_it_now_href = f"/v/{vin}/tests#test-{test_id}"
        except Exception:  # noqa: BLE001
            pass

    how_it_fails = {"fault_tree": fault_tree, "open_codes": open_codes,
                    "next_test_label": next_test_label, "do_it_now_href": do_it_now_href}

    # --- 5. hypotheses touching this system -----------------------------------
    key_norm = key.lower()
    label_norm = label.lower()
    hyps = []
    try:
        jv = jobs_bridge.build_job_view(vin)
    except Exception:  # noqa: BLE001
        jv = {}
    for sugg in jv.get("suggested_hypotheses") or []:
        sys_norm = (sugg.get("system") or "").strip().lower()
        if sys_norm and (sys_norm == key_norm or sys_norm in label_norm or label_norm.startswith(sys_norm)):
            hyps.append({"text": sugg.get("text"), "status": "suggested",
                        "evidence_count": len(sugg.get("evidence_for") or []) +
                                          len(sugg.get("evidence_against") or []),
                        "next_test": sugg.get("next_test")})
    job = jv.get("job") or {}
    for h in job.get("hypotheses") or []:
        sys_norm = (h.get("system") or "").strip().lower()
        if sys_norm and (sys_norm == key_norm or sys_norm in label_norm):
            hyps.append({"text": h.get("text"), "status": h.get("status") or "open",
                        "evidence_count": len(h.get("evidence_for") or []) +
                                          len(h.get("evidence_against") or []),
                        "next_test": None})

    add_hyp_href = f"/v/{vin}/job?step=7&system={key}&codes={','.join(open_codes)}"
    hypotheses = {"rows": hyps, "add_href": add_hyp_href}

    # --- 6. what this car has taught -----------------------------------------
    try:
        case_match = cases_bridge.match(vin, open_codes) if open_codes else {"matches": [], "count": 0}
    except Exception:  # noqa: BLE001
        case_match = {"matches": [], "count": 0}
    taught = {
        "codes": codes_status,
        "sessions": this_row.get("sessions"), "first": this_row.get("first"),
        "last": this_row.get("last"), "case_matches": case_match.get("matches") or [],
    }

    # --- 7. others' experience ------------------------------------------------
    try:
        experience = experience_bridge.links_for(family=key)
    except Exception:  # noqa: BLE001
        experience = {"links": [], "count": 0}

    # --- 8. what else should I look at ----------------------------------------
    candidates: dict[str, dict[str, Any]] = {}
    for e in upstream + downstream:
        candidates.setdefault(e["system"], e)
    for o, row in co_occ.items():
        candidates.setdefault(o, {"system": o, "label": labels.get(o, o),
                                  "confidence": "UNKNOWN", "why": row.get("reading") or "",
                                  "href": f"/v/{vin}/systems/{o}"})

    ranked = []
    for other_key, e in candidates.items():
        conf_w = _CONFIDENCE_WEIGHT.get(e.get("confidence", "UNKNOWN"), 0.3)
        lift = (co_occ.get(other_key) or {}).get("lift") or 1.0
        other_status = (by_system.get(other_key) or {}).get("status") or "clean"
        unverified_mult = 1.5 if other_status in ("cleared_unverified", "stale") else 1.0
        score = conf_w * float(lift) * unverified_mult
        why_bits = [e.get("why") or ""]
        if e.get("hot"):
            why_bits.append(f"seen together on this car ({e.get('lift'):.2f}x lift)" if e.get("lift") else
                            "seen together on this car")
        ranked.append({"system": other_key, "label": labels.get(other_key, other_key),
                       "href": f"/v/{vin}/systems/{other_key}", "score": score,
                       "why": " -- ".join(b for b in why_bits if b)})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    look_at_next = ranked[:3]

    # --- 9. learned DIDs correlated with this system's channels --------------
    chan_names = _channel_display_names(rec)
    learned_dids: list[dict[str, Any]] = []
    learned_available = True
    try:
        learned_data = learned_store.learned(vin) or {}
    except Exception:  # noqa: BLE001 -- an unreadable store is an honest empty state, not a 500
        learned_data = {}
        learned_available = False
    learned_entries = (learned_data.get(vin) or []) if isinstance(learned_data, dict) else []
    for entry in learned_entries:
        if entry.get("status") != "accepted":
            continue
        name = (entry.get("name") or "").strip().lower()
        if name and name in chan_names:
            learned_dids.append({
                "module": entry.get("module"), "did": entry.get("did"),
                "name": entry.get("name"), "unit": entry.get("unit"),
                "confidence": entry.get("confidence"), "at": entry.get("at"),
                "watch_href": f"/v/{vin}/liveboard?watch={entry.get('did')}",
            })
    learned = {"available": learned_available, "dids": learned_dids}

    # --- 10. freeze frame, this system's channels highlighted ----------------
    mapped_codes = {r["code"] for r in codes_status}
    freeze_frames_view = []
    for ff in dview_freeze:
        base = _base_code(ff.get("code") or "")
        if base not in mapped_codes:
            continue
        rows = [{"name": row.get("name"), "value": row.get("value"),
                "highlighted": (row.get("name") or "").strip().lower() in chan_names}
               for row in ff.get("all") or []]
        freeze_frames_view.append({"code": ff.get("code"), "rows": rows,
                                   "href": f"/v/{vin}/code/{base}"})

    return {
        "key": key, "label": label,
        "status_strip": status_strip,
        "relationship": relationship,
        "components": components,
        "how_it_fails": how_it_fails,
        "hypotheses": hypotheses,
        "taught": taught,
        "experience": experience,
        "look_at_next": look_at_next,
        "learned": learned,
        "freeze_frames": freeze_frames_view,
        "unknown_marker": UNKNOWN_MARKER,
        "attested_footnote": ("Mechanic inputs are attested claims, not car measurements: "
                              "they never replace the knowledge-table value shown beside them "
                              "and never enter the evidence gate as something the car itself "
                              "measured."),
    }


__all__ = ["build_system_view", "UNKNOWN_MARKER"]
