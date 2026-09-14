"""The evidence gate: a diagnosis is not "confirmed" until the proof exists.

Aviation's return-to-service discipline, applied to a one-person shop. The
caller states a diagnosis -- codes, the component condemned, the mechanism --
and cites their evidence. This module checks each criterion against the log
corpus where it can, takes attestation where it must (a smoke test leaves no
log), and returns CONFIRMED only when all four hold:

1. **Demonstrated** -- the fault is chronic, returned after a clear, or is
   standing now. A code seen once and since cleared is not a demonstrated
   fault, and parts ordered against it are a guess.
2. **Mechanism stated** -- a causal sentence, not a part name. "Canister
   blocked so ORVR back-pressure trips the nozzle" is a mechanism;
   "canister" is not.
3. **Measurement implicates the component** -- at least one cited
   measurement, verified in the corpus where the type allows (actuator
   outcome, freeze frame, recording event, live parameter). A DTC is
   explicitly NOT a measurement -- codes select the tree, they do not
   convict the part.
4. **Disconfirmation attempted** -- the test that would have exonerated the
   component was run, and is described with its result.

Anything short of that returns NOT CONFIRMED with the specific missing
test -- pulled from the fault tree when one covers the codes -- because
"you are guessing" is only useful when followed by "and here is the test
that stops the guessing".

The component is also checked against the fault tree's do-not list: a
condemned part that the platform evidence says is low-yield (purge solenoid
alone, gas cap, standalone vent valve) is warned about even when the four
criteria pass.
"""

from __future__ import annotations

import json
from typing import Any

from . import analysis, faulttree, fes as fes_mod, knowledge
from .catalog import CATALOG

#: Measurement types the corpus can verify, vs those it can only record as
#: operator attestation.
_VERIFIABLE = {"actuator", "freeze_frame", "parameter", "recording_event"}
_ATTESTED = {"manual"}

#: Component keywords -> the do-not warning they trip. Transcribed from the
#: EVAP tree's do_not list and EVAP_STELVIO.md field evidence.
_COMPONENT_WARNINGS = (
    (("purge solenoid", "purge valve"),
     "Platform evidence: purge solenoid alone is low-yield, and owners "
     "report replacing it with no resolution. Confirm it fails a KOEO "
     "actuator test before condemning it."),
    (("gas cap", "fuel cap", "filler cap"),
     "Low hit rate on this platform -- one documented owner spent ~$144 on "
     "a dealer cap with no change."),
    (("vent valve",),
     "Field consensus argues against the standalone vent valve on NA cars: "
     "the vent function is integrated in the canister module. One tech "
     "reported one vent valve in six years."),
    (("canister", "esim"),
     "Canister and ESIM are separate parts (TSB 9100469). Verify which one "
     "is at fault before ordering -- replacing the canister for an ESIM "
     "fault is a bulletin-warned error."),
)


def _parse_measurements(raw: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Accept a JSON array of measurement dicts; tolerate a bare string."""
    problems: list[str] = []
    if not raw or not raw.strip():
        return [], problems
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # A plain sentence is treated as one manual attestation.
        return [{"type": "manual", "description": raw.strip()}], problems
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        problems.append("measurements must be a JSON array of objects")
        return [], problems
    out = []
    for i, m in enumerate(data):
        if isinstance(m, str):
            out.append({"type": "manual", "description": m})
        elif isinstance(m, dict):
            out.append(m)
        else:
            problems.append(f"measurement #{i + 1} is not an object")
    return out, problems


def _verify_measurement(m: dict[str, Any], vin: str) -> dict[str, Any]:
    """Check one cited measurement against the corpus."""
    mtype = str(m.get("type", "")).strip().lower()
    result: dict[str, Any] = {"cited": m, "type": mtype}

    if mtype == "dtc":
        result.update(status="rejected",
                      note="a DTC is not a measurement -- codes select the "
                           "tree, they do not convict the part")
        return result

    if mtype in _ATTESTED:
        desc = str(m.get("description", "")).strip()
        if not desc:
            result.update(status="rejected",
                          note="manual measurement needs a description of "
                               "the test and its result")
        else:
            result.update(status="attested",
                          note="operator-attested; leaves no log to verify")
        return result

    if mtype == "actuator":
        wanted = str(m.get("operation", "")).strip().lower()
        if not wanted:
            result.update(status="rejected", note="actuator cite needs an "
                                                  "'operation' name")
            return result
        for entry in CATALOG.select(kind="fes", vin=vin):
            if entry.parse_error:
                continue
            try:
                log = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
            except Exception:
                continue
            for a in log.actuators:
                if wanted in a.operation.lower():
                    result.update(status="verified",
                                  found={"operation": a.operation,
                                         "outcome": a.to_dict().get("outcome"),
                                         "file": entry.name,
                                         "timestamp": entry.timestamp})
                    return result
        result.update(status="not_found",
                      note=f"no actuator run matching {wanted!r} in this "
                           "car's logs")
        return result

    if mtype == "freeze_frame":
        code = knowledge.base_code(str(m.get("code", "")))
        for entry in CATALOG.select(kind="fes", vin=vin):
            if entry.parse_error:
                continue
            try:
                log = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
            except Exception:
                continue
            for d in log.dtcs:
                if d.freeze_frame and knowledge.base_code(d.full) == code:
                    result.update(status="verified",
                                  found={"dtc": d.full, "file": entry.name,
                                         "timestamp": entry.timestamp})
                    return result
        result.update(status="not_found",
                      note=f"no freeze frame for {code} in this car's logs")
        return result

    if mtype == "parameter":
        pname = str(m.get("name", "")).strip().lower()
        fname = str(m.get("file", "")).strip()
        if not pname:
            result.update(status="rejected", note="parameter cite needs a "
                                                  "'name'")
            return result
        for entry in CATALOG.select(kind="fes", vin=vin):
            if fname and entry.name != fname:
                continue
            if entry.parse_error:
                continue
            try:
                log = fes_mod.load_fes(entry.path, timestamp=entry.timestamp)
            except Exception:
                continue
            hits = [n for n in log.param_names() if pname in n.lower()]
            if hits:
                series = log.series(hits[0])
                result.update(status="verified",
                              found={"parameter": hits[0],
                                     "file": entry.name,
                                     "stats": series.stats()})
                if series.stats().get("static"):
                    result["caution"] = (
                        "this parameter never changed across the session -- "
                        "consistent with a modelled default, weak as "
                        "implicating evidence")
                return result
        result.update(status="not_found",
                      note=f"parameter {pname!r} not found"
                           + (f" in {fname}" if fname else " in any session"))
        return result

    if mtype == "recording_event":
        from . import csvlog, paths
        fname = str(m.get("file", "")).strip()
        cond = str(m.get("condition", "")).strip()
        if not fname or not cond:
            result.update(status="rejected",
                          note="recording_event cite needs 'file' and "
                               "'condition'")
            return result
        try:
            rec = csvlog.load_csv(paths.resolve_csv(fname))
            x = rec.crossings(cond)
            if x["count"] > 0:
                result.update(status="verified",
                              found={"file": fname,
                                     "condition": x["condition"],
                                     "excursions": x["count"]})
            else:
                result.update(status="not_found",
                              note=f"{cond!r} never held in {fname}")
        except Exception as exc:
            result.update(status="not_found", note=str(exc))
        return result

    result.update(status="rejected",
                  note=f"unknown measurement type {mtype!r}; use one of: "
                       "actuator, freeze_frame, parameter, recording_event, "
                       "manual")
    return result


def _next_tree_test(codes: list[str]) -> str:
    trees = faulttree.trees_for(codes)
    if trees:
        s = trees[0].steps[0]
        return f"{trees[0].key} step {s.id}: {s.title} ({s.cost})"
    return "no fault tree covers these codes yet -- work from the TSB matches"


def assess(vin: str, codes: str, component: str, mechanism: str,
           measurements: str, disconfirming_test: str) -> dict[str, Any]:
    """Run the four-criterion gate and return the verdict."""
    code_list = [c for c in
                 __import__("re").split(r"[,\s;]+", codes) if c.strip()]
    if not code_list:
        return {"error": "at least one DTC is required to gate a diagnosis"}
    if not vin.strip():
        return {"error": "vin is required -- the gate verifies evidence "
                         "against one vehicle's corpus"}

    criteria: dict[str, dict[str, Any]] = {}

    # --- 1. demonstrated ----------------------------------------------------
    entries = CATALOG.select(vin=vin)
    history = analysis.dtc_history(entries) if entries else {}
    per_code: dict[str, str] = {}
    demonstrated = False
    for c in code_list:
        base = knowledge.base_code(c)
        rec = next((r for k, r in history.items()
                    if knowledge.base_code(k) == base), None)
        if rec is None:
            per_code[base] = "never seen in this car's logs"
        elif rec.returned_after_clear:
            per_code[base] = "returned after a clear -- live, reproducing"
            demonstrated = True
        elif rec.chronic:
            per_code[base] = (f"chronic: {rec.session_count} sessions, "
                              f"{rec.first_seen} to {rec.last_seen}")
            demonstrated = True
        elif "cleared" in rec.statuses and rec.session_count == 1:
            per_code[base] = ("seen once, then cleared -- not demonstrated; "
                              "the monitor has not confirmed a return")
        else:
            per_code[base] = f"seen in {rec.session_count} session(s)"
            demonstrated = demonstrated or rec.session_count >= 2
    criteria["demonstrated"] = {
        "met": demonstrated,
        "per_code": per_code,
        "next_test": None if demonstrated else (
            "drive cycles until the monitor runs (EVAP: fuel 15-85%, "
            "cold-start windows), then re-scan; or demonstrate the fault "
            "directly (smoke test) instead of waiting for the code"),
    }

    # --- 2. mechanism -------------------------------------------------------
    mech = mechanism.strip()
    mech_ok = len(mech.split()) >= 5
    criteria["mechanism"] = {
        "met": mech_ok,
        "stated": mech or "(none)",
        "next_test": None if mech_ok else (
            "state the causal chain in a sentence -- 'component X failed in "
            "way Y, producing symptom Z'. A part name alone is a guess "
            "wearing a diagnosis's clothes"),
    }

    # --- 3. measurement -----------------------------------------------------
    cited, problems = _parse_measurements(measurements)
    checked = [_verify_measurement(m, vin) for m in cited]
    verified = [c for c in checked if c["status"] == "verified"]
    attested = [c for c in checked if c["status"] == "attested"]
    meas_ok = bool(verified or attested)
    criteria["measurement"] = {
        "met": meas_ok,
        "checked": checked,
        "problems": problems,
        "note": (None if verified else
                 ("all evidence is operator-attested; nothing in the logs "
                  "corroborates it" if attested else None)),
        "next_test": None if meas_ok else _next_tree_test(code_list),
    }

    # --- 4. disconfirmation --------------------------------------------------
    disc = disconfirming_test.strip()
    disc_ok = len(disc.split()) >= 5
    criteria["disconfirmation"] = {
        "met": disc_ok,
        "stated": disc or "(none)",
        "next_test": None if disc_ok else (
            "run and describe the test that would have EXONERATED "
            f"{component or 'the component'} -- e.g. actuate it and show it "
            "responds, or isolate it and show the symptom persists"),
    }

    # --- component sanity ----------------------------------------------------
    warnings: list[str] = []
    comp_low = component.strip().lower()
    if comp_low:
        for keys, warning in _COMPONENT_WARNINGS:
            if any(k in comp_low for k in keys):
                warnings.append(warning)

    unmet = [k for k, v in criteria.items() if not v["met"]]
    confirmed = not unmet
    out: dict[str, Any] = {
        "verdict": "CONFIRMED" if confirmed else "NOT CONFIRMED",
        "codes": [knowledge.base_code(c) for c in code_list],
        "component": component or "(none stated)",
        "criteria": criteria,
    }
    if not confirmed:
        out["missing"] = unmet
        out["plain_answer"] = (
            "You are guessing. Missing: " + ", ".join(unmet) +
            ". The next_test field under each unmet criterion says what "
            "closes it.")
    else:
        out["plain_answer"] = (
            "All four criteria hold on cited, checked evidence. Proceed -- "
            "and verify the repair afterwards (readiness + permanent DTCs; "
            "small-leak claims need SLVT or Mode $06 per TSB 18-048-23).")
    if warnings:
        out["component_warnings"] = warnings
    return out
