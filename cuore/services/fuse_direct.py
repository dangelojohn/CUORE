"""What the fuses page tells the mechanic to check NOW, and the ground points.

Pure matching (:func:`direct`) over fuse rows, symptom texts and current codes, plus
thin loaders for the real state (:func:`job_inputs`) and the grounds
(:func:`grounds`). Nothing here talks to the car and nothing is invented: a fuse is
named only when (a) a symptom or code description shares the fuse's printed circuit
text ("linked by circuit name") or (b) the fuse / ground sits on CUORE's electrical
path for a current code ("linked by CUORE's electrical path").
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional

BY_NAME = "linked by circuit name"
BY_PATH = "linked by CUORE's electrical path"
GROUND_IDS = ("g003a", "g003b", "esim_ground", "battery_neg_strap")
STRAP_PN_NAME = ("ground strap", "battery negative")
TEST_DOC = "docs/maintenance/GROUND_VOLTAGE_DROP_TEST.md"   # read only to know whether the written procedure exists
TEST_LINE = "Voltage drop to battery negative under load; clean to bare metal."
ACCESS_CUE = re.compile(r"\b(cover|under|behind|panel|footwell|glove|lid|trim|flap|beneath)\b", re.I)
PRETTY = {"g003a": "G003A", "g003b": "G003B", "esim_ground": "ESIM ground", "battery_neg_strap": "Battery strap"}
OWNER_NOTE_ID = "85bf07ba0829"
OUTSIDE_REPORT = ("Related outside report (not a reading): NHTSA ODI 11664142, a 2018 Stelvio with warning lamps "
                  "traced to a corroded, broken starter ground wire.")


def _circuit(label: str) -> str:
    """The printed circuit text of a fuse: the part of its label after the position / in brackets."""
    m = re.search(r"\(([^)]*)\)", label or "")
    return (m.group(1) if m else label or "").lower()


def _rules(text: str) -> list[tuple[str, Callable[[str], bool]]]:
    """(phrase, circuit predicate) pairs a symptom / code text asks for."""
    t = (text or "").lower()
    out: list[tuple[str, Callable[[str], bool]]] = []
    if "window" in t:
        heat = bool(re.search(r"heater|defrost|demist", t))

        def ok(c: str, t=t, heat=heat) -> bool:
            if "window" not in c or (("heater" in c) != heat):
                return False
            if "rear" in t and "front" not in t:
                return "rear" in c
            if "front" in t and "rear" not in t:
                return "front" in c
            return True
        out.append(("window", ok))
    if re.search(r"\bunlock|central locking|door lock", t):
        out.append(("central locking", lambda c: "central locking" in c))
    return out


def _short(text: str, n: int = 70) -> str:
    s = re.sub(r"\s*\([^)]*\)", "", text or "").strip()
    s = re.split(r"[.;,\n]", s, 1)[0].strip()
    if len(s) > n:
        s = s[:n].rsplit(" ", 1)[0]
    return s[:1].upper() + s[1:] if s else ""


def _ref(it: dict[str, Any]) -> str:
    return it.get("position") or it.get("label") or it.get("id")


def anchor(item_id: Any) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in str(item_id))


def reach_clause(box: dict[str, Any]) -> str:
    """How to get at a box, from its own sourced ``where`` text; "access not sourced" when that text has no access cue."""
    w = re.sub(r"\s+", " ", str(box.get("where") or "")).strip()
    if w and ACCESS_CUE.search(w):
        w = re.sub(r"\s*\((?:third-party|unverified)[^)]*\)\s*\.?$", "", w).rstrip(". ")
        return "Reach it: " + w[:1].lower() + w[1:] + "."
    return "Access to the box is not sourced."


def direct(items: list[dict[str, Any]], boxes: list[dict[str, Any]], symptoms: list[dict[str, Any]],
           codes: list[str], code_text: dict[str, str], path_for_code: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    """``symptoms``: newest first, each ``{text, at}``. Returns ``call`` (one line of text), ``call_segs`` (the same
    line as ``{text, href}`` pieces so every fuse / ground name links to its row), ``call_targets`` (go-to chips),
    ``call_items`` / ``call_box``, ``more`` (plain lines), ``groups`` (codes grouped by the same path),
    ``matches`` (ranked fuse/relay cards: rank 0 = in the call, 1 = other circuit-name match, 2 = path only),
    ``ground_ids`` and ``codes``."""
    bx = {b["id"]: b for b in boxes}
    hits: dict[str, dict[str, Any]] = {}
    ground_ids: list[str] = []
    primary: Optional[dict[str, Any]] = None

    def add(it: dict[str, Any], why: str, via: str, code: str = "") -> None:
        h = hits.setdefault(it["id"], {"item": it, "whys": [], "via": via, "name_whys": [], "path_codes": []})
        if why not in h["whys"]:
            h["whys"].append(why)
        if via == BY_NAME:
            h["via"] = BY_NAME
            if why not in h["name_whys"]:
                h["name_whys"].append(why)
        elif code and code not in h["path_codes"]:
            h["path_codes"].append(code)

    for s in symptoms:
        found = []
        for phrase, pred in _rules(s.get("text", "")):
            found += [it for it in items if pred(_circuit(it.get("label", "")))]
        for it in found:
            add(it, f"matches the symptom \"{_short(s.get('text', ''))}\"", BY_NAME)
        if found and primary is None:
            primary = {"what": _short(s.get("text", "")), "items": found}
    seen_code: dict[tuple, dict[str, Any]] = {}
    for c in codes:
        found = []
        for phrase, pred in _rules(code_text.get(c, "")):
            found += [it for it in items if pred(_circuit(it.get("label", "")))]
        for it in found:
            add(it, f"matches {c} \"{code_text.get(c, '')}\"", BY_NAME)
        if found and primary is None:
            primary = {"what": f"{c} {code_text.get(c, '')}".strip(), "items": found}
        try:
            path = path_for_code(c).get("path") or []
        except Exception:  # noqa: BLE001
            path = []
        elems = {p["element"]: p for p in path}
        names: list[tuple[str, str, str]] = []   # (label, href, fuse id or "")
        for it in items:
            if it["id"] in elems or set(it.get("feeds_elements") or []) & set(elems):
                shared = sorted(set(it.get("feeds_elements") or []) & set(elems))
                add(it, f"on CUORE's electrical path for {c} (" + (elems[it["id"]]["role"] if it["id"] in elems
                    else "feeds " + ", ".join(shared)) + ")", BY_PATH, c)
                names.append((_ref(it), "#fuse-" + anchor(it["id"]), it["id"]))
        for e, p in elems.items():
            if p.get("role") == "ground" and e in GROUND_IDS:
                if e not in ground_ids:
                    ground_ids.append(e)
                names.append((PRETTY.get(e, e), "#ground-" + e, ""))
        if names:
            key = tuple(dict.fromkeys(n[0] for n in names))
            g = seen_code.setdefault(key, {"codes": [], "targets": []})
            g["codes"].append(c)
            for n in names:
                if n not in g["targets"]:
                    g["targets"].append(n)
    groups = [{"n": len(g["codes"]), "codes": g["codes"], "targets": g["targets"], "names": list(k)}
              for k, g in seen_code.items()]
    more = [f"{', '.join(g['codes'])}: check " + ", ".join(g["names"]) + " (CUORE's electrical path)" for g in groups]
    call_ids = {it["id"] for it in (primary or {}).get("items", [])}
    matches = []
    for h in hits.values():
        it = h["item"]
        b = bx.get(it.get("box")) or {}
        rank = 0 if it["id"] in call_ids else 1 if h["via"] == BY_NAME else 2
        matches.append({"item": it, "id": it["id"], "ref": _ref(it), "box_id": it.get("box") or "none",
                        "box": b.get("short") or "box not stated", "where": b.get("pick_where") or "",
                        "why": h["whys"], "via": h["via"], "name_whys": h["name_whys"], "path_codes": h["path_codes"],
                        "rank": rank})
    matches.sort(key=lambda m: (m["rank"], m["box_id"], m["ref"]))
    segs: list[dict[str, str]] = []
    targets: list[dict[str, str]] = []
    call_items: list[str] = []
    call_box = ""
    if primary:
        its = list({i["id"]: i for i in primary["items"]}.values())
        circuit = _circuit(its[0].get("label", ""))
        b = bx.get(its[0].get("box")) or {}
        call_box = b.get("id") or ""
        segs.append({"text": f"{primary['what']}: check ", "href": ""})
        for k, i in enumerate(its):
            segs.append({"text": " and " if k else "", "href": ""})
            segs.append({"text": _ref(i), "href": "#fuse-" + anchor(i["id"])})
        loc = (f" in the {b['short']} box ({b['pick_where']})" if b.get("short") and b.get("pick_where")
               else f" in the {b['short']} box" if b.get("short") else "")
        segs.append({"text": f" ({circuit}){loc}.", "href": ""})
        if b:
            segs.append({"text": " " + reach_clause(b), "href": ""})
            targets.append({"kind": "box", "text": f"{b['short']} box", "href": "#fuse-box-" + b["id"]})
        for i in its:
            targets.append({"kind": "fuse", "text": _ref(i), "href": "#fuse-" + anchor(i["id"])})
            call_items.append(i["id"])
    elif groups:
        g = groups[0]
        segs.append({"text": "Open codes point at ", "href": ""})
        for k, (label, href, _id) in enumerate(g["targets"]):
            segs.append({"text": ", " if k else "", "href": ""})
            segs.append({"text": label, "href": href})
        segs.append({"text": ".", "href": ""})
        for label, href, iid in g["targets"]:
            targets.append({"kind": "ground" if iid == "" else "fuse", "text": label, "href": href})
            if iid:
                call_items.append(iid)
        more = more[1:]
    call = "".join(x["text"] for x in segs)
    return {"call": call, "call_segs": segs, "call_targets": targets, "call_items": call_items, "call_box": call_box,
            "more": more, "groups": groups, "matches": matches, "ground_ids": ground_ids, "codes": codes}


# --- real-state loaders ------------------------------------------------------

def _closed_flag(s: dict[str, Any]) -> bool:
    """The symptom record's own closed / resolved marker, if the store carries one."""
    if s.get("resolved") or s.get("closed"):
        return True
    return str(s.get("status") or "").strip().lower() in ("resolved", "closed", "fixed", "done")


def resolved_symptom_ids(vin: str) -> set[str]:
    """Symptom ids (12 hex chars) named by a visible note tagged "resolved" for this car. The symptom store has no
    status field, so the owner's "resolved" note is the record that closes a symptom."""
    out: set[str] = set()
    try:
        from . import mes_bridge
        for n in mes_bridge.notes(vin)["notes"]:
            if n.get("hidden") or "resolved" not in [str(t).lower() for t in n.get("tags") or []]:
                continue
            out.update(re.findall(r"\b[0-9a-f]{12}\b", n.get("text") or ""))
    except Exception:  # noqa: BLE001
        pass
    return out


def job_inputs(vin: str, open_codes: list[str], dossier: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """(symptoms newest first, {code: description}) from the car's own records. Never raises."""
    syms: list[dict[str, Any]] = []
    try:
        from . import timeline_bridge
        closed = resolved_symptom_ids(vin)
        for s in timeline_bridge.symptoms(vin).get("symptoms", []):
            sid = str(s.get("id") or "")
            if s.get("hidden") or _closed_flag(s) or (sid and any(sid.startswith(c) or c.startswith(sid) for c in closed)):
                continue
            syms.append({"text": s.get("text") or "", "at": s.get("at") or "", "id": sid})
        syms.sort(key=lambda s: s["at"], reverse=True)
    except Exception:  # noqa: BLE001
        pass
    text: dict[str, str] = {}
    try:
        cp = (dossier or {}).get("current_picture") or {}
        for k in ("last_session_with_findings", "latest_session"):
            for d in (cp.get(k) or {}).get("dtcs", []):
                c = str(d.get("code") or "").split("-")[0]
                if c and d.get("description"):
                    text.setdefault(c, d["description"])
    except Exception:  # noqa: BLE001
        pass
    try:
        from mes import jobs
        for j in jobs.open_jobs(vin):
            for h in j.get("hypotheses") or []:
                if h.get("deleted"):
                    continue
                for c in open_codes:
                    m = re.search(re.escape(c) + r"[-0-9A-Fa-f]*\s*'([^']+)'", h.get("text") or "")
                    if m:
                        text.setdefault(c, m.group(1))
    except Exception:  # noqa: BLE001
        pass
    return syms, text


def strap_part() -> Optional[dict[str, str]]:
    """The battery-negative ground strap from the parts catalogue, read at runtime; None when absent."""
    try:
        from . import parts_catalog
        cat = parts_catalog.load() or {}
    except Exception:  # noqa: BLE001
        return None
    for did, d in (cat.get("diagrams") or {}).items():
        for p in d.get("parts") or []:
            blob = f"{p.get('name', '')} {p.get('description', '')}".lower()
            if all(k in blob for k in STRAP_PN_NAME) and p.get("pn"):
                return {"pn": p["pn"], "name": p.get("name", ""), "description": p.get("description", ""),
                        "diagram": d.get("title") or did, "ref": str(p.get("ref") or ""), "diagram_id": did}
    return None


def grounds(vin: str, repo_root: Path) -> list[dict[str, Any]]:
    from . import electrical_bridge as eb
    from . import fuse_health

    def el(i: str) -> dict[str, Any]:
        return eb.get_element(i) or {}

    def path_names(code: str) -> str:
        try:
            ids = [p["element"] for p in eb.path_for_code(code).get("path") or []]
        except Exception:  # noqa: BLE001
            return ""
        lab = {"f82": "F82", "bcm_feed_20a": "20 A BCM feed", "bcm": "BCM", "xy201": "XY201", "g003a": "G003A",
               "g003b": "G003B", "ecm": "ECM", "purge_valve_connector": "purge-valve connector",
               "esim_connector": "ESIM connector", "esim_ground": "ESIM ground"}
        return " > ".join(lab.get(i, i) for i in ids)

    test_exists = (repo_root / TEST_DOC).is_file()
    test_ref = "A written step-by-step version of this test is kept with CUORE." if test_exists else ""
    owner_note = False
    try:
        from . import mes_bridge
        owner_note = any(n.get("id", "").startswith(OWNER_NOTE_ID) for n in mes_bridge.notes(vin)["notes"])
    except Exception:  # noqa: BLE001
        pass

    def last(eid: str) -> str:
        rows = []
        try:
            rows += [(r.get("at") or "", f"{r.get('condition')} on {str(r.get('at'))[:10]} by {r.get('by') or 'technician'}"
                      + (f" - {r['note']}" if r.get("note") else "")) for r in eb.list_inspections(vin, eid)]
        except Exception:  # noqa: BLE001
            pass
        try:
            rows += [(r.get("at") or "", f"{'Tested OK' if r.get('result') == 'ok' else 'Faulty'} on {str(r.get('at'))[:10]} "
                      f"by {r.get('by') or 'technician'}" + (f" - {r['note']}" if r.get("note") else ""))
                     for r in fuse_health._checks(vin, eid)]
        except Exception:  # noqa: BLE001
            pass
        return max(rows)[1] if rows else ""

    def where(e: dict[str, Any]) -> tuple[str, str]:
        """(location text or "" when not sourced, the source of that statement)."""
        loc = e.get("location") or {}
        if loc.get("confidence") == "UNKNOWN" or loc.get("zone") == "unknown":
            return "", loc.get("source") or "none"
        zone = str(loc.get("zone") or "").replace("_", " ")
        return f"{zone.capitalize()}. Exact spot not given by the source.", loc.get("source") or ""

    def test_for(e: dict[str, Any]) -> str:
        return TEST_LINE

    out = []
    for gid, join in (("g003a", "G003B"), ("g003b", "G003A")):
        e = el(gid)
        w, src = where(e)
        out.append({"id": gid, "name": e.get("label") or gid.upper(),
                    "connects": f"Frame ground, paired with {join}, beside inline connector XY201. On CUORE's electrical path "
                                f"for the BCM supply / U-code cascade: {path_names('U0100')}.",
                    "where": w, "source": src + (f"; {', '.join(e.get('tsb_refs') or [])}" if e.get("tsb_refs") else ""),
                    "confidence": (e.get("location") or {}).get("confidence") or "",
                    "applies": "Bulletin names the 2020 Stelvio; applies to this 2018 car: unverified.",
                    "owner": ("Owner says G003A was replaced about two years ago (owner-attested; no CUORE record of "
                              "the work).") if gid == "g003a" and owner_note else "",
                    "last": last(gid), "test": test_for(e), "hint": (e.get("inspection_hint") or "").strip().rstrip("."), "test_ref": test_ref, "part": None, "outside": ""})
    e = el("esim_ground")
    w, src = where(e)
    out.append({"id": "esim_ground", "name": e.get("label") or "ESIM ground point",
                "connects": f"Ground return of the ESIM (EVAP leak-detection module). On CUORE's electrical path for the EVAP "
                            f"codes: {path_names('P0456')}.",
                "where": w or "The ESIM connector is near the left rear wheel well (inferred).",
                "source": src, "confidence": (e.get("location") or {}).get("confidence") or "", "applies": "", "owner": "",
                "last": last("esim_ground"), "test": test_for(e), "hint": (e.get("inspection_hint") or "").strip().rstrip("."), "test_ref": test_ref, "part": None, "outside": ""})
    sp = strap_part()
    out.append({"id": "battery_neg_strap", "name": "Battery-negative ground strap",
                "connects": "Battery negative terminal to the vehicle ground. The catalogue names the strap 'BATTERY NEGATIVE'; "
                            "the other end is not stated.",
                "where": ("Engine Wiring diagram, callout " + sp["ref"] + ".") if sp and sp["ref"] else "",
                "source": f"Mopar parts catalogue, {sp['diagram']}" if sp else "Mopar parts catalogue (not loaded on this computer)",
                "confidence": "", "applies": "", "owner": "", "last": last("battery_neg_strap"),
                "test": TEST_LINE, "hint": "", "test_ref": test_ref, "part": sp, "outside": OUTSIDE_REPORT})
    for g in out:
        g["where_known"] = bool(g["where"])
    return out


# --- search over this page's own items ---------------------------------------

SYNONYMS: dict[str, tuple[str, ...]] = {
    "wiper": ("wiper", "washer", "wash"), "wipers": ("wiper", "washer", "wash"), "washer": ("washer", "wiper", "wash"),
    "window": ("window",), "windows": ("window",),
    "lock": ("lock", "central locking"), "locks": ("lock", "central locking"), "locking": ("lock", "central locking"),
    "unlock": ("lock", "central locking"),
    "heater": ("heater", "heating", "defrost", "demist"), "heating": ("heater", "heating", "defrost", "demist"),
    "defrost": ("heater", "defrost", "demist"),
    "horn": ("horn",),
    "lights": ("light", "lamp"), "light": ("light", "lamp"), "lamp": ("light", "lamp"), "lamps": ("light", "lamp"),
    "radio": ("radio", "hi-fi", "hifi", "usb", "infotainment", "aux"), "hifi": ("hi-fi", "hifi", "radio", "audio"),
    "hi-fi": ("hi-fi", "hifi", "radio", "audio"), "usb": ("usb", "aux"), "audio": ("hi-fi", "hifi", "radio", "audio"),
    "socket": ("socket", "outlet", "12 v"), "outlet": ("socket", "outlet", "12 v"),
    "trailer": ("trailer", "tow"), "tow": ("tow", "trailer"), "towing": ("tow", "trailer"),
    "ground": ("ground", "earth"), "earth": ("ground", "earth"),
}
SEARCH_HINT = "Try a system word (window, lock, wiper...)"


def search(q: str, items: list[dict[str, Any]], boxes: list[dict[str, Any]], grounds_: list[dict[str, Any]],
           status_f: str = "", box_f: str = "") -> list[dict[str, Any]]:
    """Items on the page that match ``q`` (position, circuit, box, type, colour, ground name / connections, plus a small
    synonym index: wiper / washer, lock / central locking, ...). Every word must match. ``15A`` / ``15 A`` match the
    fuse's rating field only; a bare number matches the position number or the rating. Status / box filters narrow the
    fuse and relay results the same way they narrow the page."""
    q = re.sub(r"\s+", " ", (q or "").strip().lower())[:80]
    if not q:
        return []
    bx = {b["id"]: b for b in boxes}
    out: list[dict[str, Any]] = []

    def word_ok(w: str, hay: str) -> bool:
        return w in hay or any(sy in hay for sy in SYNONYMS.get(w, ()))

    def ok(words: list[str], hay: str, item: Optional[dict[str, Any]] = None) -> bool:
        rating = item.get("rating_a") if item is not None else None
        rating = float(rating) if isinstance(rating, (int, float)) else None
        for w in words:
            m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*a", w)
            if m and item is not None:
                if rating is None or float(m.group(1)) != rating:
                    return False
            elif re.fullmatch(r"\d+", w) and item is not None:
                pos = re.search(r"\d+", str(item.get("position") or ""))
                if not ((pos and int(pos.group()) == int(w)) or (rating is not None and rating == float(w))):
                    return False
            elif not word_ok(w, hay):
                return False
        return True

    qn = re.sub(r"(\d)\s+a\b", r"\1a", q)   # "15 a" -> "15a"
    words = qn.split(" ")
    for it in items:
        if box_f and (it.get("box") or "none") != box_f:
            continue
        if status_f and it.get("status") != status_f:
            continue
        b = bx.get(it.get("box")) or {}
        sp = it.get("spec") or {}
        hay = " ".join(str(x) for x in (it.get("position"), it.get("label"), it.get("kind"), b.get("short"), b.get("label"),
                                         b.get("pick_where"), sp.get("type"), sp.get("colour"),
                                         sp.get("relay_type"), sp.get("relay_number")) if x).lower()
        if ok(words, hay, it):
            a = it.get("rating_a")
            out.append({"kind": it.get("kind") or "fuse", "ref": _ref(it), "text": it.get("label") or "",
                        "where": b.get("short") or "box not stated",
                        "amps": f"{a:g} A" if isinstance(a, (int, float)) else "",
                        "href": "#fuse-" + anchor(it["id"])})
    if not status_f:
        for b in boxes:
            if box_f and b["id"] != box_f:
                continue
            hay = " ".join(str(x) for x in (b.get("short"), b.get("label"), b.get("where"), b.get("pick_where")) if x).lower()
            if all(word_ok(w, hay) for w in words):
                out.append({"kind": "box", "ref": b.get("short") or b["id"], "text": b.get("label") or "",
                            "where": b.get("pick_where") or "", "amps": "", "href": "#fuse-box-" + b["id"]})
        if not box_f:
            for g in grounds_:
                hay = " ".join(str(g.get(k) or "") for k in ("id", "name", "connects", "where")).lower()
                if all(word_ok(w, hay) for w in words):
                    out.append({"kind": "ground", "ref": g["name"], "text": g["connects"][:90], "where": g["where"],
                                "amps": "", "href": "#ground-" + g["id"]})
    return out
