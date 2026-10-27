"""Data for the interactive Sensors outline (a standalone partial; sensors.html includes it later).

``outline(vin, sensor=None)`` returns one dict that ``_sensors_interactive.html`` renders: the car outline
(side and top) with every sensor as a 44 px tap target coloured by VALIDITY, plus one card per sensor.

Validity is one of (label + shape + colour, never colour alone):

  Invalid        no valid reading: the module returned a "not available" marker or an impossible value
  Suspect        a number that cannot be trusted as decoded (a cross-check inside the repo disagrees)
  Unconfirmed    the only readings come from a decoding this repo does not confirm for this car
  Not recorded   no reading on record (never 0)
  OK             a valid reading from a confirmed decoding

Evidence only. Nothing here opens the adapter: the live state is the in-process poller snapshot (a plain dict
read); saved values come from :mod:`cuore.services.sensor_health`, partner readings from
:mod:`cuore.services.sensor_crosscheck` (saved readings only), expected bands from ``mes.known_good`` through
``known_good_bridge``. The slow parts are cached on the state files' size and mtime, so a warm call is cheap.
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

from . import cache
from .bench_interactive import _live_snapshot, _tok, age_text

#: key, label, glyph, what it means (the legend and the card use these words)
STATES: list[tuple[str, str, str, str]] = [
    ("invalid", "Invalid", "✕", "no valid reading: a not-available marker or an impossible value"),
    ("suspect", "Suspect", "!", "a number that cannot be trusted as decoded"),
    ("unconfirmed", "Unconfirmed", "?", "only an unconfirmed decoding has been read"),
    ("not_recorded", "Not recorded", "–", "no reading on record yet"),
    ("ok", "OK", "✓", "a valid reading from a confirmed decoding"),
]
STATE_LABEL = {k: lab for k, lab, _g, _m in STATES}
STATE_GLYPH = {k: g for k, _l, g, _m in STATES}
CONFIRMED = {"confirmed", "legislated", "computed"}
UNCONF_PREFIX = "decoding unconfirmed"
_REF_W = 400.0          # layout width in px: 44 px targets must not overlap at a phone's width
_PITCH = 47.0           # centre-to-centre distance of two targets, px
_EDGE = 24.0

CONF_WORDS = {"SOURCED": "from a source", "INFERRED": "worked out, not checked", "GENERAL": "general knowledge only",
              "UNKNOWN": "not known"}
RULE_WORD = {"AGREE": "Agree", "DISAGREE": "Disagree", "UNCONFIRMED DECODING": "Unconfirmed decoding",
             "CONDITION NOT MET": "Condition not met", "NOT RECORDED": "Not recorded"}


# --- small helpers -------------------------------------------------------------------------------------

def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    return None


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:.1f}" if abs(v) >= 10 else f"{v:.3g}"


def _unit_norm(u: Any) -> str:
    return str(u or "").strip().lower().replace("°", "")


def _pct(v: float, lo: float, hi: float) -> float:
    return round(max(0.0, min(100.0, (v - lo) / (hi - lo) * 100.0)), 1) if hi > lo else 0.0


def _sig() -> tuple:
    """State-file freshness: what makes the cached model stale."""
    from . import sensor_health as sh
    out = []
    try:
        d = sh._sd()
        for name in (sh.CHECKS_FILE, sh.SNAPSHOTS_FILE, sh.FULLSCAN_FILE, "observations.jsonl", "audit.jsonl",
                     "jobs.jsonl", sh.RANGES_FILE, "element_locations.jsonl"):
            try:
                st = (d / name).stat()
                out.append((name, st.st_mtime_ns, st.st_size))
            except OSError:
                out.append((name, 0, 0))
        out.append(str(d))
    except Exception:  # noqa: BLE001
        pass
    return tuple(out)


# --- validity --------------------------------------------------------------------------------------------

def classify(s: dict[str, Any], reg: Optional[dict[str, Any]] = None) -> tuple[str, str]:
    """(state key, one-line reason) for one :func:`sensor_health.health` row."""
    reg = reg or {}
    vals = [v for v in s.get("values") or []]
    if s.get("no_valid"):
        bad = [v for v in vals if v.get("invalid") and "wrong decode" not in v["invalid"]]
        why = "; ".join(f"{v.get('label')}: {v['invalid']}" for v in bad) or next(
            (r for r in s.get("reasons") or [] if r.startswith("No valid")), "no valid reading")
        return "invalid", why
    if s.get("suspect"):
        sus = [v for v in vals if (v.get("suspect") and not str(v["suspect"]).startswith(UNCONF_PREFIX))
               or "wrong decode" in (v.get("invalid") or "")]
        if sus:
            return "suspect", "; ".join(f"{v.get('label')}: {v.get('suspect') or v.get('invalid')}" for v in sus)
        un = [v for v in vals if v.get("suspect")]
        return "unconfirmed", "; ".join(f"{v.get('label')}: {v['suspect']}" for v in un)
    good = [v for v in vals if v.get("value") is not None and not v.get("invalid")]
    if not good:
        r = next((x for x in s.get("reasons") or [] if x), "")
        return "not_recorded", r or "No value for any channel is on record yet."
    confirmed = [v for v in good if str(getattr(reg.get(v["channel"]), "confidence", "")) in CONFIRMED
                 and not getattr(reg.get(v["channel"]), "untrusted", False)]
    if not confirmed:
        names = ", ".join(str(v.get("label") or v["channel"]) for v in good)
        return "unconfirmed", f"Only unconfirmed decodings have been read ({names}); not confirmed on this car."
    return "ok", f"{len(confirmed)} confirmed channel(s) read with a valid value."


# --- condition and band ----------------------------------------------------------------------------------

def _rpm_events(events: list[dict[str, Any]]) -> list[tuple[float, float, str]]:
    """[(epoch, rpm, at)] of every recorded engine speed, oldest first."""
    out = []
    for e in events:
        if e.get("channel") == "engine_rpm" and e.get("error") is None and _num(e.get("value")) is not None:
            try:
                out.append((datetime.fromisoformat(str(e["at"])[:19]).timestamp(), float(e["value"]), str(e["at"])))
            except ValueError:
                continue
    return out


def _engine(rpms: list[tuple[float, float, str]], at: Any, window_s: float = 10.0) -> dict[str, Any]:
    """Engine state AT THE MOMENT of a reading: the recorded engine speed nearest to ``at`` within ``window_s``.
    Unknown when none was recorded then (an older or newer speed says nothing about that moment)."""
    try:
        t = datetime.fromisoformat(str(at)[:19]).timestamp()
    except ValueError:
        return {"rpm": None, "at": None, "state": "unknown"}
    best = min(rpms, key=lambda r: abs(r[0] - t), default=None)
    if best is None or abs(best[0] - t) > window_s:
        return {"rpm": None, "at": None, "state": "unknown"}
    return {"rpm": best[1], "at": best[2], "state": "stopped" if best[1] < 1 else "running"}


def band_applies(conditions: str, eng: dict[str, Any]) -> tuple[Optional[bool], str]:
    """(applies?, note). Only an idle band is checked, against engine speed; anything else is not checked."""
    c = (conditions or "").lower()
    if "idle" not in c:
        return None, ""
    r = eng.get("rpm")
    if r is None:
        return None, "engine speed was not read at the same moment, so whether the car was at idle is not known"
    if r < 1:
        return False, "the engine was stopped"
    if r > 1100:
        return False, f"the engine was at {_fmt(r)} rpm, not at idle"
    return True, f"engine at {_fmt(r)} rpm"


def _band(channel: str, unit: str, vin: str, eng: dict[str, Any]) -> Optional[dict[str, Any]]:
    try:
        from . import known_good_bridge
        row = known_good_bridge.known_good_for(channel, vin=vin)
    except Exception:  # noqa: BLE001
        return None
    if not row or row.get("confidence") == "UNKNOWN" or not row.get("normal"):
        return None
    ku = _unit_norm(row.get("unit"))
    if ku and _unit_norm(unit) and ku != _unit_norm(unit):
        return None
    lo, hi = float(row["normal"][0]), float(row["normal"][1])
    span = (hi - lo) or 1.0
    applies, note = band_applies(row.get("conditions") or "", eng)
    return {"lo": lo, "hi": hi, "scale": [lo - span, hi + span], "conditions": row.get("conditions") or "",
            "applies": applies, "applies_note": note, "confidence": row.get("confidence") or "",
            "generic": bool(row.get("generic")), "source": row.get("source") or "",
            "idle": "idle" in (row.get("conditions") or "").lower(),
            "text": f"{_fmt(lo)} to {_fmt(hi)} {row.get('unit') or unit}".strip()}


def _judge(row: dict[str, Any]) -> None:
    """Fill state / state_text / glyph / pos from the row's value, validity and band."""
    v, b = row["value"], row["band"]
    val = row["validity"]
    if row["missing"] and v is None and not row["parts"]:
        st, txt, gl = "missing", "Not recorded", "–"
    elif b is None:
        st, txt, gl = "no_band", "No band on record", "–"
    elif val != "ok" or v is None:
        why = {"invalid": "invalid reading", "suspect": "suspect decoding", "unconfirmed": "decoding unconfirmed"}.get(val, "no single value")
        st, txt, gl = "not_judged", f"Not judged: {why}", "–"
    elif b["applies"] is False:
        st, txt, gl = "not_judged", f"Not judged: this band is for {b['conditions'] or 'another condition'}; {b['applies_note']}", "–"
    elif v < b["lo"]:
        st, txt, gl = "out", "Out of band (below)", "✕"
    elif v > b["hi"]:
        st, txt, gl = "out", "Out of band (above)", "✕"
    else:
        st, txt, gl = "in", "In band", "✓"
    if st in ("in", "out") and b["applies"] is None and b["idle"]:
        txt += " (whether the car was at idle is not known)"
    row["state"], row["state_text"], row["glyph"] = st, txt, gl
    row["pos"] = _pct(v, *b["scale"]) if (b and v is not None and val == "ok") else None
    if row["pos"] is None and v is not None and b:
        row["pos_loose"] = _pct(v, *b["scale"])
    row["beyond"] = bool(b and v is not None and (v < b["scale"][0] or v > b["scale"][1]))


def _validity(ch: str, value: Any, unit: str, formula: str, reg: dict[str, Any]) -> tuple[str, str]:
    """(invalid|suspect|unconfirmed|ok, why) for one channel value."""
    from . import sensor_health as sh
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "ok", ""
    bad = sh.invalid_reason(ch, value, unit, formula)
    if bad and "wrong decode" not in bad:
        return "invalid", bad
    sus = bad or sh.suspect_reason(ch, value, {})
    if sus:
        return ("unconfirmed", sus) if sus.startswith(UNCONF_PREFIX) else ("suspect", sus)
    c = reg.get(ch)
    conf = str(getattr(c, "confidence", "") or "")
    if c is not None and (conf not in CONFIRMED or getattr(c, "untrusted", False)):
        return "unconfirmed", f"decoding {conf or 'unknown'}: not confirmed on this car"
    return "ok", ""


# --- the model (cached) ----------------------------------------------------------------------------------

def _zone_label(zone: Optional[str]) -> str:
    from ..web import sensor_profile_svg as sp
    z = sp.resolve_zone(zone)
    top = sp.TOP_ZONES.get(z or "") or {}
    return top.get("label") or sp.ZONE_BY_ID.get(z or "", {}).get("label") or ""


def _channel_row(vin: str, ch: str, v: Optional[dict[str, Any]], meta: dict[str, Any], reg: dict[str, Any],
                 rpms: list[tuple[float, float, str]], plaus: dict[str, tuple]) -> dict[str, Any]:
    m = meta.get(ch) or {}
    unit = (v or {}).get("unit") or m.get("unit") or ""
    raw = (v or {}).get("value")
    parts: list[tuple[str, str]] = []
    val: Optional[float] = None
    if isinstance(raw, dict):
        parts = [(str(k), _fmt(x) if _num(x) is not None else str(x)) for k, x in raw.items()]
    else:
        val = _num(raw)
    validity, why = ("ok", "")
    if v is not None:
        if v.get("invalid"):
            validity, why = ("suspect" if "wrong decode" in v["invalid"] else "invalid"), v["invalid"]
        elif v.get("suspect"):
            validity = "unconfirmed" if str(v["suspect"]).startswith(UNCONF_PREFIX) else "suspect"
            why = v["suspect"]
        else:
            validity, why = _validity(ch, raw, unit, m.get("formula", ""), reg) if val is not None else ("ok", "")
            if not parts and val is None:
                validity = "ok"
    c = reg.get(ch)
    eng = _engine(rpms, (v or {}).get("read_at"))
    row = {"channel": ch, "name": (m.get("name") or (v or {}).get("label") or ch).strip().capitalize() or ch,
           "unit": unit, "pid": getattr(c, "pid", "") or "", "conf": str(getattr(c, "confidence", "") or "unknown"),
           "formula": m.get("formula", ""), "value": val, "parts": parts,
           "value_text": (f"{_fmt(val)} {unit}".strip() if val is not None
                          else ", ".join(f"{k} {x}" for k, x in parts)),
           "at": (v or {}).get("read_at"), "age": age_text((v or {}).get("read_at")) if v else "",
           "origin": "saved reading" if v else "", "live": False, "missing": v is None or (val is None and not parts),
           "validity": validity, "why": why, "redecoded": (v or {}).get("redecoded") or "",
           "band": _band(ch, unit, vin, eng) if val is not None or v is None else None,
           "plaus": plaus.get(_unit_norm(unit))}
    if row["band"] is None and v is None:
        row["band"] = _band(ch, unit, vin, eng)
    _judge(row)
    return row


def _plausible() -> dict[str, tuple]:
    from . import sensor_health as sh
    return {k: tuple(v) for k, v in getattr(sh, "_PLAUSIBLE", {}).items()}   # a test may stub sensor_health


def _connector_and_harness(vin: str, s: dict[str, Any], els: dict[str, Any], hd: dict[str, Any]) -> dict[str, Any]:
    eid = s.get("element_id") or ""
    el = els.get(eid) if eid else None
    conn = None
    if eid:
        for k, e in els.items():
            if e.get("kind") == "connector" and (k == f"{eid}_connector" or eid in (e.get("feeds") or [])):
                conn = {"label": e.get("label") or k, "id": k}
                break
    har = [{"title": h.get("title") or h.get("id"), "id": h.get("id"),
            "ends": (h.get("ends") or "")[:200]}
           for h in hd.get("harnesses", [])
           if s["id"] in (h.get("related") or {}).get("sensors", [])
           or (eid and eid in (h.get("related") or {}).get("elements", []))]
    return {"element": ({"id": eid, "label": el.get("label") or eid, "kind": el.get("kind") or "",
                         "hint": el.get("inspection_hint") or "", "tsb_refs": el.get("tsb_refs") or []}
                        if el else ({"id": eid, "label": eid, "kind": "", "hint": "", "tsb_refs": []} if eid else None)),
            "connector": conn, "harness": har}


def _rule_entries(cc: dict[str, Any], owners: dict[str, list[str]], by_id: dict[str, dict]) -> dict[str, list[dict]]:
    """{sensor id: [rule entry]} from the cross-check results; a rule belongs to every sensor owning a side."""
    out: dict[str, list[dict]] = {}
    for r in cc.get("results") or []:
        sides = []
        sids: list[str] = []
        for sd in r.get("sides") or []:
            base = re.split(r"[@.]", str(sd.get("key") or ""), 1)[0]
            own = owners.get(base, [])
            sids += [o for o in own if o not in sids]
            val = _num(sd.get("value"))
            sides.append({"label": sd.get("label") or sd.get("key"), "key": sd.get("key"),
                          "value_text": f"{_fmt(val)} {sd.get('unit') or ''}".strip() if val is not None else "not recorded",
                          "at": sd.get("at") or "", "confirmed": bool(sd.get("confirmed")), "note": sd.get("note") or "",
                          "owners": own})
        ent = {"id": r.get("id"), "title": r.get("title"), "status": r.get("status"),
               "word": RULE_WORD.get(r.get("status"), str(r.get("status"))), "css": r.get("css") or "",
               "mark": r.get("mark") or "", "reason": r.get("reason") or "", "sides": sides,
               "would_be": RULE_WORD.get(r.get("would_be") or "", ""), "tolerance": (r.get("tolerance") or {}).get("text") or "",
               "condition": r.get("condition_text") or "", "age": r.get("age_text") or "", "sensors": sids}
        for sid in sids:
            out.setdefault(sid, []).append(ent)
    return out


def _model(vin: str) -> dict[str, Any]:
    return cache.get_or_build(("sensors_interactive", vin, _sig()), lambda: _build_model(vin))


def _build_model(vin: str) -> dict[str, Any]:
    from ..web import sensor_profile_svg as sp
    from . import harnesses, layout_bridge, sensor_crosscheck as sc, sensor_health as sh
    try:
        data = sh.health(vin)
    except Exception as exc:  # noqa: BLE001 -- the partial says so instead of failing
        return {"sensors": [], "error": f"Sensor health is not available: {exc}", "marks": {}}
    sensors = list(data.get("sensors") or [])
    sensors.sort(key=lambda s: (str(s.get("system") or "zz"), str(s.get("label") or s.get("id"))))
    try:
        from ..live import channels as channels_mod
        reg = channels_mod.registry()
    except Exception:  # noqa: BLE001
        reg = {}
    try:
        meta = sh._channel_meta()
    except Exception:  # noqa: BLE001
        meta = {}
    try:
        events = sh._events(vin)
    except Exception:  # noqa: BLE001
        events = []
    rpms = _rpm_events(events)
    try:
        els = layout_bridge.elements() or {}
    except Exception:  # noqa: BLE001
        els = {}
    hd = harnesses.data()
    owners: dict[str, list[str]] = {}
    for s in sensors:
        for ch in s.get("channels") or []:
            owners.setdefault(ch, []).append(s["id"])
    try:
        series = sc.load_saved(vin)
        for lst in series.values():
            lst.sort(key=lambda r: r.t)
        cc = sc.evaluate(vin, series=series)
    except Exception as exc:  # noqa: BLE001
        cc = {"results": [], "error": str(exc)}
    rules = _rule_entries(cc, owners, {s["id"]: s for s in sensors})
    plaus = _plausible()
    out: list[dict[str, Any]] = []
    for n, s in enumerate(sensors, 1):
        state, why = classify(s, reg)
        by_ch = {v["channel"]: v for v in s.get("values") or []}
        rows = [_channel_row(vin, ch, by_ch.get(ch), meta, reg, rpms, plaus) for ch in s.get("channels") or []]
        # a rule entry may also name this sensor through a partner's side; partners = other owners
        mine = rules.get(s["id"], [])
        partners = []
        for r in mine:
            for p in r["sensors"]:
                if p != s["id"] and p not in partners:
                    partners.append(p)
        zid = sp.resolve_zone(s.get("zone"))
        out.append({"id": s["id"], "n": n, "label": s.get("label") or s["id"], "system": s.get("system") or "other",
                    "module": s.get("module") or "", "bus": s.get("bus") or "", "state": state,
                    "state_label": STATE_LABEL[state], "glyph": STATE_GLYPH[state], "why": why,
                    "zone": s.get("zone"), "side": s.get("side"), "zone_id": zid, "zone_label": _zone_label(s.get("zone")),
                    "loc_conf": s.get("location_confidence") or "UNKNOWN",
                    "loc_conf_word": CONF_WORDS.get(s.get("location_confidence") or "UNKNOWN", "not known"),
                    "loc_source": s.get("location_source") or "", "readable": bool(s.get("readable", True)),
                    "readable_note": s.get("readable_note") or "", "last_read": s.get("last_read"),
                    "codes": s.get("codes") or [], "code_match": (s.get("code_match") or {}).get("codes") or [],
                    "rows": rows, "rules": mine, "partners": partners, "stale": bool(s.get("stale")),
                    "health_reason": (s.get("reasons") or [""])[0],
                    **_connector_and_harness(vin, s, els, hd)})
    byid = {s["id"]: s for s in out}
    for s in out:   # partners the other way round: a rule listed on a partner names this sensor too
        s["partners"] = [p for p in s["partners"] if p in byid]
    marks = {"side": _place(out, "side"), "top": _place(out, "top")}
    counts = {k: sum(1 for s in out if s["state"] == k) for k, *_ in STATES}
    return {"sensors": out, "byid": byid, "marks": marks, "counts": counts, "error": "",
            "cc_error": cc.get("error") or ""}


# --- the drawing -------------------------------------------------------------------------------------------

_PAD_Y = {"side": 120, "top": 130}


def _place(sensors: list[dict[str, Any]], view: str) -> dict[str, Any]:
    """Greedy, deterministic placement of 44 px targets on the extended drawing. Positions in % of the stage.
    Small areas are placed first so they stay on their anchor; a crowded area fans out around its own."""
    from ..web import sensor_profile_svg as sp
    if view == "side":
        w, h = sp._VB_W, sp._VB_H
    else:
        w, h = sp._TOP_W, sp._TOP_H
    padv = _PAD_Y[view]
    scale = _REF_W / w
    pw, ph = w * scale, (h + 2 * padv) * scale
    groups: dict[str, dict[str, Any]] = {}
    for s in sensors:
        zid = s["zone_id"]
        if zid is None:
            continue
        right = (s.get("side") or "").lower() == "right" or zid.endswith("_right_wheel_well")
        if view == "side":
            if right:
                continue
            key, x, y = zid, float(sp.ZONE_BY_ID[zid]["ax"]), float(sp.ZONE_BY_ID[zid]["ay"])
        else:
            a = sp._top_anchor({"zone": s["zone"], "side": s.get("side")})
            if a is None:
                continue
            key, x, y = a[0], float(a[1]), float(a[2])
        g = groups.setdefault(key, {"x": x * scale, "y": (y + padv) * scale, "items": []})
        g["items"].append(s)
    # candidate offsets on a fine grid, nearest to the anchor first: a crowded area fans out around its own anchor
    cells = sorted(((float(dx), float(dy)) for dx in range(-400, 401, 8) for dy in range(-300, 301, 8)),
                   key=lambda c: (c[0] ** 2 + c[1] ** 2, c[1], c[0]))
    taken: list[tuple[float, float]] = []
    marks: list[dict[str, Any]] = []
    unfit: list[dict[str, Any]] = []
    for key in sorted(groups, key=lambda k: (len(groups[k]["items"]), groups[k]["x"], groups[k]["y"])):
        g = groups[key]
        for s in sorted(g["items"], key=lambda i: i["n"]):
            spot = None
            for dx, dy in cells:
                px, py = g["x"] + dx, g["y"] + dy
                if not (_EDGE <= px <= pw - _EDGE and _EDGE <= py <= ph - _EDGE):
                    continue
                if all((px - tx) ** 2 + (py - ty) ** 2 >= (_PITCH - 2) ** 2 for tx, ty in taken):
                    spot = (px, py)
                    break
            if spot is None:
                unfit.append(s)
                continue
            taken.append(spot)
            marks.append({"id": s["id"], "left": round(spot[0] / pw * 100, 2), "top": round(spot[1] / ph * 100, 2)})
    marks.sort(key=lambda m: next(s["n"] for s in sensors if s["id"] == m["id"]))
    art = sp._car_line_art() if view == "side" else sp._car_top_art()
    label = ("Side view of the car, left side, nose to the left" if view == "side"
             else "Top view of the car, nose to the left, left side at the bottom")
    svg = (f'<svg class="si-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 {-padv} {w} {h + 2 * padv}" '
           f'role="img" aria-label="{label}">{art}</svg>')
    placed_ids = {m["id"] for m in marks}
    return {"svg": svg, "marks": marks, "ids": placed_ids, "unfit": [s["id"] for s in unfit]}


# --- the public function -------------------------------------------------------------------------------------

def _view_rows(sp_row: dict[str, Any], snap: dict[str, Any], connected: bool, now: datetime) -> dict[str, Any]:
    """A copy of a cached channel row with the live value laid over it when a session is open."""
    row = dict(sp_row)
    row["parts"] = list(sp_row["parts"])
    if not connected:
        return row
    lv = (snap.get("channels") or {}).get(row["channel"]) or {}
    n = _num(lv.get("value"))
    if n is None:
        return row
    validity, why = _validity(row["channel"], n, lv.get("unit") or row["unit"], row["formula"], {})
    if row["band"] is not None:   # the band's condition is judged against the engine speed read in the same session
        b = dict(row["band"])
        r = _num(((snap.get("channels") or {}).get("engine_rpm") or {}).get("value"))
        b["applies"], b["applies_note"] = band_applies(b["conditions"], {"rpm": r})
        row["band"] = b
    # a live number also needs the registry's decoding confidence; keep the cached row's judgement of that
    if validity == "ok" and row["validity"] == "unconfirmed":
        validity, why = "unconfirmed", row["why"]
    row.update(value=n, parts=[], value_text=f"{_fmt(n)} {lv.get('unit') or row['unit']}".strip(),
               at=now.isoformat(timespec="seconds"), age="live", origin="live from the open session", live=True,
               missing=False, validity=validity, why=why, redecoded="")
    _judge(row)
    return row


def _links(vin: str, s: dict[str, Any], token: str) -> dict[str, Any]:
    code = ""
    if s["codes"]:
        code = s["codes"][0]["code"]
    elif s["code_match"]:
        code = s["code_match"][0]
    eid = (s.get("element") or {}).get("id") or ""
    path_href = _tok(f"/v/{vin}/electrical?code={quote(code)}", token) if code else ""
    layout_href = (_tok(f"/v/{vin}/electrical" + (f"?code={quote(code)}" if code else "") + (f"#el-{quote(eid)}" if eid else ""), token)
                   if (code or eid) else "")
    return {"path_href": path_href, "path_code": code, "path_from": ("stored on this sensor" if s["codes"] else "listed for this sensor type") if code else "",
            "layout_href": layout_href,
            "data_href": _tok(f"/v/{vin}/sensors/data", token),
            "readings_href": _tok(f"/v/{vin}/sensors/readings", token),
            "csv_href": _tok(f"/v/{vin}/sensors/readings.csv", token)}


def outline(vin: str, sensor: Optional[str] = None, *, token: str = "", base: str = "",
            snapshot: Optional[dict[str, Any]] = None, now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """The Sensors outline block. ``sensor`` selects one (None = nothing selected). ``None`` when ``sensor`` is
    not a sensor of this car (the route turns that into a 404). ``snapshot`` lets a caller or a test pass the
    poller's snapshot; by default the in-process poller is read (no adapter contact)."""
    from ..web import sensor_profile_svg as sp
    now = now or datetime.now()
    m = _model(vin)
    base = base or f"/v/{vin}/sensors/outline"
    if sensor and sensor not in m.get("byid", {}):
        return None
    snap = snapshot if snapshot is not None else _live_snapshot()
    connected = bool(snap.get("active"))
    out: dict[str, Any] = {"vin": vin, "token": token, "base": base, "error": m.get("error", ""), "cc_error": m.get("cc_error", ""),
                           "connected": connected, "stream_url": _tok("/api/live/stream", token),
                           "connect_text": "" if connected else "Not connected: connect to see live. Showing the last recorded values.",
                           "legend": [{"key": k, "label": lab, "glyph": g, "means": means, "n": m.get("counts", {}).get(k, 0)}
                                      for k, lab, g, means in STATES],
                           "selected": sensor or "", "credit": sp.SIDE_VIEW_CREDIT,
                           "sensors": [], "views": {}, "unplaced": [], "choices": []}
    if not m.get("sensors"):
        return out
    cards = []
    for s in m["sensors"]:
        c = dict(s)
        c["rows"] = [_view_rows(r, snap, connected, now) for r in s["rows"]]
        c["live"] = any(r["live"] for r in c["rows"])
        c.update(_links(vin, s, token))
        c["href"] = _tok(f"{base}?sensor={quote(s['id'])}", token) + "#si-pop"
        c["partner_labels"] = [{"id": p, "n": m["byid"][p]["n"], "label": m["byid"][p]["label"],
                                "state": m["byid"][p]["state"], "state_label": m["byid"][p]["state_label"],
                                "href": _tok(f"{base}?sensor={quote(p)}", token) + "#si-pop"} for p in s["partners"]]
        cards.append(c)
    byid = {c["id"]: c for c in cards}
    out["sensors"] = cards
    out["by_id"] = byid
    sel = byid.get(sensor or "")
    partner_ids = set(sel["partners"]) if sel else set()
    for view in ("side", "top"):
        v = m["marks"][view]
        marks = []
        for mk in v["marks"]:
            c = byid[mk["id"]]
            marks.append({**mk, "n": c["n"], "label": c["label"], "state": c["state"], "state_label": c["state_label"],
                          "glyph": c["glyph"], "href": c["href"], "partners": " ".join(c["partners"]),
                          "sel": mk["id"] == (sensor or ""), "partner": mk["id"] in partner_ids})
        out["views"][view] = {"svg": v["svg"], "marks": marks,
                              "unfit": [byid[i] for i in v["unfit"] if i in byid]}
    placed_any = m["marks"]["side"]["ids"] | m["marks"]["top"]["ids"]
    out["unplaced"] = [c for c in cards if c["id"] not in placed_any]
    out["selected_card"] = sel
    out["partner_ids"] = sorted(partner_ids)
    out["choices"] = [{"id": c["id"], "n": c["n"], "label": c["label"]} for c in cards]
    return out


__all__ = ["outline", "classify", "STATES", "band_applies"]
