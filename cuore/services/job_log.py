"""Organised repair log for the Job page (step 9).

``log_view(job, kind, sort, q, fault)`` turns ``job["actions"]`` into chips with
counts, filtered + sorted one-line rows, folded groups of near-identical
entries, durations and per-fault first/last dates. Pure functions over the
job dict: no I/O, no writes. Retracted actions (``job["retracted_actions"]``)
never appear in the list; they are only counted.

The Job page calls ``job_log_context(job, request.query_params)`` and renders
``_job_log.html`` with the result under the name ``log``.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping, Optional
from urllib.parse import quote, urlencode

from ..web import page_search

# chip id -> (plain label, action kinds it holds)
KIND_CHIPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("repair", "Repairs & parts", ("repair", "part")),
    ("test", "Tests", ("test",)),
    ("inspection", "Inspections", ("inspection",)),
    ("clear", "Clears", ("clear",)),
    ("note", "Notes", ("note", "understand")),
    ("reading", "Readings", ("observation",)),
)
_KIND_TO_CHIP = {k: cid for cid, _l, ks in KIND_CHIPS for k in ks}
_CHIP_LABEL = {cid: label for cid, label, _ks in KIND_CHIPS}
_NOUN = {"repair": "repair", "test": "test", "inspection": "inspection",
         "clear": "clear", "note": "note", "reading": "reading"}
SORTS = (("newest", "Newest first"), ("oldest", "Oldest first"),
         ("kind", "By kind"), ("fault", "By fault code"))
_SORT_IDS = {s for s, _ in SORTS}

DTC_RE = re.compile(r"\b([PBCU][0-9A-F]{4})(?:-[0-9A-F]{2})?\b")
SUMMARY_MAX = 140
MIN_GROUP = 3
SIMILAR = 0.4
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_BEFORE_RE = re.compile(r"(?:present before the clear|before the clear)[^:]*:?(.*)", re.I | re.S)


def _chip_of(a: Mapping[str, Any]) -> str:
    return _KIND_TO_CHIP.get(a.get("kind") or "note", "note")


def _ref_parts(ref: Any) -> tuple[str, str, str]:
    if isinstance(ref, Mapping):
        return str(ref.get("kind") or ""), str(ref.get("id") or ""), str(ref.get("label") or "")
    if ref:
        return "", str(ref), str(ref)
    return "", "", ""


def _ref_href(vin: str, kind: str, id_: str) -> Optional[str]:
    """Only ref kinds that have a page are linked; everything else stays plain text."""
    if not vin or not id_:
        return None
    if kind == "bulletin":
        return f"/tsb?vin={quote(vin)}"
    if kind == "live":
        return f"/v/{vin}/liveboard"
    if kind in ("log", "observation", "note") and re.match(r"(SCAN_|FESLog_)", id_):
        return f"/v/{vin}/scans"
    if kind == "note" and re.fullmatch(r"[0-9a-f]{12}", id_):
        return f"/v/{vin}/notes"
    return None


def faults_of(text: str) -> list[str]:
    """Distinct DTC base codes (P0455-00 -> P0455), in order of first mention."""
    out: list[str] = []
    for m in DTC_RE.finditer(text or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def summarise(text: str, limit: int = SUMMARY_MAX) -> str:
    """First sentence, at most ``limit`` chars, never cut mid-word."""
    t = re.sub(r"\s+", " ", text or "").strip()
    m = re.search(r"(?<=[A-Za-z0-9\)\]][.!?])\s+(?=[A-Z0-9])", t)
    first = t[:m.start()] if m else t
    if len(first) <= limit:
        return first
    cut = first[:limit - 1]
    if first[limit - 1] != " " and " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-(") + "…"


def _day(s: Any) -> Optional[date]:
    m = _DATE_RE.match(str(s or ""))
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _ago(d: Optional[date], today: date) -> str:
    if d is None:
        return ""
    n = (today - d).days
    if n < 0:
        return "in the future"
    if n == 0:
        return "today"
    return "1 day ago" if n == 1 else f"{n} days ago"


def _words(text: str) -> frozenset[str]:
    t = DTC_RE.sub(" ", text.lower())
    t = re.sub(r"[\w.-]*\d[\w.-]*", " ", t)
    return frozenset(re.findall(r"[a-z]{3,}", t))


def _similar(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= SIMILAR


def _opening(text: str) -> str:
    """First two alphabetic words ("descriptive entry", "repair history"): the
    house style that marks a family of entries."""
    return " ".join(re.findall(r"[A-Za-z]{3,}", text)[:2]).lower()


def _same_family(g: dict[str, Any], e: dict[str, Any]) -> bool:
    if g["chip"] != e["chip"]:
        return False
    if e["chip"] == "clear":      # every clear is a repeat of one event type; the group expands to each
        return True
    return ((_opening(g["summary"]) == _opening(e["summary"]) != "")
            or _similar(g["_words"], e["_words"]))


def _codes_before_clear(text: str) -> Optional[set[str]]:
    """Codes the entry says were present before the clear; None when it does not say."""
    m = _BEFORE_RE.search(text or "")
    if not m:
        return None
    tail = m.group(1)
    codes = set(faults_of(tail))
    if codes:
        return codes
    return set() if re.search(r"\bnone\b|\b0 stored\b", tail[:80], re.I) else None


def _entry(a: Mapping[str, Any], vin: str, today: date) -> dict[str, Any]:
    text = a.get("text") or ""
    rk, rid, rlabel = _ref_parts(a.get("ref"))
    when = a.get("event_date") or a.get("effective_date") or a.get("at") or ""
    d = _day(when) or _day(a.get("at"))
    chip = _chip_of(a)
    summ = summarise(text)
    return {
        "id": a.get("id"), "kind": a.get("kind"), "chip": chip, "kind_label": _NOUN[chip],
        "summary": summ, "text": text, "long": len(re.sub(r"\s+", " ", text).strip()) > len(summ),
        "date": str(when)[:16].replace("T", " "), "day": d.isoformat() if d else "",
        "days_ago": _ago(d, today), "approx": bool(a.get("date_uncertain")),
        "recorded": str(a.get("at") or "")[:16].replace("T", " "),
        "faults": faults_of(text + " " + rlabel + " " + rid),
        "ref": ({"kind": rk, "id": rid, "label": rlabel or rid, "href": _ref_href(vin, rk, rid)}
                if (rid or rlabel) else None),
        "_sortkey": str(when) or str(a.get("at") or ""),
        "_before": _codes_before_clear(text) if chip == "clear" else None,
        "_words": _words(summ),
    }


def _sort(entries: list[dict[str, Any]], how: str) -> list[dict[str, Any]]:
    if how == "oldest":
        return sorted(entries, key=lambda e: e["_sortkey"])
    newest = sorted(entries, key=lambda e: e["_sortkey"], reverse=True)
    if how == "kind":
        order = {cid: i for i, (cid, _l, _k) in enumerate(KIND_CHIPS)}
        return sorted(newest, key=lambda e: order[e["chip"]])
    if how == "fault":
        return sorted(newest, key=lambda e: (not e["faults"], e["faults"][0] if e["faults"] else ""))
    return newest


def _returned(members: list[dict[str, Any]]) -> Optional[tuple[int, int]]:
    """(returned, comparable) from the clears' own text, else None.

    A clear is comparable when it and the next clear (by date) both say which
    codes were present before them; it 'returned' when any code present before
    this clear is listed again before the next one."""
    ordered = sorted(members, key=lambda e: e["_sortkey"])
    comparable = returned = 0
    for cur, nxt in zip(ordered, ordered[1:]):
        if cur["_before"] is None or nxt["_before"] is None:
            continue
        comparable += 1
        if cur["_before"] & nxt["_before"]:
            returned += 1
    return (returned, comparable) if comparable else None


def _span(entries: list[dict[str, Any]]) -> tuple[str, str]:
    days = sorted(e["day"] for e in entries if e["day"])
    return (days[0], days[-1]) if days else ("", "")


def _public(e: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in e.items() if not k.startswith("_")}


def _fold(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per entry, except near-identical same-kind sets of >= MIN_GROUP,
    which become one group row placed where its first member sat."""
    groups: list[list[dict[str, Any]]] = []
    for e in entries:
        for g in groups:
            if _same_family(g[0], e):
                g.append(e)
                break
        else:
            groups.append([e])
    lead = {id(g[0]): g for g in groups if len(g) >= MIN_GROUP}
    folded = {id(m) for g in lead.values() for m in g[1:]}
    rows: list[dict[str, Any]] = []
    for e in entries:
        if id(e) in lead:
            g = lead[id(e)]
            first, last = _span(g)
            n = len(g)
            noun = _NOUN[e["chip"]] + "s"
            label = f"{n} {noun}, {first} → {last}" if first else f"{n} {noun}"
            ret = _returned(g) if e["chip"] == "clear" else None
            if ret:
                label += f"; codes returned after {ret[0]} of {ret[1]} that had a later clear to compare"
            rows.append({"group": True, "chip": e["chip"], "kind_label": _NOUN[e["chip"]],
                         "count": n, "first": first, "last": last, "label": label,
                         "returned": ret[0] if ret else None, "returned_of": ret[1] if ret else None,
                         "entries": [_public(m) for m in g]})
        elif id(e) not in folded:
            rows.append({"group": False, **_public(e)})
    return rows


def _url(base: str, **p: Any) -> str:
    qs = urlencode({k: v for k, v in p.items() if v})
    return base + (("&" if "?" in base else "?") + qs if qs else "") + "#job-log"


def log_view(job: Mapping[str, Any], kind: Optional[str] = None, sort: str = "newest",
             q: Optional[str] = None, fault: Optional[str] = None, *,
             vin: str = "", base: Optional[str] = None, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    vin = vin or str(job.get("vin") or "")
    base = base or (f"/v/{vin}/job?step=9" if vin else "?step=9")
    sort = sort if sort in _SORT_IDS else "newest"
    kind = kind if kind in _CHIP_LABEL else None
    q = page_search.clean_q(q)
    m = DTC_RE.search((fault or "").upper())
    fault = m.group(1) if m else None

    allx = [_entry(a, vin, today) for a in job.get("actions") or []]
    counts = {cid: 0 for cid, _l, _k in KIND_CHIPS}   # whole log, so chips stay stable while filtering
    for e in allx:
        counts[e["chip"]] += 1

    def keep(e: dict[str, Any]) -> bool:
        if kind and e["chip"] != kind:
            return False
        if fault and fault not in e["faults"]:
            return False
        if q:
            hay = page_search.haystack([e["text"], e["kind"], e["ref"] and e["ref"]["label"]])
            if not page_search.matches(q, hay, ()):
                return False
        return True

    shown = [e for e in allx if keep(e)]
    rows = _fold(_sort(shown, sort))

    def link(**over: Any) -> str:
        p = {"log_kind": kind, "log_sort": None if sort == "newest" else sort,
             "log_q": q, "log_fault": fault}
        p.update(over)
        return _url(base, **p)

    per_fault: dict[str, list[dict[str, Any]]] = {}
    for e in allx:
        for f in e["faults"]:
            per_fault.setdefault(f, []).append(e)
    fault_rows = []
    for f, es in sorted(per_fault.items()):
        first, last = _span(es)
        fault_rows.append({"code": f, "count": len(es), "first": first, "last": last,
                           "active": f == fault, "href": link(log_fault=None if f == fault else f)})

    opened, closed = _day(job.get("opened_at")), _day(job.get("closed_at"))
    open_days = ((closed or today) - opened).days if opened else None
    first, last = _span(allx)
    span_days = (date.fromisoformat(last) - date.fromisoformat(first)).days if first else None

    chips = [{"id": "", "label": "All", "count": len(allx), "active": kind is None,
              "href": link(log_kind=None)}]
    chips += [{"id": cid, "label": label, "count": counts[cid], "active": kind == cid,
               "href": link(log_kind=None if kind == cid else cid)} for cid, label, _k in KIND_CHIPS]
    sorts = [{"id": s, "label": label, "active": s == sort,
              "href": link(log_sort=None if s == "newest" else s)} for s, label in SORTS]

    return {
        "kind": kind, "sort": sort, "q": q, "fault": fault, "base": base,
        "chips": chips, "sorts": sorts, "faults": fault_rows, "rows": rows,
        "total": len(allx), "matched": len(shown), "lines": len(rows),
        "retracted_count": len(job.get("retracted_actions") or []),
        "filtered": bool(kind or fault or q), "clear_url": link(log_kind=None, log_q=None, log_fault=None),
        "open_days": open_days, "span_first": first, "span_last": last, "span_days": span_days,
    }


def job_log_context(job: Mapping[str, Any], params: Mapping[str, Any], vin: str = "") -> dict[str, Any]:
    """What the Job page calls: ``{"log": log_view(...)}`` from ``request.query_params``."""
    return {"log": log_view(job, kind=params.get("log_kind") or None,
                            sort=params.get("log_sort") or "newest",
                            q=params.get("log_q") or None, fault=params.get("log_fault") or None,
                            vin=vin or str(job.get("vin") or ""))}
