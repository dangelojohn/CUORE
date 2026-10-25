"""Routes for the "Ask Claude" panel on the code page (copy, run, save back)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form
from fastapi.responses import JSONResponse, RedirectResponse

from ..api.deps import require_token
from ..services import ask_claude, ask_claude_runner, mes_bridge

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def panel_context(vin: str, code: str) -> dict[str, Any]:
    """Template context for ``_ask_claude.html``; never raises."""
    try:
        b = ask_claude.build(vin, code)
        head, tail = b["head"], b["tail"]
    except Exception as exc:  # noqa: BLE001
        head, tail = f"(prompt could not be built: {type(exc).__name__})\n", ""
    return {"ac_head": head, "ac_tail": tail, "ac_run": ask_claude_runner.available(),
            "ac_prefix": ask_claude.SAVE_PREFIX}


@router.post("/v/{vin}/code/{code}/ask-claude/run")
def run(vin: str, code: str, observed: str = Form(""), question: str = Form("")):
    try:
        prompt = ask_claude.compose(vin, code, observed, question)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)
    res = ask_claude_runner.start(prompt)
    if res.get("unavailable"):
        return JSONResponse({"error": "Claude CLI not found on this PC."}, status_code=404)
    if res.get("busy"):
        return JSONResponse({"error": "Another Ask Claude run is in progress."}, status_code=409)
    return JSONResponse(res)


@router.get("/v/{vin}/code/{code}/ask-claude/status/{job_id}")
def status(vin: str, code: str, job_id: str):
    j = ask_claude_runner.status(job_id)
    if j is None:
        return JSONResponse({"state": "error", "error": "Unknown run id."}, status_code=404)
    # JSON data; the page inserts the answer with textContent (never innerHTML).
    return JSONResponse({"state": j["state"], "answer": j.get("answer") or "",
                         "error": j.get("error") or ""})


@router.post("/v/{vin}/code/{code}/ask-claude/save")
def save(vin: str, code: str, text: str = Form(...)):
    mes_bridge.add_note(vin, ask_claude.analysis_note_text(text), target_kind="code",
                        target_id=code.strip().upper(), author="claude",
                        tags=[ask_claude.SAVE_TAG])
    return RedirectResponse(url=f"/v/{vin}/code/{code.strip().upper()}#ask-claude",
                            status_code=303)
