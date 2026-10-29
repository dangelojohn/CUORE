"""Configuration page: GET /v/{vin}/configuration (read-only PROXI). The POST routes only run the
read-only 0x22 discovery/read or record the owner's acceptance and MES-screen names. No route writes
to the car."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..api.deps import require_token
from ..live import proxi_read
from .routes import _dossier, _page, _set_active_vehicle, _vehicle_bar

router = APIRouter(include_in_schema=False, dependencies=[Depends(require_token)])


def _back(vin: str, text: str, kind: str) -> RedirectResponse:
    return RedirectResponse(f"/v/{vin}/configuration?msg={quote(text[:300])}&mk={kind}", status_code=303)


@router.get("/v/{vin}/configuration", response_class=HTMLResponse)
def configuration_page(request: Request, vin: str, msg: str = "", mk: str = "") -> HTMLResponse:
    response = _page(request, "configuration.html", vin=vin, bar=_vehicle_bar(vin, _dossier(vin)),
                     tab="configuration", c=proxi_read.view(vin), flash_msg=msg[:300],
                     flash_kind="err" if mk == "err" else "ok")
    _set_active_vehicle(response, vin)
    return response


@router.post("/v/{vin}/configuration/discover")
def configuration_discover(vin: str) -> RedirectResponse:
    try:
        r = proxi_read.discover(vin)
        reason = r.get("aborted_reason")
        return _back(vin, (f"Discovery stopped: {reason}. " if reason else "Discovery finished. ")
                     + f"{r['requests']} requests, {r['replies']} replies. Candidates are not accepted.",
                     "err" if reason else "ok")
    except Exception as exc:  # noqa: BLE001
        return _back(vin, f"Not run: {exc}", "err")


@router.post("/v/{vin}/configuration/accept")
def configuration_accept(vin: str, did: str = Form(""), reason: str = Form("")) -> RedirectResponse:
    try:
        a = proxi_read.accept_candidate(vin, did, reason)
        return _back(vin, f"Accepted {a['did']}. Now read it.", "ok")
    except Exception as exc:  # noqa: BLE001
        return _back(vin, f"Not accepted: {exc}", "err")


@router.post("/v/{vin}/configuration/read")
def configuration_read(vin: str) -> RedirectResponse:
    try:
        r = proxi_read.read(vin)
        ch = r["changed"]
        extra = "" if ch is None else f" {len(ch)} byte(s) changed since the previous read."
        return _back(vin, f"Read {r['length']} bytes from {r['did']}.{extra}", "ok")
    except Exception as exc:  # noqa: BLE001
        return _back(vin, f"Not read: {exc}", "err")


@router.post("/v/{vin}/configuration/names")
def configuration_names(vin: str, screenshot: str = Form(""), mes_date: str = Form(""),
                        byte: str = Form(""), mask: str = Form(""), name: str = Form(""),
                        value: str = Form(""), bulk: str = Form("")) -> RedirectResponse:
    """Naming only (no car contact). Names are never sent to the car."""
    try:
        rows = proxi_read.parse_bulk(bulk)
        if byte.strip() or name.strip():
            rows.append({"byte": byte, "mask": mask, "name": name, "value": value})
        if not rows:
            return _back(vin, "No rows entered.", "err")
        res = proxi_read.add_names(vin, rows, screenshot, mes_date)
        tally = {}
        for r in res["added"]:
            tally[r["agreement"]] = tally.get(r["agreement"], 0) + 1
        return _back(vin, f"Saved {len(res['added'])} name(s): " + ", ".join(f"{n} {k}" for k, n in tally.items()), "ok")
    except Exception as exc:  # noqa: BLE001
        return _back(vin, f"Not saved: {exc}", "err")
