"""SLVT replica -- a read-only re-creation of the wiTECH Small Leak
Verification Test described in bulletin 18-048-23.

What the bulletin actually contains (NHTSA MC-10236933-9999, two pages,
"Information Only"): the SLVT is mandatory during P0456 diagnosis; it must
run first to verify a leak is present and again after any repair, component
replacement or PCM software update; a road test cannot confirm the repair;
follow the Service Library procedure; and two wiTECH screenshots (Fig. 1
failed, Fig. 2 passed). It states NO fuel-level range, temperature, engine
state, soak time or numeric pass limit -- those live in the Service Library
procedure, which is not in this repo. Nothing here invents them: every
precondition carries a ``source`` saying where it comes from.

What wiTECH does that CUORE must not: it commands the ECM to run the leak
test through an unpublished UDS RoutineControl (0x31). ``cuore/live/safety.py``
is read-only by design and this module never sends it. The replica instead
waits for the ECM's own EVAP monitor and READS the outcome through three
existing read-only operations:

* ``ops.obd_readiness``  -- Mode 01 PID 01/41, the EVAP monitor state;
* ``ops.obd_mode06``     -- the EVAP on-board test results with limits;
* ``ops.module_dtcs("ECM")`` -- UDS 0x19 02 status bits of P0456/P0455/P0440.

:func:`evaluate` is a pure function of those reads; :func:`run` does the
reads and records one ``slvt_replica`` store observation plus one ``test``
action on the VIN's open job.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from ..data import load_tsb_catalogue
from ..live import mode06 as mode06_mod
from ..live import ops as live_ops
from ..live import store as live_store
from ..live.errors import LiveError
from . import cache, dossier_bridge, jobs_bridge, tsb_bridge
from .errors import BadRequest

BULLETIN = "18-048-23"
BULLETIN_ITEM_ID = "tsb-18-048-23"
BULLETIN_URL = "https://static.nhtsa.gov/odi/tsbs/2023/MC-10236933-9999.pdf"
OBSERVATION_KIND = "slvt_replica"

ECM = "ECM"
#: The three EVAP codes whose UDS status the replica reads.
DTC_CODES: tuple[str, ...] = ("P0456", "P0455", "P0440")
#: J1979 EVAP OBDMID 3C = the 0.020" (small) leak test; the graded one.
SMALL_LEAK_MIDS: tuple[str, ...] = ("3C",)
EVAP_MONITOR = "Evaporative system"
#: ISO 14229 DTC status bits used here.
BIT_FAILED_THIS_CYCLE = 0x02       # testFailedThisOperationCycle
BIT_NOT_COMPLETED_THIS_CYCLE = 0x40  # testNotCompletedThisOperationCycle

HEADER = ("This is a read-only replica of the wiTECH Small Leak Verification Test: wiTECH "
          "commands the ECM to run its leak test through an unpublished RoutineControl that "
          "CUORE never sends, so the replica waits for the ECM's own EVAP monitor run and "
          "reads the result instead.")

CRITERION = ("PASS = the EVAP monitor completed this cycle AND the Mode 06 small-leak test "
             "(OBDMID 3C) is within its limits AND testFailedThisOperationCycle is clear on "
             "P0456, P0455 and P0440. FAIL = any of those failed. INCONCLUSIVE = the monitor "
             "has not run (or a read is missing), so nothing can be graded.")

#: Bulletin text, quoted from the 18-048-23 PDF (revision markers removed).
BULLETIN_SEQUENCE: tuple[dict[str, str], ...] = (
    {"step": "Run the SLVT first, to verify a leak is present (mandatory during P0456 diagnosis).",
     "quote": "It is mandatory to run the wiTECH SLVT while performing the P0456 diagnostics. "
              "The wiTECH SLVT MUST be run first to verify a leak is present"},
    {"step": "Follow the Service Library diagnostic for P0456; it explains how to read the "
             "result (Fig. 1 failed, Fig. 2 passed) and choose the repair.",
     "quote": "When diagnosing the P0456, follow the service diagnostic procedure outlined in "
              "Service Library."},
    {"step": "Repair or replace the part.", "quote": ""},
    {"step": "Run the SLVT again after repairing or replacing any component, including PCM "
             "software updates for P0456.",
     "quote": "run after repairing or replacing any components to verify the fix. This "
              "includes PCM Software Updates to correct P0456 concerns."},
    {"step": "A road test does not confirm the repair.",
     "quote": "A road test will not confirm the repair, as P0456 is only set with multiple "
              "engine off and drive cycles, which cannot be reproduced during a dealer visit."},
)

REPLICA_SEQUENCE: tuple[str, ...] = (
    "Tick the preconditions below that are true.",
    "Let the ECM run its own EVAP monitor. The replica cannot start it: that is the "
    "RoutineControl wiTECH uses and CUORE does not send.",
    "Press Run: three read-only reads (readiness, Mode 06, ECM DTC status) are graded and "
    "recorded.",
)

#: The two wiTECH result screens printed in the bulletin (single readings from a
#: 2019 RAM 1500 5.7 V8 eTorque; examples, not limits).
BULLETIN_FIGURES: tuple[dict[str, Any], ...] = (
    {"fig": "Fig. 1", "title": "Failed Test Screen", "message": "Small Leak Test Failed.",
     "rows": (("Fuel Tank Pressure", "8", "Pa"),)},
    {"fig": "Fig. 2", "title": "Passed Test Screen", "message": "Test passed.",
     "rows": (("ESIM Switch Test", "Passed", ""), ("Purge Solenoid Test", "Passed", ""),
              ("Small Leak Test", "Passed", ""), ("Fuel Tank Pressure", "-275", "Pa"))},
)

FIGURE_NOTE = ("Example readings from a 2019 RAM 1500 5.7 V8 eTorque, as printed in the "
               "bulletin. They show what wiTECH displays; they are not limits for this car.")


# --- the preconditions -------------------------------------------------------


def preconditions() -> list[dict[str, Any]]:
    """The checklist, each item tagged with its source: ``bulletin`` (stated by
    18-048-23), ``cuore`` (CUORE's own EVAP research) or ``replica`` (needed
    because the replica reads instead of commands). The bulletin gives no
    fuel range, temperatures, engine state or soak; item ``conditions`` is
    where those are checked, against the Service Library procedure."""
    lo, hi = dossier_bridge._EVAP_FUEL_WINDOW
    return [
        {"id": "sequence", "source": "bulletin",
         "text": "This is the first SLVT (confirming the leak) or the re-run after a repair, "
                 "component replacement or PCM software update.",
         "quote": "MUST be run first to verify a leak is present and run after repairing or "
                  "replacing any components to verify the fix."},
        {"id": "no_road_test", "source": "bulletin",
         "text": "I am not treating a road test as confirmation of the repair.",
         "quote": "A road test will not confirm the repair."},
        {"id": "conditions", "source": "bulletin",
         "text": "Fuel level, temperatures, engine state and soak time are checked against the "
                 "Service Library P0456 procedure (the bulletin itself states none).",
         "quote": "follow the service diagnostic procedure outlined in Service Library."},
        {"id": "fuel_window", "source": "cuore",
         "text": f"Fuel level is inside the {lo:g}-{hi:g} % EVAP monitor window used elsewhere "
                 "in CUORE (not from the bulletin).", "quote": ""},
        {"id": "no_clear", "source": "replica",
         "text": "No DTC or readiness clear since the monitor ran: a clear resets the monitors "
                 "and status bits and every read would come back inconclusive.", "quote": ""},
        {"id": "monitor_run", "source": "replica",
         "text": "The ECM has run its own EVAP monitor since the repair. The replica waits for "
                 "it and never starts it.", "quote": ""},
    ]


# --- evaluation (pure) ---------------------------------------------------------


def _within(rec: dict[str, Any]) -> Optional[bool]:
    v, lo, hi = rec.get("value"), rec.get("min"), rec.get("max")
    if all(isinstance(x, (int, float)) for x in (v, lo, hi)):
        return lo <= v <= hi
    passed = rec.get("passed")
    return passed if isinstance(passed, bool) else None


def _dtc_rows(dtcs: Optional[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """One row per watched code, and whether the ECM's DTC list was readable."""
    d = dtcs or {}
    records = d.get("dtcs") or []
    readable = bool(records) and not d.get("error")
    by_code = {str(r.get("code") or "").upper(): r for r in records}
    rows: list[dict[str, Any]] = []
    for code in DTC_CODES:
        rec = by_code.get(code)
        if rec is None:
            rows.append({"code": code, "tracked": False, "status": None, "status_hex": None,
                         "failed_this_cycle": None, "not_completed_this_cycle": None,
                         "state": "not_tracked" if readable else "unread"})
            continue
        st = int(rec.get("status") or 0)
        rows.append({"code": code, "tracked": True, "status": st, "status_hex": f"{st:02X}",
                     "failed_this_cycle": bool(st & BIT_FAILED_THIS_CYCLE),
                     "not_completed_this_cycle": bool(st & BIT_NOT_COMPLETED_THIS_CYCLE),
                     "state": "failed" if st & BIT_FAILED_THIS_CYCLE else "clear"})
    return rows, readable


def _mode06_rows(m06: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    results = (m06 or {}).get("results") or {}
    rows: list[dict[str, Any]] = []
    for mid in mode06_mod.EVAP_MIDS:
        for hdr, recs in ((results.get(mid) or {}).get("by_ecu") or {}).items():
            for r in recs:
                rows.append({"mid": mid, "name": mode06_mod.obdmid_name(mid),
                             "tid": r.get("tid"), "ecu": hdr, "value": r.get("value"),
                             "min": r.get("min"), "max": r.get("max"), "unit": r.get("unit"),
                             "within": _within(r), "graded": mid in SMALL_LEAK_MIDS})
    return rows


def _monitor(readiness: Optional[dict[str, Any]], dtc_rows: list[dict[str, Any]]
             ) -> dict[str, Any]:
    """EVAP monitor state this cycle: Mode 01 PID 41 first; if the ECU does not
    list the EVAP monitor there, P0456's own testNotCompletedThisOperationCycle."""
    tdc = (readiness or {}).get("this_drive_cycle") or {}
    mon = next((m for m in tdc.get("monitors") or [] if m.get("monitor") == EVAP_MONITOR), None)
    if mon is not None:
        return {"state": "complete" if mon.get("complete") else "not_complete",
                "source": "readiness, this drive cycle (Mode 01 PID 41)"}
    p0456 = next(r for r in dtc_rows if r["code"] == "P0456")
    if p0456["tracked"]:
        return {"state": "not_complete" if p0456["not_completed_this_cycle"] else "complete",
                "source": "P0456 testNotCompletedThisOperationCycle (UDS), because PID 41 "
                          "did not list the EVAP monitor"}
    return {"state": "unknown", "source": "neither PID 41 nor the P0456 status bits were readable"}


def evaluate(vin: str, reads: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Grade one set of reads. ``reads`` holds ``readiness`` (``ops.obd_readiness``),
    ``mode06`` (``ops.obd_mode06``) and ``dtcs`` (``ops.module_dtcs("ECM")``) results;
    a missing or errored one simply cannot support a pass. Pure: no I/O."""
    reads = reads or {}
    dtc_rows, dtc_readable = _dtc_rows(reads.get("dtcs"))
    m06_rows = _mode06_rows(reads.get("mode06"))
    graded = [r for r in m06_rows if r["graded"]]
    if not graded:
        small_leak = "missing"
    elif any(r["within"] is False for r in graded):
        small_leak = "outside"
    elif any(r["within"] is None for r in graded):
        small_leak = "unknown"
    else:
        small_leak = "within"
    monitor = _monitor(reads.get("readiness"), dtc_rows)

    failed: list[str] = []
    for r in dtc_rows:
        if r["state"] == "failed":
            failed.append(f"{r['code']} testFailedThisOperationCycle is set (status {r['status_hex']})")
    if small_leak == "outside":
        for r in graded:
            if r["within"] is False:
                failed.append(f"Mode 06 {r['name']} (MID {r['mid']} TID {r['tid']}): value "
                              f"{r['value']} outside {r['min']}..{r['max']}")
    notes: list[str] = []
    unproven: list[str] = []
    if monitor["state"] != "complete":
        unproven.append("the EVAP monitor has not completed this cycle" if monitor["state"] ==
                        "not_complete" else "the EVAP monitor state could not be read")
    if small_leak == "missing":
        unproven.append("the ECM returned no Mode 06 small-leak result (MID 3C)")
    elif small_leak == "unknown":
        unproven.append("the Mode 06 small-leak result has no usable limits")
    if not dtc_readable:
        unproven.append("the ECM DTC status list could not be read")
    elif dtc_rows[0]["state"] == "not_tracked":
        unproven.append("the ECM does not track P0456")
    for r in dtc_rows[1:]:
        if r["state"] == "not_tracked":
            notes.append(f"{r['code']} is not tracked by this ECM, so it cannot count against the test")

    if failed:
        verdict = "fail"
        reasons = failed
        if monitor["state"] != "complete":
            notes.append("The EVAP monitor has not completed this cycle, so a Mode 06 value "
                         "may be left over from an earlier cycle; the failure is not cleared "
                         "until the monitor reruns.")
    elif unproven:
        verdict = "inconclusive"
        reasons = [s[0].upper() + s[1:] for s in unproven]
    else:
        verdict = "pass"
        reasons = ["EVAP monitor complete this cycle", "Mode 06 small-leak test within limits",
                   "testFailedThisOperationCycle clear on " + ", ".join(
                       r["code"] for r in dtc_rows if r["tracked"])]
    summary = {"pass": "PASS - the ECM's own monitor ran and found no small leak.",
               "fail": "FAIL - " + "; ".join(failed) if failed else "",
               "inconclusive": "INCONCLUSIVE - " + "; ".join(unproven) if unproven else ""}[verdict]
    return {"vin": vin, "bulletin": BULLETIN, "verdict": verdict, "summary": summary,
            "reasons": reasons, "notes": notes, "criterion": CRITERION, "monitor": monitor,
            "mode06": {"small_leak": small_leak, "rows": m06_rows,
                       "unsupported": sorted(
                           mid for mid, e in ((reads.get("mode06") or {}).get("results") or {}).items()
                           if mid in mode06_mod.EVAP_MIDS and not e.get("by_ecu"))},
            "dtcs": dtc_rows, "dtc_list_readable": dtc_readable}


# --- the live part -------------------------------------------------------------


def link_available() -> bool:
    """Is the adapter reachable for a read right now (same rule as /v/{vin}/verify)."""
    try:
        s = live_ops.status()
        strip = {"port": s.get("port"), "mes_state": (s.get("mes") or {}).get("state"),
                 "lock_holder": (s.get("lock") or {}).get("process"), "error": None}
    except Exception:  # noqa: BLE001 - a broken status must read as "no link"
        return False
    return dossier_bridge.live_available(strip)


def _check_vin(vin: str) -> str:
    vin = (vin or "").strip().upper()
    if not vin:
        raise BadRequest("a VIN is required")
    return vin


def _stream_since(vin: str, since: str) -> str:
    """The stream of the ECM DTC read this run just made (so the replica's own
    observation is only 'from the car' when its reads were); ``unknown`` if none."""
    try:
        for o in reversed(cache.recent_observations(20, vin=vin, kind="module_dtcs")):
            if (o.get("at") or "") >= since:
                return str(o.get("stream") or "unknown")
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def _read(fn: Any) -> dict[str, Any]:
    try:
        return fn()
    except LiveError as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def run(vin: str, confirmed: Iterable[str] = ()) -> dict[str, Any]:
    """Do the three read-only reads, grade them, and record the outcome.

    With no live link nothing is read or recorded: the result is inconclusive
    with ``ran`` False. ``confirmed`` are the precondition ids the tech ticked;
    they are stored with the result, they do not change the grade."""
    vin = _check_vin(vin)
    ids = [p["id"] for p in preconditions()]
    ticked = [i for i in ids if i in set(confirmed)]
    pre = {"confirmed": ticked, "missing": [i for i in ids if i not in ticked]}
    if not link_available():
        out = evaluate(vin, {})
        out.update(ran=False, preconditions=pre, job_id=None,
                   reason="No live link: the adapter is not reachable (or MES / another process "
                          "holds the port), so nothing was read or recorded.")
        return out
    started = datetime.now().isoformat(timespec="seconds")
    reads = {"readiness": _read(lambda: live_ops.obd_readiness()),
             "mode06": _read(lambda: live_ops.obd_mode06(list(mode06_mod.EVAP_MIDS))),
             "dtcs": _read(lambda: live_ops.module_dtcs(ECM, vin=vin))}
    if all(r.get("error") for r in reads.values()):  # the link was refused outright
        out = evaluate(vin, {})
        out.update(ran=False, preconditions=pre, job_id=None,
                   reason="No live link: every read failed (" + str(reads["dtcs"]["error"])
                   + "), so nothing was recorded.")
        return out
    out = evaluate(vin, reads)
    out.update(ran=True, at=started, preconditions=pre, job_id=None)
    live_store.record_observation(
        OBSERVATION_KIND, out, vin=vin, bus="can_c",
        cable=str((reads["dtcs"] or {}).get("cable") or ""), stream=_stream_since(vin, started))
    out["job_id"] = _record_on_job(vin, out)
    return out


def _record_on_job(vin: str, result: dict[str, Any]) -> Optional[str]:
    """One ``test`` action on the VIN's open job, if it has one. Never raises:
    the reads are already recorded and must not be lost to a job-store error."""
    try:
        job = jobs_bridge.jobs_mod.current(vin)
        if not job:
            return None
        obs = cache.recent_observations(1, vin=vin, kind=OBSERVATION_KIND)
        at = obs[-1]["at"] if obs else result.get("at", "")
        missing = result["preconditions"]["missing"]
        text = (f"SLVT replica (read-only, bulletin {BULLETIN}): {result['summary']}"
                + (f" Preconditions not ticked: {', '.join(missing)}." if missing else ""))
        jobs_bridge.add_action(job["id"], "test", text, ref={
            "kind": "observation", "id": f"{OBSERVATION_KIND}@{at}",
            "label": f"SLVT replica {result['verdict']}"})
        return job["id"]
    except Exception:  # noqa: BLE001
        return None


# --- the page's view -------------------------------------------------------------


def bulletin_links() -> dict[str, str]:
    """The NHTSA PDF url, from the TSB catalogue row when it carries one."""
    url = BULLETIN_URL
    try:
        row = next(i for i in load_tsb_catalogue()["items"] if i.get("number") == BULLETIN)
        url = next((l["url"] for l in row.get("links") or [] if l.get("url")), url)
    except Exception:  # noqa: BLE001
        pass
    return {"pdf": url, "row_anchor": tsb_bridge.row_anchor(BULLETIN_ITEM_ID)}


def last_result(vin: str) -> Optional[dict[str, Any]]:
    obs = cache.recent_observations(1, vin=vin, kind=OBSERVATION_KIND)
    if not obs:
        return None
    data = dict(obs[-1].get("data") or {})
    data["observed_at"] = obs[-1].get("at")
    data["from_car"] = live_store.is_from_car(obs[-1])
    return data


def build_view(vin: str) -> dict[str, Any]:
    vin = _check_vin(vin)
    return {"vin": vin, "bulletin": BULLETIN, "header": HEADER, "criterion": CRITERION,
            "preconditions": preconditions(), "bulletin_sequence": BULLETIN_SEQUENCE,
            "replica_sequence": REPLICA_SEQUENCE, "figures": BULLETIN_FIGURES,
            "figure_note": FIGURE_NOTE, "links": bulletin_links(),
            "link_available": link_available(), "last": last_result(vin)}


__all__ = ["BULLETIN", "HEADER", "CRITERION", "preconditions", "evaluate", "run",
           "build_view", "last_result", "link_available"]
