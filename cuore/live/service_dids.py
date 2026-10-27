"""Read-only "service-value discovery": find which cluster DID holds the service values.

CUORE cannot reset the service interval until it can READ the service values
back. MES's "Service Interval Reset" runs on the instrument cluster (IPC,
ISO code 00 03 50 8B 14, CAN-C). This module:

* :func:`expected_values` -- what the real (non-simulated) MES Service logs and
  CUORE's own records say the values are (never invented; unknown = omitted).
* :func:`plan` -- which CAN-C modules and DID ranges to sweep, capped to a run
  of about three minutes. ``0x22`` only.
* :func:`run` -- the sweep, through ``ops.module_discover_dids`` (the same
  guarded, interlocked, audited read path every other read uses).
* :func:`match` -- compare each reply to the expected values under many
  decodings; a hit is a CANDIDATE, never a confirmation.
* :func:`results` -- the last run's candidates plus the next step.

Nothing here writes to the car: no SecurityAccess (0x27), no
WriteDataByIdentifier (0x2E), no routines (0x31), no IO control (0x2F), no
memory write (0x3D). ``uds.request`` additionally asserts read-only for every
frame, so even a bug here cannot send one.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import audit, store
from .addressing import by_code

STATUS = "candidate — unconfirmed until it changes after a reset"
OBS_KIND = "service_dids"
IPC_ISO = "00 03 50 8B 14"

#: Seconds per request used for the estimate. Deliberately pessimistic: a silent
#: DID costs the 0.15 s per-DID timeout plus adapter turnaround; an NRC answer is faster.
SECONDS_PER_REQUEST = 0.25
#: Hard cap on requests in one run (~144 s at SECONDS_PER_REQUEST, under three minutes).
MAX_REQUESTS = 576

NEVER = ["0x27", "0x2E", "0x2F", "0x31", "0x3D", "0x34", "0x35", "0x36", "0x37", "0x14", "0x11",
         "0x85", "0x28"]

#: module -> (why, [(start, end, label)]). Chosen from did_catalog / addressing / the
#: GIORGIO module map: IPC 0x0104 brightness is the one catalogued IPC DID, so 0x01xx is
#: the cluster's own data block; ECM 0x2001 (odometer) and 0x2003 are danardi78 entries
#: still listed unverified; 0xF1xx is the ISO 14229 identification block.
_PLAN: dict[str, dict[str, Any]] = {
    "IPC": {
        "why": ("The cluster that MES's Service Interval Reset adjusts "
                "(ISO 00 03 50 8B 14, CAN-C, answered in SCAN_2610260906). The service "
                "counters live here."),
        "ranges": [(0xF180, 0xF1FF, "identification block"),
                   (0x0100, 0x01FF, "cluster data block (0x0104 brightness is catalogued)"),
                   (0x2000, 0x207F, "counter / odometer-style block (as on the ECM)")],
    },
    "ECM": {
        "why": ("Catalogue lists ECM 0x2001 as odometer (danardi78, unverified); a second "
                "odometer source helps tell the odometer apart from the service counters."),
        "ranges": [(0x2000, 0x203F, "odometer / programming-events block")],
    },
}


def _hex(v: int) -> str:
    return f"{v:04X}"


def _ranges_text(ranges: list[tuple[int, int, str]]) -> list[dict[str, Any]]:
    return [{"start": _hex(a), "end": _hex(b), "count": b - a + 1, "why": w}
            for a, b, w in ranges]


# --- expected values ---------------------------------------------------------------------

_HDR_DATE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*([AP]M)?",
                       re.I)
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_NUM = r"(-?\d+(?:\.\d+)?)"
_FIELDS = {
    "odometer": re.compile(r"^Odometer:\s*" + _NUM + r"\s*km", re.I),
    "next service km": re.compile(r"^Distance till next service:\s*" + _NUM + r"\s*km", re.I),
    "next service days": re.compile(r"^Days till next service:\s*" + _NUM + r"\s*days", re.I),
    "last service date": re.compile(r"^Last service date:\s*(\d{1,2})/(\d{1,2})/(\d{4})", re.I),
}
_UNITS = {"odometer": "km", "next service km": "km", "next service days": "days",
          "last service date": "date"}


def _mes_log_dir(log_dir: Optional[str | Path]) -> Optional[Path]:
    if log_dir:
        return Path(log_dir)
    try:
        from .config import mes_folders
        return Path(mes_folders()["log_folder"])
    except Exception:
        return None


def _header_at(lines: list[str]) -> str:
    for ln in lines[:6]:
        m = _HDR_DATE.match(ln)
        if m:
            mo, d, y, h, mi, s, ap = m.groups()
            h = int(h)
            if ap:
                h = h % 12 + (12 if ap.upper() == "PM" else 0)
            try:
                return datetime(int(y), int(mo), int(d), h, int(mi), int(s)).isoformat(
                    timespec="seconds")
            except ValueError:
                return ""
    return ""


def _parse_service_log(path: Path, vin: str) -> Optional[dict[str, Any]]:
    """One Service Interval Reset log -> {"at", "values", "adjusted"} or None to skip."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if "SIMULATION MODE" in text:
        return None
    lines = text.splitlines()
    head = "\n".join(lines[:12])
    if "Service Interval Reset" not in head:
        return None
    iso = re.search(r"ECU ISO code:\s*([0-9A-F ]+)", head, re.I)
    if iso and " ".join(iso.group(1).split()).upper() != IPC_ISO:
        return None
    vin_in_log = _VIN_RE.search(head)
    if vin_in_log and vin and vin_in_log.group(1) != vin and "VIN" in head.upper():
        return None  # a log that names a different car
    # last READING block that carries each field (blocks fill up line by line)
    values: dict[str, Any] = {}
    for ln in lines:
        s = ln.strip()
        for name, rx in _FIELDS.items():
            m = rx.match(s)
            if not m:
                continue
            if name == "last service date":
                mo, d, y = (int(x) for x in m.groups())
                values[name] = f"{y:04d}-{mo:02d}-{d:02d}"
            else:
                f = float(m.group(1))
                values[name] = int(f) if f == int(f) else f
    adjusted = [ln.strip() for ln in lines if ln.strip().startswith("EXECUTING ADJUSTMENT")
                or ln.strip().isupper() and "RESET" in ln]
    return {"log": path.name, "at": _header_at(lines), "values": values,
            "adjusted": bool(adjusted)}


def _owner_oil_values(vin: str) -> list[dict[str, Any]]:
    try:
        from . import owner_events
        rows = owner_events.load(vin)
    except Exception:
        return []
    best = None
    for r in rows:
        if r.get("kind") != "engine_oil_change" or r.get("odometer_km") in (None, ""):
            continue
        try:
            odo = float(r["odometer_km"])
        except (TypeError, ValueError):
            continue
        if best is None or str(r.get("at") or "") >= str(best[1].get("at") or ""):
            best = (odo, r)
    if best is None:
        return []
    odo, r = best
    return [{"name": "odometer at last oil change (owner event)",
             "value": int(odo) if odo == int(odo) else odo, "unit": "km",
             "source": {"log": f"owner_events:{r.get('id', '')}", "at": str(r.get("at") or "")}}]


def expected_values(vin: str, log_dir: Optional[str | Path] = None) -> dict[str, Any]:
    """Latest known service values: real MES Service logs plus CUORE owner events."""
    values: list[dict[str, Any]] = []
    notes: list[str] = []
    try:
        d = _mes_log_dir(log_dir)
        parsed: list[dict[str, Any]] = []
        if d and d.is_dir():
            for p in sorted(d.glob("FESLog_*.txt")):
                try:
                    if "Service Interval Reset" not in p.read_text(
                            encoding="utf-8", errors="replace")[:600]:
                        continue
                except OSError:
                    continue
                one = _parse_service_log(p, vin)
                if one:
                    parsed.append(one)
        parsed.sort(key=lambda x: (x["at"], x["log"]), reverse=True)
        for name in _UNITS:
            for one in parsed:
                if name in one["values"]:
                    values.append({"name": name, "value": one["values"][name],
                                   "unit": _UNITS[name],
                                   "source": {"log": one["log"], "at": one["at"]}})
                    break
        if values:
            src_at = max(v["source"]["at"] for v in values)
            later = [p for p in parsed if p["at"] > src_at and p["adjusted"]]
            for p in later:
                notes.append(f"{p['log']} ({p['at']}) ran a service adjustment but logged no "
                             "read-back, so the cluster's values may have moved since")
            notes.append("Attributed by log and date, not VIN: these FES logs carry no VIN "
                         "header. Odometer is the value at the log time; the car has been "
                         "driven since, so an exact odometer match is only possible if it has "
                         "not.")
            notes.append("Service interval (16000 km) and period (365 days) equal the "
                         "post-reset next-service values, so a 16000 or 365 candidate may be "
                         "the interval setting rather than the countdown.")
        else:
            notes.append("no real (non-simulated) MES Service Interval Reset log with "
                         "readings was found")
    except Exception as exc:  # never raise on bad data
        notes.append(f"MES log scan failed: {exc}")
    values.extend(_owner_oil_values(vin))
    return {"values": values, "note": " ".join(notes)}


# --- plan --------------------------------------------------------------------------------

def plan(vin: str = "", modules: Optional[list[str]] = None) -> dict[str, Any]:
    """The sweep to run. ``modules`` overrides the default (IPC, ECM); any module not on
    CAN-C, or without a DID plan, is listed under ``refused`` and never swept."""
    want = [m.upper() for m in (modules or list(_PLAN))]
    mods: list[dict[str, Any]] = []
    refused: list[dict[str, str]] = []
    did_ranges: list[dict[str, Any]] = []
    total = 0
    for code in want:
        ecu = by_code(code)
        if ecu is None:
            refused.append({"code": code, "reason": "unknown module"})
            continue
        if ecu.bus_key != "can_c":
            refused.append({"code": code, "reason": f"{code} is on {ecu.bus_key}, not CAN-C; "
                            "this read-only discovery only touches CAN-C"})
            continue
        spec = _PLAN.get(code)
        if spec is None:
            refused.append({"code": code, "reason": "no service-DID plan for this module"})
            continue
        n = sum(b - a + 1 for a, b, _ in spec["ranges"])
        if total + n > MAX_REQUESTS:
            refused.append({"code": code, "reason": f"would exceed the {MAX_REQUESTS}-request cap"})
            continue
        total += n
        mods.append({"code": code, "bus": "can_c", "why": spec["why"]})
        for r in _ranges_text(spec["ranges"]):
            did_ranges.append({"module": code, **r})
    return {
        "modules": mods,
        "did_ranges": did_ranges,
        "services": ["0x22"],
        "max_requests": total,
        "est_seconds": round(total * SECONDS_PER_REQUEST),
        "preconditions": [
            "close MES (the MES interlock refuses to transmit while it is running)",
            "stop any live-data poll session (the poller guard refuses otherwise)",
            "plain cable on CAN-C with the 500 kbps bitrate verified by the session's own check",
            "ignition on, engine off; default session only (no 0x10 03 or 0x3E is sent)",
        ],
        "never": list(NEVER),
        "refused": refused,
    }


# --- matching ----------------------------------------------------------------------------

def _payload(reply: dict[str, Any]) -> list[int]:
    out: list[int] = []
    for b in reply.get("bytes") or []:
        try:
            out.append(int(str(b), 16) & 0xFF)
        except (TypeError, ValueError):
            return []
    return out


def _bcd(n: int, digits: int) -> Optional[bytes]:
    s = f"{n:0{digits}d}"
    if len(s) != digits or digits % 2:
        return None
    return bytes(int(s[i:i + 2], 16) for i in range(0, digits, 2))


def _date_forms(iso: str) -> list[tuple[str, bytes]]:
    try:
        y, mo, d = (int(x) for x in iso.split("-"))
    except (ValueError, AttributeError):
        return []
    forms: list[tuple[str, bytes]] = []
    y2 = y % 100
    orders = {"YMD": (y, mo, d), "DMY": (d, mo, y), "MDY": (mo, d, y)}
    for name, parts in orders.items():
        # BCD, 2-digit year and 4-digit year
        for ydig, tag in ((2, "yy"), (4, "yyyy")):
            seq = b""
            ok = True
            for label, v in zip(name, parts):
                if label == "Y":
                    piece = _bcd(y2 if ydig == 2 else y, ydig)
                else:
                    piece = _bcd(v, 2)
                if piece is None:
                    ok = False
                    break
                seq += piece
            if ok:
                forms.append((f"BCD {name} ({tag})", seq))
        # binary, 1-byte year (yy) and 2-byte year big/little endian
        for ybytes, tag in ((1, "yy"), (2, "yyyy BE"), (3, "yyyy LE")):
            seq = b""
            for label, v in zip(name, parts):
                if label == "Y":
                    if ybytes == 1:
                        seq += bytes([y2])
                    elif ybytes == 2:
                        seq += y.to_bytes(2, "big")
                    else:
                        seq += y.to_bytes(2, "little")
                else:
                    seq += bytes([v])
            forms.append((f"binary {name} ({tag})", seq))
    return forms


def _find_all(hay: bytes, needle: bytes) -> list[int]:
    out, i = [], hay.find(needle)
    while i != -1 and needle:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


def _fmt_value(v: Any) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def match(replies: list[dict[str, Any]], expected: Any) -> list[dict[str, Any]]:
    """Candidates: any DID reply whose bytes decode to an expected value exactly."""
    try:
        exp = expected.get("values", []) if isinstance(expected, dict) else list(expected or [])
    except Exception:
        return []
    found: dict[tuple, dict[str, Any]] = {}
    for rep in replies or []:
        try:
            module = str(rep.get("module") or rep.get("ecu") or "")
            did = str(rep.get("did") or "")
            raw = _payload(rep)
            if not raw:
                continue
            data = bytes(raw)
            rawhex = " ".join(f"{b:02X}" for b in raw)
            for item in exp:
                name, val, unit = item.get("name"), item.get("value"), item.get("unit")
                label = f"{name} = {_fmt_value(val)}"
                if unit == "date":
                    for form, seq in _date_forms(str(val)):
                        for off in _find_all(data, seq):
                            _add(found, module, did, off, form, str(val), label, rawhex)
                    continue
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    continue
                targets = {float(val): "", }
                if unit == "km":
                    targets[float(val) * 10] = " (tenths of km, x10)"
                for width in (1, 2, 3, 4):
                    for off in range(0, len(data) - width + 1):
                        chunk = data[off:off + width]
                        for order in (("big",) if width == 1 else ("big", "little")):
                            n = int.from_bytes(chunk, order)
                            for tgt, suffix in targets.items():
                                if float(n) == tgt:
                                    dec = (f"u{width * 8}" if width == 1 else
                                           f"u{width * 8} {order}-endian") + suffix
                                    _add(found, module, did, off, dec,
                                         n / 10 if suffix else n, label, rawhex)
        except Exception:
            continue
    out: list[dict[str, Any]] = []
    by_loc: dict[tuple, list[dict[str, Any]]] = {}
    for c in found.values():
        by_loc.setdefault((c["module"], c["did"], c["offset"], c["decoding"].split(" (")[0],
                           str(c["value"])), []).append(c)
    for group in by_loc.values():
        qty = sorted({c["matches"] for c in group})
        for c in group:
            if len(qty) > 1:
                c["warning"] = ("this one value also matches " +
                                "; ".join(q for q in qty if q != c["matches"]) +
                                " -- it cannot tell the quantities apart until a reset "
                                "changes one of them")
            out.append(c)
    out.sort(key=lambda c: (c["module"], c["did"], c["offset"], c["matches"]))
    return out


def _add(found: dict, module: str, did: str, off: int, decoding: str, value: Any,
         matches: str, raw: str) -> None:
    key = (module, did, off, decoding, matches)
    found.setdefault(key, {"module": module, "did": did, "offset": off, "decoding": decoding,
                           "value": value, "matches": matches, "status": STATUS, "raw": raw})


# --- run ---------------------------------------------------------------------------------

def run(vin: str, max_seconds: float = 180, *, _plan: Optional[dict[str, Any]] = None,
        log_dir: Optional[str | Path] = None) -> dict[str, Any]:
    """Sweep the planned DID ranges (0x22 only) via ops.module_discover_dids, record and match."""
    from . import ops
    started = datetime.now().isoformat(timespec="seconds")
    t0 = time.monotonic()
    p = _plan or plan(vin)
    replies: list[dict[str, Any]] = []
    errors: list[str] = []
    requests = 0
    aborted: Optional[str] = None
    audit.record("service_dids_run_start", vin=vin, modules=[m["code"] for m in p["modules"]],
                 max_requests=p["max_requests"], max_seconds=max_seconds)
    try:
        ranges_by_mod: dict[str, list[dict[str, Any]]] = {}
        for r in p["did_ranges"]:
            ranges_by_mod.setdefault(r["module"], []).append(r)
        for mod in p["modules"]:
            code = mod["code"]
            ecu = by_code(code)
            if ecu is None or ecu.bus_key != "can_c":
                errors.append(f"{code}: refused, not a CAN-C module")
                continue
            for r in ranges_by_mod.get(code, []):
                if time.monotonic() - t0 >= max_seconds:
                    aborted = f"time budget of {max_seconds:g}s used up"
                    break
                left = p["max_requests"] - requests
                if left <= 0:
                    aborted = "request cap reached"
                    break
                try:
                    res = ops.module_discover_dids(
                        code, vin=vin, ranges=[f"{r['start']}-{r['end']}"],
                        max_dids=min(int(r["count"]), left))
                except Exception as exc:
                    errors.append(f"{code} {r['start']}-{r['end']}: {type(exc).__name__}: {exc}")
                    aborted = f"{type(exc).__name__}: {exc}"
                    break
                requests += int(res.get("tried") or 0)
                if res.get("stopped_early"):
                    errors.append(f"{code} {r['start']}-{r['end']}: stopped early "
                                  f"({res['stopped_early']})")
                for h in res.get("positive") or []:
                    rep = {"module": code, "did": h["did"], "bytes": h.get("bytes") or [],
                           "ascii": h.get("ascii")}
                    replies.append(rep)
                    store.record_observation(OBS_KIND, {"entry": "reply", **rep}, vin=vin,
                                             bus="can_c", cable="", stream="service_dids sweep (see did_discovery for the wire record)")
            if aborted:
                break
    except Exception as exc:
        aborted = aborted or f"{type(exc).__name__}: {exc}"
    exp = expected_values(vin, log_dir=log_dir)
    matches = match(replies, exp)
    finished = datetime.now().isoformat(timespec="seconds")
    summary = {"started": started, "finished": finished, "requests": requests,
               "replies": len(replies), "matches": matches, "errors": errors,
               "aborted_reason": aborted}
    store.record_observation(OBS_KIND, {"entry": "summary", **summary,
                                        "expected": exp["values"]}, vin=vin, bus="can_c",
                             cable="", stream="service_dids sweep (see did_discovery for the wire record)")
    audit.record("service_dids_run_end", vin=vin, requests=requests, replies=len(replies),
                 matches=len(matches), errors=len(errors), aborted=aborted)
    return summary


# --- results -----------------------------------------------------------------------------

NEXT_STEP = ("record these; after the next MES service reset, re-run: the DID whose value "
             "changes from 16000 is confirmed")


def results(vin: str) -> dict[str, Any]:
    """The last run's candidates plus the next step. Never raises."""
    try:
        rows = store.recent_observations(500, vin=vin, kind=OBS_KIND)
    except Exception:
        rows = []
    last = None
    for r in rows:
        d = r.get("data") or {}
        if d.get("entry") == "summary":
            if last is None or str(r.get("at") or "") >= str(last.get("at") or ""):
                last = r
    if last is None:
        return {"ran": False, "candidates": [], "next_step": NEXT_STEP,
                "note": "no service-DID run recorded for this VIN yet"}
    d = last["data"]
    return {"ran": True, "at": last.get("at"), "requests": d.get("requests"),
            "replies": d.get("replies"), "candidates": d.get("matches") or [],
            "errors": d.get("errors") or [], "aborted_reason": d.get("aborted_reason"),
            "next_step": NEXT_STEP}


__all__ = ["expected_values", "plan", "run", "match", "results", "STATUS"]
