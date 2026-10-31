"""Where CUORE stands against the 19 modules MultiEcuScan reads on this car.

One place answers four questions the Modules page, the module page, the
Report and the Bay sheet all ask, so they cannot disagree:

* :func:`all_modules` -- every one of the 19 MES modules, each READ, PARTLY
  READ, NOT READ (reason and date) or NOT TRIED (blocker), plus the plain
  count "N of 19 read".
* :func:`identity_remainder` -- ISO code, hardware version and homologation
  for the 8 CAN-C modules: the MES value, and what a recorded CUORE reply
  holds (decoded) or why none does.
* :func:`snapshot_fields` -- the 28 stored-code snapshot fields MES prints for
  the ECM, each bound, candidate or NOT DECODED, with the raw bytes.
* :func:`not_read_lines` -- the same facts as short lines for the Report and
  the Bay sheet.

Only recorded data is used (observations, the adapter audit file, MES's own
log files already summarised in ``cuore/data``). Nothing here touches the
adapter, asks for anything new, or decides a scale: a scale is unconfirmed
until a person accepts it (``snapshot_bindings``). Unknown stays unknown, and
an unread module is never shown as clean.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from ..live import audit, framing, read_state, snapshot_bindings, store, uds

_DATA = Path(__file__).resolve().parent.parent / "data"

READ = "READ"
PARTLY = "PARTLY READ"
NOT_READ = "NOT READ"
NOT_TRIED = "NOT TRIED"

#: the 9 of the 19 that the live registry addresses and CUORE has tried
CORE = ("ECM", "TCM", "BCM", "IPC", "RFHUB", "DTCM", "ESM", "DASM", "ABS")
CAN_C_EIGHT = ("ECM", "TCM", "BCM", "IPC", "RFHUB", "DTCM", "ESM", "DASM")

_LABELS = {
    "ECM": "Engine control module", "TCM": "Transmission control module",
    "BCM": "Body computer", "IPC": "Instrument panel cluster",
    "RFHUB": "Radio frequency hub", "DTCM": "Drive train / transfer case module",
    "ESM": "Gearbox selector module", "DASM": "Driver assistance (radar) module",
    "ABS": "Anti-lock brakes / ESC",
}


def _load(name: str) -> dict[str, Any]:
    return json.loads((_DATA / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _coverage() -> dict[str, Any]:
    return _load("module_coverage.json")


@lru_cache(maxsize=1)
def _identity_data() -> dict[str, Any]:
    return _load("identity_remainder.json")


@lru_cache(maxsize=1)
def _snapshot_data() -> dict[str, Any]:
    return _load("ecm_snapshot_fields.json")


def _s(x: Any) -> str:
    return str(x or "").strip()


def applies(vin: str) -> bool:
    """The 19-module list is the MES module list for ONE real car. Any other
    vehicle (and every demo car) keeps its own data and gets no such list."""
    from . import demo_cars
    v = _s(vin).upper()
    return bool(v) and v == _coverage().get("vin") and not demo_cars.is_demo(v)


# --- recorded identity ---------------------------------------------------------------

def _from_car(vin: str, kind: str) -> list[dict[str, Any]]:
    try:
        return [o for o in store.recent_observations(5000, vin=vin, kind=kind) if store.is_from_car(o)]
    except Exception:  # noqa: BLE001 -- a coverage view must still render
        return []


def _identity_reads(vin: str) -> dict[str, dict[str, Any]]:
    """``{module: {"at", "summary", "good_at"}}`` from the newest identity read of
    each module (any answered field counts for ``good_at``)."""
    out: dict[str, dict[str, Any]] = {}
    obs = _from_car(vin, "identity") + _from_car(vin, "module_identity")
    for o in sorted(obs, key=lambda x: _s(x.get("at"))):
        d = o.get("data") or {}
        ecu = _s(d.get("ecu")).upper()
        fields = d.get("fields") or {}
        if not ecu or not fields:
            continue
        summ = read_state.identity_summary(fields)
        slot = out.setdefault(ecu, {"at": None, "summary": None, "good_at": None})
        slot["at"], slot["summary"] = _s(o.get("at")), summ
        if summ["answered"]:
            slot["good_at"] = _s(o.get("at"))
    return out


# --- the 19 --------------------------------------------------------------------------

def _core_row(code: str, live: dict[str, Any], ident: dict[str, Any], tree: set[str]) -> dict[str, Any]:
    lv = live.get(code) or {}
    last, good = lv.get("last"), lv.get("good")
    iv = ident.get(code)
    isum = (iv or {}).get("summary")
    codes_ok = bool(last) and last["why"] is None
    ident_ok = bool(isum) and isum["state"] == read_state.READ
    parts: list[str] = []
    if last is None:
        parts.append("Codes: no code read on record for this car.")
    elif last["why"] is None:
        parts.append(f"Codes: read answered {last['at']}.")
    else:
        parts.append(f"Codes: NOT READ, {last['why']} ({last['at']})."
                     + (f" Last good code read {good}." if good else ""))
    if isum is None:
        parts.append("Identity: no identity read on record for this car.")
    else:
        parts.append(f"Identity ({iv['at']}): {isum['line'].replace('identity ', '', 1)}.")
    ever_answered = bool(good) or bool(iv and iv.get("good_at"))
    attempted = last is not None or iv is not None
    if codes_ok and ident_ok:
        state = READ
    elif ever_answered or codes_ok:
        state = PARTLY
    elif attempted:
        state = NOT_READ
    else:
        state = NOT_TRIED
    when = max([x for x in ((last or {}).get("at"), (iv or {}).get("at")) if x] or [""])
    if state == NOT_READ:
        why = (last or {}).get("why") or (isum or {}).get("line") or "no answer"
        headline = f"{why}; last tried {when}"
    elif state == PARTLY:
        headline = "some of it answered, the rest did not; see below"
    elif state == READ:
        headline = f"codes and identity answered; newest attempt {when}"
    else:
        headline = "no read of this module is on record for this car"
    return {"code": code, "label": _LABELS.get(code, code), "state": state, "headline": headline,
            "detail": parts, "when": when or None, "blocker": None,
            "href": f"modules/{code}" if code in tree else None}


def _json_row(m: dict[str, Any]) -> dict[str, Any]:
    la = m.get("last_attempt")
    bus = ((m.get("bus") or {}).get("value") or "unknown").replace("_", "-").upper()
    if la:
        state, headline = NOT_READ, f"{la['what']} (last tried {la['date']})"
    else:
        state, headline = NOT_TRIED, "no CUORE request to this module is on record"
    return {"code": m["id"], "label": m["label"], "state": state, "headline": headline,
            "detail": [f"Bus: {bus} ({(m.get('bus') or {}).get('confidence') or 'unrecorded'}).",
                       f"Address: {(m.get('address') or {}).get('note') or 'unknown'}."],
            "when": la["date"] if la else None, "blocker": m.get("blocker"), "href": None}


def all_modules(vin: str, *, live: Optional[dict[str, Any]] = None,
                identity: Optional[dict[str, Any]] = None,
                tree: Optional[set[str]] = None) -> dict[str, Any]:
    """Every MES module for this car. ``live``/``identity``/``tree`` may be
    supplied (tests); by default they come from the recorded reads."""
    if not applies(vin):
        return {"applies": False, "rows": [], "total": 0, "read": 0, "counts": {}, "line": ""}
    if live is None:
        from . import modules_bridge
        try:
            live = modules_bridge._live_read_state(vin)
        except Exception:  # noqa: BLE001
            live = {}
    ident = identity if identity is not None else _identity_reads(vin)
    tree = tree or set()
    rows = [_core_row(c, live, ident, tree) for c in CORE]
    rows += [_json_row(m) for m in _coverage()["modules"]]
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in (READ, PARTLY, NOT_READ, NOT_TRIED)}
    n = len(rows)
    line = (f"{counts[READ]} of {n} read. {counts[PARTLY]} partly read, {counts[NOT_READ]} not read, "
            f"{counts[NOT_TRIED]} not tried.")
    return {"applies": True, "rows": rows, "total": n, "read": counts[READ], "counts": counts,
            "line": line}


# --- identity remainder --------------------------------------------------------------

def _recorded_f193() -> dict[str, dict[str, Any]]:
    """Newest positive ``22 F193`` reply per module in the adapter audit file."""
    out: dict[str, dict[str, Any]] = {}
    try:
        lines = audit.log_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        if '"22F193"' not in line.upper().replace(" ", ""):
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("event") != "uds" or o.get("error") or _s(o.get("req")).upper() != "22F193":
            continue
        for payload in framing.reassemble(_s(o.get("raw")), headers_on=True).values():
            if payload[:3] == ["62", "F1", "93"] and len(payload) > 3:
                out[_s(o.get("ecu")).upper()] = {"at": _s(o.get("iso"))[:16].replace("T", " "),
                                                 "bytes": payload[3:]}
    return out


def _same(mes: str, got: list[str]) -> bool:
    raw = " ".join(got).upper()
    asc = uds._ascii(got) if hasattr(uds, "_ascii") else ""
    return mes.upper() in (raw, _s(asc).upper())


def identity_remainder(vin: str, code: str) -> list[dict[str, Any]]:
    """ISO code, hardware version, homologation for one CAN-C module, or ``[]``."""
    code = _s(code).upper()
    if not applies(vin) or code not in CAN_C_EIGHT:
        return []
    data = _identity_data()
    mes = data["modules"][code]
    f193 = _recorded_f193().get(code)
    in_plan = 0xF193 in uds.IDENTITY_ORDER
    out = []
    for item in data["items"]:
        key = item["key"]
        mv = mes[key]
        row = {"key": key, "label": item["label"], "mes": mv, "mes_src": mes["src"],
               "did": item["did"], "cuore": None, "state": NOT_READ, "match": None, "next": None}
        if key == "hw_version" and f193:
            val = " ".join(f193["bytes"])
            row.update(cuore=val, state=READ, match=_same(mv, f193["bytes"]),
                       note=f"22 F193 reply recorded {f193['at']}: raw {val}.")
        elif key == "hw_version":
            if in_plan:
                row["next"] = ("F193 is in the identity read plan; the next identity read of this "
                               "module will ask for it.")
            else:
                row["next"] = ("Not read: F193 was never asked of this module and is not in the "
                               "identity read plan. Marked for the next car session; not added.")
        else:
            row["next"] = ("Not read: no source on file names the identifier that holds it. "
                           "Marked for the next car session; no request is added.")
        out.append(row)
    return out


# --- snapshot ------------------------------------------------------------------------

def _paired_record(vin: str, startups: int) -> Optional[dict[str, dict[str, Any]]]:
    """``{DID hex: identifier}`` of the recorded ECM 19 04 reply whose startups
    counter (200A) is ``startups``, else ``None``."""
    for o in sorted(_from_car(vin, "dtc_detail"), key=lambda x: _s(x.get("at")), reverse=True):
        d = o.get("data") or {}
        if _s(d.get("ecu")).upper() != "ECM":
            continue
        recs = ((d.get("snapshot") or {}).get("records")) or []
        idents = [i for r in recs for i in (r.get("identifiers") or [])]
        by = {_s(i.get("did")).upper(): i for i in idents}
        b = (by.get("200A") or {}).get("bytes")
        if b and int("".join(b), 16) == startups:
            for i in idents:
                i["_at"] = _s(o.get("at"))
            return by
    return None


def _num(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def snapshot_fields(vin: str, code: str = "ECM") -> dict[str, Any]:
    """The 28 MES snapshot fields against the one paired recorded reply."""
    if not applies(vin) or _s(code).upper() != "ECM":
        return {"applies": False}
    data = _snapshot_data()
    pair = data["pair"]
    rec = _paired_record(vin, pair["startups"])
    accepted = snapshot_bindings.bindings_for(vin, "ECM")
    rows, used = [], set()
    for f in data["fields"]:
        did = f["did"]
        ident = (rec or {}).get(did) if did else None
        raw = " ".join(ident["bytes"]) if ident and ident.get("bytes") else None
        value = ident.get("value") if ident else None
        kind = f["kind"]
        if kind == "bound":
            ok = ident is not None and _num(value) is not None and abs(_num(value) - f["mes_num"]) < 0.005
            state = "BOUND" if ok else "NOT VERIFIED HERE"
        elif kind == "candidate":
            state = "CANDIDATE" if ident is not None else "NOT VERIFIED HERE"
        else:
            state = "NOT DECODED"
        if did and ident is not None:
            used.add(did)
        rows.append({"name": f["mes_name"], "unit": f["unit"], "state": state, "did": did,
                     "mes_value": f["mes_value"], "raw": raw, "cuore_value": value,
                     "scale": ("accepted by a person" if did and int(did, 16) in accepted
                               else ("unconfirmed" if did else "none")),
                     "note": f["note"]})
    spare = []
    for did, i in (rec or {}).items():
        if did not in used and i.get("bytes"):
            spare.append({"did": did, "length": len(i["bytes"]), "raw": " ".join(i["bytes"])})
    n = {k: sum(1 for r in rows if r["state"] == k)
         for k in ("BOUND", "CANDIDATE", "NOT DECODED", "NOT VERIFIED HERE")}
    line = (f"{n['BOUND']} of {len(rows)} bound, {n['CANDIDATE']} candidates, {n['NOT DECODED']} "
            f"NOT DECODED" + (f", {n['NOT VERIFIED HERE']} not verifiable on this machine"
                              if n["NOT VERIFIED HERE"] else "") + ". Every scale is unconfirmed "
            "until a person accepts it.")
    return {"applies": True, "rows": rows, "counts": n, "line": line, "pair": pair,
            "paired_record_found": rec is not None, "spare": spare, "total": len(rows)}


# --- short lines for the Report and the Bay sheet ------------------------------------

def not_read_lines(vin: str, *, modules: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """What was not read, from the same data, ready to print. ``{"applies"...}``."""
    mods = modules if modules is not None else all_modules(vin)
    if not mods.get("applies"):
        return {"applies": False}
    lines = [f"{r['code']}: {r['state']}: {r['headline']}" + (f". Blocker: {r['blocker']}" if r["blocker"] else "")
             for r in mods["rows"] if r["state"] != READ]
    ident_missing = 0
    for c in CAN_C_EIGHT:
        ident_missing += sum(1 for x in identity_remainder(vin, c) if x["state"] != READ)
    snap = snapshot_fields(vin, "ECM")
    return {"applies": True, "count_line": mods["line"], "lines": lines,
            "identity_line": (f"Identity items not read on the 8 CAN-C modules: {ident_missing} of "
                              f"{len(CAN_C_EIGHT) * 3} (ISO code, hardware version, homologation)."),
            "snapshot_line": ("ECM stored-code snapshot: " + snap["line"]) if snap.get("applies") else ""}


__all__ = ["all_modules", "identity_remainder", "snapshot_fields", "not_read_lines", "applies",
           "READ", "PARTLY", "NOT_READ", "NOT_TRIED"]
