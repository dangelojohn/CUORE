"""Repair verification from the module's own DTC status byte.

After a repair and a clear, the question is not "are the codes gone?" -- a
clear empties the list at once -- but "has the ECU re-run the test, and did
it pass?". The UDS status byte (ISO 14229-1 D.2) answers exactly that, per
code, with no Mode 01 readiness and no dealer tool:

    0x01 testFailed                       failing right now
    0x02 testFailedThisOperationCycle     failed on this drive
    0x04 pendingDTC                       failed on this or the last drive
    0x08 confirmedDTC                     matured (MIL-level)
    0x10 testNotCompletedSinceLastClear   has NOT run since the clear
    0x20 testFailedSinceLastClear         failed at least once since the clear
    0x40 testNotCompletedThisOperationCycle
    0x80 warningIndicatorRequested

``19 02 FF`` reports only codes whose status ANDs with the mask, so a code
at status 0x00 -- tested and passed, since the clear and this cycle -- is
simply absent. Absence from a reply the module did give is reported as
"likely passed" with that reason, never as "unknown" and never as proof.

Pure: no I/O. Stdlib only.
"""

from __future__ import annotations

from typing import Any, Iterable

STATES = {
    "failing": "the test is failing now or failed on this drive",
    "failed_since_clear": "the test has failed at least once since the last clear",
    "not_run_since_clear": "the test has not completed since the last clear; drive on",
    "passed_since_clear": "the test has run since the last clear and never failed",
    "likely_passed": ("not in the module's reply, which for a module that answered means "
                      "status 0x00: tested and passed. Confirm on the next read"),
}


def _base(code: str) -> str:
    return code.upper().split("-")[0].strip()


def classify_status(status: int) -> str:
    if status & 0x03:
        return "failing"
    if status & 0x20:
        return "failed_since_clear"
    if status & 0x10:
        return "not_run_since_clear"
    return "passed_since_clear"


def assess(codes: Iterable[str], records: list[dict[str, Any]],
           answered: bool) -> dict[str, Any]:
    """Per-code state from one ``19 02 FF`` reply, plus an overall verdict."""
    wanted = [_base(c) for c in codes if c.strip()]
    by_base: dict[str, dict[str, Any]] = {}
    for rec in records:
        by_base.setdefault(_base(rec["code"]), rec)
    rows = []
    for code in wanted:
        rec = by_base.get(code)
        if rec is None:
            state = "likely_passed" if answered else None
            rows.append({"code": code, "status": None, "state": state,
                         "meaning": STATES.get(state or "", "no answer from the module")})
            continue
        st = int(rec.get("status") or 0)
        state = classify_status(st)
        rows.append({"code": rec["code"], "status": f"0x{st:02X}", "state": state,
                     "meaning": STATES[state], "confirmed": bool(st & 0x08),
                     "pending": bool(st & 0x04), "mil_requested": bool(st & 0x80)})
    states = {r["state"] for r in rows}
    if not answered:
        verdict = "no answer from the module: nothing can be concluded"
    elif states & {"failing", "failed_since_clear"}:
        verdict = ("NOT REPAIRED: at least one test has failed since the clear. The fault is "
                   "still there, or the repair was the wrong part.")
    elif "not_run_since_clear" in states:
        verdict = ("NOT YET KNOWN: at least one test has not run since the clear. Keep "
                   "driving; EVAP tests need fuel between about 15 and 85 % and cold starts.")
    elif states <= {"passed_since_clear"}:
        verdict = ("TESTS PASSED since the clear. Strong repair evidence; for EVAP also "
                   "confirm the permanent code has gone (Mode 0A) before calling it closed.")
    else:
        verdict = ("PROBABLY PASSED: some codes were absent from the reply (status 0x00). "
                   "Read again after the next drive to confirm.")
    return {"codes": rows, "verdict": verdict}


def timeline(codes: Iterable[str], observations: list[dict[str, Any]],
             module: str) -> list[dict[str, Any]]:
    """Each earlier real read of ``module`` reduced to these codes' states."""
    wanted = [_base(c) for c in codes if c.strip()]
    out = []
    for obs in observations:
        data = obs.get("data") or {}
        if (data.get("ecu") or "").upper() != module.upper() or data.get("error"):
            continue
        if data.get("codes") is None:
            continue
        a = assess(wanted, data.get("dtcs") or [], answered=True)
        out.append({"at": obs.get("at"),
                    "states": {_base(r["code"]): r["state"] for r in a["codes"]}})
    return out


__all__ = ["STATES", "classify_status", "assess", "timeline"]
