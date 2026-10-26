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
    ("returned", "Returned after a clear", True),
    ("chronic", "Chronic", True),
    ("recurring", "Recurring", True),
    ("cleared", "Cleared", True),
    ("seen-once", "Seen once", False),
)
STATE_HELP = (
    ("returned", "erased and set again: the fault is live and reproducing."),
    ("chronic", "recurs across sessions or across meaningful distance."),
    ("recurring", "seen in more than one session, not yet chronic."),
    ("cleared", "erased once and not seen since, which proves nothing until the relevant monitor has actually run."),
    ("seen-once", "a single sighting."),
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
        g = sorted(g, key=lambda r: 0 if r.get("in_job") else 1)
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
        state = next(iter(states)) if len(states) == 1 else "open"
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
