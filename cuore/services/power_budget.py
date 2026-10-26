"""The power and ground budget: MEASURED voltage drops along a feed or a
ground, showing where along a path the volts are lost.

Posture
-------
* Only measured numbers are shown. A segment nobody measured is "not
  measured", never 0 V.
* Reference limits live in ``cuore/data/voltage_drop_limits.json`` and each
  carries its basis. They are general automotive screening figures (outside
  facts, labelled), not an FCA specification.
* Measurements are an append-only JSONL log, ``voltage_drops.jsonl``, in the
  same state directory (and through the same safe ``append_jsonl`` /
  ``read_jsonl`` helpers) as the electrical inspections. They are separate
  from inspections because an inspection has a fixed condition vocabulary
  and no numeric field. History is never rewritten.
* Nothing here talks to the car.

Record: ``{id, vin, kind: "voltage_drop", element, from_point, to_point,
side, role, condition, volts, battery_v, by, meter, tag, note, media_ids,
at}``.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .. import bootstrap  # noqa: F401 -- side effect: puts `mes` on sys.path
from . import electrical_bridge

LIMITS_PATH = Path(__file__).resolve().parent.parent / "data" / "voltage_drop_limits.json"
STORE_NAME = "voltage_drops.jsonl"

MAX_VOLTS = 20.0          # a drop larger than any 12 V system's supply is a typo
MAX_TEXT = 80
MAX_NOTE = 500

# severity order: higher is worse. "none" = nothing measured.
_SEVERITY = {"none": 0, "no_load": 1, "good": 2, "watch": 3, "over": 4}
VERDICT_LABELS = {
    "none": "Not measured",
    "no_load": "Engine off: not a valid test",
    "good": "Good",
    "watch": "Watch",
    "over": "Over limit",
}

_limits_cache: Optional[dict[str, Any]] = None


# --- reference data --------------------------------------------------------

def limits() -> dict[str, Any]:
    global _limits_cache
    if _limits_cache is None:
        _limits_cache = json.loads(LIMITS_PATH.read_text(encoding="utf-8"))
    return _limits_cache


def conditions() -> list[dict[str, Any]]:
    return limits()["conditions"]


def _condition(key: str) -> Optional[dict[str, Any]]:
    return next((c for c in conditions() if c["key"] == key), None)


def tags() -> list[dict[str, Any]]:
    return limits()["tags"]


def _phase(tag: str) -> str:
    t = (tag or "").strip().lower()
    if t.startswith("before"):
        return "before"
    if t.startswith("after"):
        return "after"
    return ""


# --- the store -------------------------------------------------------------

def _store_path() -> Path:
    from mes import electrical_inspections
    return electrical_inspections.state_dir() / STORE_NAME


def _all_records() -> list[dict[str, Any]]:
    from mes import paths
    out = []
    for rec in paths.read_jsonl(_store_path()):
        if rec.get("kind") != "voltage_drop" or "volts" not in rec:
            continue
        if not isinstance(rec.get("volts"), (int, float)) or not math.isfinite(rec["volts"]):
            continue
        out.append(rec)
    return out


def measurements(vin: str, element: str = "") -> list[dict[str, Any]]:
    """Voltage-drop records for a VIN (optionally one element), oldest first."""
    return [r for r in _all_records()
            if r.get("vin") == vin and (not element or r.get("element") == element)]


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _seg_key(frm: str, to: str) -> str:
    return _norm(frm) + " -> " + _norm(to)


def parse_volts(raw: Any) -> float:
    """Parse a typed voltage. Refuses blank, NaN, infinity, negatives and
    anything above :data:`MAX_VOLTS`. A decimal comma is accepted when there
    is no point. Raises ValueError with a message fit to show the user."""
    if isinstance(raw, bool):
        raise ValueError("volts must be a number")
    if isinstance(raw, (int, float)):
        val = float(raw)
    else:
        text = str(raw or "").strip()
        if text[-1:].lower() == "v":
            text = text[:-1].strip()
        if not text:
            raise ValueError("enter the measured volts (for example 0.042)")
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        try:
            val = float(text)
        except ValueError:
            raise ValueError(f"volts must be a number, got {str(raw)[:20]!r}") from None
    if not math.isfinite(val):
        raise ValueError("volts must be a finite number")
    if val < 0:
        raise ValueError("enter the size of the drop without a minus sign "
                         "(polarity does not matter for this test)")
    if val > MAX_VOLTS:
        raise ValueError(f"{val:g} V is larger than any drop in a 12 V system; check the meter range")
    return round(val, 4)


def _clean_text(value: Any, label: str, limit: int, required: bool = False) -> str:
    text = " ".join(str(value or "").split())
    if required and not text:
        raise ValueError(f"{label} is required")
    if len(text) > limit:
        raise ValueError(f"{label} is longer than {limit} characters")
    return text


def _element_info(element: str) -> dict[str, Any]:
    el = electrical_bridge.get_element(element)
    if not el:
        raise ValueError(f"unknown electrical element {element!r}")
    return el


def default_side(kind: str) -> str:
    return "ground" if kind == "ground" else "feed"


def record(vin: str, element: str, *, volts: Any, condition: str,
           from_point: str = "", to_point: str = "", preset: str = "",
           side: str = "", by: str = "", meter: str = "", tag: str = "",
           note: str = "", battery_v: Any = "",
           media_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Validate and append one measurement. Raises ValueError (message fit
    for the user) on anything bad; nothing is written then."""
    vin = (vin or "").strip()
    if not vin or len(vin) > 40:
        raise ValueError("vin is required")
    element = (element or "").strip()
    el = _element_info(element)

    cond = (condition or "").strip()
    if _condition(cond) is None:
        raise ValueError("condition must be one of: " + ", ".join(c["key"] for c in conditions()))

    role = "chain"
    pside = ""
    if preset:
        found = next((p for p in presets_for(element) if p["id"] == preset), None)
        if found is None:
            raise ValueError("unknown segment choice")
        from_point, to_point, role, pside = found["from"], found["to"], found["role"], found["side"]
    from_point = _clean_text(from_point, "'from' point", MAX_TEXT, required=True)
    to_point = _clean_text(to_point, "'to' point", MAX_TEXT, required=True)
    if _norm(from_point) == _norm(to_point):
        raise ValueError("the 'from' and 'to' points are the same")

    side = (side or pside or default_side(el.get("kind", ""))).strip().lower()
    if side not in limits()["sides"]:
        raise ValueError("side must be 'ground' or 'feed'")

    tag = _clean_text(tag, "tag", 40).lower()
    if tag and tag not in {t["key"] for t in tags()}:
        raise ValueError("tag must be one of: " + ", ".join(t["key"] for t in tags()))

    v = parse_volts(volts)
    bat = None
    if str(battery_v or "").strip():
        bat = parse_volts(battery_v)
        if bat < 5:
            raise ValueError("battery volts looks too low to be a 12 V battery reading")

    entry = {
        "id": uuid.uuid4().hex[:12],
        "vin": vin,
        "kind": "voltage_drop",
        "element": element,
        "from_point": from_point,
        "to_point": to_point,
        "side": side,
        "role": role,
        "condition": cond,
        "volts": v,
        "battery_v": bat,
        "by": _clean_text(by, "by", 60) or "owner",
        "meter": _clean_text(meter, "meter", 60),
        "tag": tag,
        "note": _clean_text(note, "note", MAX_NOTE),
        "media_ids": [str(m).strip()[:60] for m in (media_ids or []) if str(m).strip()][:5],
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    from mes import paths
    paths.append_jsonl(_store_path(), entry)
    return entry


# --- verdicts ---------------------------------------------------------------

def presets_for(element: str) -> list[dict[str, Any]]:
    """Suggested segments for an element: by element id first, else by kind.
    Each carries a stable ``id`` (``p0``...), formatted from/to labels, side,
    role, why, and an optional limit override."""
    el = electrical_bridge.get_element(element) or {}
    pre = limits()["presets"]
    raw = pre["by_element"].get(element) or pre["by_kind"].get(el.get("kind", "")) or []
    out = []
    for i, p in enumerate(raw):
        out.append({
            "id": f"p{i}",
            "from": p["from"].replace("{label}", el.get("label", element)),
            "to": p["to"].replace("{label}", el.get("label", element)),
            "side": p.get("side", default_side(el.get("kind", ""))),
            "role": p.get("role", "chain"),
            "why": p.get("why", ""),
            "limit": p.get("limit"),
        })
    return out


def judge(volts: float, side: str, condition: str,
          override: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Verdict for one reading against the limit table."""
    lim = override or limits()["sides"].get(side) or limits()["sides"]["ground"]
    basis = lim.get("basis", "")
    cond = _condition(condition) or {}
    if not cond.get("loaded", True):
        return {"key": "no_load", "label": VERDICT_LABELS["no_load"],
                "good_max": lim["good_max"], "watch_max": lim["watch_max"],
                "basis": cond.get("hint", "")}
    if volts <= lim["good_max"]:
        key = "good"
    elif volts <= lim["watch_max"]:
        key = "watch"
    else:
        key = "over"
    return {"key": key, "label": VERDICT_LABELS[key], "good_max": lim["good_max"],
            "watch_max": lim["watch_max"], "basis": basis}


def _fmt2(v: float) -> str:
    """Two decimals, but never hides a third that matters (0.042 stays)."""
    return f"{v:.2f}" if round(v, 2) == round(v, 4) else f"{v:.3f}"


def _compare_text(before: dict[str, Any], after: dict[str, Any]) -> str:
    bt, at = before.get("tag") or "before", after.get("tag") or "after"
    after_word = "after" if at.split(" ", 1)[1:] == bt.split(" ", 1)[1:] else at
    return f"{_fmt2(before['volts'])} V {bt} → {_fmt2(after['volts'])} V {after_word}"


def _latest(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not rows:
        return None
    return max(enumerate(rows), key=lambda p: (p[1].get("at", ""), p[0]))[1]


def _segments(vin: str, element: str, recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Segments in order (presets first, then others by first record), each
    with the latest reading per condition, verdicts and before/after."""
    order: list[str] = []
    meta: dict[str, dict[str, Any]] = {}
    for p in presets_for(element):
        k = _seg_key(p["from"], p["to"])
        order.append(k)
        meta[k] = {"from": p["from"], "to": p["to"], "side": p["side"], "role": p["role"],
                   "why": p["why"], "limit": p["limit"], "preset": True}
    by_seg: dict[str, list[dict[str, Any]]] = {}
    for r in recs:
        k = _seg_key(r["from_point"], r["to_point"])
        if k not in meta:
            order.append(k)
            meta[k] = {"from": r["from_point"], "to": r["to_point"],
                       "side": r.get("side", "ground"), "role": r.get("role", "chain"),
                       "why": "", "limit": None, "preset": False}
        by_seg.setdefault(k, []).append(r)

    out = []
    for k in order:
        m = meta[k]
        rows = by_seg.get(k, [])
        readings = []
        for c in conditions():
            crow = [r for r in rows if r["condition"] == c["key"]]
            last = _latest(crow)
            if not last:
                readings.append({"condition": c["key"], "label": c["label"], "loaded": c["loaded"],
                                 "rec": None, "verdict": None, "compare": None})
                continue
            verdict = judge(last["volts"], m["side"], c["key"], m["limit"])
            before = _latest([r for r in crow if _phase(r.get("tag", "")) == "before"])
            after = _latest([r for r in crow if _phase(r.get("tag", "")) == "after"])
            compare = None
            if before and after:
                compare = {
                    "before": before, "after": after,
                    "text": _compare_text(before, after),
                    "delta": round(after["volts"] - before["volts"], 4),
                    "before_verdict": judge(before["volts"], m["side"], c["key"], m["limit"]),
                    "after_verdict": judge(after["volts"], m["side"], c["key"], m["limit"]),
                }
            readings.append({"condition": c["key"], "label": c["label"], "loaded": c["loaded"],
                             "rec": last, "verdict": verdict, "compare": compare})
        have = [r for r in readings if r["rec"]]
        worst = max((r["verdict"]["key"] for r in have), key=lambda x: _SEVERITY[x], default="none")
        headline = None
        if have:
            valid = [r for r in have if r["loaded"]] or have
            headline = max(valid, key=lambda r: (_SEVERITY[r["verdict"]["key"]], r["rec"]["volts"]))
        wiggle_note = ""
        steady = next((r for r in readings if r["condition"] == "running_loads" and r["rec"]), None) \
            or next((r for r in readings if r["condition"] == "running" and r["rec"]), None)
        wig = next((r for r in readings if r["condition"] == "wiggle" and r["rec"]), None)
        if steady and wig and wig["rec"]["volts"] > steady["rec"]["volts"]:
            wiggle_note = (f"Wiggling read {_fmt2(wig['rec']['volts'] - steady['rec']['volts'])} V "
                           f"higher than the steady reading ({_fmt2(wig['rec']['volts'])} V vs "
                           f"{_fmt2(steady['rec']['volts'])} V): the reading changes with movement.")
        out.append({
            "key": k, "from": m["from"], "to": m["to"], "side": m["side"], "role": m["role"],
            "why": m["why"], "preset": m["preset"], "readings": readings,
            "n": len(rows), "verdict": {"key": worst, "label": VERDICT_LABELS[worst]},
            "headline": headline, "wiggle_note": wiggle_note,
            "limit": m["limit"] or limits()["sides"].get(m["side"]),
        })
    return out


def _totals(segs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Total drop per loaded condition: the sum of the chain segments' latest
    readings. Cross-check segments are left out (they overlap). Only given
    when two or more chain segments exist; ``partial`` when some chain
    segments have no reading for that condition."""
    chain = [s for s in segs if s["role"] == "chain"]
    if len(chain) < 2:
        return []
    tot = limits()["total"]
    out = []
    for c in conditions():
        if not c["loaded"]:
            continue
        vals = []
        for s in chain:
            r = next((x for x in s["readings"] if x["condition"] == c["key"] and x["rec"]), None)
            if r:
                vals.append(r["rec"]["volts"])
        if not vals:
            continue
        total = round(sum(vals), 4)
        key = "good" if total <= tot["good_max"] else "watch" if total <= tot["watch_max"] else "over"
        out.append({"condition": c["key"], "label": c["label"], "volts": total,
                    "count": len(vals), "of": len(chain), "partial": len(vals) < len(chain),
                    "verdict": {"key": key, "label": VERDICT_LABELS[key]}, "basis": tot["basis"]})
    return out


# --- panel / overview --------------------------------------------------------

def _call(el_label: str, segs: list[dict[str, Any]], recs: list[dict[str, Any]]) -> dict[str, str]:
    """The one-line directing call shown at the top of the panel."""
    if not recs:
        first = segs[0] if segs else None
        if first:
            return {"level": "todo",
                    "text": (f"{el_label} not measured yet — measure the drop "
                             f"{first['from']} to {first['to']}, engine running with loads on, "
                             f"before cleaning.")}
        return {"level": "todo",
                "text": f"{el_label} not measured yet — record a drop between two points "
                        f"on it, engine running, before cleaning."}
    comps = [r["compare"] for s in segs for r in s["readings"] if r["compare"]]
    if comps:
        c = comps[0]
        text = f"{el_label}: {c['text']}."
        if c["after_verdict"]["key"] == "over":
            return {"level": "alert", "text": text + " Still over the limit — keep looking."}
        return {"level": "good", "text": text}
    has_before = any(_phase(r.get("tag", "")) == "before" for r in recs)
    has_after = any(_phase(r.get("tag", "")) == "after" for r in recs)
    worst = max((s["verdict"]["key"] for s in segs), key=lambda x: _SEVERITY[x], default="none")
    if has_before and not has_after:
        return {"level": "todo",
                "text": f"{el_label}: before reading recorded ({VERDICT_LABELS[worst].lower()}). "
                        f"Clean it, then measure the same segment again with the same loads "
                        f"and tag it after cleaning."}
    loaded = [r for s in segs for r in s["readings"] if r["rec"] and r["loaded"]]
    if not loaded:
        return {"level": "todo",
                "text": f"{el_label}: only engine-off readings so far, which prove nothing. "
                        f"Measure again with the engine running and loads on."}
    if worst == "over":
        return {"level": "alert", "text": f"{el_label}: a segment is over the limit."}
    if worst == "watch":
        return {"level": "warn", "text": f"{el_label}: a segment is in the watch band."}
    return {"level": "good", "text": f"{el_label}: measured segments are within the limits."}


def _bar(seg: dict[str, Any], scale: float) -> list[dict[str, Any]]:
    """Bars for the ladder: the headline reading, plus its before/after pair
    when both exist. Widths are percentages of ``scale`` volts."""
    h = seg["headline"]
    if not h:
        return []
    lim = seg["limit"]
    out = []
    rows = []
    if h["compare"]:
        rows = [("before", h["compare"]["before"], h["compare"]["before_verdict"]),
                ("after", h["compare"]["after"], h["compare"]["after_verdict"])]
    else:
        rows = [("", h["rec"], h["verdict"])]
    for name, rec, verdict in rows:
        out.append({"name": name, "volts": rec["volts"], "verdict": verdict,
                    "pct": min(100.0, round(100.0 * rec["volts"] / scale, 2)),
                    "good_pct": min(100.0, round(100.0 * lim["good_max"] / scale, 2)),
                    "watch_pct": min(100.0, round(100.0 * lim["watch_max"] / scale, 2)),
                    "condition": h["label"], "tag": rec.get("tag", "")})
    return out


def panel(vin: str, element: str, *, redirect_to: str = "", error: str = "",
          saved: bool = False, open_form: bool = False) -> dict[str, Any]:
    """Everything ``_power_budget_panel.html`` needs for one element."""
    el = electrical_bridge.get_element(element) or {"id": element, "label": element, "kind": ""}
    recs = measurements(vin, element)
    segs = _segments(vin, element, recs)
    label = el.get("label") or element
    scale = max([0.5] + [r["rec"]["volts"] for s in segs for r in s["readings"] if r["rec"]])
    scale = round(scale * 1.1, 3)
    for s in segs:
        s["bars"] = _bar(s, scale)
    worst = max((s["verdict"]["key"] for s in segs), key=lambda x: _SEVERITY[x], default="none")
    return {
        "vin": vin,
        "element": {"id": element, "label": label, "kind": el.get("kind", ""),
                    "side": default_side(el.get("kind", ""))},
        "call": _call(label, segs, recs),
        "segments": segs,
        "totals": _totals(segs),
        "n_measurements": len(recs),
        "verdict": {"key": worst, "label": VERDICT_LABELS[worst]},
        "scale_v": scale,
        "presets": presets_for(element),
        "conditions": conditions(),
        "tags": tags(),
        "sides": limits()["sides"],
        "redirect_to": redirect_to or f"/v/{vin}/power-budget/{element}",
        "error": error,
        "saved": saved,
        "open_form": open_form or bool(error),
        "page_url": f"/v/{vin}/power-budget/{element}",
    }


FIRST_ELEMENT = "g003a"


def overview(vin: str) -> dict[str, Any]:
    """Every element with a measurement (worst verdict first), and G003A
    first with its call if it has none yet."""
    recs = measurements(vin)
    ids: list[str] = []
    for r in recs:
        if r["element"] not in ids:
            ids.append(r["element"])
    first_unmeasured = FIRST_ELEMENT not in ids and electrical_bridge.get_element(FIRST_ELEMENT) is not None
    return {"vin": vin, "measured": ids, "first_unmeasured": first_unmeasured,
            "n_measurements": len(recs)}


def api_payload(vin: str, element: str = "") -> dict[str, Any]:
    ov = overview(vin)
    ids = ([element] if element else ([FIRST_ELEMENT] if ov["first_unmeasured"] else []) + ov["measured"])
    paths_out = []
    for eid in ids:
        p = panel(vin, eid)
        paths_out.append({
            "element": p["element"], "call": p["call"], "verdict": p["verdict"],
            "n_measurements": p["n_measurements"], "totals": p["totals"],
            "segments": [{
                "from": s["from"], "to": s["to"], "side": s["side"], "role": s["role"],
                "verdict": s["verdict"],
                "limit": {"good_max": s["limit"]["good_max"], "watch_max": s["limit"]["watch_max"],
                          "basis": s["limit"]["basis"]},
                "wiggle_note": s["wiggle_note"],
                "readings": [{
                    "condition": r["condition"], "volts": r["rec"]["volts"],
                    "verdict": r["verdict"]["key"], "at": r["rec"]["at"], "by": r["rec"]["by"],
                    "meter": r["rec"]["meter"], "tag": r["rec"]["tag"], "id": r["rec"]["id"],
                    "comparison": r["compare"]["text"] if r["compare"] else None,
                } for r in s["readings"] if r["rec"]],
            } for s in p["segments"]],
        })
    return {"vin": vin, "measurements": ov["n_measurements"],
            "limits_basis": limits()["about"], "paths": paths_out}
