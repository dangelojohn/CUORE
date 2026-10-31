"""Codes page "Read all modules": one read-only action over every confirmed CAN-C module.

Loops the existing guarded round (:func:`cuore.live.ops.module_code_round`, one module per call, so the transport's
session gap applies between modules) on the CURRENT bus only; it never changes the cable. A CAN ERROR is retried once
(``five_minute._read_once``) and the action stops after CAN ERROR twice. It adds no address, service or bitrate and
never clears. Every module gets a result line: codes found with count, "no stored codes" only when the module truly
answered, NOT READ with the reason otherwise; modules not tried are listed with the reason.

The run is a background thread (the web request returns at once; the page polls :func:`status`), one run at a time.
The probe is injectable so tests run with no port and no car.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable, Optional

from ..live import five_minute
from . import codes_read

MAX_CAN_ERRORS = 2
_RUN_LOCK = threading.Lock()
_STATE: dict[str, dict[str, Any]] = {}


def _probe() -> Any:
    from ..live import connect_session
    return connect_session.ConnectProbe()


def _busy_reason(probe: Any) -> str:
    """Why another owner holds the adapter, or ``""``. Our own lock is checked by the caller."""
    from ..live import connect_session
    if five_minute._RUN_LOCK.locked():
        return "a five-minute test is running; reads go one at a time"
    if connect_session._RUN_LOCK.locked():
        return "a connect session is running; reads go one at a time"
    if probe.mes_running():
        return "MultiEcuScan is open; close it first (one adapter owner at a time)"
    return ""


def _not_tried(vin: str, tried: set[str], modules_fn: Optional[Callable[..., dict[str, Any]]]) -> list[dict[str, str]]:
    try:
        if modules_fn is None:
            from ..live import ops
            modules_fn = ops.modules
        rows = modules_fn(vin=vin)["modules"]
    except Exception:  # noqa: BLE001
        return []
    out = []
    for m in rows:
        c = str(m["code"])
        if c in tried:
            continue
        bus = m.get("bus") or codes_read.BUS
        if bus != codes_read.BUS:
            why = f"on {bus}, not the current bus; needs its cable (Scan page)"
        else:
            why = "no confirmed address for this car"
        out.append({"module": c, "why": why})
    return out


def _line(code: str, row: dict[str, Any], err: str) -> tuple[str, str, str]:
    """``(state, why, text)`` for one module from its round row."""
    if row.get("skipped"):
        why = str(row["skipped"])
    elif row.get("read") and not err:
        codes = [str(x) for x in row.get("codes") or []]
        if codes:
            n = len(codes)
            return "codes", "", f"{code}: {n} stored code{'' if n == 1 else 's'}: {', '.join(codes)}"
        return "none", "", f"{code}: no stored codes"
    else:
        why = err or str(row.get("error") or row.get("warning") or "the module did not answer")
    return "not_read", why, f"{code}: NOT READ, {why}. Not clean."


def run(vin: str, *, probe: Any = None, modules_fn: Optional[Callable[..., dict[str, Any]]] = None,
        confirm: bool = True) -> dict[str, Any]:
    """Run once in the calling thread (the route goes through :func:`start`). Returns the final state."""
    probe = probe or _probe()
    st = _STATE[vin] = {"vin": vin, "running": True, "refused": False, "reason": "", "progress": "",
                        "results": [], "not_tried": [], "started": datetime.now().isoformat(timespec="seconds")}

    def finish(reason: str = "", refused: bool = False) -> dict[str, Any]:
        st.update(running=False, refused=refused, reason=reason, progress="")
        return st

    mods = [m["code"] for m in codes_read.readable_modules(vin, modules_fn)]
    if not mods:
        return finish("no confirmed CAN-C modules for this car", True)
    try:
        volts = probe.voltage()
    except Exception as e:  # noqa: BLE001
        return finish(f"battery voltage could not be read ({str(e)[:100]}); nothing was read", True)
    if volts is None:
        return finish("no battery voltage reading; cannot confirm the engine is running", True)
    if volts < five_minute.MIN_VOLTS:
        return finish(f"battery is {volts:.1f} V, below {five_minute.MIN_VOLTS} V: start the engine and keep it "
                      "running", True)
    st["progress"] = "Reading the VIN"
    detail = ""
    try:
        got = str(probe.read_vin().get("vin") or "").strip().upper()
    except Exception as e:  # noqa: BLE001
        got, detail = "", f" ({str(e)[:100]})"
    if got != vin.strip().upper():
        return finish(f"the car reported VIN {got or 'nothing'}{detail}, not {vin}: nothing was read or filed", True)
    retries: list[dict[str, Any]] = []
    can_errors = 0
    tried: set[str] = set()
    stopped = False
    for i, code in enumerate(mods, 1):
        if can_errors >= MAX_CAN_ERRORS:
            stopped = True
            break
        st["progress"] = f"Reading {code} ({i} of {len(mods)})"
        tried.add(code)

        def attempt(c: str = code) -> dict[str, Any]:
            r = probe.code_round("can_c", [c], vin, confirm)
            row = next((x for x in r.get("modules") or [] if str(x.get("module")).upper() == c), {})
            return {"row": row, "error": str(row.get("error") or "")}

        r, err = five_minute._read_once(attempt, f"{code} codes", retries)
        if err and five_minute._is_can_error(err):
            can_errors += 1
        state, why, text = _line(code, r.get("row") or {}, err)
        st["results"].append({"module": code, "state": state, "why": why, "text": text})
    st["retries"] = retries
    st["not_tried"] = _not_tried(vin, tried, modules_fn)
    if stopped:
        st["not_tried"] = [{"module": c, "why": "stopped after CAN ERROR twice"} for c in mods if c not in tried] \
            + st["not_tried"]
        st["stopped"] = "Stopped after CAN ERROR twice."
    return finish()


def start(vin: str, *, probe: Any = None, modules_fn: Optional[Callable[..., dict[str, Any]]] = None,
          wait: bool = False) -> dict[str, Any]:
    """Refuse or launch the run in a background thread. Returns ``{started, reason}``; never raises."""
    probe = probe or _probe()
    if not _RUN_LOCK.acquire(blocking=False):
        return {"started": False, "reason": "a Read all modules run is already in progress; reads go one at a time"}
    try:
        why = _busy_reason(probe)
    except Exception as e:  # noqa: BLE001
        why = f"could not check the adapter owner ({str(e)[:100]})"
    if not why and not codes_read.readable_modules(vin, modules_fn):
        why = "no confirmed CAN-C modules for this car"
    if why:
        _RUN_LOCK.release()
        return {"started": False, "reason": why}
    _STATE[vin] = {"vin": vin, "running": True, "refused": False, "reason": "", "progress": "Starting",
                   "results": [], "not_tried": []}

    def body() -> None:
        try:
            run(vin, probe=probe, modules_fn=modules_fn)
        except Exception as e:  # noqa: BLE001
            _STATE[vin].update(running=False, refused=True, reason=f"stopped: {str(e)[:160]}", progress="")
        finally:
            _RUN_LOCK.release()

    t = threading.Thread(target=body, name="codes-scan-all", daemon=True)
    t.start()
    if wait:
        t.join()
    return {"started": True, "reason": ""}


def status(vin: str) -> Optional[dict[str, Any]]:
    """The last or current run for this car, or None. No car contact."""
    return _STATE.get(vin)


__all__ = ["start", "run", "status", "MAX_CAN_ERRORS"]
