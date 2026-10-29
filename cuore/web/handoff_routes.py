"""wiTECH hand-off page: GET /v/{vin}/handoff (current job) and ?job=<id>. Read-only, printable.

Built from existing services only: the job store (mes.jobs, via fault_board._job_for), the fault board
context, and the parity board. Nothing here is computed from raw files and nothing is invented.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..api.deps import require_token
from ..services import fault_board, parity
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

WITECH_RE = re.compile(r"wi-?tech|flash|programming|calibration|proxi|routine|security", re.I)
# Plain job system words -> module/function words that parity rows use.
ALIASES = {"transmission": ("tcm", "transmission", "8hp", "zf"), "engine": ("ecm",),
           "driveline": ("driveline", "transfer case", "differential"), "brakes": ("abs", "brake"),
           "abs": ("abs",), "body": ("bcm", "body"), "evap": ("evap",)}
DONE_KINDS = ("repair", "part", "parts", "inspection", "clear", "fix")
STATUS_WORD = {"open": "Open", "supported": "Supported", "refuted": "Refuted", "confirmed": "Confirmed"}
STATUS_MARK = {"open": "○", "supported": "◐", "refuted": "✗", "confirmed": "✓"}


def _clip(t: Any, n: int) -> str:
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _src(ref: str) -> tuple[str, str]:
    """(timestamp, source label) from an evidence ref such as obs:module_dtcs:ECM@2026-10-25T13:32:31."""
    ts = ref.split("@", 1)[1].replace("T", " ") if "@" in ref else ""
    if ref.startswith("obs:"):
        return ts, "CUORE read (" + ref[4:].split("@")[0].replace(":", " ") + ")"
    if ref.startswith("log:"):
        return ts, "MES log (" + ref[4:] + ")"
    if ref.startswith("job:"):
        return ts, "job record"
    return ts, "recorded note"


def _ref_text(e: Any) -> str:
    if isinstance(e, dict):
        return str(e.get("label") or e.get("text") or e.get("id") or e.get("ref") or "")
    return str(e)


def _codes_now(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_mod: dict[str, list[dict[str, Any]]] = {}
    for c in cards:
        if c.get("kind") != "code" or c.get("status") not in ("active", "pending", "permanent", "stored"):
            continue
        ev = (c.get("evidence") or {}).get("status") or []
        ts, src = _src(ev[0]) if ev else ("", "")
        by_mod.setdefault(c.get("module") or "Unassigned", []).append(
            {"code": c["code"], "desc": c.get("description") or "", "status": c.get("status_label") or c.get("status"),
             "mark": c.get("status_mark") or "", "detail": c.get("status_detail") or "",
             "last_read": ts or (c.get("last_seen") or "").replace("T", " "), "source": src or "fault board"})
    return [{"module": m, "rows": r} for m, r in sorted(by_mod.items())]


def _witech(job: dict[str, Any], cards: list[dict[str, Any]], modules: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in job.get("hypotheses") or []:
        if h.get("deleted"):
            continue
        for field, label in (("next_test", "next test"), ("text", "hypothesis text")):
            m = WITECH_RE.search(h.get(field) or "")
            if m:
                out.append({"where": "Hypothesis: " + _clip(h.get("text"), 70),
                            "why": f"Its {label} mentions '{m.group(0)}'.", "text": _clip(h.get(field), 220)})
                break
    for a in job.get("actions") or []:
        m = WITECH_RE.search(a.get("text") or "")
        if m:
            out.append({"where": f"Job action ({a.get('kind')}, {str(a.get('at') or '')[:10]})",
                        "why": f"The entry mentions '{m.group(0)}'.", "text": _clip(a.get("text"), 220)})
    seen: set[str] = set()
    for c in cards:
        nt = (c.get("next_test") or {}).get("text") or ""
        if c.get("kind") == "code" and nt and WITECH_RE.search(nt) and nt not in seen:
            seen.add(nt)
            out.append({"where": f"Fault board: {c['code']} ({c.get('module')})",
                        "why": "The suggested next test for this code is a wiTECH task.", "text": _clip(nt, 220)})
    terms: set[str] = set()
    for m in modules:
        m = (m or "").strip().lower()
        if m:
            terms.add(m)
            terms.update(ALIASES.get(m, ()))
    pats = [(t, re.compile(r"\b" + re.escape(t) + r"\b", re.I)) for t in sorted(terms) if len(t) >= 3]
    for it in parity.load().get("items", []):
        # only functions that change the car: reads that wait on documents are CUORE's own gap, not wiTECH work
        if it.get("state") != "documents" or it.get("group") not in ("writes", "configuration", "keys"):
            continue
        blob = " ".join([it.get("function") or ""] + [str((it.get(k) or {}).get("note") or "") for k in ("mes", "alfaobd", "cuore")]
                        + [it.get("closes") or ""])
        hit = next((t for t, p in pats if p.search(blob)), None)
        if hit:
            out.append({"where": "Parity board: " + (it.get("function") or it.get("id")),
                        "why": f"A write CUORE cannot perform yet (awaiting the manufacturer's procedure); wiTECH, or MES where it has the function, does it today. Matched on '{hit}', which this job involves.",
                        "text": _clip((it.get("cuore") or {}).get("note") or "", 220)})
    return out


def handoff_context(vin: str, job_id: Optional[str]) -> dict[str, Any]:
    job = fault_board._job_for(vin, job_id or None)
    ctx = fault_board.fault_board_context(vin, job.get("id") if job else None)
    cards = [c for g in ctx["groups"] for c in g["cards"]]
    present = ("active", "pending", "permanent")
    modules = {c.get("module") for c in cards if c.get("kind") == "code" and c.get("status") in present}
    hyps, evidence = [], []
    for h in (job or {}).get("hypotheses") or []:
        if h.get("deleted"):
            continue
        st = h.get("status") or "open"
        modules.add(h.get("system_text") or "")
        hyps.append({"title": _clip(h.get("text"), 160), "status": STATUS_WORD.get(st, st), "mark": STATUS_MARK.get(st, "?"),
                     "system": h.get("system_text") or "", "likelihood": h.get("likelihood") or "",
                     "next_test": h.get("next_test") or "", "n_for": len(h.get("evidence_for") or []),
                     "n_against": len(h.get("evidence_against") or [])})
        for side in ("evidence_for", "evidence_against"):
            for e in h.get(side) or []:
                t = _ref_text(e)
                ts, src = _src(t)
                evidence.append({"what": _clip(t, 200), "side": "for" if side == "evidence_for" else "against", "ts": ts,
                                 "source": src, "hyp": _clip(h.get("text"), 50), "outside": "outside" in t.lower() or t.startswith("ext:")})
    for c in cards:
        if c.get("kind") == "code" and c.get("status") in present:
            for ref in ((c.get("evidence") or {}).get("status") or [])[:2]:
                ts, src = _src(ref)
                evidence.append({"what": f"{c['code']} {c.get('status_label') or ''}: {_clip(c.get('status_detail'), 160)}",
                                 "side": "reading", "ts": ts, "source": src, "hyp": "", "outside": False})
    done = [{"at": str(a.get("effective_date") or a.get("at") or "")[:16].replace("T", " "), "kind": a.get("kind"),
             "clear": a.get("kind") == "clear", "text": _clip(a.get("text"), 260)}
            for a in (job or {}).get("actions") or [] if a.get("kind") in DONE_KINDS]
    now = datetime.now()
    return {"job": job, "codes": _codes_now(cards), "present_line": ctx["present_line"], "hyps": hyps, "evidence": evidence[:14],
            "done": done, "needs": _witech(job, cards, modules) if job else [],
            "generated": now.strftime("%Y-%m-%d %H:%M"), "printed": now.strftime("%Y-%m-%d")}


@router.get("/v/{vin}/handoff", response_class=HTMLResponse)
def handoff_page(request: Request, vin: str, job: str = "") -> HTMLResponse:
    dossier = _dossier(vin)
    h = handoff_context(vin, job.strip() or None)
    response = _page(request, "handoff.html", vin=vin, bar=_vehicle_bar(vin, dossier), tab="job", h=h)
    _set_active_vehicle(response, vin)
    return response
