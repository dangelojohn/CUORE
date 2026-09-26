"""Checks for the ``detail=False`` summarised UDS DTC results (2026-09-26).

A UDS 0x19 02 reply lists every code a module TRACKS, not every code that is
failing -- the ECM alone tracks 278 and reports all of them, which is why
``module_dtcs``/``scan_modules`` gained a ``detail`` flag and
:func:`cuore.live.ops._compact_dtc_result`. This exercises that helper
directly on hand-built records, and confirms the contract that matters most:
the FULL result is what gets recorded as the observation (the evidence gate
needs the full status bytes) and only the RETURNED value is ever summarised.

Same posture as the other files in this folder: plain script, ``check()``,
exit 1 on failure. ``CUORE_STATE_DIR`` is set to a fresh temp directory
BEFORE cuore is imported, so this never touches the bench's real
observations log.

Run:
    .venv/Scripts/python.exe cuore/tests/check_detail.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-detail-")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import ops, store  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want) -> None:
    check(label, got == want, f"got {got!r} want {want!r}")


# ===========================================================================
# a minimal stand-in for a live.transport.Session -- _observe only reads
# sess.bus.key, sess.link.cable, sess.link.vin and sess.stream.describe, so a
# real adapter session is not needed to exercise it.
# ===========================================================================

class _FakeBus:
    key = "can_c"


class _FakeLink:
    cable = "none"
    vin = ""


class _FakeStream:
    describe = "test-fixture"


class FakeSession:
    def __init__(self) -> None:
        self.bus = _FakeBus()
        self.link = _FakeLink()
        self.stream = _FakeStream()
        self.auto_verified = None


# ===========================================================================
# 1. _compact_dtc_result on hand-built records
# ===========================================================================
#
# status bits (ISO 14229-1 DTC status byte), per cuore.live.coverage:
#   0x4D = testFailed | pendingDTC | confirmedDTC | testFailedSinceLastClear
#          -> ACTIVE (0x4D & 0x0D = 0x0D)
#   0x40 = testNotCompletedThisOperationCycle only -> neither active nor
#          history; counted only in "tracked"
#   0x20 = testFailedSinceLastClear only -> HISTORY, not active
#   0x10 = testNotCompletedSinceLastClear -> counted in not_run_since_clear
#
# (0x28 -- confirmedDTC(0x08) + testFailedSinceLastClear(0x20) -- also sets
# the confirmedDTC bit that is part of ACTIVE_MASK, so classify_records calls
# it active, not history; 0x20 alone is the unambiguous "history only" case.)

RECORDS = [
    {"code": "P0455-00", "status": 0x4D},   # active
    {"code": "P0562-00", "status": 0x40},   # tracked only
    {"code": "P0300-00", "status": 0x20},   # history
    {"code": "P0128-00", "status": 0x10},   # not run since clear (tracked only)
]

full_module = {
    "ecu": "ECM", "bus": "can_c", "mask": "FF", "error": None, "nrc": None,
    "dtcs": RECORDS, "codes": [r["code"] for r in RECORDS], "availability_mask": 4,
}

compact = ops._compact_dtc_result(full_module)
check_eq("compact keeps active codes only", compact["active"], ["P0455-00"])
check_eq("compact keeps history codes", compact["history"], ["P0300-00"])
check_eq("compact counts every tracked record", compact["tracked"], 4)
check_eq("compact counts not-run-since-clear", compact["not_run_since_clear"], 1)
check_eq("active_records holds the full record for the active code only",
         compact["active_records"], [{"code": "P0455-00", "status": 0x4D}])
check("compact keeps ecu/bus/mask/error/nrc", all(k in compact for k in
      ("ecu", "bus", "mask", "error", "nrc")), str(compact))
check("compact drops the full dtcs list", "dtcs" not in compact, str(compact))
check("compact drops codes and availability_mask", "codes" not in compact and
      "availability_mask" not in compact, str(compact))
check("compact does not invent warning/note when absent",
      "warning" not in compact and "note" not in compact, str(compact))

# a module with a warning and no faults at all
empty_module = {"ecu": "TCM", "bus": "can_c", "mask": "FF", "error": None,
                "nrc": None, "warning": "no answer from the module", "dtcs": []}
compact_empty = ops._compact_dtc_result(empty_module)
check_eq("a clean module reports no active codes", compact_empty["active"], [])
check_eq("a clean module reports no history codes", compact_empty["history"], [])
check_eq("a clean module has zero tracked", compact_empty["tracked"], 0)
check("warning is kept when present", compact_empty.get("warning") ==
      "no answer from the module")

# a skipped module (scan_modules: no confirmed address) is untouched -- it
# never had a "dtcs" key to summarise
skipped = {"ecu": "ESM", "skipped": "no confirmed address"}
check_eq("a skipped module passes through unchanged",
         ops._compact_dtc_result(skipped), skipped)


# ===========================================================================
# 2. the observation recorded is the FULL result; only the return is summarised
# ===========================================================================

store.observations_path().unlink(missing_ok=True)
sess = FakeSession()
recorded = ops._observe(sess, "module_dtcs", dict(full_module), "ZASFAKPN5J7B88115")
returned_compact = ops._compact_dtc_result(recorded)

obs = store.recent_observations(10, vin="ZASFAKPN5J7B88115", kind="module_dtcs")
check_eq("exactly one observation was recorded", len(obs), 1)
stored_data = obs[0]["data"] if obs else {}
check_eq("the stored observation keeps the full dtcs list",
         stored_data.get("dtcs"), RECORDS)
check_eq("the stored observation keeps every code, tracked or not",
         len(stored_data.get("dtcs") or []), 4)
check("the stored observation carries no compacted 'active' summary field",
      "active" not in stored_data, str(stored_data))
check_eq("the value returned for a detail=False caller is the compact form",
         returned_compact["active"], ["P0455-00"])
check("the compact return has no full dtcs list", "dtcs" not in returned_compact,
      str(returned_compact))


print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
