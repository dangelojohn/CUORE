"""Mechanic-first direction for the Job page: the one-line call, short hypothesis titles,
the first test step, readable system labels and a page-only search. Pure functions over the
job and dossier data already on the page; nothing here reads the car or invents a fact."""
from __future__ import annotations

import re
from typing import Any

from ..web import page_search as ps  # noqa: E402

MAX_TITLE = 110
MAX_STEP = 170

# blocker word -> (what to do, where to do it). The words come from the dossier verdict's own blocker.
_BLOCKER_FIX = (
    ("fuel", "burn fuel into the 15-85 % window", "Bench fuel gate", "/v/{vin}"),
)

JOB_SYNONYMS = (
    ("abs", "brake", "brakes"), ("network", "can", "bus", "u-code"), ("window", "regulator", "riser"),
    ("evap", "fuel vapour", "purge"), ("immobiliser", "immobilizer", "keyless", "rfhub"),
)


def system_label(key: str, labels: dict[str, str] | None) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    if labels and key in labels:
        return labels[key]
    return key.replace("_", " ").replace("/", " / ").strip().capitalize()


def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    if cut.count("(") > cut.count(")"):   # never end inside an open bracket
        cut = cut[:cut.rindex("(")]
    return cut.rstrip(" ,;:-(") + "..."


def priority_of(text: str) -> int:
    m = re.match(r"\s*PRIORITY\s+(\d+)", text or "", re.I)
    return int(m.group(1)) if m else 99


def hyp_title(h: dict, labels: dict[str, str] | None = None) -> str:
    """A short title out of a long research text: the CLAIM's first clause, else the priority note, else the system."""
    text = re.sub(r"\s+", " ", h.get("text") or "").strip()
    sysl = system_label(h.get("system") or "", labels)
    m = re.search(r"CLAIM:\s*(.+)", text)
    if m:
        body = re.split(r"(?<=[a-z0-9\)])\.\s|;\s", m.group(1), 1)[0]
        body = body[:1].upper() + body[1:]
        return _clip(body, MAX_TITLE)
    m = re.match(r"PRIORITY\s+\d+\s*\(([^;)]*)", text, re.I)
    note = m.group(1).strip() if m else ""
    note = re.sub(r"^[A-Z]+:\s*", "", note)
    if note:
        return _clip((sysl + " - " if sysl else "") + note, MAX_TITLE)
    first = re.sub(r"^PRIORITY\s+\d+\s*(\([^)]*\))?\.?\s*", "", text, flags=re.I)
    return _clip(first or sysl or "Hypothesis", MAX_TITLE)


def first_step(next_test: str) -> str:
    """The first numbered item of a long next-test list, trimmed to a sentence a mechanic can act on."""
    t = re.sub(r"\s+", " ", next_test or "").strip()
    if not t:
        return ""
    m = re.match(r"1\)\s*(.*?)(?=\s+\d\)\s|$)", t)
    one = m.group(1) if m else t
    one = re.sub(r"^(Free|Read-only|Multimeter|Optional):\s*", "", one)
    if ";" in one[30:]:   # the first clause is the action; the rest is detail for Full reasoning
        one = one[:30 + one[30:].index(";")]
    return _clip(one[:1].upper() + one[1:], MAX_STEP)


def _fuel_pct(verdict: dict) -> str:
    m = re.search(r"set at ([\d.]+)\s*%", (verdict or {}).get("next_action") or "")
    if not m:
        return ""
    try:
        return f"{float(m.group(1)):.1f}"
    except ValueError:
        return m.group(1)


def _top_hyp(hyps: list[dict]) -> dict | None:
    live = [h for h in hyps if not h.get("deleted") and h.get("status") in ("open", "supported") and h.get("next_test")]
    live.sort(key=lambda h: priority_of(h.get("text") or ""))
    return live[0] if live else None


def build_call(vin: str, verdict: dict | None, hyps: list[dict], labels: dict[str, str] | None = None) -> dict[str, Any]:
    """``segs``: [{text, href}] for one call line; ``go_chips``; ``why`` lines; ``next_href`` of the next-test link."""
    segs: list[dict] = []
    why: list[str] = []
    top = _top_hyp(hyps)
    next_href = f"/v/{vin}/job?step=6&hypothesis={top['id']}#hyp-{top['id']}" if top else ""
    blocker = ((verdict or {}).get("blocker") or "").strip()
    if blocker:
        fix = next((f for f in _BLOCKER_FIX if f[0] in blocker.lower()), None)
        if fix:
            pct = _fuel_pct(verdict or {})
            head = f"Fuel {pct} %: " if pct else "Fuel is out of the window: "
            segs += [{"text": head, "href": ""}, {"text": fix[1], "href": ""}, {"text": ". Go to ", "href": ""},
                     {"text": fix[2], "href": fix[3].format(vin=vin)}, {"text": ".", "href": ""}]
        else:
            segs += [{"text": f"Blocked: {blocker}. ", "href": ""},
                     {"text": "Verify repair", "href": f"/v/{vin}/verify"}]
        why += [b for b in ((verdict or {}).get("basis") or [])]
        if (verdict or {}).get("summary"):
            why.insert(0, verdict["summary"])
    if top:
        step = first_step(top["next_test"])
        lead = " Meanwhile, next test: " if segs else "Next test: "
        title = hyp_title(top, labels)
        segs += [{"text": lead + step + " ", "href": ""}, {"text": "Do it now", "href": next_href}]
        why.append(f"Next test is for: {title} ({system_label(top.get('system') or '', labels)}).")
    if not segs:
        segs = [{"text": "No test is waiting. Add a hypothesis or read the car.", "href": ""}]
    chips = [
        {"text": "Record a test", "href": f"/v/{vin}/job?step=6"},
        {"text": "Hypotheses", "href": f"/v/{vin}/job?step=7"},
        {"text": "Codes", "href": f"/v/{vin}/job?step=4"},
        {"text": "Verify repair", "href": f"/v/{vin}/job?step=10"},
    ]
    if blocker:
        chips.insert(0, {"text": "Bench", "href": f"/v/{vin}"})
    return {"segs": segs, "go_chips": chips, "why": why, "next_href": next_href,
            "text": "".join(s["text"] for s in segs)}


def _hyp_hay(h: dict, labels) -> str:
    ev = [e.get("label") for e in (h.get("evidence_for") or []) + (h.get("evidence_against") or [])]
    return ps.haystack([h.get("text"), hyp_title(h, labels), system_label(h.get("system") or "", labels),
                        h.get("next_test"), " ".join(h.get("codes") or []), " ".join(x for x in ev if x)])


def search(q: str, vin: str, hyps: list[dict], codes: list[dict], open_work: list[dict],
           labels: dict[str, str] | None = None) -> dict[str, Any]:
    """Page-only search over this job's hypotheses, codes, evidence and tests. ``hyp_ids`` are the matching
    hypotheses (shown first on the page); ``results`` is the link list under the call."""
    q = ps.clean_q(q)
    out: list[dict] = []
    ids: list[str] = []
    if not q:
        return {"q": "", "results": [], "hyp_ids": [], "hint": ""}
    for h in hyps:
        if h.get("deleted"):
            continue
        if ps.matches(q, _hyp_hay(h, labels), JOB_SYNONYMS):
            ids.append(h["id"])
            out.append({"kind": "Hypothesis", "ref": hyp_title(h, labels),
                        "text": system_label(h.get("system") or "", labels),
                        "href": f"/v/{vin}/job?step=7&hypothesis={h['id']}#hyp-{h['id']}"})
        ev_hits = [e for e in (h.get("evidence_for") or []) + (h.get("evidence_against") or [])
                   if e.get("label") and ps.matches(q, ps.haystack([e.get("label")]), JOB_SYNONYMS)]
        if ev_hits:
            out.append({"kind": "Evidence", "ref": f"{len(ev_hits)} evidence item{'' if len(ev_hits) == 1 else 's'}: {ev_hits[0]['label']}"[:110],
                        "text": "on " + hyp_title(h, labels),
                        "href": f"/v/{vin}/job?step=7&hypothesis={h['id']}#hyp-{h['id']}"})
    for c in codes:
        if ps.matches(q, ps.haystack([c.get("code"), c.get("description"), c.get("family"), c.get("status_label")]), JOB_SYNONYMS):
            out.append({"kind": "Code", "ref": c["code"], "text": c.get("description") or "",
                        "href": c.get("href") or f"/v/{vin}/code/{c['code']}"})
    for card in open_work or []:
        for s in card.get("steps") or []:
            if ps.matches(q, ps.haystack([s.get("text"), s.get("ref"), card.get("title")]), JOB_SYNONYMS):
                out.append({"kind": "Test", "ref": s["text"], "text": ("done" if s.get("done") else "to do") + " - " + (card.get("title") or ""),
                            "href": f"/v/{vin}/job?step=6#{s.get('id', '')}"})
    return {"q": q, "results": out, "hyp_ids": ids,
            "hint": "Try a system, a code or a test word (brake, network, P0455, smoke test)."}
