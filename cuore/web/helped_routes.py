"""Technician feedback loop: one-tap "This helped / This was wrong" on CUORE's
advice, and the private ``/feedback-summary`` page.

Rows go through the existing feedback store (:mod:`cuore.services.feedback_bridge`,
``feedback.jsonl``): kind ``confirm`` (helped) or ``disagree`` (wrong), target
``{page, section="helped", item, label}``, author from ``actor()``. No customer
data is collected; the note is capped at 140 characters. "Helped" rows are
marked dismissed so they do not fill the mechanic inbox; "wrong" rows stay open.

Not registered here -- ``app.py`` needs (next to the inbox_routes lines)::

    from .web import helped_routes
    app.include_router(helped_routes.router)
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import actor, require_token
from ..services import feedback_bridge
from ..services.errors import BridgeError
from .routes import _page, _safe_redirect

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])

SECTION = "helped"
MAX_NOTE = 140
PAGES = {"bench": "Bench next action", "codes": "Codes advice", "tests": "Tests next test",
         "systems": "Systems guide", "arrive": "Arrive ready leads", "find": "Find top result"}


@router.post("/v/{vin}/helped", response_class=HTMLResponse)
async def helped_submit(request: Request, vin: str) -> RedirectResponse:
    form = await request.form()
    back = _safe_redirect(str(form.get("redirect_to", "")), "/")
    verdict = str(form.get("verdict", "")).strip()
    page = str(form.get("page", "")).strip()[:40]
    item = str(form.get("item", "")).strip()[:60]
    if verdict in ("helped", "wrong") and page and item:
        text = str(form.get("text", "")).strip()[:MAX_NOTE] if verdict == "wrong" else ""
        target = {"page": page, "section": SECTION, "item": item,
                  "label": str(form.get("label", "")).strip()[:120] or item}
        try:
            row = feedback_bridge.add(vin, "confirm" if verdict == "helped" else "disagree",
                                      target, text=text, author=actor(request, "technician"))
            if verdict == "helped":
                feedback_bridge.set_status(row["id"], "dismissed")
        except BridgeError:
            pass  # never 500 a technician's tap
    return RedirectResponse(url=back, status_code=303)


def summarize(days: int = 7) -> dict[str, Any]:
    from mes import feedback as feedback_mod
    rows = [r for r in feedback_mod.load() if (r.get("target") or {}).get("section") == SECTION]
    rows.sort(key=lambda r: r.get("at", ""), reverse=True)
    cut = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    week = [r for r in rows if r.get("at", "") >= cut]
    def split(rs):
        h = [r for r in rs if r["kind"] == "confirm"]
        return h, [r for r in rs if r["kind"] == "disagree"]
    wh, ww = split(week)
    by_page: dict[str, list[int]] = {}
    by_item: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        t = r["target"]; i = 0 if r["kind"] == "confirm" else 1
        by_page.setdefault(t["page"], [0, 0])[i] += 1
        by_item.setdefault((t["page"], t["item"]), [0, 0])[i] += 1
    wrong_items = Counter({k: v[1] for k, v in by_item.items() if v[1]})
    top = wrong_items.most_common(1)
    return {"helped_week": len(wh), "wrong_week": len(ww), "total": len(rows),
            "top_wrong": ({"page": top[0][0][0], "item": top[0][0][1], "n": top[0][1]} if top else None),
            "pages": sorted(([p, v[0], v[1]] for p, v in by_page.items()), key=lambda x: -(x[1] + x[2])),
            "by_item": sorted(([k[0], k[1], v[0], v[1]] for k, v in by_item.items()), key=lambda x: (-x[3], -x[2])),
            "notes": [r for r in rows if r["kind"] == "disagree" and r.get("text")]}


@router.get("/feedback-summary", response_class=HTMLResponse)
def feedback_summary(request: Request) -> HTMLResponse:
    return _page(request, "feedback_summary.html", s=summarize(), page_names=PAGES, vin="")
