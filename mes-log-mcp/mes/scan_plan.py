"""The owner's ten-scan plan: knowledge, not state.

Owner's directive (2026-10-14): "about ten complete scans over the
diagnosis, one guided scan per visit" -- not fifty single reads, and not a
hand-typed checklist re-invented per car. This module is the one place that
states what each of those ten scans IS: its purpose, what has to be true
before it is worth running, what it proves, and which bypass cable (if any)
it needs. It holds no case state of its own -- no VIN, no dates, no scan
ids -- that half lives in ``cuore.services.scan_plan_bridge``, the only
thing allowed to decide whether a given car's evidence satisfies a given
row (same split :mod:`mes.mechanic_tests` keeps from the bench/tests pages
that render it).

Order matters: :data:`PLAN` is the sequence as the owner specified it, not
sorted by any other key. ``gates`` marks whether an incomplete row holds up
every row after it (the normal case -- this is a diagnosis, not a buffet)
or is explicitly conditional on something that may not apply (``repair``:
"if any" -- a car whose Test A came back clean needs no ESIM/wiring repair,
so it must not permanently stall the plan at row 3).

Nothing here talks to a car, a log, or the live link -- see this package's
own top-level docstring for why ``mes`` never imports anything from
``cuore``.
"""

from __future__ import annotations

from typing import Any

#: One row per scan the owner wants to see over a diagnosis. ``id`` is
#: stable (used as the row's step id everywhere it is referenced -- the
#: bridge, the template, a future checklist entry); ``cables`` is empty for
#: "no cable, CAN-C only".
PLAN: tuple[dict[str, Any], ...] = (
    {
        "id": "baseline", "n": 1,
        "title": "Baseline after the last clear",
        "purpose": "Confirm the car is clean under its own power, with every "
                   "monitor given a fair chance to run -- the baseline the rest "
                   "of this diagnosis is read against.",
        "preconditions": ["Fuel between 15% and 85% (the EVAP monitor's own window)",
                          "A full drive cycle completed since the last clear"],
        "proves": "Whether the car comes back clean on its own, before any test "
                  "or repair is credited with anything.",
        "cables": [], "gates": True,
    },
    {
        "id": "test_a_esim", "n": 2,
        "title": "After Test A + ESIM commanded test",
        "purpose": "Capture the car's state with both ESIM signal-path tests' "
                   "own results attached, before anything is touched.",
        "preconditions": ["wiTECH Test A (ESIM switch) run and recorded",
                          "ESIM commanded vent test run and recorded"],
        "proves": "Whether the ESIM signal path is implicated, with both tests' "
                  "pass/fail on file next to this scan.",
        "cables": [], "gates": True,
    },
    {
        "id": "repair", "n": 3,
        "title": "After the ESIM/wiring repair (if any)",
        "purpose": "Show what the car reports immediately after whatever repair "
                   "Test A or the commanded test pointed to.",
        "preconditions": ["A repair was made to the ESIM or its wiring, only if "
                          "Test A/the commanded test found one was needed"],
        "proves": "Whether the repair changed anything the car reports, before a "
                  "drive cycle has had a chance to.",
        "cables": [], "gates": False,
    },
    {
        "id": "witech_flash", "n": 4,
        "title": "After the wiTECH flash check/flash",
        "purpose": "Confirm the ECM's own calibration is current, or capture "
                   "what changed if a flash was applied.",
        "preconditions": ["wiTECH flash check run (and a flash applied if one "
                          "was due)"],
        "proves": "Whether a calibration update is part of the fix.",
        "cables": [], "gates": True,
    },
    {
        "id": "verify_drive", "n": 5,
        "title": "Verification drive-cycle read",
        "purpose": "The proof scan: EVAP monitor complete, Mode $06 passing "
                   "with margin, no code back.",
        "preconditions": ["A full drive cycle completed since the last repair "
                          "step above", "Fuel 15-85%"],
        "proves": "Whether the fix holds under the car's own monitor, not just "
                  "a visual check.",
        "cables": [], "gates": True,
    },
    {
        "id": "network", "n": 6,
        "title": "Network: after BCM supply/ground work",
        "purpose": "Confirm the network cascade (U-codes) does not return once "
                   "the BCM's own supply/ground work is done.",
        "preconditions": ["BCM supply (F82 fuse) and ground (XY201/G003A/B) work "
                          "completed"],
        "proves": "Whether the U-code cascade was one power/ground event, not a "
                  "chronic bus fault.",
        "cables": [], "gates": True,
    },
    {
        "id": "body_a5", "n": 7,
        "title": "With blue A5 (body/comfort full picture)",
        "purpose": "Sweep the IHS/body bus for the full body/comfort picture "
                   "this car has never had with the OEM tool.",
        "preconditions": ["Blue A5 cable fitted and declared"],
        "proves": "Whether any body/comfort module is carrying a code this "
                  "car's history has never surfaced.",
        "cables": ["blue A5"], "gates": True,
    },
    {
        "id": "chassis_a6", "n": 8,
        "title": "With grey A6 (chassis/ADAS)",
        "purpose": "Sweep the CH bus for the chassis/ADAS modules this car has "
                   "never had scanned either.",
        "preconditions": ["Grey A6 cable fitted and declared"],
        "proves": "Whether a chassis/ADAS module (brakes, steering, cameras/"
                  "radar) is carrying anything.",
        "cables": ["grey A6"], "gates": True,
    },
    {
        "id": "post_repair", "n": 9,
        "title": "Post-repair confirmation, 1-2 weeks later",
        "purpose": "A cold read a week or two after release: the fix holding "
                  "under normal driving, not just the shop's own drive cycle.",
        "preconditions": ["1-2 weeks of normal driving since release",
                          "No new complaint in the meantime"],
        "proves": "Whether the fix holds past the shop floor.",
        "cables": [], "gates": True,
    },
    {
        "id": "release", "n": 10,
        "title": "Release scan for the case record",
        "purpose": "The record scan: what the car looked like the day it went "
                  "back to the owner.",
        "preconditions": ["Every open item above resolved or explicitly "
                          "accepted"],
        "proves": "Nothing new -- it is the case record, not a test.",
        "cables": [], "gates": True,
    },
)

#: The owner's own number -- see ``cuore.live.scanlog.PLAN_TOTAL``, which
#: this must always equal (both say "ten scans"; this module's own tests
#: check they stay in lockstep rather than silently drift apart).
TOTAL = len(PLAN)


def get(step_id: str) -> dict[str, Any] | None:
    return next((dict(s) for s in PLAN if s["id"] == step_id), None)


__all__ = ["PLAN", "TOTAL", "get"]
