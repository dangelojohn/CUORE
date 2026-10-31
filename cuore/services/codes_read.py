"""Read one module's stored codes on request: the "Read now" list on the Codes page.

This is the web door to the one read that already exists (:func:`cuore.live.ops.module_dtcs`, UDS 0x19 02 inside a
guarded read session). It adds no address, service, identifier or bitrate. It offers only CAN-C modules whose address is
CONFIRMED in the registry (other buses need the cable wizard on the Scan page), and it reads one module per press.

A module that does not answer is reported as NOT READ with the reason, never as "no codes". Nothing is cleared.
The reader is injectable so tests run with a fake link and no port.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from ..live import read_state, store

BUS = "can_c"
NOT_CLEAN = "not read, do not treat as clean"


def readable_modules(vin: str, modules_fn: Optional[Callable[..., dict[str, Any]]] = None) -> list[dict[str, str]]:
    """Confirmed CAN-C modules, registry order: ``[{code, name}]``. Never raises; no car contact."""
    try:
        if modules_fn is None:
            from ..live import ops
            modules_fn = ops.modules
        rows = modules_fn(bus=BUS, vin=vin)["modules"]
    except Exception:  # noqa: BLE001 -- the page works without the list
        return []
    return [{"code": str(m["code"]), "name": str(m.get("name") or "")} for m in rows
            if m.get("usable") and m.get("bus") in (None, BUS)]


def _stored_count(d: dict[str, Any]) -> Optional[int]:
    if d.get("active") is not None:       # compact result
        return len(d.get("active") or []) + len(d.get("history") or [])
    from . import code_compare            # full result: same status mask the parity page uses
    recs = d.get("dtcs")
    if recs is None:
        return None
    return sum(1 for r in recs if int(r.get("status") or 0) & code_compare.STORED_MASK)


def summarise(d: dict[str, Any]) -> dict[str, Any]:
    """One module result as ``{module, state, count, why, line}``; ``state`` is read / not_read."""
    mod = str(d.get("ecu") or "").upper()
    why = read_state.reason(d)
    if why:
        return {"module": mod, "state": "not_read", "count": None, "why": why,
                "line": f"{mod}: {read_state.banner(why)}"}
    n = _stored_count(d)
    if n is None:
        return {"module": mod, "state": "not_read", "count": None, "why": "no code list in the reply",
                "line": f"{mod}: {read_state.banner('no code list in the reply')}"}
    return {"module": mod, "state": "read", "count": n, "why": "",
            "line": f"{mod}: {n} stored code{'' if n == 1 else 's'}" if n else f"{mod}: no stored codes"}


def last_reads(vin: str) -> dict[str, dict[str, Any]]:
    """Newest module_dtcs observation from the car per module: ``{module: summary + at}``. No car contact."""
    out: dict[str, dict[str, Any]] = {}
    try:
        obs = [o for o in store.recent_observations(n=2000, vin=vin, kind="module_dtcs") if store.is_from_car(o)]
    except Exception:  # noqa: BLE001
        return out
    for o in sorted(obs, key=lambda x: str(x.get("at") or "")):
        s = summarise(o.get("data") or {})
        if s["module"]:
            out[s["module"]] = {**s, "at": str(o.get("at") or "")}
    return out


def panel(vin: str, modules_fn: Optional[Callable[..., dict[str, Any]]] = None,
          reads: Optional[dict[str, dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """The Read-now list: each readable module with its last answer (or "never read"). No car contact."""
    last = last_reads(vin) if reads is None else reads
    rows = []
    for m in readable_modules(vin, modules_fn):
        r = last.get(m["code"])
        rows.append({**m, "when": (r["at"][:16].replace("T", " ") if r else ""),
                     "state": r["state"] if r else "never",
                     "line": (r["line"].split(": ", 1)[-1] if r else "never read from the car")})
    return rows


def read_now(vin: str, code: str, reader: Optional[Callable[..., dict[str, Any]]] = None,
             modules_fn: Optional[Callable[..., dict[str, Any]]] = None) -> dict[str, Any]:
    """Read ``code`` once. Returns ``{ok, module, line, state}``; refuses a module that is not on the list."""
    code = (code or "").strip().upper()
    allowed = {m["code"] for m in readable_modules(vin, modules_fn)}
    if code not in allowed:
        return {"ok": False, "module": code, "state": "refused",
                "line": f"{code or 'That module'} is not on the read list. Use the Scan page for other buses."}
    try:
        if reader is None:
            from ..live import ops
            reader = ops.module_dtcs
        d = reader(code, vin=vin, detail=False)
    except Exception as e:  # noqa: BLE001 -- adapter busy, no port, session refused: say it, never "clean"
        msg = str(getattr(e, "message", "") or e)[:160] or e.__class__.__name__
        return {"ok": False, "module": code, "state": "not_read",
                "line": f"{code}: could not read ({msg}). {NOT_CLEAN.capitalize()}."}
    if d.get("car_mismatch"):     # the car on the cable is not the car of this page
        return {"ok": False, "module": code, "state": "not_read",
                "line": f"{code}: {d['car_mismatch']}. {NOT_CLEAN.capitalize()} for this car."}
    s = summarise(d if d.get("ecu") else {**d, "ecu": code})
    return {"ok": s["state"] == "read", "module": code, "state": s["state"], "line": s["line"]}
