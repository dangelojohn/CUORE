"""Fuse and relay health: every fuse/relay CUORE can source, with a colour.

green  OK                   (technician check OK, or inferred -- labelled -- from the modules it feeds answering)
orange fault / suspect      (technician suspect / voltage drop over the entered limit / supply code / code path names it)
red    dead / blown         (technician blown, or every module it feeds is silent)
grey   no evidence yet

Reads saved data only; never contacts the car. Rows come from
``cuore/data/fuses_stelvio_2018.json`` (sourced rows only) plus technician
additions in ``fuse_items.jsonl``. Checks are append-only in
``fuse_checks.jsonl``.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..live import config as _config

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "fuses_stelvio_2018.json"
CHECKS_FILE = "fuse_checks.jsonl"
ITEMS_FILE = "fuse_items.jsonl"
FULLSCAN_FILE = "fullscan_last.json"
SENSOR_CHECKS_FILE = "sensor_checks.jsonl"

RESULTS = ("ok", "suspect", "blown")
METHODS = ("visual", "continuity", "voltage_drop", "voltage")
KINDS = ("fuse", "relay")
STATUSES = ("green", "orange", "red", "grey")
_RANK = {"grey": 0, "green": 1, "orange": 2, "red": 3}

_SUPPLY_WORDS = re.compile(r"\b(voltage|supply|power|battery|b\+|undervoltage|overvoltage)\b", re.I)
_MODULE_TOKENS = re.compile(r"\b(ECM|TCM|BCM|IPC|RFHUB|DASM|HALF|ABS|DTCM|EPS|ORC|ESM|ETM|AFLS|PAM)\b")


def _sd() -> Path:
    return _config.state_dir()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_jsonl(name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for line in (_sd() / name).read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict):
                out.append(o)
    except OSError:
        pass
    return out


def _append(name: str, rec: dict[str, Any]) -> None:
    p = _sd() / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _num(v: Any) -> Optional[float]:
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


# --- registry ---------------------------------------------------------------

def _base() -> dict[str, Any]:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"boxes": [], "items": []}


def boxes() -> list[dict[str, Any]]:
    return [dict(b) for b in _base().get("boxes", [])]


def catalogue_parts() -> dict[str, Any]:
    """Fuse/relay part types, read from the catalogue in ProgramData at call
    time -- catalogue rows stay out of git, so the data file only names the
    diagrams (and named extra parts) to pull. ``parts`` is empty when the
    catalogue has not been built on this computer."""
    ref = _base().get("catalogue_parts") or {}
    out: dict[str, Any] = {"source": ref.get("source", ""), "parts": []}
    try:
        from . import parts_catalog
        cat = parts_catalog.load() or {}
    except Exception:  # noqa: BLE001 -- no catalogue: show nothing, not an error
        return out
    diagrams = cat.get("diagrams") or {}
    rows = [p for did in ref.get("diagram_ids") or [] for p in (diagrams.get(did) or {}).get("parts") or []]
    for x in ref.get("extra_parts") or []:
        rows += [p for p in (diagrams.get(x.get("diagram_id")) or {}).get("parts") or []
                 if p.get("name") == x.get("name")]
    seen: set[str] = set()
    for p in rows:
        if p.get("pn") and p["pn"] not in seen:
            seen.add(p["pn"])
            out["parts"].append({"pn": p["pn"], "name": p.get("name", ""), "description": p.get("description", "")})
    return out


def registry() -> list[dict[str, Any]]:
    """Sourced rows plus technician-added rows (marked)."""
    box_zone = {b["id"]: b.get("zone") for b in _base().get("boxes", [])}
    rows = [dict(r, added_by_technician=False) for r in _base().get("items", [])]
    seen = {r["id"] for r in rows}
    for rec in _read_jsonl(ITEMS_FILE):
        if not rec.get("id") or rec["id"] in seen or not str(rec.get("source") or "").strip():
            continue
        seen.add(rec["id"])
        row = dict(rec)
        row.setdefault("zone", box_zone.get(row.get("box")))
        row.setdefault("side", None)
        row.setdefault("feeds_modules", [])
        row.setdefault("feeds_elements", [])
        row.setdefault("part_numbers", [])
        row["added_by_technician"] = True
        row["notes"] = ("Added by technician" + (f" ({row.get('by')}, {row.get('added_at')})" if row.get("by") else "")
                        + (". " + row["notes"] if row.get("notes") else "."))
        rows.append(row)
    return rows


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def add_item(*, kind: str, label: str, source: str, box: str = "", position: str = "",
             rating_a: Any = None, feeds_modules: Optional[list[str]] = None, notes: str = "",
             by: str = "technician") -> dict[str, Any]:
    """A technician adds a fuse/relay read off the box cover or the manual.
    ``source`` is REQUIRED (what it was read from)."""
    kind = (kind or "").strip().lower()
    if kind not in KINDS:
        raise ValueError("kind must be fuse or relay")
    label = (label or "").strip()
    if not label:
        raise ValueError("a label is required")
    source = (source or "").strip()
    if not source:
        raise ValueError("a source is required (owner's manual page, box cover photo, ...)")
    box = (box or "").strip()
    box_ids = {b["id"] for b in _base().get("boxes", [])}
    if box and box not in box_ids:
        raise ValueError("unknown fuse box: " + box)
    rating = None
    if rating_a not in (None, ""):
        rating = _num(rating_a)
        if rating is None or rating <= 0:
            raise ValueError("rating must be a positive number of amps")
    position = (position or "").strip()
    item_id = "tech-" + _slug(f"{box or 'nobox'}-{position or label}")[:60]
    if any(r["id"] == item_id for r in registry()):
        raise ValueError("that fuse/relay is already in the list")
    mods = [m.strip().upper() for m in (feeds_modules or []) if m and m.strip()]
    rec = {"id": item_id, "kind": kind, "box": box or None, "position": position or None, "rating_a": rating,
           "label": label, "feeds_modules": mods, "feeds_elements": [], "part_numbers": [],
           "location_confidence": "SOURCED", "source": source, "notes": (notes or "").strip(),
           "by": (by or "technician").strip() or "technician", "added_at": _now()}
    _append(ITEMS_FILE, rec)
    return rec


# --- technician checks ------------------------------------------------------

def add_check(vin: str, item_id: str, result: str, method: str, value: str = "", unit: str = "",
              note: str = "", by: str = "technician", limit: str = "") -> dict[str, Any]:
    result = (result or "").strip().lower()
    method = (method or "").strip().lower()
    if result not in RESULTS:
        raise ValueError("result must be one of: " + ", ".join(RESULTS))
    if method not in METHODS:
        raise ValueError("method must be one of: " + ", ".join(METHODS))
    if not (vin or "").strip():
        raise ValueError("vin is required")
    if item_id not in {r["id"] for r in registry()}:
        raise ValueError("unknown fuse/relay: " + str(item_id))
    if method in ("voltage_drop", "voltage") and value.strip() and _num(value) is None:
        raise ValueError("value must be a number")
    if limit.strip() and _num(limit) is None:
        raise ValueError("limit must be a number")
    rec = {"id": uuid.uuid4().hex[:12], "vin": vin.strip(), "item": item_id, "at": _now(), "by": (by or "technician").strip() or "technician",
           "result": result, "method": method, "value": value.strip(), "unit": unit.strip(),
           "limit": limit.strip(), "note": note.strip()}
    _append(CHECKS_FILE, rec)
    return rec


def _checks(vin: str, item_id: str) -> list[dict[str, Any]]:
    rows = [c for c in _read_jsonl(CHECKS_FILE)
            if c.get("item") == item_id and (not c.get("vin") or str(c["vin"]).upper() == vin.upper())]
    return sorted(rows, key=lambda c: str(c.get("at") or ""))


def _inspections(vin: str, item: dict[str, Any]) -> list[dict[str, Any]]:
    """Electrical-inspection store entries whose element id is this item's id (or its element_id)."""
    ids = {item["id"], item.get("element_id") or item["id"]}
    out = []
    try:
        from mes import electrical_inspections
        for e in electrical_inspections.load(vin):
            if e.get("element") in ids:
                out.append(e)
    except Exception:  # noqa: BLE001 - store unavailable: no evidence from it
        pass
    return out


# --- module / code evidence -------------------------------------------------

def _fullscan() -> tuple[str, dict[str, dict[str, Any]]]:
    p = _sd() / FULLSCAN_FILE
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", {}
    at = ""
    m = re.search(r"(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$", str(d.get("scan_id") or ""))
    if m:
        yy, mo, dd, hh, mi = m.groups()
        at = f"20{yy}-{mo}-{dd}T{hh}:{mi}:00"
    else:
        try:
            at = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            pass
    mods: dict[str, dict[str, Any]] = {}
    for c in d.get("coverage") or []:
        mod, cat = c.get("module"), c.get("category")
        if not mod:
            continue
        state = "answered" if cat == "answered" else ("no_answer" if cat == "not_reachable" else "unknown")
        why = c.get("why") or ""
        if state == "no_answer" and "needs" in why and "cable" in why:
            state = "needs_cable"
        mods[mod] = {"state": state, "at": at, "src": "the last full scan", "active": c.get("active")}
    return at, mods


def _module_states(vin: str) -> dict[str, dict[str, Any]]:
    _, mods = _fullscan()
    last = None
    for c in _read_jsonl(SENSOR_CHECKS_FILE):
        if c.get("vin") and str(c["vin"]).upper() != vin.upper():
            continue
        last = c
    if last:
        for m, ok in (last.get("modules_answered") or {}).items():
            if (last.get("at") or "") >= (mods.get(m, {}).get("at") or ""):
                mods[m] = {"state": "answered" if ok else "no_answer", "at": last.get("at") or "",
                           "src": "the last sensor check", "active": mods.get(m, {}).get("active")}
    return mods


def _module_of(text: str) -> str:
    m = _MODULE_TOKENS.search(text or "")
    return m.group(1) if m else ""


def _current_codes(vin: str, mods: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Stored codes not superseded by a later clean full scan of their module."""
    try:
        from . import mes_bridge
        dtcs = mes_bridge.extract_dtcs(vin=vin).get("dtcs", [])
    except Exception:  # noqa: BLE001 - no MES logs: no code evidence
        return []
    fs_at, _ = _fullscan()
    out = []
    for r in dtcs:
        occ = sorted(r.get("occurrences") or [], key=lambda o: str(o.get("timestamp") or ""))
        status = str(occ[-1].get("status") or "") if occ else (r.get("statuses_seen") or [""])[-1]
        if status != "stored":
            continue
        last_seen = str(r.get("last_seen") or "").replace(" ", "T")
        mod = _module_of(" ".join(r.get("modules") or []))
        ms = mods.get(mod)
        if ms and ms.get("src") == "the last full scan" and ms.get("state") == "answered" \
                and ms.get("active") == 0 and (fs_at or "") > last_seen:
            continue
        out.append({"code": str(r.get("dtc") or ""), "module": mod,
                    "description": (r.get("descriptions") or [""])[0], "last_seen": last_seen})
    return out


def _path_hops(code: str) -> set[str]:
    try:
        from mes import electrical
        p = electrical.code_electrical_path(code.split("-")[0])
        return {h.get("id") for h in p.get("path", []) if h.get("id")}
    except Exception:  # noqa: BLE001
        return set()


# --- health -----------------------------------------------------------------

def _worse(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


#: same rule as sensor_health: evidence older than this is not current health.
STALE_AFTER_DAYS = 7


def _age_days(at: Any) -> Optional[int]:
    try:
        return (datetime.now() - datetime.fromisoformat(str(at)[:19])).days
    except ValueError:
        return None


def health(vin: str) -> dict[str, Any]:
    mods = _module_states(vin)
    codes = _current_codes(vin, mods)
    hops = {c["code"]: _path_hops(c["code"]) for c in codes}
    items = []
    for row in registry():
        status, reasons, evidence, rcodes = "grey", [], [], []

        # technician evidence (checks + inspections), newest wins
        tech: list[tuple[str, str, str]] = []  # (at, result, text)
        for c in _checks(vin, row["id"]):
            val = f" {c.get('value')} {c.get('unit') or ''}".rstrip() if c.get("value") else ""
            lim = f" (limit {c['limit']} {c.get('unit') or ''})".replace("  ", " ") if c.get("limit") else ""
            text = f"{c.get('by')} checked by {c.get('method')}: {c.get('result')}{val}{lim}" + (f" - {c['note']}" if c.get("note") else "")
            res = c["result"]
            vv, ll = _num(c.get("value")), _num(c.get("limit"))
            if c.get("method") == "voltage_drop" and vv is not None and ll is not None and vv > ll and res == "ok":
                res = "suspect"
                text += f" -> voltage drop {vv:g} is over the limit {ll:g}, treated as suspect"
            tech.append((str(c.get("at") or ""), res, text))
            evidence.append({"kind": "technician check", "at": c.get("at"), "text": text})
        for e in _inspections(vin, row):
            cond = str(e.get("condition") or "")
            res = "ok" if cond in ("ok", "repaired", "replaced") else "suspect"
            text = f"inspection record: {cond}" + (f" - {e['note']}" if e.get("note") else "")
            tech.append((str(e.get("at") or ""), res, text))
            evidence.append({"kind": "inspection", "at": e.get("at"), "text": text})
        tech.sort()
        tech_at = tech[-1][0] if tech else ""
        if tech:
            at, res, text = tech[-1]
            if res == "blown":
                status = "red"
                reasons.append(f"RED: a technician recorded it blown/open/no voltage ({at}).")
            elif res == "suspect":
                status = "orange"
                reasons.append(f"ORANGE: the technician marked it suspect or the voltage drop is out of limit ({at}).")
            else:
                status = "green"
                reasons.append(f"GREEN: a technician check recorded it OK ({at}).")

        fed = [m for m in row.get("feeds_modules") or []]
        # module silence
        known = [(m, mods[m]) for m in fed if m in mods]
        if fed and len(known) == len(fed) and all(s["state"] == "no_answer" for _, s in known):
            at = max(s["at"] for _, s in known)
            if at > tech_at:
                status = _worse(status, "red")
                reasons.append(f"RED: every module it feeds ({', '.join(fed)}) did not answer in {known[0][1]['src']} ({at}).")
                evidence.append({"kind": "module silent", "at": at, "text": ", ".join(fed) + " did not answer"})
        # supply codes on fed modules + code paths naming this element
        supply_hit = False
        ids = {row["id"], row.get("element_id") or row["id"]}
        for c in codes:
            if c["last_seen"] and tech_at and c["last_seen"] <= tech_at:
                continue
            if c["module"] in fed and _SUPPLY_WORDS.search(c["description"] or ""):
                supply_hit = True
                status = _worse(status, "orange")
                rcodes.append(c["code"])
                reasons.append(f"ORANGE: active code {c['code']} on {c['module']} reads as a supply/voltage fault ({c['description'][:80]}).")
                evidence.append({"kind": "code", "at": c["last_seen"], "text": f"{c['code']} {c['description'][:100]}"})
            elif ids & hops.get(c["code"], set()):
                status = _worse(status, "orange")
                rcodes.append(c["code"])
                reasons.append(f"ORANGE: code {c['code']} has an electrical path that names this fuse as a supply hop to check "
                               "(a place to look, not proof it is faulty).")
                evidence.append({"kind": "code path", "at": c["last_seen"], "text": f"{c['code']} path includes {row['id']}"})
        # inferred green
        if not tech and fed and status == "grey" and not supply_hit:
            if all(m in mods and mods[m]["state"] == "answered" for m in fed):
                at = max(mods[m]["at"] for m in fed)
                age = _age_days(at)
                if age is not None and age > STALE_AFTER_DAYS:
                    reasons.append(f"GREY: the module it feeds last answered {at} ({age} days ago) -- too old to "
                                   "count as current health; run a full scan or record a check.")
                    evidence.append({"kind": "inferred (stale)", "at": at, "text": ", ".join(fed) + " answered"})
                    items.append({**row, "status": "grey", "reasons": reasons, "evidence": evidence,
                                  "codes": rcodes, "stale": True})
                    continue
                status = "green"
                reasons.append(f"GREEN (inferred: the module it feeds answered at {at}): every module it feeds ({', '.join(fed)}) "
                               f"answered in {mods[fed[0]]['src']} and none has a supply code. Not a direct fuse test.")
                evidence.append({"kind": "inferred", "at": at, "text": ", ".join(fed) + " answered"})
        if status == "grey":
            reasons.append("GREY: no evidence yet -- no technician check, and no fed module on record to infer from."
                           if not fed else "GREY: no evidence yet -- no technician check and the modules it feeds have no usable scan answer.")
        items.append({**row, "status": status, "reasons": reasons, "evidence": evidence, "codes": rcodes})

    counts = {k: sum(1 for i in items if i["status"] == k) for k in STATUSES}
    counts["total"] = len(items)
    bx = boxes()
    unplaced = [i["id"] for i in items if not i.get("zone")]
    ats = [str(e["at"]) for i in items for e in i["evidence"] if e.get("at")]
    return {"vin": vin, "checked_at": max(ats) if ats else None, "boxes": bx, "items": items, "counts": counts,
            "unplaced": unplaced, "gaps": gaps(items, bx)}


def gaps(items: list[dict[str, Any]], bx: list[dict[str, Any]]) -> list[str]:
    out = []
    for b in bx:
        if not b.get("full_list_sourced"):
            n = sum(1 for i in items if i.get("box") == b["id"])
            out.append(f"{b['label']}: full fuse list not sourced yet ({n} listed). Add the owner's manual fuse table "
                       "or photos of the box cover.")
    nr = [i for i in items if i["kind"] == "fuse" and i.get("rating_a") is None]
    if nr:
        out.append(f"{len(nr)} listed fuse(s) have no amp rating in any source.")
    if sum(1 for i in items if i["kind"] == "relay") < 2:
        out.append("Relays: only the starter relay is named in any source (and its location is unverified). No relay list "
                   "or positions for any box. Add them from the box cover.")
    nf = [i for i in items if not i.get("feeds_modules")]
    if nf:
        out.append(f"{len(nf)} row(s) have no sourced module they feed, so the page cannot infer their health from module answers.")
    unp = [i for i in items if not i.get("zone")]
    if unp:
        out.append(f"{len(unp)} row(s) have no sourced location and are not on the drawing: "
                   + ", ".join(i["label"] for i in unp) + ".")
    out.append("The Mopar catalogue lists fuse and relay part TYPES for the power distribution center, not which position uses which.")
    out.append("Interior and luggage-compartment rows come from a third-party diagram (unverified); no FCA fuse table has been read.")
    return out
