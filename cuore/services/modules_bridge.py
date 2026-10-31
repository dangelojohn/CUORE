"""The module-tree view: MultiEcuScan's Info/Errors/Parameters/Actuators/
Adjustments breakdown, per module, for one vehicle.

MultiEcuScan shows a car as a tree of modules, each with its own identity,
errors, live parameters, actuator tests and adjustment history. CUORE's
logs and live tooling already know all of this -- it has just never been
assembled per-module in one place. Nothing here invents data; every field
traces to an existing bridge or library:

* **identity** (hardware/software numbers, ISO code, VIN match) -- the
  latest all-systems SCAN log, via ``mes_bridge.analyze_scan``. A car with
  no SCAN log in the corpus gets no identity fields, not guessed ones.
* **errors** -- the corpus-wide classified DTC list from
  ``mes_bridge.extract_dtcs``, cross-referenced against the dossier's
  *current* findings (``mes_bridge.workup``'s ``current_picture``) so a
  code reads as active / cleared-but-unverified / stale rather than just
  "seen at some point".
* **parameters** -- the public UDS DID catalog
  (``cuore.live.did_catalog.all_dids``), each with a known-good band from
  ``known_good_bridge`` where one exists and the last value this car was
  actually observed to report, from ``cuore.live.store``.
* **actuators** -- what has been *learned* from a real dealer-tool capture
  for this VIN (``cuore.live.actuate.list_actuators``), which modules a
  replay refuses outright (``cuore.live.safety.ACTUATION_BLOCKED_MODULES``,
  plus anything on CAN-CH), and the exact consent phrase a run would
  require. Nothing here runs one -- there is no HTTP route for that, by
  design; ``run_actuator`` exists only as an MCP tool on the ``obd2``
  server.
* **adjustments already done** -- the dossier's ``already_attempted`` list.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import known_good_bridge, mes_bridge, sensor_health
from .errors import NotFound

from mes import modules as modules_mod  # noqa: E402

from ..live import actuate, audit, did_catalog, framing, read_state, safety, store  # noqa: E402
from . import mes_coverage  # noqa: E402
from ..live.addressing import MODULES as _ADDR_MODULES, by_code as _addr_by_code  # noqa: E402

#: Statuses in the order a module list should read: worst first.
_STATUS_RANK = {"active": 0, "not_read": 1, "cleared_unverified": 2, "stale": 3, "unknown": 4,
                "clean": 5}

#: ``Dtc.module`` and the dossier's ``ecu_seen`` are MES's own printed strings,
#: not abbreviations -- "Engine / ECM", "Continental ABS MK C1", "Magneti
#: Marelli IAW 10JA CF6/EOBD Injection (2.0)". ``modules.normalize_abbrev``
#: only resolves the first form. This maps the manufacturer/ECU-description
#: form too, from the one place that already carries both: the live link's
#: own address table (``cuore.live.addressing``), whose ``name`` is exactly
#: MES's printed ECU description for each module it addresses.
_DESC_TO_ABBREV = {addr.name.upper(): addr.code for addr in _ADDR_MODULES}

_WORD_RE = re.compile(r"[A-Z0-9/]+")


def _resolve_module(raw: str) -> str | None:
    """Best-effort: a free-text module string from the log corpus -> abbrev.

    Tries, in order: direct abbrev normalisation ("Engine / ECM" style),
    an exact match against the live link's known ECU-description strings,
    then a scan for any registered abbreviation appearing as a whole token
    inside the string (catches MES's own "Radio frequency hub (RFHUB)
    Continental" form). Returns ``None`` -- never a guess -- when nothing
    matches.
    """
    name = (raw or "").strip()
    if not name:
        return None
    direct = modules_mod.normalize_abbrev(name)
    if direct:
        return direct
    exact = _DESC_TO_ABBREV.get(name.upper())
    if exact:
        return exact
    for token in _WORD_RE.findall(name.upper()):
        resolved = modules_mod.normalize_abbrev(token)
        if resolved:
            return resolved
    return None


def _bus_of(abbrev: str) -> str:
    addr = _addr_by_code(abbrev)
    return addr.bus_key if addr else "unknown"


def _blocked(abbrev: str) -> tuple[bool, str]:
    """Whether an actuator replay on this module is refused outright, and why.

    Mirrors ``cuore.live.safety.assert_actuation_module_allowed`` exactly --
    this is the same gate, read rather than enforced, so the module list and
    the real refusal can never disagree."""
    bus = _bus_of(abbrev)
    if abbrev in safety.ACTUATION_BLOCKED_MODULES or bus == "can_ch":
        return True, ("safety-critical (brakes, airbag, steering, torque vectoring, "
                       "driveline/park lock, or the immobiliser) or the CAN-CH bus -- "
                       "actuator replay is refused here; use MultiEcuScan or wiTECH "
                       "for this test")
    return False, ""


def _errors_by_module(vin: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """This car's whole classified DTC corpus, grouped by module.

    Each code is tagged against the dossier's *current* findings, not its
    lifetime chronic/returned label: a chronic code that is not in the
    latest read is "stale" here even though it is still chronic in the
    corpus-wide sense -- what a module tree needs to show is what is open
    right now.
    """
    dossier = mes_bridge.workup(vin=vin)
    current = dossier.get("current_picture") or {}
    active_codes: set[str] = set()
    for key in ("latest_session", "last_session_with_findings"):
        session = current.get(key) or {}
        for d in session.get("dtcs", []):
            code = d.get("code") or d.get("dtc") or ""
            if code:
                active_codes.add(code)

    extracted = mes_bridge.extract_dtcs(vin=vin)
    out: dict[str, dict[str, Any]] = {}
    for rec in extracted.get("dtcs", []):
        full = rec.get("dtc") or ""
        base = full.split("-")[0]
        if full in active_codes or base in active_codes:
            status = "active"
        elif rec.get("severity") == "cleared":
            status = "cleared_unverified"
        else:
            status = "stale"
        resolved = {_resolve_module(m) for m in (rec.get("modules") or [])}
        resolved.discard(None)
        for key in (resolved or {"UNKNOWN"}):
            bucket = out.setdefault(
                key, {"active": 0, "cleared_unverified": 0, "stale": 0, "codes": []})
            bucket[status] += 1
            bucket["codes"].append({
                "dtc": full,
                "status": status,
                "severity": rec.get("severity"),
                "description": (rec.get("descriptions") or [""])[0],
                "last_seen": rec.get("last_seen"),
            })
    return out, dossier


def _scan_identity(vin: str) -> dict[str, dict[str, Any]]:
    """Per-module identity from the newest all-systems SCAN, if there is one."""
    try:
        scan = mes_bridge.analyze_scan(vin=vin)
    except NotFound:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for m in scan.get("modules", []):
        abbrev = _resolve_module(m.get("abbrev") or "") or (m.get("abbrev") or "").upper()
        if abbrev:
            out[abbrev] = {**m, "scan_file": scan.get("file"),
                           "scan_timestamp": scan.get("timestamp")}
    return out


def _naive(at: Any) -> str:
    """An ISO time as naive local ``YYYY-MM-DDTHH:MM:SS`` so reads from different
    sources (audit log has a UTC offset, observations and scans do not) sort
    together. Unparseable -> ``""`` (sorts oldest, is dropped)."""
    try:
        dt = datetime.fromisoformat(str(at))
    except ValueError:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.isoformat(timespec="seconds")


def _single_car_on_file() -> bool:
    try:
        return len(mes_bridge.vehicles(real_only=True)) == 1
    except Exception:  # noqa: BLE001 -- unknown means not provably single
        return False


def _audit_dtc_reads(vin: str = "") -> list[tuple[str, str, Optional[str]]]:
    """``[(at, module, why or None)]`` for every module DTC-list read (UDS 19 02)
    in the adapter audit log, for ``vin`` only. A row carries the VIN of the car
    that was connected; it counts when it matches. An older row with no VIN
    counts only while this is the single car on file. Never guessed."""
    out: list[tuple[str, str, Optional[str]]] = []
    want = (vin or "").strip().upper()
    single = _single_car_on_file()
    try:
        lines = audit.log_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        if '"uds"' not in line or '"1902' not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        ecu = str(o.get("ecu") or "").upper()
        at = _naive(o.get("iso"))
        if o.get("event") != "uds" or not ecu or not at or not str(o.get("req") or "").startswith("1902"):
            continue
        row_vin = str(o.get("vin") or "").strip().upper()
        if row_vin:
            if row_vin != want:
                continue
        elif not single:
            continue
        raw = str(o.get("raw") or "")
        flat = raw.replace(" ", "").upper()
        d: dict[str, Any] = {"error": o.get("error")}
        if "7F19" in flat:
            d["nrc"] = flat[flat.index("7F19") + 4:flat.index("7F19") + 6] or "?"
        elif not d["error"] and (not flat or framing.no_data(raw)):
            d["warning"] = "no answer from the module"
        out.append((at, ecu, read_state.reason(d)))
    return out


def _scan_dtc_reads() -> list[tuple[str, str, Optional[str]]]:
    """The same triples from the saved full scan (``fullscan_last.json``)."""
    at, mods = sensor_health._fullscan()
    at = _naive(at)
    if not at:
        return []
    return [(at, m.upper(), None if v["state"] == "answered"
             else f"full scan: {v['why'] or 'module did not answer'}")
            for m, v in mods.items()]


#: a failed attempt older than this is history, not the module's state today
_OLD_ATTEMPT_DAYS = 1


def _age_note(at: str, now: Optional[datetime] = None) -> str:
    """`` (old: last tried N days ago on DATE; not the state today, read it again)`` for a
    failed read older than a day, else ``""``. Never turns NOT READ into clean."""
    try:
        when = datetime.fromisoformat(str(at))
    except ValueError:
        return ""
    days = ((now or datetime.now()) - when).days
    if days < _OLD_ATTEMPT_DAYS:
        return ""
    return (f" (old: last tried {days} day{'s' if days != 1 else ''} ago on {when:%Y-%m-%d}; "
            "not the state today, read the module again)")


def _live_read_state(vin: str) -> dict[str, dict[str, Any]]:
    """``{module: {"last": newest read, "good": newest answered read}}`` from
    every source of module reads: this car's ``module_dtcs`` observations, the
    adapter audit log and the saved full scan. The newest attempt wins whatever
    its source: a module whose newest read did not answer is NOT READ (with the
    last good date), and an old failure never hides a newer good read."""
    reads: list[tuple[str, str, Optional[str]]] = []
    try:
        for o in store.recent_observations(n=1000, vin=vin, kind="module_dtcs"):
            d = o.get("data") or {}
            ecu = str(d.get("ecu") or "").upper()
            if ecu and _naive(o.get("at")):
                reads.append((_naive(o.get("at")), ecu, read_state.reason(d)))
    except Exception:  # noqa: BLE001 -- the module tree must still render
        pass
    for source in (lambda: _audit_dtc_reads(vin), _scan_dtc_reads):
        try:
            reads.extend(source())
        except Exception:  # noqa: BLE001
            continue
    out: dict[str, dict[str, Any]] = {}
    for at, ecu, why in sorted(reads, key=lambda r: r[0], reverse=True):
        slot = out.setdefault(ecu, {"last": None, "good": None})
        if slot["last"] is None:
            slot["last"] = {"at": at, "why": why}
        if slot["good"] is None and why is None:
            slot["good"] = at
    return out


def list_modules(vin: str) -> list[dict[str, Any]]:
    """Every module this car's logs (or the live registry) have anything to say about.

    Raises :class:`NotFound` when the VIN has no logs at all -- same rule
    the dossier itself uses, via ``mes_bridge.workup``.
    """
    errors_by_module, dossier = _errors_by_module(vin)
    scan_identity = _scan_identity(vin)
    ecu_seen = {_resolve_module(e) for e in (dossier.get("identity", {}).get("ecu_seen") or [])}
    ecu_seen.discard(None)
    attempted = dossier.get("already_attempted") or []
    learned = actuate.list_actuators(vin).get(vin, [])
    live = _live_read_state(vin)

    rows: list[dict[str, Any]] = []
    for abbrev in sorted(ecu_seen | set(errors_by_module) | set(scan_identity)):
        reg = modules_mod.describe(abbrev)
        ident = scan_identity.get(abbrev, {})
        errs = errors_by_module.get(
            abbrev, {"active": 0, "cleared_unverified": 0, "stale": 0, "codes": []})
        blocked, reason = _blocked(abbrev)
        acts = [a for a in learned if (a.get("module") or "").upper() == abbrev]
        known = abbrev in ecu_seen or abbrev in scan_identity
        if errs["active"]:
            status = "active"
        elif errs["cleared_unverified"]:
            status = "cleared_unverified"
        elif errs["stale"]:
            status = "stale"
        elif known:
            status = "clean"
        else:
            status = "unknown"
        not_read = None
        not_read_old = False
        last_good = None
        lv = live.get(abbrev)
        if lv and lv["last"] and lv["last"]["why"]:
            # newest live read of this module got no answer: worse than any
            # older "clean"/"stale" the logs imply, and never a green state
            if status != "active":
                status = "not_read"
            not_read = read_state.banner(f"{lv['last']['why']} at {lv['last']['at']}")
            old_note = _age_note(lv["last"]["at"])
            if old_note:
                not_read += old_note
                not_read_old = True
            last_good = ({"at": lv["good"], "label": "not read this session"}
                         if lv["good"] else None)
        elif status == "unknown" and not (lv and lv["good"]):
            not_read = read_state.banner("never read")
        done = [a for a in attempted if abbrev in (a.get("operation") or "").upper()]
        rows.append({
            "code": abbrev,
            "name": reg.get("name"),
            "domain": reg.get("domain"),
            "tier": reg.get("tier"),
            "bus": _bus_of(abbrev),
            "identity": {
                "hardware": ident.get("hardware") or None,
                "software": ident.get("software") or None,
                "iso": ident.get("iso_code") or None,
                "vin_match": (ident.get("vin") == vin) if ident.get("vin") else None,
            },
            "errors": {
                "active": errs["active"],
                "cleared_unverified": errs["cleared_unverified"],
                "stale": errs["stale"],
                "codes": [c["dtc"] for c in errs["codes"]],
            },
            "params": {"available": len(did_catalog.all_dids(abbrev))},
            "actuators": {"available": len(acts), "blocked": blocked, "reason": reason},
            "adjustments": done,
            "last_seen": ident.get("scan_timestamp"),
            "status": status,
            "not_read": not_read,
            "not_read_old": not_read_old,
            "last_good_read": last_good,
        })
    rows.sort(key=lambda r: (_STATUS_RANK.get(r["status"], 9), r["code"]))
    return rows


def module_detail(vin: str, code: str) -> dict[str, Any]:
    """One module's full tab set: errors, parameters, actuators, adjustments, info.

    Raises :class:`NotFound` for a module code this vehicle's logs and the
    live registry both have nothing on.
    """
    abbrev = (code or "").strip().upper()
    if not abbrev:
        raise NotFound("a module code is required")

    rows = list_modules(vin)
    row = next((r for r in rows if r["code"] == abbrev), None)
    if row is None:
        raise NotFound(
            f"{abbrev} is not a module this vehicle's logs or the live registry know about")

    errors_by_module, dossier = _errors_by_module(vin)
    codes = errors_by_module.get(abbrev, {"codes": []})["codes"]
    error_rows = []
    for c in codes:
        frame = None
        try:
            found = mes_bridge.freeze_frames(code=c["dtc"], vin=vin)
            frames = found.get("frames") or []
            frame = frames[0].get("freeze_frame") if frames else None
        except NotFound:
            frame = None
        error_rows.append({**c, "freeze_frame": frame})

    specs = did_catalog.all_dids(abbrev)
    observations = store.recent_observations(n=500, vin=vin, kind="did")
    param_rows = []
    for d in specs:
        did_hex = f"{d.did:04X}"
        last_value = None
        for obs in observations:
            data = obs.get("data") or {}
            if (str(data.get("ecu") or "").upper() == abbrev
                    and str(data.get("did") or "").upper() == did_hex):
                last_value = data
                break
        param_rows.append({
            "did": did_hex,
            "name": d.name,
            "unit": d.unit,
            "confidence": d.confidence,
            "note": d.note,
            "band": known_good_bridge.sourced_band(d.name),
            "last_value": last_value,
        })

    learned = actuate.list_actuators(vin).get(vin, [])
    actuator_rows = []
    for a in learned:
        if (a.get("module") or "").upper() != abbrev:
            continue
        phrase = actuate.consent_phrase(abbrev, a.get("name") or "",
                                        routine=(a.get("kind") == "routine"))
        actuator_rows.append({**a, "consent_phrase": phrase,
                              "blocked": row["actuators"]["blocked"],
                              "blocked_reason": row["actuators"]["reason"]})

    attempted = dossier.get("already_attempted") or []
    adjustment_rows = [a for a in attempted if abbrev in (a.get("operation") or "").upper()]

    per_code_tsb = (dossier.get("tsb_matches") or {}).get("per_code") or {}
    tsb_rows = []
    seen_ids: set[str] = set()
    for c in codes:
        base = (c["dtc"] or "").split("-")[0]
        for t in per_code_tsb.get(base, []):
            tid = t.get("bulletin") or t.get("title") or str(t)
            if tid not in seen_ids:
                seen_ids.add(tid)
                tsb_rows.append(t)

    return {
        **row,
        "errors_detail": error_rows,
        "parameters": param_rows,
        "actuators_detail": actuator_rows,
        "adjustments_detail": adjustment_rows,
        "tsb": tsb_rows,
        "identity_remainder": mes_coverage.identity_remainder(vin, abbrev),
        "snapshot_fields": mes_coverage.snapshot_fields(vin, abbrev),
    }


__all__ = ["list_modules", "module_detail"]
