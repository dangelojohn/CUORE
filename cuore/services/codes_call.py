"""What the codes page says first, and how it groups the rows.

Pure functions over the shaped code rows plus one thin loader (:func:`job_state`) that reads
the open job's blocker the same way the bench does. Nothing here talks to the car; the call
names only codes the job really has open, and only the action the job's own blocker states.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Optional

#: (key, heading, open by default). "returned" is only shown when a code really returned after a clear.
GROUPS = (
    ("returned", "Came back after a clear", True),
    ("chronic", "Keeps coming back", True),
    ("recurring", "In 2+ visits", True),
    ("cleared", "Cleared", True),
    ("seen-once", "Seen once", False),
)
#: the word a technician says for each internal state key (keys stay as the data and CSS names)
STATE_LABEL = {key: label for key, label, _ in GROUPS}
#: the same states as a verb phrase after "N codes": (one code, several codes)
CALL_WORD = {"returned": ("came back after a clear",) * 2, "chronic": ("keeps coming back", "keep coming back"),
             "recurring": ("seen in 2+ visits",) * 2, "cleared": ("cleared",) * 2, "seen-once": ("seen once",) * 2}
STATE_HELP = (
    (STATE_LABEL["returned"], "erased and set again: the fault is live and reproducing."),
    (STATE_LABEL["chronic"], "comes back across visits or across a meaningful distance."),
    (STATE_LABEL["recurring"], "seen in more than one visit, not yet a repeat pattern."),
    (STATE_LABEL["cleared"], "erased once and not seen since, which proves nothing until the relevant monitor has actually run."),
    (STATE_LABEL["seen-once"], "a single sighting."),
)
FUEL_ACTION = "fuel level first: burn fuel to 15-85 %, then run a drive cycle"

#: query-word groups for the page-only search (shared matcher in ``web/page_search.py``).
CODE_SYNONYMS = (
    ("evap", "evaporative", "evaporation", "purge", "vapour", "vapor"),
    ("abs", "brake", "brakes", "esp"),
    ("network", "can", "bus", "communication", "comms"),
    ("o2", "oxygen", "lambda"), ("window", "riser"), ("engine", "ecm"),
)


def base(code: str) -> str:
    return (code or "").split("-")[0].upper()


def short_module(name: str) -> str:
    """"Body / BCM (Body Computer Module)" -> "BCM"; "Continental ABS MK C1" -> "ABS"."""
    n = (name or "").strip()
    if "/" in n:
        return re.sub(r"\s*\(.*$", "", n.rsplit("/", 1)[1]).strip() or n
    m = re.search(r"\b([A-Z][A-Z0-9]{1,5})\b", n)
    return m.group(1) if m else n[:14]


def short_modules(names: list[str], limit: int = 2) -> str:
    out = list(dict.fromkeys(short_module(n) for n in names or [] if n))
    return ", ".join(out[:limit]) + (f" +{len(out) - limit}" if len(out) > limit else "")


def short_desc(descs: list[str], n: int = 90) -> str:
    s = re.split(r"\s+-\s+", (descs or [""])[0] or "", 1)[0].strip()
    return (s[:n].rsplit(" ", 1)[0] + "...") if len(s) > n else s


def shape(rows: list[dict[str, Any]], job_codes: set[str]) -> None:
    """Add the short module / description, job flag and search text to each row, in place."""
    for r in rows:
        r["modules_short"] = short_modules(r.get("modules") or [])
        r["desc_short"] = short_desc(r.get("descriptions") or [])
        r["in_job"] = base(r.get("dtc", "")) in job_codes
        r["code_href_id"] = base(r.get("dtc", ""))
        r["search_parts"] = [r.get("dtc"), " ".join(r.get("descriptions") or []), " ".join(r.get("modules") or []),
                             r["modules_short"], r.get("system_bucket"), r.get("severity")]


def group_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """State groups in diagnosis order, the open job's codes first inside each; empty groups dropped."""
    out = []
    for key, label, opened in GROUPS:
        g = [r for r in rows if (r.get("severity") or "seen-once") == key]
        if not g:
            continue
        # the open job's codes first, then the fault board's own order (priority tier, then most recent)
        g = sorted(g, key=lambda r: (0 if r.get("in_job") else 1, (r.get("fb") or {}).get("rank", 9999)))
        out.append({"key": key, "label": label, "open": opened, "rows": g, "n": len(g),
                    "job_n": sum(1 for r in g if r.get("in_job"))})
    return out


def build_call(rows: list[dict[str, Any]], job_codes: set[str], blocker: Optional[str], vin: str,
               action_text: Optional[str] = None, query: str = "") -> dict[str, Any]:
    """``call_segs`` (``{text, href}`` pieces), ``call`` (the same line as text) and ``targets`` (Go-to chips)."""
    mine = [r for r in rows if r.get("in_job")]
    segs: list[dict[str, str]] = []
    targets: list[dict[str, str]] = []
    if not mine and query:
        n = len(rows)
        txt = (f"{n} code{'' if n == 1 else 's'} match “{query}”; none on the open job."
               if n else f"No code matches “{query}”.")
        segs.append({"text": txt, "href": ""})
    elif not mine:
        segs.append({"text": "No open codes on this car right now.", "href": ""})
    else:
        cnt = Counter(r.get("system_bucket") or "Other" for r in mine)
        fuel = (blocker or "") == "fuel out of window" and cnt.get("EVAP")
        bucket = "EVAP" if fuel else cnt.most_common(1)[0][0]
        grp = [r for r in mine if (r.get("system_bucket") or "Other") == bucket]
        states = {r.get("severity") for r in grp}
        one = next(iter(states)) if len(states) == 1 else None
        state = CALL_WORD.get(one, ("open", "open"))[0 if len(grp) == 1 else 1]
        segs.append({"text": f"{len(grp)} {bucket} code{'' if len(grp) == 1 else 's'} {state}: ", "href": ""})
        for k, r in enumerate(grp):
            segs.append({"text": ", " if k else "", "href": ""})
            segs.append({"text": base(r["dtc"]), "href": f"/v/{vin}/code/{base(r['dtc'])}"})
        action = FUEL_ACTION if fuel else (action_text or "")
        segs.append({"text": (" - " + action.rstrip(".") + ".") if action else ".", "href": ""})
        if fuel:
            targets.append({"kind": "bench", "text": "Fuel gate on the Bench", "href": f"/v/{vin}"})
    return {"call": "".join(s["text"] for s in segs), "call_segs": segs, "targets": targets,
            "job_count": len(mine)}


def job_state(vin: str, dossier: dict[str, Any]) -> tuple[set[str], Optional[str], Optional[str]]:
    """(open job codes, the verdict's blocker key, the curated action for it). Never raises, never touches the car."""
    try:
        from . import bench_bridge, dossier_bridge, mes_bridge
        codes = {base(c) for c in mes_bridge.open_codes_for(dossier)}
        v = dossier_bridge.build_view(vin, dossier, None).get("verdict") or {}
        b = v.get("blocker")
        act = bench_bridge.LABELS["blocker"].get(b) if b not in (None, "none", "no data") else None
        return codes, b, (act[:1].lower() + act[1:]) if act else None
    except Exception:  # noqa: BLE001 -- the page works without a job
        return set(), None, None


#: board statuses worth a chip on the Codes page (the row's own state chip already says the rest)
BOARD_CHIPS = {"verifying": "Verifying", "proven-fixed": "Proven fixed"}


def attach_board(rows: list[dict[str, Any]], vin: str) -> None:
    """Give each row ``fb`` = the fault board's card for that code (key, chip, can_fix/can_undo). Never raises.

    Uses ``fault_board.board`` (its facts are cached on the log/state fingerprint). The fault key is the card's own
    ``code:<module>:<code>``; with two modules for one code the one matching the row's module wins.
    """
    try:
        from . import fault_board
        by_code: dict[str, list[dict[str, Any]]] = {}
        for c in fault_board.board(vin):
            if c.get("kind") == "code":
                by_code.setdefault(c["code"], []).append(c)
        for r in rows:
            cards = by_code.get(base(r.get("dtc", "")))
            if not cards:
                continue
            mod = fault_board._short_module(r.get("modules") or [])
            c = (next((x for x in cards if x["module"] == mod), None)
                 or next((x for x in cards if x.get("fixed")), None) or cards[0])
            chip = ("Returned after fix" if c.get("returned_after_fix") else BOARD_CHIPS.get(c["status"], ""))
            v = view(c)
            r["fb"] = {**v, "key": c["key"], "chip": chip, "status": c["status"], "can_fix": bool(c.get("can_fix")),
                       "can_undo": bool(c.get("can_undo")), "detail": c.get("status_detail", "")}
            r["last_seen_ago"] = v["last_seen_text"]
    except Exception:  # noqa: BLE001 -- the Codes page works without the board
        return


# --- one story per fault: the fault board's card, the same words on every page -----------------

#: chip class (existing cuore.css classes) per board status; the word and mark always sit beside the colour
_STATUS_CHIP = {"permanent": "returned", "active": "returned", "pending": "chronic", "verifying": "chronic",
                "history": "plain", "proven-fixed": "ok", "resolved": "ok"}
#: board statuses that mean "the car reports it now"
STANDING = ("permanent", "active", "pending")


def last_seen_text(ts: Any, now: Any = None) -> str:
    """"11 h ago · 2026-10-26" (under a day) or "3 d ago · 2026-10-23". One formatter for every page."""
    from datetime import datetime
    from . import fault_board
    d = fault_board._dt(ts)
    if d is None:
        return "—"
    secs = max(0.0, ((now or datetime.now()) - d).total_seconds())
    ago = "just now" if secs < 3600 else (f"{int(secs // 3600)} h ago" if secs < 86400 else f"{int(secs // 86400)} d ago")
    return f"{ago} · {d.strftime('%Y-%m-%d')}"


def view(card: dict[str, Any], now: Any = None) -> dict[str, Any]:
    """The small, template-ready story of one board card (status word, mark, last seen, tier, Fixed state)."""
    returned = bool(card.get("returned_after_fix"))
    return {
        "key": card["key"], "code": card.get("code") or "", "module": card.get("module") or "",
        "kind": card.get("kind"), "title": card.get("label") or card.get("code") or "",
        "status": card["status"], "label": card["status_label"], "mark": card["status_mark"],
        "chip": _STATUS_CHIP.get(card["status"], "plain"),
        "returned": returned, "chip_extra": "Returned after fix" if returned else "",
        "last_seen": card.get("last_seen"), "last_seen_text": last_seen_text(card.get("last_seen"), now),
        "present_text": card.get("present_text", ""), "rank": card.get("rank", 9999),
        "tier": (card.get("importance") or {}).get("tier", 99), "tier_name": (card.get("importance") or {}).get("name", ""),
        "standing": card["status"] in STANDING, "can_fix": bool(card.get("can_fix")),
        "can_undo": bool(card.get("can_undo")), "detail": card.get("status_detail", ""),
        "href": card.get("href") or "",
    }


def board_views(vin: str) -> list[dict[str, Any]]:
    """Every board card as a :func:`view`, board order (priority tier, then most recent). Never raises."""
    try:
        from datetime import datetime
        from . import fault_board
        now = datetime.now()
        return [view(c, now) for c in fault_board.board(vin)]
    except Exception:  # noqa: BLE001 -- pages work without the board
        return []


def code_view(vin: str, code: str, views: Optional[list[dict[str, Any]]] = None) -> Optional[dict[str, Any]]:
    """The best (lowest rank) board view for a code across modules, or None."""
    b = base(code)
    hits = [v for v in (views if views is not None else board_views(vin)) if v["kind"] == "code" and v["code"] == b]
    return min(hits, key=lambda v: v["rank"]) if hits else None


def standing_views(vin: str, views: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Present / permanent / active (pending) code faults, board order."""
    return [v for v in (views if views is not None else board_views(vin)) if v["kind"] == "code" and v["standing"]]
