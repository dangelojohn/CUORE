"""Per-VIN capability facts and known limitations: what this car cannot or
should not be asked, measured once so the next session does not re-ask.

Seed facts ship in code (measured, cited); more can be recorded at runtime as
``kind="capability"`` observations. A later record for the same key wins.
"""

from __future__ import annotations

from typing import Any

from . import store

KIND = "capability"

#: 2018 Alfa Stelvio 2.0T GME-T4, ECM 18DAF110, measured 2026-10-14/15.
_STELVIO = "ZASFAKPN5J7B88115"
SEED_FACTS: dict[str, dict[str, dict[str, Any]]] = {
    _STELVIO: {
        "engine_hours_available": {
            "value": False, "status": "measured",
            "evidence": "PID 7F not supported: 0x60-group bitmap advertises only 68, 6B, "
                        "70, 72; PIDs 4D/4E absent from the 0x40 bitmap; PID 1F is run "
                        "time since start only (74 s at the scan). Real engine hours are "
                        "not available over OBD on this car."},
        "pid_6b_egr_temp": {
            "value": "junk", "status": "measured",
            "evidence": "PID 6B returned 2699.2 C at warm idle; do not trust or plot."},
        "ibs_dids_to_verify": {
            "value": ["BCM 1004", "BCM 1005", "ECM 19BD"], "status": "unverified",
            "evidence": "BCM 1004 answered 0x90 = 14.4 V (A/10, formula unverified) against "
                        "adapter 14.3-14.5 V and PID 42 14.25 V. BCM 1005 (IBS composite) and "
                        "ECM 19BD (IBS SoC %) are catalogued, not yet read."},
        "egr_external_valve": {
            "value": "unverified", "status": "unverified",
            "evidence": "No source found. PID 2C/2D read 0.0 % at warm idle; Mode 06 "
                        "OBDMID 0x31 TIDs A0/A1 placeholder-like, scaling unknown. MultiAir "
                        "engines usually use internal EGR via valve timing."},
    },
}


def record_capability(vin: str, key: str, value: Any, *, evidence: str = "",
                      status: str = "measured", stream: str = "") -> None:
    store.record_observation(KIND, {"key": key, "value": value, "status": status,
                                    "evidence": evidence}, vin=vin, stream=stream)


def capabilities(vin: str) -> dict[str, dict[str, Any]]:
    """``{key: {value, status, evidence, source}}``: seed facts, overridden by recorded ones."""
    out = {k: {**v, "source": "builtin"} for k, v in SEED_FACTS.get(vin, {}).items()}
    for obs in store.recent_observations(n=100000, vin=vin, kind=KIND):
        d = obs.get("data") or {}
        if d.get("key"):
            out[d["key"]] = {"value": d.get("value"), "status": d.get("status", ""),
                             "evidence": d.get("evidence", ""), "source": "recorded",
                             "at": obs.get("at")}
    return out


def capability_rows(vin: str) -> list[dict[str, Any]]:
    """Flat rows for a page: key, value text, status, evidence."""
    return [{"key": k, "value": ", ".join(map(str, v["value"])) if isinstance(v["value"], list)
             else str(v["value"]), "status": v.get("status", ""), "evidence": v.get("evidence", "")}
            for k, v in sorted(capabilities(vin).items())]


__all__ = ["KIND", "SEED_FACTS", "record_capability", "capabilities", "capability_rows"]
