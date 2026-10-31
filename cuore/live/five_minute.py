"""The five-minute mechanic test: a yardstick, not a feature.

Owner goal (2026-10-31): 1) plug in and CUORE finds every module; 2) reads every module's
identity and codes, none silent; 3) live data matching MES; 4) a clear statement of anything
it could not read; 5) one real service job proven by read-back.

This module only MEASURES. It is read-only: it calls the identity (22), codes (19), the
legislated OBD reads and the ABS connect test (22 / 3E / 10 01), all of which the transport
allowlist already permits. It never calls a clear, a write or an actuator, and it does not
touch the consent gate or the transport barrier.

Rules kept: MES must be closed; battery at least 13.2 V (engine running) or the run refuses
with the reason; confirmed bit rates only; every read happens strictly one at a time (a
process-wide lock refuses a second run, because concurrent calls gave CAN ERROR on
2026-10-31); a CAN ERROR is retried once and the retry is recorded. A step passes only if
every one of its items passes: no partial credit, no weighting, no invented numbers.
Results are appended to ``<state_dir>/five_minute/<timestamp>.json``.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from .config import state_dir

MIN_VOLTS = 13.2
#: A MES CSV counts as "same session" when written within this many seconds before the run.
SAME_SESSION_S = 3600
STEP_TITLES = {
    1: "Every module on the bus answers",
    2: "Identity and codes read from every module",
    3: "Live data with a confirmed scale (compared with MES)",
    4: "Statement of everything that could not be read",
    5: "One real service job proven by read-back",
}
STEP5_TEXT = "NOT AVAILABLE: no documented procedure yet"
_BUS_FOR_CABLE = {"none": "can_c", "blue_a5": "can_ihs", "grey_a6": "can_ch"}
_RUN_LOCK = threading.Lock()


# --- the car, behind one small interface so tests can fake it ------------------------------

class LiveProbe:
    """Default probe: the real read-only ops. Tests substitute a fake with the same methods."""

    def cable(self) -> str:
        from .transport import link
        return link().cable

    def mes_running(self) -> bool:
        from . import interlock
        return bool(interlock.mes_status().get("running"))

    def bus_ready(self, bus_key: str, cable: str) -> tuple[bool, str]:
        from .buses import BUSES
        from .transport import declared_rate, link
        bus = BUSES[bus_key]
        if bus.bitrate_confidence != "confirmed":
            return False, f"{bus.name}: bit rate is not confirmed"
        if declared_rate(bus, cable) != bus.bitrate and bus_key == "can_ch":
            return False, "CAN-CH is only ever used at 500 kbit/s"
        if bus_key != "can_c" and not link().is_verified(bus):
            return False, f"{bus_key} is not verified under the declared cable (run verify_bus first)"
        return True, ""

    def voltage(self) -> Optional[float]:
        from . import ops
        return ops.obd_voltage().get("volts")

    def modules(self, bus_key: str, vin: Optional[str] = None) -> list[dict[str, Any]]:
        """Registry modules on this bus with the address this car would use: the
        same resolver every send goes through (per-car addresses.json first, a
        clash on one bus makes both unusable). ``present`` is True only for rows
        the registry marks "confirmed", never for "unverified" ones."""
        from .addressing import on_bus
        from .uds import address_table
        rows = {r["code"]: r for r in address_table(vin) if r["bus"] == bus_key}
        out = []
        for m in on_bus(bus_key):
            r = rows.get(m.code) or {}
            target, clash = r.get("target"), r.get("clash")
            why = ("no confirmed address on this car" if target is None
                   else f"address {target:02X} is claimed by {', '.join(clash)} on the same bus" if clash else "")
            out.append({"code": m.code, "name": m.name, "usable": not why,
                        "present": m.present == "confirmed", "target": target, "why": why})
        return out

    def roster(self, vin: str) -> list[dict[str, Any]]:
        from . import responders
        from .addressing import by_code
        out = []
        for g in responders._mes_modules(responders.load_mes_modules(vin)["blocks"]):
            m = by_code(g["code"]) if g.get("code") else None
            out.append({"code": g.get("code"), "name": g.get("name"), "bus": m.bus_key if m else None})
        return out

    def identity(self, code: str, vin: str, confirm: bool) -> dict[str, Any]:
        from . import ops
        return ops.module_identity(code, vin=vin, confirm=confirm)

    def dtcs(self, code: str, vin: str, confirm: bool) -> dict[str, Any]:
        from . import ops
        return ops.module_dtcs(code, vin=vin, confirm=confirm)

    def abs_connect(self, vin: str) -> dict[str, Any]:
        from . import abs_connect
        return abs_connect.abs_connect_test("ABS", vin=vin, confirm=True)

    def channels(self, bus_key: str) -> list[dict[str, Any]]:
        from . import channels, did_catalog
        out = []
        for c in channels.available_channels():
            if c.bus != bus_key or c.untrusted or c.kind not in ("pid", "did", "battery"):
                continue
            if c.confidence in ("legislated", "confirmed") or did_catalog.is_confirmed(c.id):
                out.append(c.to_dict())
        return out

    def read_channel(self, ch: dict[str, Any], vin: str, confirm: bool) -> dict[str, Any]:
        from . import ops
        if ch["kind"] == "pid":
            r = ops.obd_pid(ch["pid"])
            return {"value": r.get("value"), "unit": r.get("unit"), "error": r.get("error") or r.get("warning")}
        from .readall import FormulaError, eval_formula
        r = ops.module_did(ch["module"], ch["did"], vin=vin, confirm=confirm)
        data = r.get("bytes")
        if r.get("error") or not data or not ch.get("formula"):
            return {"value": None, "unit": ch.get("unit"), "error": r.get("error") or "no data"}
        try:
            v = eval_formula(ch["formula"], [int(b, 16) for b in data])
            if isinstance(v, dict):
                v = v.get(ch.get("field"))
            return {"value": float(v), "unit": ch.get("unit"), "error": None}
        except (FormulaError, TypeError, ValueError) as e:
            return {"value": None, "unit": ch.get("unit"), "error": f"formula: {e}"}

    def mes_csv(self, since_epoch: float) -> Optional[dict[str, Any]]:
        """Newest MES CSV written within SAME_SESSION_S before the run: {name, ranges}."""
        from .. import bootstrap  # noqa: F401 -- side effect: mes on sys.path
        from mes import csvlog, paths
        best = None
        for p in paths.iter_csv_files():
            try:
                mt = p.stat().st_mtime
            except OSError:
                continue
            if mt >= since_epoch - SAME_SESSION_S and (best is None or mt > best[0]):
                best = (mt, p)
        if best is None:
            return None
        rec = csvlog.load_csv(best[1])
        ranges: dict[str, dict[str, Any]] = {}
        for col in rec.columns:
            vals = []
            for row in rec.rows:
                try:
                    vals.append(float(str(row[col.index]).replace(",", ".")))
                except (ValueError, IndexError):
                    pass
            if vals:
                ranges[col.name.strip().lower()] = {"min": min(vals), "max": max(vals), "unit": col.unit}
        return {"name": best[1].name, "ranges": ranges}


# --- helpers --------------------------------------------------------------------------------

def _item(id_: str, label: str, passed: bool, reason: str = "", **detail: Any) -> dict[str, Any]:
    return {"id": id_, "label": label, "passed": bool(passed), "reason": reason, **detail}


def _step(n: int, items: list[dict[str, Any]], note: str = "") -> dict[str, Any]:
    ok = sum(1 for i in items if i["passed"])
    return {"n": n, "title": STEP_TITLES[n], "passed": bool(items) and ok == len(items),
            "items": items, "pass_count": ok, "item_count": len(items),
            "note": note or ("" if items else "no items to check, so the step cannot pass")}


def _is_can_error(msg: str) -> bool:
    return "CAN ERROR" in (msg or "").upper()


def _read_once(fn: Callable[[], dict[str, Any]], label: str, retries: list[dict[str, Any]]
               ) -> tuple[dict[str, Any], str]:
    """Run one read; on CAN ERROR retry exactly once and record both outcomes."""
    def attempt() -> tuple[dict[str, Any], str]:
        try:
            r = fn() or {}
        except Exception as e:  # noqa: BLE001 -- a failed read is a finding, not a crash
            return {}, f"{type(e).__name__}: {e}"
        return r, str(r.get("error") or "")
    r, err = attempt()
    if err and _is_can_error(err):
        r2, err2 = attempt()
        retries.append({"read": label, "first_error": err, "retry_error": err2 or None,
                        "retry_recovered": not err2})
        return r2, err2
    return r, err


def _identity_ok(r: dict[str, Any]) -> list[str]:
    return [k for k, v in (r.get("fields") or {}).items() if v.get("ascii") or v.get("bytes")]


def _why_silent(r: dict[str, Any], err: str) -> str:
    if err:
        return err
    nrcs = {str(v) for f in (r.get("fields") or {}).values() if f.get("nrc") for v in (
        f["nrc"].values() if isinstance(f["nrc"], dict) else [f["nrc"]])}
    if r.get("nrc"):
        nrcs |= {str(v) for v in (r["nrc"].values() if isinstance(r["nrc"], dict) else [r["nrc"]])}
    return ("module refused: " + ", ".join(sorted(nrcs))) if nrcs else (r.get("warning") or "no answer")


def _result_base(vin: str, bus: str, cable: str, started: datetime) -> dict[str, Any]:
    return {"version": 1, "vin": vin, "bus": bus, "cable": cable, "started": started.isoformat(timespec="seconds"),
            "refused": False, "reason": "", "seconds": None, "voltage": None, "steps": [],
            "not_read": [], "retries": [], "mes_csv": None, "read_only": True,
            "steps_passed": 0, "steps_total": 5, "all_passed": False}


def save(result: dict[str, Any]) -> Path:
    d = state_dir() / "five_minute"
    d.mkdir(parents=True, exist_ok=True)
    stamp = result["started"].replace("-", "").replace(":", "")
    p, k = d / f"{stamp}.json", 1
    while p.exists():
        k += 1
        p = d / f"{stamp}-{k}.json"
    p.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return p


def history(limit: int = 10) -> list[dict[str, Any]]:
    d = state_dir() / "five_minute"
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json"), reverse=True)[:limit] if d.is_dir() else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"file": p.name, "started": r.get("started"), "vin": r.get("vin"), "bus": r.get("bus"),
                    "seconds": r.get("seconds"), "refused": r.get("refused"), "reason": r.get("reason"),
                    "steps_passed": r.get("steps_passed"), "steps_total": r.get("steps_total"),
                    "step_flags": [s["passed"] for s in r.get("steps", [])]})
    return out


# --- the run --------------------------------------------------------------------------------

def run(vin: str, *, bus: str = "", confirm: bool = False, probe: Any = None,
        persist: bool = True) -> dict[str, Any]:
    """Run the test once. Returns the result dict (refusals included, with ``refused`` True)."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {**_result_base(vin, bus, "", datetime.now()), "refused": True,
                "reason": "a five-minute run is already in progress; reads go strictly one at a "
                          "time (concurrent calls produced CAN ERROR on 2026-10-31)"}
    t0 = time.monotonic()
    try:
        probe = probe or LiveProbe()
        started = datetime.now()
        cable = probe.cable()
        want = bus or _BUS_FOR_CABLE.get(cable, "")
        res = _result_base(vin, want, cable, started)

        def refuse(reason: str) -> dict[str, Any]:
            res.update(refused=True, reason=reason, seconds=round(time.monotonic() - t0, 2))
            if persist:
                save(res)
            return res

        if want not in _BUS_FOR_CABLE.values():
            return refuse(f"cable {cable!r} reaches no bus this test knows")
        if _BUS_FOR_CABLE.get(cable) != want:
            return refuse(f"bus {want} needs cable {[c for c, b in _BUS_FOR_CABLE.items() if b == want][0]} "
                          f"declared; the declared cable is {cable!r}")
        if want == "can_ch" and not confirm:
            return refuse("CAN-CH needs confirm=True (grey A6 cable, 500 kbit/s only)")
        if probe.mes_running():
            return refuse("MultiEcuScan is open; close it first (one adapter owner at a time)")
        ok, why = probe.bus_ready(want, cable)
        if not ok:
            return refuse(why)
        volts = probe.voltage()
        res["voltage"] = volts
        if volts is None:
            return refuse("no battery voltage reading; cannot confirm the engine is running")
        if volts < MIN_VOLTS:
            return refuse(f"battery is {volts:.1f} V, below {MIN_VOLTS} V: start the engine and "
                          "keep it running (owner rule: long work runs with the engine running)")
        _measure(res, vin, want, confirm, probe, started)
        res["seconds"] = round(time.monotonic() - t0, 2)
        res["steps_passed"] = sum(1 for s in res["steps"] if s["passed"])
        res["all_passed"] = res["steps_passed"] == 5
        if persist:
            save(res)
        return res
    finally:
        _RUN_LOCK.release()


def _measure(res: dict[str, Any], vin: str, bus: str, confirm: bool, probe: Any,
             started: datetime) -> None:
    retries: list[dict[str, Any]] = res["retries"]
    table = probe.modules(bus, vin)
    roster = probe.roster(vin) or []
    expected: dict[str, dict[str, Any]] = {m["code"]: dict(m, via="module table") for m in table if m["present"]}
    unaddressed: list[dict[str, Any]] = []
    for g in roster:
        if g.get("code") and g.get("bus") == bus:
            if g["code"] in expected:
                expected[g["code"]]["via"] = "module table + MES roster"
            else:
                expected[g["code"]] = {"code": g["code"], "name": g.get("name"), "via": "MES roster"}
        elif not g.get("code"):
            unaddressed.append(g)
    by_table = {m["code"]: m for m in table}
    s1, s2, reads = [], [], {}
    for code, m in expected.items():
        m = {**by_table.get(code, {}), **m}
        label = f"{code} ({m.get('name') or ''}) via {m['via']}"
        if not m.get("usable"):
            why = m.get("why") or "no confirmed address in the module table"
            s1.append(_item(code, label, False, f"NOT READ: {why}"))
            s2.append(_item(code, label, False, f"NOT READ: {why}"))
            continue
        ident, ierr = _read_once(lambda c=code: probe.identity(c, vin, confirm), f"{code} identity", retries)
        dtc, derr = _read_once(lambda c=code: probe.dtcs(c, vin, confirm), f"{code} codes", retries)
        fields = _identity_ok(ident) if not ierr else []
        dtc_ok = not derr and "codes" in dtc
        item1 = _item(code, label, bool(fields) or dtc_ok,
                      "" if (fields or dtc_ok) else "NOT READ: " + _why_silent(ident, ierr))
        if not item1["passed"] and bus == "can_ch" and code == "ABS":
            ct = probe.abs_connect(vin)
            item1["connect_test"] = {"answered_by": ct.get("answered_by"), "conclusion": ct.get("conclusion"),
                                     "requests_sent": ct.get("requests_sent")}
        s1.append(item1)
        if not item1["passed"]:
            s2.append(_item(code, label, False, "NOT READ: module did not answer in step 1"))
            continue
        problems = []
        if not fields:
            problems.append("identity: " + _why_silent(ident, ierr))
        if not dtc_ok:
            problems.append("codes: " + _why_silent(dtc, derr))
        reads[code] = {"identity_fields": fields, "codes": dtc.get("codes") if dtc_ok else None}
        s2.append(_item(code, label, not problems, "; ".join(problems),
                        identity_fields=fields, codes=dtc.get("codes") if dtc_ok else None))
    for g in unaddressed:
        why = "listed in the MES roster for this car but has no CUORE module address"
        s1.append(_item(f"mes:{g.get('name')}", f"{g.get('name')} (MES roster)", False, f"NOT READ: {why}"))
        s2.append(_item(f"mes:{g.get('name')}", f"{g.get('name')} (MES roster)", False, f"NOT READ: {why}"))
    # step 3
    csv = None
    try:
        csv = probe.mes_csv(started.timestamp())
    except Exception as e:  # noqa: BLE001
        res["mes_csv_error"] = f"{type(e).__name__}: {e}"
    res["mes_csv"] = csv["name"] if csv else None
    s3 = []
    for ch in probe.channels(bus):
        if ch["kind"] == "battery":
            r = {"value": res["voltage"], "unit": "V", "error": None}
        else:
            r, e = _read_once(lambda c=ch: probe.read_channel(c, vin, confirm), f"channel {ch['id']}", retries)
            r = {"value": r.get("value"), "unit": r.get("unit"), "error": e or r.get("error")}
        v = r["value"]
        if r["error"] or v is None:
            s3.append(_item(ch["id"], ch["name"], False, f"NOT READ: {r['error'] or 'no value'}"))
            continue
        if csv is None:
            cmp_, ok_ = "NOT COMPARED (no same-session MES CSV)", False
        else:
            rng = csv["ranges"].get(ch["name"].strip().lower())
            if rng is None:
                cmp_, ok_ = "NOT COMPARED (no such column in the MES CSV)", False
            elif rng["min"] <= v <= rng["max"]:
                cmp_, ok_ = f"within MES range {rng['min']}..{rng['max']} {rng['unit'] or ''}".strip(), True
            else:
                cmp_, ok_ = f"outside MES range {rng['min']}..{rng['max']} {rng['unit'] or ''}".strip(), False
        s3.append(_item(ch["id"], ch["name"], ok_, "" if ok_ else cmp_, value=v, unit=r["unit"], mes=cmp_))
    # step 4: everything not read, each with its reason
    not_read = []
    for n, items in ((1, s1), (2, s2), (3, s3)):
        for i in items:
            if not i["passed"]:
                not_read.append({"step": n, "item": i["label"], "reason": i["reason"]})
    not_read.append({"step": 5, "item": "service job proof", "reason": STEP5_TEXT})
    s4 = [_item(f"{n['step']}:{n['item']}", n["item"], bool(n["reason"]), n["reason"]) for n in not_read]
    res["not_read"] = not_read
    res["steps"] = [_step(1, s1), _step(2, s2), _step(3, s3), _step(4, s4),
                    _step(5, [_item("service_job", "service job proven by read-back", False, STEP5_TEXT)],
                          STEP5_TEXT)]
    res["reads"] = reads
