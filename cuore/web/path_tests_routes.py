"""Voltage-drop plan / split / shared points / repair proof for one code's
electrical path, plus the printable path sheet.

Registers the ``path_tests_for`` Jinja global (read by
``_electrical_path.html`` via ``_path_tests.html``, guarded with
``is defined``) and three routes. Reads saved data only -- never the car.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..services import electrical_safety, path_tests as pt
from . import electrical_routes as er
from .routes import templates as _shared_templates

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _word(text: str, token: str) -> bool:
    return len(token) >= 4 and re.search(r"(?<![a-z0-9])" + re.escape(token.lower()) + r"(?![a-z0-9])",
                                         text.lower()) is not None


def _code_table(vin: str) -> dict[str, dict[str, Any]]:
    try:
        from ..services import tsb_xref_bridge
        return tsb_xref_bridge._code_table(vin)
    except Exception:  # noqa: BLE001
        return {}


def _ground_scores(vin: str, elements: dict[str, dict[str, Any]], hops: list[dict[str, Any]]) -> dict[str, dict]:
    try:
        from ..services import electrical_extras, wiring_bridge
        mods = {m["module"].upper(): m for m in wiring_bridge.wiring_map(vin).get("modules", [])}
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for h in hops:
        mc = electrical_extras.module_code_for(h["id"], elements.get(h["id"]) or h, set(mods))
        m = mods.get(mc or "")
        if m:
            g = m["ground_suspect"]
            out[h["id"]] = {"module": mc, "score": g["score"], "of_reads": g["of_reads"],
                            "low_confidence": g["low_confidence"]}
    return out


def _knowledge(vin: str, code: str, hops: list[dict[str, Any]],
               elements: dict[str, dict[str, Any]]) -> tuple[dict[str, dict], dict]:
    per_hop: dict[str, dict[str, list]] = {h["id"]: {"tsb": [], "links": []} for h in hops}
    for h in hops:
        for ref in (elements.get(h["id"]) or {}).get("tsb_refs") or []:
            per_hop[h["id"]]["tsb"].append({"number": str(ref), "why": f"listed on {h['label']} in the layout data"})
    code_tsb: list[dict[str, str]] = []
    try:
        from ..services import tsb_xref_bridge
        on_hops = {t["number"] for v in per_hop.values() for t in v["tsb"]}
        for r in tsb_xref_bridge.xref(vin).get("by_code", {}).get(code.upper(), []):
            if str(r.get("number")) not in on_hops:
                code_tsb.append({"number": str(r.get("number")), "why": str(r.get("reason") or "")[:200]})
    except Exception:  # noqa: BLE001
        pass
    code_links: list[dict[str, str]] = []
    try:
        from ..services import experience_bridge
        for ln in experience_bridge.links_for(code=code.upper(), vin=vin).get("links") or []:
            url = str(ln.get("url") or ln.get("href") or "")
            if not url.startswith(("http://", "https://")):
                continue
            title = str(ln.get("title") or url)
            text = " ".join(str(ln.get(k) or "") for k in ("title", "reason", "why", "note", "summary"))
            hit = next((h for h in hops if _word(text, h["label"]) or _word(text, h["id"].replace("_", " "))), None)
            row = {"title": title, "url": url}
            (per_hop[hit["id"]]["links"] if hit else code_links).append(row)
    except Exception:  # noqa: BLE001
        pass
    return per_hop, {"tsb": code_tsb, "links": code_links}


def path_tests_for(vin: str, code: str) -> dict[str, Any]:
    code = (code or "").upper()
    elec = er.electrical_path_for(vin, code)
    if not elec["found"]:
        return {"found": False, "code": code}
    elements = er._elements()
    path = elec["path"]
    hops = pt.electrical_hops(path)
    segments = pt.build_segments(path, elements)
    records = pt.read_all(vin)
    results = pt.latest_results(records, vin, code)
    table = _code_table(vin)
    others: dict[str, dict[str, Any]] = {}
    for c, row in table.items():
        if c.upper() == code:
            continue
        try:
            p = er._code_path(c).get("path") or []
        except Exception:  # noqa: BLE001
            p = []
        if p:
            others[c] = {"ids": [h.get("id") for h in p], "active": bool(row.get("active"))}
    shared = pt.shared_points(code, hops, others)
    me = table.get(code) or {}
    newest = max((str(r.get("last_seen") or "") for r in table.values()), default="")
    repairs = pt.latest_repairs(records, vin)
    scores = _ground_scores(vin, elements, hops)
    know, code_level = _knowledge(vin, code, hops, elements)
    split = pt.split_suggestion(hops, segments, results)
    for s in segments:
        s["result"] = results.get(s["id"])
        s["history"] = pt.history_for(records, vin, code, s["id"])[::-1]
    rows = []
    for h in hops:
        el = elements.get(h["id"]) or {}
        rows.append({
            "id": h["id"], "label": h["label"], "role": h.get("role"), "kind": h.get("kind"),
            "location": (h.get("location") or {}).get("description"),
            "condition": h.get("condition"),
            "safety": electrical_safety.flags_for(el or h, h["id"]),
            "shared": shared.get(h["id"]), "ground_score": scores.get(h["id"]),
            "tsb": know[h["id"]]["tsb"], "links": know[h["id"]]["links"],
            "split_here": h["id"] == split.get("hop_id"),
            "cleared": split["cleared"].get(h["id"]),
            "repair": pt.repair_state(h["id"], repairs.get(h["id"]), segments, records, vin, code,
                                      str(me.get("last_seen") or ""), newest),
        })
    return {"found": True, "code": code, "vin": vin, "hops": rows, "segments": segments, "split": split,
            "code_level": code_level, "general_label": pt.GENERAL_LABEL, "states": pt.STATES,
            "state_labels": pt.STATE_LABELS, "has_segments": bool(segments),
            "post_href": f"/v/{vin}/code/{code}", "sheet_href": f"/v/{vin}/code/{code}/path-sheet"}


_shared_templates.env.globals["path_tests_for"] = path_tests_for


def _back(form: Any, vin: str, code: str) -> str:
    base = str(form.get("redirect_to", "") or "")
    if not er._safe_redirect(base) or len(base) > 300:
        base = f"/v/{vin}/code/{quote(code)}"
    return base.split("#")[0]


def _done(base: str, err: Optional[str], ok: str) -> RedirectResponse:
    sep = "&" if "?" in base else "?"
    q = f"pt={ok}" if err is None else "pt_error=" + quote(err)
    return RedirectResponse(url=f"{base}{sep}{q}#path-tests", status_code=303)


@router.post("/v/{vin}/code/{code}/path-test", response_class=HTMLResponse)
async def path_test_submit(request: Request, vin: str, code: str) -> RedirectResponse:
    form = await request.form()
    if not (pt.valid_vin(vin) and pt.valid_code(code)):
        return RedirectResponse(url="/", status_code=303)
    base = _back(form, vin, code)
    data = path_tests_for(vin, code)
    if not data.get("found"):
        return _done(base, "no electrical path known for this code", "")
    rec, err = pt.validate_test(dict(form), vin, code, data["segments"])
    if rec:
        pt.append(rec)
    return _done(base, err, "test")


@router.post("/v/{vin}/code/{code}/path-repair", response_class=HTMLResponse)
async def path_repair_submit(request: Request, vin: str, code: str) -> RedirectResponse:
    form = await request.form()
    if not (pt.valid_vin(vin) and pt.valid_code(code)):
        return RedirectResponse(url="/", status_code=303)
    base = _back(form, vin, code)
    data = path_tests_for(vin, code)
    if not data.get("found"):
        return _done(base, "no electrical path known for this code", "")
    rec, err = pt.validate_repair(dict(form), vin, code, {h["id"] for h in data["hops"]})
    if rec:
        pt.append(rec)
    return _done(base, err, "repair")


@router.get("/v/{vin}/code/{code}/path-sheet", response_class=HTMLResponse)
def path_sheet(request: Request, vin: str, code: str) -> HTMLResponse:
    if not (pt.valid_vin(vin) and pt.valid_code(code)):
        return HTMLResponse("bad vin or code", status_code=400)
    data = path_tests_for(vin, code)
    try:
        car = er._vehicle_bar(vin, er._dossier(vin))
    except Exception:  # noqa: BLE001
        car = {}
    return _shared_templates.TemplateResponse(
        request, "path_sheet.html", {"vin": vin, "code": code.upper(), "data": data, "car": car})
