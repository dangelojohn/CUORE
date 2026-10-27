"""Data for two interactive Bench pieces (standalone partials; bench.html includes them later).

* :func:`live_proof` -- for the top present fault, the 2-4 live readings that bear on its leading hypothesis,
  each with a target band, the latest value with its age, and "not recorded" when there is none (never 0).
* :func:`fault_map` -- the side / top car outline with the fault's dependency elements highlighted in one
  colour and similar faults' elements in a second, plus one card per element.

Evidence only. Nothing here opens the adapter: the live state is read from the in-process poller snapshot
(a plain dict read), saved values from ``live_snapshots.jsonl`` and from-car observations. Every builder it
calls is cached (fault board facts, fault_similarity table, layout paths), so a warm call is well under 0.5 s.
A reading's decoding confidence is shown from the channel registry; a decoding the repo itself calls
unconfirmed (or a channel this car's EVAP system is documented not to support) is labelled so.
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from . import cache

#: board statuses that count as a "present" fault (same set the Bench's Faults list uses)
PRESENT = ("permanent", "active", "pending", "verifying")

EVAP_WINDOW = (15.0, 85.0)
_EVAP_CODE = re.compile(r"^(P04[0-5]\d|P1CEA)$")

#: The EVAP proving readings, in the order a mechanic reads them. ``band`` is only ever a sourced window:
#: the fuel window is the EVAP monitor's own (cuore.live.repair, dossier_bridge._EVAP_FUEL_WINDOW); a trim
#: band is looked up live from the known-good table (generic, labelled). ``None`` = no sourced target.
_EVAP_ROWS: list[dict[str, Any]] = [
    {"channel": "fuel_level", "scale": (0.0, 100.0), "band": EVAP_WINDOW,
     "band_label": "EVAP window 15-85 %",
     "band_source": "EVAP tests need fuel between about 15 and 85 % (cuore/live/repair.py; dossier_bridge)",
     "in": "In window", "out": "Outside window",
     "why": "Outside the window the EVAP monitor does not run, so no pass or fail is recorded."},
    {"channel": "commanded_evap_purge", "scale": (0.0, 100.0), "band": None,
     "band_label": "no sourced target",
     "band_source": "PID 2E is the ECM's commanded purge duty, not measured flow (cuore/live/purge_trim.py)",
     "why": "Above 0 % the ECM is commanding the purge valve open; 0 % means a purge-flow check cannot be read."},
    {"channel": "short_fuel_trim_b1", "scale": (-25.0, 25.0), "band": "known_good",
     "band_label": "generic closed-loop guideline",
     "in": "Within guideline", "out": "Outside guideline",
     "why": "Fuel trim should move when purge opens; a flat trim with purge commanded points away from the purge path."},
    {"channel": "evap_vapor_pressure", "scale": (-8192.0, 8192.0), "band": None,
     "band_label": "no sourced target",
     "band_source": "cuore/live/purge_trim.py",
     "unconfirmed": "Unconfirmed on this car: CUORE's purge-trim notes say the FCA ESIM system has no pressure "
                    "sensor, so this channel may never answer.",
     "why": "EVAP vapour pressure (PID 32). Expect 'not recorded' on this car."},
]


# --- small helpers -----------------------------------------------------------------------------------

def _tok(url: str, token: str) -> str:
    if not token:
        return url
    return url + ("&" if "?" in url else "?") + "token=" + quote(token)


def _parse(ts: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "")[:19])
    except (TypeError, ValueError):
        return None


def age_text(ts: Any, now: Optional[datetime] = None) -> str:
    """"3 min ago" / "5 h ago" / "4 d ago" for an ISO timestamp; "" when unreadable."""
    t = _parse(ts)
    if t is None:
        return ""
    s = ((now or datetime.now()) - t).total_seconds()
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{int(s // 60)} min ago"
    if s < 172800:
        return f"{int(s // 3600)} h ago"
    return f"{int(s // 86400)} d ago"


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().split()[0])
    except (ValueError, IndexError):
        return None


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def _pct(v: float, lo: float, hi: float) -> float:
    return round(max(0.0, min(100.0, (v - lo) / (hi - lo) * 100.0)), 1) if hi > lo else 0.0


# --- the fault ---------------------------------------------------------------------------------------

def _cards(vin: str) -> list[dict[str, Any]]:
    from . import fault_board
    try:
        return fault_board.board(vin)
    except Exception:  # noqa: BLE001 -- a bench piece must render without it
        return []


def _top_present(cards: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    return next((c for c in cards if c.get("kind") == "code" and c.get("status") in PRESENT), None)


def _leading_hypothesis(vin: str, card: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The best-ranked suspect hypothesis for this code: one whose codes name it, or one that is the job's own
    hypothesis for it (a job hypothesis may carry no code list). Else the card's first hypothesis."""
    code = card.get("code") or ""
    mine = {h.get("evidence_id") for h in card.get("hypotheses") or []}
    try:
        from . import fault_board
        best = None
        for s in fault_board._facts(vin).get("suspects") or []:
            if s.get("kind") != "hypothesis":
                continue
            if code in {fault_board._base(c) for c in s.get("codes") or []} or s.get("id") in mine:
                if best is None or (s.get("rank") or 99) < (best.get("rank") or 99):
                    best = s
        if best:
            return {"id": best.get("id"), "title": best.get("title") or "", "rank": best.get("rank"),
                    "next_test": (best.get("next_test") or "").strip()}
    except Exception:  # noqa: BLE001
        pass
    h = (card.get("hypotheses") or [None])[0]
    return {"id": h["evidence_id"], "title": h["title"], "rank": None, "next_test": h.get("next_test") or ""} if h else None


# --- values: live, saved snapshot, from-car observation ------------------------------------------------

def _live_snapshot() -> dict[str, Any]:
    try:
        from ..live import poller as poller_mod
        return poller_mod.poller().snapshot()
    except Exception:  # noqa: BLE001
        return {"active": False, "channels": {}}


def _snapshots() -> list[dict[str, Any]]:
    """Saved live-source snapshots, newest first (cached on the file's state)."""
    try:
        from ..live import ui_store
        p = Path(ui_store.snapshots_path())
        st = p.stat()
        key = ("bench_interactive_snaps", str(p), st.st_mtime_ns, st.st_size)
    except Exception:  # noqa: BLE001
        return []

    def build() -> list[dict[str, Any]]:
        from ..live import ui_store
        rows = [e for e in ui_store._read_all_snapshots() if e.get("source") == "live"]
        rows.sort(key=lambda e: e.get("at") or "", reverse=True)
        return rows[:200]

    return cache.get_or_build(key, build)


def _saved_value(vin: str, cid: str, pid: str) -> Optional[dict[str, Any]]:
    """Newest recorded value for a channel: a saved live snapshot, or a from-car PID observation."""
    best: Optional[dict[str, Any]] = None
    for e in _snapshots():
        v = (e.get("values") or {}).get(cid)
        n = _num(v.get("value")) if isinstance(v, dict) else None
        if n is not None:
            best = {"value": n, "at": e.get("at"), "origin": f"saved live snapshot {e.get('id', '')}".strip()}
            break
    try:
        from ..live import store as live_store
        obs = (cache.recent_observations(200, vin=vin, kind="pids_snapshot")
               + cache.recent_observations(200, vin=vin, kind="pid"))
        for o in obs:
            if not live_store.is_from_car(o):
                continue
            d = o.get("data") or {}
            n = None
            if str(d.get("pid") or "").upper() == pid or d.get("name") == cid:
                first = next(iter((d.get("by_ecu") or {}).values()), None)
                n = _num(first.get("value")) if isinstance(first, dict) else _num(d.get("value"))
            else:
                for readings in (d.get("by_ecu") or {}).values():
                    ent = readings.get(pid) or readings.get(pid.lower()) if isinstance(readings, dict) else None
                    if isinstance(ent, dict) and _num(ent.get("value")) is not None:
                        n = _num(ent.get("value"))
                        break
            if n is not None and (best is None or (o.get("at") or "") > (best["at"] or "")):
                best = {"value": n, "at": o.get("at"), "origin": f"PID {pid} read from the car"}
    except Exception:  # noqa: BLE001
        pass
    return best


def _band_for(spec: dict[str, Any], vin: str) -> Optional[dict[str, Any]]:
    b = spec.get("band")
    if b is None:
        return None
    if b == "known_good":
        try:
            from . import known_good_bridge
            sb = known_good_bridge.sourced_band(spec["channel"], vin=vin) or {}
            n = sb.get("normal")
            if n:
                tag = "generic guideline" if sb.get("generic") else "sourced band"
                return {"lo": float(n[0]), "hi": float(n[1]), "label": f"{spec['band_label']} {_fmt(n[0])} to {_fmt(n[1])}",
                        "source": f"{tag}: {sb.get('source') or 'known-good table'} ({sb.get('confidence') or 'unrated'})"}
        except Exception:  # noqa: BLE001
            pass
        return None
    return {"lo": float(b[0]), "hi": float(b[1]), "label": spec["band_label"], "source": spec.get("band_source", "")}


def _row(vin: str, spec: dict[str, Any], live: dict[str, Any], connected: bool, reg: dict[str, Any],
         now: datetime) -> dict[str, Any]:
    cid = spec["channel"]
    ch = reg.get(cid)
    unit = getattr(ch, "unit", "") or ""
    lo, hi = spec["scale"]
    band = _band_for(spec, vin)
    val = at = origin = None
    live_now = False
    lv = (live.get("channels") or {}).get(cid) or {}
    if connected and _num(lv.get("value")) is not None:
        val, at, origin, live_now = _num(lv["value"]), now.isoformat(timespec="seconds"), "live from the open session", True
    else:
        sv = _saved_value(vin, cid, getattr(ch, "pid", "") or "")
        if sv:
            val, at, origin = sv["value"], sv["at"], sv["origin"]
    row: dict[str, Any] = {
        "channel": cid, "name": (getattr(ch, "name", cid) or cid).capitalize(), "unit": unit,
        "pid": getattr(ch, "pid", ""), "decode": getattr(ch, "confidence", "unknown"),
        "scale": [lo, hi], "why": spec.get("why", ""), "unconfirmed": spec.get("unconfirmed"),
        "band": band, "in_label": spec.get("in", "In band"), "out_label": spec.get("out", "Outside band"),
        "band_pos": [_pct(band["lo"], lo, hi), _pct(band["hi"], lo, hi)] if band else None,
        "value": val, "value_text": f"{_fmt(val)} {unit}".strip() if val is not None else "",
        "at": at, "age": "live" if live_now else (age_text(at, now) if at else ""),
        "origin": origin, "live": live_now,
        "pos": _pct(val, lo, hi) if val is not None else None,
    }
    row["state"], row["state_text"] = _state(row)
    return row


def _state(row: dict[str, Any]) -> tuple[str, str]:
    v, b = row["value"], row["band"]
    if v is None:
        return "missing", "Not recorded"
    if b is None:
        return "no_band", "No target band"
    if v < b["lo"]:
        return "out", f"{row['out_label']} (below)"
    if v > b["hi"]:
        return "out", f"{row['out_label']} (above)"
    return "in", row["in_label"]


def _generic_specs(code: str) -> list[dict[str, Any]]:
    """Fallback for a non-EVAP code: its primary system's live channels that have a sourced normal band."""
    try:
        from mes import systems as sysmod
        from . import known_good_bridge
        out: list[dict[str, Any]] = []
        for e in sysmod.systems_for_code(code):
            if e.get("role") != "primary" or e.get("system") == "UNKNOWN":
                continue
            for cid in (sysmod.SYSTEMS.get(e["system"]) or {}).get("live_channels", []):
                n = (known_good_bridge.sourced_band(cid) or {}).get("normal")
                if n and len(out) < 4 and all(o["channel"] != cid for o in out):
                    span = (n[1] - n[0]) or 1.0
                    out.append({"channel": cid, "scale": (n[0] - span * 0.5, n[1] + span * 0.5), "band": "known_good",
                                "band_label": "sourced normal range",
                                "why": f"Live channel of the {e['system']} system, which this code implicates."})
        return out
    except Exception:  # noqa: BLE001
        return []


def live_proof(vin: str, *, token: str = "", snapshot: Optional[dict[str, Any]] = None,
               now: Optional[datetime] = None, cards: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """The Bench "Live proof" block for the top present fault.

    ``{fault, hypothesis, rows[], connected, connect_text, note, stream_url}``. ``snapshot`` lets a caller (or
    a test) pass the poller's snapshot; by default the in-process poller is read (no adapter contact).
    """
    now = now or datetime.now()
    card = _top_present(cards if cards is not None else _cards(vin))
    snap = snapshot if snapshot is not None else _live_snapshot()
    connected = bool(snap.get("active"))
    out: dict[str, Any] = {"vin": vin, "fault": None, "hypothesis": None, "rows": [], "connected": connected,
                           "connect_text": "" if connected else "Not connected: connect to see live. Showing the last recorded values.",
                           "note": "", "stream_url": _tok("/api/live/stream", token), "token": token}
    if card is None:
        out["note"] = "No present fault to prove."
        return out
    code = card.get("code") or ""
    out["fault"] = {"key": card["key"], "code": code, "label": card.get("label") or code, "status": card.get("status")}
    hyp = _leading_hypothesis(vin, card)
    out["hypothesis"] = hyp
    evap = bool(_EVAP_CODE.match(code)) or "evap" in ((hyp or {}).get("title") or "").lower()
    specs = _EVAP_ROWS if evap else _generic_specs(code)
    if not specs:
        out["note"] = f"No live reading is defined for {code} yet. Nothing is shown rather than guessed."
        return out
    try:
        from ..live import channels as channels_mod
        reg = channels_mod.registry()
    except Exception:  # noqa: BLE001
        reg = {}
    out["rows"] = [_row(vin, s, snap, connected, reg, now) for s in specs[:4]]
    return out


# --- fault map ---------------------------------------------------------------------------------------

_KIND_WORD = {"module": "module", "fuse": "fuse", "fuse_box": "fuse box", "relay": "relay", "ground": "ground",
              "connector": "connector", "splice": "splice", "harness_section": "harness run", "harness": "harness run"}


def _path_for(code: str) -> list[dict[str, Any]]:
    from . import layout_bridge
    try:
        return list(layout_bridge.code_path(code).get("path") or [])
    except Exception:  # noqa: BLE001
        return []


def _overlay(vin: str, path: list[dict[str, Any]], resolve) -> None:
    try:
        from . import element_locations
        element_locations.apply_to_hops(vin, path, resolve)
    except Exception:  # noqa: BLE001
        pass


def _element_extra(vin: str, eid: str) -> dict[str, Any]:
    ins = meas = None
    try:
        from . import electrical_bridge
        rows = electrical_bridge.list_inspections(vin, eid)
        if rows:
            r = rows[-1]
            ins = {"condition": str(r.get("condition") or "").replace("_", " "), "at": r.get("at"),
                   "by": r.get("by") or "", "note": r.get("note") or "", "age": age_text(r.get("at"))}
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import power_budget
        rows = power_budget.measurements(vin, eid)
        if rows:
            r = rows[-1]
            meas = {"volts": r.get("volts"), "from": r.get("from_point") or "", "to": r.get("to_point") or "",
                    "condition": str(r.get("condition") or "").replace("_", " "), "at": r.get("at"),
                    "age": age_text(r.get("at"))}
    except Exception:  # noqa: BLE001
        pass
    return {"inspection": ins, "measurement": meas}


def _similar_codes(vin: str, key: str, limit: int = 4) -> list[dict[str, Any]]:
    """Similar faults worth highlighting: those linked structurally (shared cause, system or bulletin)."""
    from . import fault_similarity
    try:
        rows = fault_similarity.similar(vin, key, limit=10)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in rows:
        kinds = {lk.get("kind") for lk in r.get("links") or []}
        if r.get("code") and kinds & {"shared_cause", "same_system", "same_bulletin"}:
            out.append({"key": r["fault_key"], "code": r["code"], "label": r.get("label") or r["code"],
                        "status": r.get("status") or ""})
        if len(out) >= limit:
            break
    return out


def _drawing(items: list[dict[str, Any]], view: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """(svg of the car outline, placed markers with % positions, unplaced items) for one view."""
    from ..web import sensor_profile_svg as sp
    if view == "side":
        w, h, art = sp._VB_W, sp._VB_H, sp._car_line_art()
    else:
        w, h, art = sp._TOP_W, sp._TOP_H, sp._car_top_art()
    pts: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    for it in items:
        zid = sp.resolve_zone(it.get("zone"))
        side = (it.get("side") or "").lower()
        right = zid is not None and (side == "right" or zid.endswith("_right_wheel_well"))
        if zid is None or (view == "side" and right):
            if zid is None:
                unplaced.append(it)
            continue
        if view == "side":
            x, y = sp.ZONE_BY_ID[zid]["ax"], sp.ZONE_BY_ID[zid]["ay"]
        else:
            a = sp._top_anchor(it)
            if a is None:
                unplaced.append(it)
                continue
            _k, x, y = a
        pts.append({"it": it, "x": float(x), "y": float(y)})
    # Greedy separation so two 44 px targets never overlap at a 360 px wide drawing (positions are %).
    ref = 360.0 / w
    placed: list[tuple[float, float]] = []
    pad = 26.0
    for p in pts:
        cands = [(0.0, 0.0)]
        for r in (50.0, 100.0, 150.0):
            for k in range(8):
                a = math.radians(k * 45 + 45)
                cands.append((r * math.cos(a), r * math.sin(a)))
        best = None
        for dx, dy in cands:
            px, py = p["x"] * ref + dx, p["y"] * ref + dy
            if not (pad <= px <= w * ref - pad and pad <= py <= h * ref - pad):
                continue
            if all((px - qx) ** 2 + (py - qy) ** 2 >= 50.0 ** 2 for qx, qy in placed):
                best = (px, py)
                break
        if best is None:
            best = (p["x"] * ref, p["y"] * ref)
        placed.append(best)
        p["left"] = round(best[0] / (w * ref) * 100, 2)
        p["top"] = round(best[1] / (h * ref) * 100, 2)
    svg = (f'<svg class="bf-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" '
           f'aria-label="{"Side view of the car, left side, nose to the left" if view == "side" else "Top view of the car, nose to the left"}">'
           f'{art}</svg>')
    return svg, pts, unplaced


def fault_map(vin: str, fault_key: Optional[str] = None, *, token: str = "", base: str = "",
              cards: Optional[list[dict[str, Any]]] = None) -> Optional[dict[str, Any]]:
    """The fault-map block. ``fault_key`` None -> the top present fault. ``None`` when the key is not a fault
    on this car (the route turns that into a 404)."""
    from ..web import sensor_profile_svg as sp
    cs = cards if cards is not None else _cards(vin)
    if fault_key:
        card = next((c for c in cs if c.get("key") == fault_key), None)
        if card is None:
            return None
    else:
        card = _top_present(cs)
    out: dict[str, Any] = {"vin": vin, "fault": None, "items": [], "legend": [], "side": None, "top": None,
                           "unplaced": [], "similar": [], "note": "", "choices": [], "token": token,
                           "credit": sp.SIDE_VIEW_CREDIT}
    out["choices"] = [{"key": c["key"], "code": c.get("code"), "label": c.get("label"), "current": bool(card and c["key"] == card["key"]),
                       "href": _tok(f"{base or f'/v/{vin}/bench/fault-map'}?fault={quote(c['key'], safe='')}", token)}
                      for c in cs if c.get("kind") == "code" and c.get("status") in PRESENT]
    if card is None:
        out["note"] = "No present fault to map."
        return out
    code = card.get("code") or ""
    is_code = card.get("kind") == "code"
    out["fault"] = {"key": card["key"], "code": code, "label": card.get("label") or code, "status": card.get("status"),
                    "path_href": _tok(f"/v/{vin}/electrical?code={quote(code)}", token) if is_code else "",
                    "is_code": is_code}
    if not is_code:
        out["note"] = "A reported symptom has no electrical path of its own."
        return out
    sims = _similar_codes(vin, card["key"])
    out["similar"] = sims

    items: dict[str, dict[str, Any]] = {}
    try:
        from . import layout_bridge
        els = layout_bridge.elements() or {}
    except Exception:  # noqa: BLE001
        els = {}

    def add(h: dict[str, Any], which: str, src_code: str) -> None:
        eid = h.get("id")
        if not eid:
            return
        loc = h.get("location") or {}
        el = els.get(eid) or {}
        if eid in items:
            if src_code not in items[eid]["codes"]:
                items[eid]["codes"].append(src_code)
            if which == "fault":
                items[eid]["on_fault_path"] = True
            return
        items[eid] = {"id": eid, "label": h.get("label") or eid, "kind": h.get("kind") or "", "role": h.get("role") or "",
                      "which": which, "on_fault_path": which == "fault", "codes": [src_code], "zone": loc.get("zone"), "side": h.get("side") or loc.get("side"),
                      "loc_text": loc.get("description") or "", "loc_conf": loc.get("confidence") or h.get("confidence") or "",
                      "loc_source": loc.get("source") or "", "hint": el.get("inspection_hint") or "",
                      "tsb_refs": el.get("tsb_refs") or [], "notes": el.get("notes") or "",
                      "source": h.get("source") or ""}

    path = _path_for(code)
    _overlay(vin, path, sp.resolve_zone)
    for h in path:
        add(h, "fault", code)
    for s in sims:
        sp_path = _path_for(s["code"])
        _overlay(vin, sp_path, sp.resolve_zone)
        for h in sp_path:
            add(h, "similar", s["code"])
    for it in items.values():
        it["which"] = ("both" if len(it["codes"]) > 1 else "fault") if it["on_fault_path"] else "similar"
    ordered = [i for i in items.values() if i["which"] != "similar"] + [i for i in items.values() if i["which"] == "similar"]
    nf = ns = nb = 0
    for it in ordered:
        if it["which"] != "similar":
            nf += 1
            nb += it["which"] == "both"
            it["num"] = str(nf)
        else:
            ns += 1
            it["num"] = f"S{ns}"
        it["kind_word"] = _KIND_WORD.get(it["kind"], it["kind"].replace("_", " "))
        zid = sp.resolve_zone(it["zone"])
        it["zone_label"] = (sp.ZONE_BY_ID[zid]["label"] or zid.replace("_", " ")) if zid else ""
        it["placed"] = zid is not None
        it["also_on"] = [c for c in it["codes"] if c != code]
        it["on_fault"] = it["on_fault_path"]
        it.update(_element_extra(vin, it["id"]))
        it["layout_href"] = _tok(f"/v/{vin}/electrical?code={quote(code)}#el-{quote(it['id'])}", token)
    out["items"] = ordered
    for view in ("side", "top"):
        svg, pts, _un = _drawing(ordered, view)
        out[view] = {"svg": svg, "marks": [{"id": p["it"]["id"], "num": p["it"]["num"], "which": p["it"]["which"],
                                            "label": p["it"]["label"], "left": p["left"], "top": p["top"]} for p in pts]}
    out["unplaced"] = [i for i in ordered if not i["placed"]]
    out["legend"] = [{"cls": "bf-fault", "mark": "1",
                      "text": f"On {code}'s own dependency path ({nf} element{'s' if nf != 1 else ''}; circle)"}]
    if sims:
        names = ", ".join(s["code"] for s in sims)
        if nb:
            out["legend"].append({"cls": "bf-fault bf-both", "mark": "1",
                                  "text": f"Circle with a dashed ring: also on a similar fault's path ({names}); {nb} of {nf}"})
        out["legend"].append({"cls": "bf-sim", "mark": "S1",
                              "text": (f"Dashed square: only on a similar fault's path ({names}); {ns} element{'s' if ns != 1 else ''}"
                                       if ns else f"Dashed square: only on a similar fault's path ({names}); none, every element is shared")})
    else:
        out["legend"].append({"cls": "bf-sim", "mark": "S1", "text": "Dashed square: on a similar fault's path (no similar fault linked to this one)"})
    if not ordered:
        out["note"] = f"No electrical path is recorded for {code} yet."
    return out


__all__ = ["live_proof", "fault_map", "age_text", "PRESENT"]
