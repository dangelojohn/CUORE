"""Module code round: 19 02 status, then 19 04 snapshot and 19 06 extended data
for each code found, for a named list of modules on one bus, in one held session.

Reuses :func:`uds.read_dtcs` (the sweep behind GET /live/scan) and
:func:`dtc_detail.dtc_snapshot` / :func:`dtc_detail.dtc_extended`; the new part
is only the loop and the compact summary. Read-only (service 0x19). Modules
with no confirmed address on this car (ESM today, DTCM until verified) are
reported as skipped with the reason, never guessed.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from . import dtc_detail, snapshot_bindings, uds
from .coverage import _FEPS
from .errors import BadCommand

#: Bus -> modules this car's session plan reads there.
DEFAULT_MODULES: dict[str, tuple[str, ...]] = {
    "can_c": ("IPC", "TCM", "ESM", "DTCM"),
    "can_ch": ("ABS",),
}

#: testFailed | pending | confirmed | failedSinceLastClear. A code whose only bit
#: is "test not completed" is not a fault record and has no snapshot worth reading.
_SET_BITS = 0x01 | 0x04 | 0x08 | 0x20


def warnings_for(bus_key: str) -> list[str]:
    return [_FEPS] if bus_key == "can_ch" else []


def round_module(sess: Any, ecu: Any, vin: str, *, only_set: bool = True, max_codes: int = 40,
                 record: Optional[Callable[[str, dict[str, Any]], None]] = None) -> dict[str, Any]:
    """One module: ``{module, codes, snapshots_decoded, snapshots_raw, candidate_fields, ...}``."""
    listing = uds.read_dtcs(sess, ecu)
    if record:
        record("module_dtcs", listing)
    row: dict[str, Any] = {"module": ecu.code, "codes": [], "snapshots_decoded": 0,
                           "snapshots_raw": 0, "candidate_fields": [],
                           "error": listing.get("error"), "nrc": listing.get("nrc")}
    if listing.get("codes") is None:
        row["read"] = False
        row["warning"] = listing.get("warning") or listing.get("note") or "no 19 02 answer"
        return row
    row["read"] = True
    recs = listing.get("dtcs") or []
    chosen = [r for r in recs if not only_set or int(r.get("status") or 0) & _SET_BITS]
    row["codes"] = [r["code"] for r in chosen]
    row["tracked"] = len(recs)
    if len(chosen) > max_codes:
        row["truncated_to"] = max_codes
        chosen = chosen[:max_codes]
    cands: list[str] = []
    for r in chosen:
        snap = dtc_detail.dtc_snapshot(sess, ecu, r["code"])
        ext = dtc_detail.dtc_extended(sess, ecu, r["code"])
        if record:
            record("dtc_detail", {"ecu": ecu.code, "dtc": r["code"], "status": r.get("status"),
                                  "status_source": "19 02", "snapshot": snap, "extended": ext})
        if snap.get("records"):
            row["snapshots_raw" if snap.get("undecoded_from") else "snapshots_decoded"] += 1
        elif snap.get("undecoded_from"):
            row["snapshots_raw"] += 1
        for name in snap.get("candidate_fields") or []:
            if name not in cands:
                cands.append(name)
    row["candidate_fields"] = cands
    if not cands and snapshot_bindings.has_scaffold(ecu.code):
        row["candidate_fields"] = snapshot_bindings.unbound_names(ecu.code, vin)
    return row


def run(sess: Any, bus_key: str, modules: list[str], vin: str, *, only_set: bool = True,
        max_codes: int = 40, record: Optional[Callable[[str, dict[str, Any]], None]] = None
        ) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for code in modules:
        try:
            ecu = uds.resolve_module(code, vin or None)
        except BadCommand as e:
            rows.append({"module": code.upper(), "skipped": str(e)})
            continue
        if ecu.bus_key != bus_key:
            rows.append({"module": ecu.code, "skipped": f"{ecu.code} is on {ecu.bus_key}, not {bus_key}"})
            continue
        rows.append(round_module(sess, ecu, vin, only_set=only_set, max_codes=max_codes, record=record))
    sess.untarget()
    return {"bus": bus_key, "modules": rows, "warnings": warnings_for(bus_key)}
