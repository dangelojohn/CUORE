"""Data for two interactive pieces of the Tests page (standalone partials; tests.html includes them later).

* :func:`live_band` -- for a test that expects a reading: each numeric pass criterion as a bar (the expected pass
  band, the current value marker), the criterion in words with its source and confidence, and the one-tap record
  form. A criterion whose parameter is a live channel id (``cuore/live/channels.py``) is a *live* reading (SSE when
  a session is connected, otherwise the newest saved value); any other numeric criterion is a *meter* reading
  (a number the mechanic types). A range ``[lo, hi]`` is a band; a lone number is a threshold whose direction the
  source does not state, so no band is drawn for it and nothing is auto-judged.
* :func:`test_map` -- the car outline with the elements the test touches highlighted, one card per element.

Evidence only: no value is invented, a missing reading is "not recorded" (never 0), a channel whose decoding the
registry does not call confirmed is labelled. Nothing here opens the adapter (the live state is a plain read of
the in-process poller snapshot). Builders are cached or read small files, so a warm call is well under 0.3 s.
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

from . import bench_interactive as bi, cache

#: seconds a live value must stay inside the band before the one-tap PASS unlocks (the JS enforces it)
HOLD_S = 3

_CONF_OK = {"confirmed", "legislated", "computed"}


def _test(test_id: str) -> Optional[dict[str, Any]]:
    from mes import mechanic_tests
    return mechanic_tests.test(test_id)


def _registry() -> dict[str, Any]:
    try:
        from ..live import channels as channels_mod
        return channels_mod.registry()
    except Exception:  # noqa: BLE001
        return {}


def _spec_text(c: dict[str, Any]) -> str:
    s, u = c.get("spec"), c.get("unit") or ""
    if isinstance(s, (list, tuple)) and len(s) == 2:
        return f"between {bi._fmt(float(s[0]))} and {bi._fmt(float(s[1]))} {u}".strip()
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return (f"{bi._fmt(float(s))} {u}".strip()
                + " (the source gives one figure and does not say whether it is a maximum, a minimum or a target)")
    return str(s)


def _reading(vin: str, c: dict[str, Any], reg: dict[str, Any], live: dict[str, Any], connected: bool,
             last: dict[str, Any], now: datetime) -> Optional[dict[str, Any]]:
    spec = c.get("spec")
    ranged = isinstance(spec, (list, tuple)) and len(spec) == 2 and all(bi._num(x) is not None for x in spec)
    scalar = isinstance(spec, (int, float)) and not isinstance(spec, bool)
    if not (ranged or scalar):
        return None   # prose spec ("see service manual"): nothing numeric to draw
    param = str(c.get("parameter") or "")
    ch = reg.get(param)
    unit = (getattr(ch, "unit", "") or c.get("unit") or "") if ch is not None else (c.get("unit") or "")
    band = scale = None
    if ranged:
        lo, hi = float(spec[0]), float(spec[1])
        span = (hi - lo) or 1.0
        scale = [round(lo - span * 0.5, 2), round(hi + span * 0.5, 2)]
        band = {"lo": lo, "hi": hi}
    val = at = origin = None
    live_now = False
    if ch is not None:
        lv = (live.get("channels") or {}).get(param) or {}
        if connected and bi._num(lv.get("value")) is not None:
            val, at, origin, live_now = bi._num(lv["value"]), now.isoformat(timespec="seconds"), "live from the open session", True
        else:
            sv = bi._saved_value(vin, param, getattr(ch, "pid", "") or "")
            if sv:
                val, at, origin = sv["value"], sv["at"], sv["origin"]
    elif last.get("value") is not None:
        val, at, origin = bi._num(last["value"]), last.get("when"), "last result recorded for this test"
    row: dict[str, Any] = {
        "parameter": param, "kind": "live" if ch is not None else "meter",
        "name": ((getattr(ch, "name", None) or param) if ch is not None else param).capitalize(),
        "unit": unit, "pid": getattr(ch, "pid", "") if ch is not None else "",
        "decode": getattr(ch, "confidence", "") if ch is not None else "",
        "unconfirmed": bool(ch is not None and (getattr(ch, "confidence", "") not in _CONF_OK or getattr(ch, "untrusted", False))),
        "criterion": _spec_text(c), "source": c.get("source") or "", "confidence": c.get("confidence") or "",
        "band": band, "scale": scale, "has_band": band is not None,
        "band_pos": [bi._pct(band["lo"], *scale), bi._pct(band["hi"], *scale)] if band else None,
        "value": val, "value_text": f"{bi._fmt(val)} {unit}".strip() if val is not None else "",
        "pos": bi._pct(val, *scale) if (val is not None and scale) else None,
        "live": live_now, "origin": origin, "at": at,
        "age": "live" if live_now else (bi.age_text(at, now) if at else ""),
    }
    row["state"], row["state_text"] = _state(row)
    return row


def _state(r: dict[str, Any]) -> tuple[str, str]:
    v, b = r["value"], r["band"]
    if v is None:
        return "missing", "Not recorded"
    if b is None:
        return "no_band", "No band to judge against"
    if v < b["lo"]:
        return "out", "Outside the band (below)"
    if v > b["hi"]:
        return "out", "Outside the band (above)"
    return "in", "Inside the band"


def _source_line(r: dict[str, Any]) -> str:
    if r["value"] is None:
        return f"{r['parameter']}: not recorded"
    return f"{r['parameter']} {r['value_text']} ({r['origin'] or 'typed by the mechanic'})"


def live_band(vin: str, test_id: str, *, token: str = "", snapshot: Optional[dict[str, Any]] = None,
              now: Optional[datetime] = None, test_def: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """The "live band" block for one test, or ``None`` when ``test_id`` is not a test.

    ``{test, readings[], connected, connect_text, note, stream_url, form, hold_s}``. ``snapshot`` / ``test_def``
    let a caller or a test pass the poller snapshot or a synthetic definition; by default the in-process poller
    and the catalogue are read (no adapter contact).
    """
    t = test_def or _test(test_id)
    if t is None:
        return None
    now = now or datetime.now()
    snap = snapshot if snapshot is not None else bi._live_snapshot()
    connected = bool(snap.get("active"))
    try:
        from . import tests_bridge
        last = tests_bridge._result_entry(vin, t["id"])
    except Exception:  # noqa: BLE001
        last = {}
    reg = _registry()
    readings = [r for r in (_reading(vin, c, reg, snap, connected, last, now) for c in t.get("pass_criteria") or []) if r]
    out: dict[str, Any] = {
        "vin": vin, "test": {"id": t["id"], "name": t.get("name") or t["id"]}, "readings": readings,
        "connected": connected, "hold_s": HOLD_S, "token": token, "stream_url": bi._tok("/api/live/stream", token),
        "connect_text": "" if connected else "Not connected: connect to see live. Showing the last recorded values.",
        "note": "", "any_live": any(r["kind"] == "live" for r in readings),
        "last": {"result": last.get("result") or "not_done", "value": last.get("value"), "unit": last.get("unit") or "",
                 "age": bi.age_text(last.get("when")) if last.get("when") else ""},
        "form": {"action": bi._tok(f"/v/{vin}/tests/{t['id']}/result", token)},
    }
    if not readings:
        out["note"] = ("This test has no numeric pass criterion, so there is no reading to band. "
                       "Judge it from its procedure and record PASS or FAIL yourself.")
    else:
        prim = readings[0]
        out["primary"] = {"parameter": prim["parameter"], "kind": prim["kind"], "unit": prim["unit"], "value": prim["value"],
                          "source": _source_line(prim)}
    return out


# --- test map ---------------------------------------------------------------------------------------

def _code_path(code: str) -> list[dict[str, Any]]:
    return bi._path_for(code)


def _system_elements(systems: list[str], limit: int = 12) -> list[dict[str, Any]]:
    try:
        from . import layout_bridge
        els = layout_bridge.elements() or {}
    except Exception:  # noqa: BLE001
        return []
    out = []
    for eid, e in els.items():
        if set(systems) & ({s for s in e.get("part_of_systems") or []} | {e.get("system")}):
            loc = e.get("location") or {}
            out.append({"id": eid, "label": e.get("label") or eid, "kind": e.get("kind") or "", "role": "",
                        "location": loc, "source": loc.get("source") or "", "confidence": loc.get("confidence") or ""})
        if len(out) >= limit:
            break
    return out


def _test_hops(t: dict[str, Any]) -> list[dict[str, Any]]:
    """The elements a test touches, with how each is tied to it (cached per test; callers get a copy)."""
    def build() -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for code in (t.get("related_codes") or [])[:3]:
            for h in _code_path(code):
                if not h.get("id"):
                    continue
                if h["id"] not in seen:
                    seen[h["id"]] = {**copy.deepcopy(h), "via": f"on the electrical path of {code}", "via_code": code}
                else:
                    seen[h["id"]]["via"] += f", {code}"
        if not seen:
            for h in _system_elements(list(t.get("systems") or [])):
                seen[h["id"]] = {**h, "via": "belongs to the " + "/".join(t.get("systems") or ["test"]) + " system", "via_code": ""}
        return list(seen.values())
    return copy.deepcopy(cache.get_or_build(("tests_map_hops", t["id"], tuple(t.get("related_codes") or []),
                                            tuple(t.get("systems") or [])), build))


def test_map(vin: str, test_id: str, *, token: str = "", test_def: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    """The test-map block, or ``None`` for an unknown test id."""
    from ..web import sensor_profile_svg as sp
    t = test_def or _test(test_id)
    if t is None:
        return None
    try:
        from . import layout_bridge
        els = layout_bridge.elements() or {}
    except Exception:  # noqa: BLE001
        els = {}
    hops = _test_hops(t)
    bi._overlay(vin, hops, sp.resolve_zone)
    items: list[dict[str, Any]] = []
    for n, h in enumerate(hops, start=1):
        eid = h["id"]
        loc = h.get("location") or {}
        el = els.get(eid) or {}
        zid = sp.resolve_zone(loc.get("zone"))
        code = h.get("via_code") or ""
        base = f"/v/{vin}/electrical?" + (f"code={quote(code)}" if code else f"system={quote((t.get('systems') or [''])[0])}")
        it = {"id": eid, "num": str(n), "label": h.get("label") or eid, "kind": h.get("kind") or "",
              "kind_word": bi._KIND_WORD.get(h.get("kind") or "", (h.get("kind") or "").replace("_", " ")),
              "role": h.get("role") or "", "which": "fault", "zone": loc.get("zone"), "side": h.get("side") or loc.get("side"),
              "loc_text": loc.get("description") or "", "loc_conf": loc.get("confidence") or h.get("confidence") or "",
              "loc_source": loc.get("source") or "", "hint": el.get("inspection_hint") or "", "via": h.get("via") or "",
              "tsb_refs": el.get("tsb_refs") or [], "placed": zid is not None,
              "zone_label": (sp.ZONE_BY_ID[zid]["label"] or zid.replace("_", " ")) if zid else "",
              "layout_href": bi._tok(f"{base}#el-{quote(eid)}", token), "path_href": bi._tok(base, token)}
        it.update(bi._element_extra(vin, eid))
        items.append(it)
    out: dict[str, Any] = {"vin": vin, "test": {"id": t["id"], "name": t.get("name") or t["id"]}, "items": items,
                           "side": None, "top": None, "unplaced": [i for i in items if not i["placed"]], "note": "",
                           "token": token, "credit": sp.SIDE_VIEW_CREDIT, "path": None}
    if items:
        out["path"] = {"label": items[0]["label"], "href": items[0]["path_href"]}
    for view in ("side", "top"):
        svg, pts, _un = bi._drawing(items, view)
        out[view] = {"svg": svg, "marks": [{"id": p["it"]["id"], "num": p["it"]["num"], "label": p["it"]["label"],
                                            "left": p["left"], "top": p["top"]} for p in pts]}
    if not items:
        out["note"] = "No element is recorded for this test yet, so nothing is highlighted. Nothing is guessed."
    return out


__all__ = ["live_band", "test_map", "HOLD_S"]
