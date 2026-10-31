"""Identify a car and open a service for it: the backend of "Add Service".

Four jobs, no page:

* :func:`validate_vin` -- length, characters, check digit. The check digit is
  required only where the market uses it (North America); elsewhere it is an
  advisory warning and never rejects a VIN.
* :func:`decode_vin` -- make, model, platform, model year, plant, market from
  ``cuore/data/vin_rules.json`` (every rule carries its source). A rule that is
  not verified is shown as unverified. No rule means unknown; nothing is guessed.
* :func:`identify_from_car` -- reads the VIN (Mode 09) and each module's identity
  through the same guarded, read-only path as the five-minute test
  (:class:`cuore.live.five_minute.LiveProbe`): cable-aware, one read at a time
  (shared run lock), confirmed bus only, MES must be closed, a CAN ERROR is
  retried once, silence is judged by :mod:`cuore.live.read_state`. It yields a
  progress event per step and per module so a page can show modules answering
  one by one. It never clears, writes, actuates or opens the consent gate.
* :func:`create_service` -- reuses :mod:`cuore.services.shop_bridge` intake (which
  opens the job), records the odometer and the per-field card, and never makes a
  second car for a VIN already on file.

Every field is ``{value, source, at, detail, verified}`` where ``source`` is one
of :data:`SOURCES`. An optional online lookup exists only as an off-by-default
stub: this module opens no network connection.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live import five_minute, read_state
from ..live.config import state_dir
from . import shop_bridge
from .errors import BadRequest

SRC_READ = "read from the car"
SRC_DECODED = "decoded from the VIN"
SRC_TYPED = "typed in"
SRC_NONE = "not found"
SOURCES = (SRC_READ, SRC_DECODED, SRC_TYPED, SRC_NONE)
_RANK = {SRC_NONE: 0, SRC_DECODED: 1, SRC_TYPED: 2, SRC_READ: 3}  # a person corrects a decode, never a read

#: The optional online lookup is a stub. Nothing in this build opens a network
#: connection; turning this on later needs the disclosure dialog in DESIGN.md.
ONLINE_LOOKUP_ENABLED = False

RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "vin_rules.json"
_VIN_CHARS = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_TRANSLIT = {**{str(d): d for d in range(10)},
             **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))),
             "P": 7, "R": 9, **dict(zip("STUVWXYZ", range(2, 10)))}
_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
#: Identity DIDs worth keeping on the card (software / hardware numbers).
_ID_DIDS = ("F187", "F188", "F189", "F18C", "F191", "F192", "F194", "F195")
_card_lock = threading.Lock()
_rules_cache: dict[str, Any] = {}


# --- fields ----------------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_field(value: Any, source: str, *, at: Optional[str] = None, detail: str = "",
               verified: bool = True, rule: str = "") -> dict[str, Any]:
    """One card field. An empty value always carries source ``not found``. ``detail``
    is the short line the mechanic reads; ``rule`` keeps the full source for the record."""
    if value is None or value == "":
        return {"value": None, "source": SRC_NONE, "at": at or _now(), "detail": detail,
                "verified": True}
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    field = {"value": value, "source": source, "at": at or _now(), "detail": detail,
             "verified": bool(verified)}
    if rule:
        field["rule"] = rule
    return field


def _not_found(why: str) -> dict[str, Any]:
    return make_field(None, SRC_NONE, detail=why)


def _val(f: Any) -> Any:
    return f.get("value") if isinstance(f, dict) else f


# --- rules and validation ---------------------------------------------------------------------

def rules() -> dict[str, Any]:
    if not _rules_cache:
        _rules_cache.update(json.loads(RULES_PATH.read_text(encoding="utf-8")))
    return _rules_cache


def _norm(vin: Any) -> str:
    return re.sub(r"\s+", "", str(vin or "")).upper()


def _wmi_rule(vin: str) -> Optional[dict[str, Any]]:
    """Longest-prefix match, so a 4-character WMI beats a 3-character one."""
    hits = [r for r in rules()["wmi"] if vin.startswith(r["prefix"])]
    return max(hits, key=lambda r: len(r["prefix"]), default=None)


def _prefix_rule(table: str, vin: str) -> Optional[dict[str, Any]]:
    hits = [r for r in rules()[table] if vin.startswith(r["prefix"])]
    return max(hits, key=lambda r: len(r["prefix"]), default=None)


def _check_digit(vin: str) -> tuple[bool, str]:
    total = sum(_TRANSLIT[c] * w for c, w in zip(vin, _WEIGHTS))
    expected = "X" if total % 11 == 10 else str(total % 11)
    return vin[8] == expected, expected


def validate_vin(vin: Any) -> dict[str, Any]:
    """``ok`` is False only for a defect that makes the VIN unusable: wrong length,
    bad characters, or (North American VINs only) a wrong check digit. The check
    digit result is always reported under ``check_digit`` with ``applies`` saying
    whether it is ``required`` or ``advisory``."""
    v = _norm(vin)
    errors: list[str] = []
    warnings: list[str] = []
    check: dict[str, Any] = {"checked": False, "valid": None, "expected": None, "applies": "advisory"}
    if len(v) != 17:
        errors.append(f"a VIN has 17 characters; this has {len(v)}")
    bad = sorted({c for c in v if c not in "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"})
    if bad:
        errors.append("characters not allowed in a VIN: " + " ".join(bad) +
                      (" (I, O and Q are never used)" if set(bad) & set("IOQ") else ""))
    if len(v) == 17 and not bad:
        rule = _wmi_rule(v)
        market = rule.get("market") if rule else None
        required = market in rules()["check_digit"]["required_markets"]
        valid, expected = _check_digit(v)
        check = {"checked": True, "valid": valid, "expected": expected,
                 "applies": "required" if required else "advisory"}
        if not valid:
            msg = f"check digit is {v[8]}, the calculation gives {expected}"
            if required:
                errors.append(msg + " (required for North American VINs)")
            else:
                warnings.append(msg + " (advisory: the check digit is only meaningful for North "
                                "American VINs, and this VIN's market is "
                                + ("not North America" if market else "unknown") + ")")
    return {"vin": v, "ok": not errors, "errors": errors, "warnings": warnings,
            "check_digit": check}


def _model_year(vin: str) -> tuple[Optional[int], str]:
    yc = rules()["year_codes"]
    i = yc["codes"].find(vin[9])
    if i < 0:
        return None, f"position 10 is {vin[9]!r}, not a model-year code"
    limit = datetime.now().year + 1
    year = yc["base_year"] + i
    while year + yc["cycle_years"] <= limit:
        year += yc["cycle_years"]
    return year, f"VIN position 10 is {vin[9]}"


def decode_vin(vin: Any) -> dict[str, Any]:
    """Make, model, platform, model_year, plant, market from the VIN alone."""
    v = _norm(vin)
    val = validate_vin(v)
    out: dict[str, dict[str, Any]] = {k: _not_found("no VIN to decode") for k in
                                       ("make", "model", "platform", "model_year", "plant", "market")}
    if len(v) == 17 and _VIN_CHARS.match(v):
        t = _now()
        year, why = _model_year(v)
        out["model_year"] = (make_field(year, SRC_DECODED, at=t, detail=why, rule=rules()["year_codes"]["source"])
                             if year else _not_found(why))
        wmi = _wmi_rule(v)
        if wmi:
            ok = wmi["verified"]
            tag = "" if ok else "UNVERIFIED: "
            out["make"] = make_field(wmi["make"], SRC_DECODED, at=t, verified=ok, rule=wmi["source"],
                                     detail=f"{tag}VIN starts {wmi['prefix']}")
            out["market"] = (make_field(wmi["market"], SRC_DECODED, at=t, verified=ok, rule=wmi["source"],
                                        detail=f"{tag}VIN starts {wmi['prefix']}")
                             if wmi.get("market") else _not_found("the VIN does not state a market"))
        else:
            out["make"] = _not_found("no rule for WMI " + v[:3])
            out["market"] = _not_found("no rule for WMI " + v[:3])
        mrule = _prefix_rule("models", v)
        if mrule and mrule.get("model"):
            out["model"] = make_field(mrule["model"], SRC_DECODED, at=t, verified=mrule["verified"],
                                      detail=f"VIN starts {mrule['prefix']}", rule=mrule["source"])
            plat = _platform_text(mrule.get("platform_key"))
            out["platform"] = (make_field(plat, SRC_DECODED, at=t, verified=mrule["verified"],
                                          detail="from the model", rule="mes.platform.platform_for("
                                          + mrule["platform_key"] + ")")
                               if plat else _not_found("no platform record for this model"))
        else:
            why = mrule["source"] if mrule else "no model rule for this VIN"
            out["model"] = _not_found(why)
            out["platform"] = _not_found("model not identified, so no platform")
        prule = _prefix_rule("plants", v)
        if prule and v[10] == prule["code"]:
            out["plant"] = make_field(prule["plant"], SRC_DECODED, at=t, verified=prule["verified"],
                                      detail=("" if prule["verified"] else "UNVERIFIED: ")
                                      + f"VIN position 11 is {v[10]}", rule=prule["source"])
        else:
            out["plant"] = _not_found(f"no plant rule for position 11 = {v[10]!r}")
    else:
        for k in out:
            out[k] = _not_found("; ".join(val["errors"]) or "not a decodable VIN")
    return {"vin": v, "validation": val, "fields": out}


def _platform_text(key: Optional[str]) -> str:
    if not key:
        return ""
    try:
        from mes import platform as platform_mod
        rec = platform_mod.platform_for(key)
    except Exception:  # noqa: BLE001
        return ""
    return str((rec or {}).get("platform") or "")


# --- identify from the car --------------------------------------------------------------------

class CarProbe(five_minute.LiveProbe):
    """The five-minute test's read-only probe plus the Mode 09 VIN read. Tests
    substitute a fake with the same methods."""

    def read_vin(self) -> dict[str, Any]:
        from ..live import ops
        return ops.obd_vin()


def identify_from_car(vin_hint: str = "", *, bus: str = "", confirm: bool = False,
                      probe: Any = None) -> Iterator[dict[str, Any]]:
    """Generator of progress events, last one ``{"event": "done", "card": {...}}``.

    Events: ``start``, ``refused`` (then ``done`` from the hint alone), ``vin``,
    ``module`` (one per module, ``answered`` true or false with the reason),
    ``done``. Modules that stay silent are listed as not found; nothing is
    inferred about them."""
    hint = _norm(vin_hint)
    lock = five_minute._RUN_LOCK
    if not lock.acquire(blocking=False):
        yield {"event": "refused", "reason": "another read is in progress; reads go strictly one at a time"}
        yield {"event": "done", "card": _card(hint, None, [], "another read is in progress")}
        return
    try:
        probe = probe or CarProbe()
        cable = probe.cable()
        want = bus or five_minute._BUS_FOR_CABLE.get(cable, "")
        yield {"event": "start", "cable": cable, "bus": want, "read_only": True, "at": _now()}
        refusal = _preflight(probe, cable, want, confirm)
        if refusal:
            yield {"event": "refused", "reason": refusal}
            yield {"event": "done", "card": _card(hint, None, [], refusal)}
            return
        vin_read, vin_why = _read_vin(probe)
        yield {"event": "vin", "vin": vin_read, "answered": bool(vin_read),
               "reason": vin_why, "at": _now()}
        vin = vin_read or hint
        retries: list[dict[str, Any]] = []
        modules: list[dict[str, Any]] = []
        for m in probe.modules(want):
            if not (m.get("present") and m.get("usable")):
                continue
            code = str(m["code"])
            r, err = five_minute._read_once(lambda c=code: probe.identity(c, vin, confirm),
                                            f"identity {code}", retries)
            ids = {d: (r.get("fields") or {}).get(d, {}).get("ascii")
                   for d in _ID_DIDS if (r.get("fields") or {}).get(d, {}).get("ascii")}
            answered = bool(five_minute._identity_ok(r)) and read_state.is_read(r) and not err
            row = {"event": "module", "code": code, "name": m.get("name"), "answered": answered,
                   "reason": "" if answered else _silence(r, err),
                   "identity": ids, "at": _now()}
            modules.append(row)
            yield row
        yield {"event": "done", "card": _card(hint, vin_read, modules, "", vin_why, retries)}
    finally:
        lock.release()


def _silence(r: dict[str, Any], err: str) -> str:
    if err:
        return five_minute._why_silent(r, err)
    return read_state.reason(r) or five_minute._why_silent(r, err)


def identify_result(events: Iterator[dict[str, Any]]) -> dict[str, Any]:
    """Run :func:`identify_from_car` to the end; return ``{"events", "card"}``."""
    evs = list(events)
    return {"events": evs, "card": evs[-1]["card"] if evs and evs[-1].get("event") == "done" else None}


def _preflight(probe: Any, cable: str, want: str, confirm: bool) -> str:
    bus_for = five_minute._BUS_FOR_CABLE
    if want not in bus_for.values():
        return f"cable {cable!r} reaches no bus this read knows"
    if bus_for.get(cable) != want:
        return f"bus {want} needs a different cable than the declared {cable!r}"
    if want == "can_ch" and not confirm:
        return "CAN-CH needs confirm=True (grey A6 cable, 500 kbit/s only)"
    if probe.mes_running():
        return "MultiEcuScan is open; close it first (one adapter owner at a time)"
    ok, why = probe.bus_ready(want, cable)
    return "" if ok else why


def _read_vin(probe: Any) -> tuple[str, str]:
    try:
        r = probe.read_vin() or {}
    except Exception as e:  # noqa: BLE001 -- a failed read is a finding, not a crash
        return "", f"{type(e).__name__}: {e}"
    v = _norm(r.get("vin"))
    if r.get("error") or not read_state.is_read(r) or len(v) != 17:
        return "", str(r.get("error") or read_state.reason(r) or r.get("warning") or "no VIN in the answer")
    return v, ""


def _card(hint: str, vin_read: Optional[str], modules: list[dict[str, Any]], refusal: str,
          vin_why: str = "", retries: Optional[list] = None) -> dict[str, Any]:
    """Assemble the card. A VIN read from the car wins over a typed one; a
    disagreement is reported, not hidden."""
    conflicts: list[str] = []
    if vin_read:
        vin = vin_read
        fvin = make_field(vin, SRC_READ, detail="OBD Mode 09 PID 02")
        if hint and hint != vin_read:
            conflicts.append(f"typed VIN {hint} differs from the VIN the car reported ({vin_read})")
    elif hint:
        vin = hint
        fvin = make_field(vin, SRC_TYPED, detail=refusal or vin_why or "the car did not report a VIN")
    else:
        vin = ""
        fvin = _not_found(refusal or vin_why or "no VIN typed and none read")
    dec = decode_vin(vin)
    answered = [m for m in modules if m["answered"]]
    ids = {f"{m['code']} {d}": v for m in answered for d, v in m["identity"].items()}
    fields = {"vin": fvin, **dec["fields"],
              "modules_answered": (make_field(f"{len(answered)} of {len(modules)}", SRC_READ,
                                              detail="module identity (22) reads") if modules
                                   else _not_found(refusal or "no module was asked")),
              "software_ids": (make_field(ids, SRC_READ, detail="identity DIDs " + ", ".join(_ID_DIDS))
                               if ids else _not_found("no module reported a software or hardware number"))}
    return {"vin": vin, "fields": fields, "validation": dec["validation"], "modules": modules,
            "silent_modules": [{"code": m["code"], "name": m["name"], "reason": m["reason"]}
                               for m in modules if not m["answered"]],
            "conflicts": conflicts, "retries": retries or [], "refused": refusal or None,
            "read_only": True, "at": _now(), "online_lookup": online_lookup(vin)}


def online_lookup(vin: str, *, enabled: bool = False) -> dict[str, Any]:
    """Off-by-default stub. Performs no network access in this build, whatever
    ``enabled`` says; a future build must show the disclosure before sending a VIN."""
    return {"enabled": False, "performed": False, "provider": None,
            "reason": "online lookup is not built; nothing was sent"
            if not (enabled and ONLINE_LOOKUP_ENABLED) else "online lookup is not implemented in this build"}


# --- the stored car card and Add Service ------------------------------------------------------

def _card_path(vin: str) -> Path:
    return state_dir() / "cars" / f"{vin}.json"


def get_card(vin: Any) -> Optional[dict[str, Any]]:
    p = _card_path(_norm(vin))
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def card_name(vin: Any) -> str:
    """'Alfa Romeo Stelvio 2018' from the stored card, or ''. Only fields with a
    value are used; an unknown model is left out, never filled in."""
    c = get_card(vin)
    if not c:
        return ""
    f = c.get("fields") or {}
    return " ".join(str(_val(f.get(k))) for k in ("make", "model", "model_year") if _val(f.get(k)))


def _save_card(card: dict[str, Any]) -> None:
    p = _card_path(card["vin"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(card, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _merge_field(old: Optional[dict[str, Any]], new: dict[str, Any]) -> dict[str, Any]:
    """A higher-ranked source is never overwritten by a lower one; a field with no
    value never replaces one that has a value."""
    if not old or not old.get("value"):
        return new
    if not new.get("value"):
        return old
    return new if _RANK[new["source"]] >= _RANK[old.get("source", SRC_NONE)] else old


def _clean_fields(fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for k, f in (fields or {}).items():
        if isinstance(f, dict):
            src = f.get("source") if f.get("source") in SOURCES else SRC_TYPED
            out[k] = make_field(f.get("value"), src, at=f.get("at"), detail=str(f.get("detail") or ""),
                                verified=f.get("verified", True), rule=str(f.get("rule") or ""))
        else:
            out[k] = make_field(f, SRC_TYPED)
    return out


def _odometer(odometer: Any, unit: str) -> Optional[dict[str, Any]]:
    if odometer is None or odometer == "":
        return None
    if isinstance(odometer, dict):
        odometer, unit = odometer.get("value"), odometer.get("unit") or unit
    try:
        if isinstance(odometer, bool):
            raise ValueError
        n = float(str(odometer).replace(",", "").strip()) if not isinstance(odometer, (int, float)) else float(odometer)
    except ValueError:
        raise BadRequest(f"odometer must be a number, got {odometer!r}") from None
    if not 0 <= n <= 3_000_000:
        raise BadRequest("odometer is out of range")
    if unit not in ("km", "mi"):
        raise BadRequest("odometer unit must be km or mi")
    return {"value": int(n) if n == int(n) else n, "unit": unit}


def _car_known(vin: str) -> bool:
    from mes import jobs as jobs_mod
    from mes import shop as shop_mod
    return bool(get_card(vin) or jobs_mod.load(vin) or shop_mod.load(vin)
                or any(c["vin"] == vin for c in shop_bridge.vehicle_choices()))


def create_service(fields: dict[str, Any], reason: str = "", odometer: Any = None, *,
                   unit: str = "km", technician: str = "") -> dict[str, Any]:
    """Open a service for the car in ``fields``. Returns ``{vin, created, existing_car,
    already_open, visit, job_id, odometer, odometer_missing, card}``.

    * An invalid VIN raises :class:`BadRequest` (check digit only where required).
    * A VIN already on file is not made a second car: its card is merged, and if a
      job is already open that job is returned instead of opening another.
    * Otherwise the existing intake opens the visit and its job, so the car appears
      in every list that reads them.
    * The odometer is recorded on the card with the visit and job it was taken at."""
    from mes import jobs as jobs_mod
    clean = _clean_fields(fields)
    vin = _norm(_val(clean.get("vin")))
    val = validate_vin(vin)
    if not val["ok"]:
        raise BadRequest("VIN rejected: " + "; ".join(val["errors"]))
    odo = _odometer(odometer, unit)
    existing = _car_known(vin)
    reading = None
    with _card_lock:
        job = jobs_mod.current(vin) if existing else None
        visit = None
        if job is None:
            name = _compose_name(clean, vin)
            visit = shop_bridge.intake(vin, reason, technician=technician, vehicle=name)
            job = {"id": visit.get("job_id")}
        card = get_card(vin) or {"vin": vin, "created_at": _now(), "fields": {}, "odometer_readings": []}
        decoded = decode_vin(vin)["fields"]
        for k, f in {**decoded, **clean}.items():
            card["fields"][k] = _merge_field(card["fields"].get(k), f)
        card["fields"]["vin"] = _merge_field(card["fields"].get("vin"), clean.get("vin") or make_field(vin, SRC_TYPED))
        if odo:
            reading = {**odo, "at": _now(), "visit_id": (visit or {}).get("id"), "job_id": job["id"]}
            card["odometer_readings"].append(reading)
        card["updated_at"] = _now()
        _save_card(card)
    return {"vin": vin, "created": visit is not None, "existing_car": existing,
            "already_open": visit is None, "visit": visit, "job_id": job["id"],
            "odometer": reading, "odometer_missing": odo is None,
            "warnings": val["warnings"], "card": card}


def _compose_name(fields: dict[str, dict[str, Any]], vin: str) -> str:
    dec = decode_vin(vin)["fields"]
    parts = [str(_val(fields.get(k)) or _val(dec.get(k)) or "") for k in ("make", "model", "model_year")]
    name = " ".join(p for p in parts if p)
    return name if _val(fields.get("model")) or _val(dec.get("model")) else (name + " (model not identified)" if name else "")


__all__ = ["SOURCES", "validate_vin", "decode_vin", "identify_from_car", "identify_result",
           "create_service", "get_card", "card_name", "online_lookup", "make_field"]
