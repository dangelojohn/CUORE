"""Checks for the shared systems vocabulary (Goal A) and per-system
VERIFIED_CLEAN (Goal B) work described in the systems-vocabulary pass:

* ``mes.systems.normalize_system`` resolves every one of the 25
  ``SYSTEMS`` keys, every system label, and a batch of free-text/alias
  spellings (electrical-layout tags, OBD-II monitor names, dossier family
  keys) to the right key -- and returns ``None`` for junk.
* ``mes.jobs.add_hypothesis``/the fold in :func:`mes.jobs.get` store a
  normalized ``system`` key plus the original ``system_text``, and an
  old-shape record (written before ``system_text`` existed) still
  normalizes correctly when read -- without rewriting the JSONL log.
* Every ``mes.mechanic_tests`` test's ``systems`` entries are real
  ``SYSTEMS`` keys (already enforced at import time by ``_t()``; checked
  here too so a future entry that broke that invariant would be caught by
  this suite specifically, not just by the catalogue failing to import).
* ``cuore.services.systems_map_bridge.system_states`` only reaches
  VERIFIED_CLEAN for a system via that system's *own* OBD monitor, read
  from the car, after the clear -- never by borrowing the whole-car
  verdict, and never from a non-serial (demo/replay) readiness source.

Same posture as ``cuore/tests/check_dossier_view.py``/``check_jobs_rules.py``:
``CUORE_STATE_DIR`` is pointed at a throwaway directory BEFORE cuore/mes is
imported. The VERIFIED_CLEAN checks use a synthetic fixture (mocking
``systems_map_bridge``'s own ``_correlate``/``_dossier_view`` -- the two
helpers that read this VIN's real MES-log corpus) rather than the real
Stelvio corpus, because that car's own EVAP codes are *returned* (ACTIVE),
not merely cleared-unverified -- the real fixture every other dossier test
in this suite uses, but not the per-code state this check needs to isolate.
The readiness reads themselves are real: appended straight to
``cuore.live.store``'s observations log with explicit, strictly increasing
timestamps (never ``record_observation``'s own now() stamp, which could
collide at one-second resolution and make "the newest reading" ambiguous
between two calls issued in the same test).

Run:
    .venv/Scripts/python.exe cuore/tests/check_system_vocab.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-system-vocab-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cuore.app import create_app  # noqa: E402 -- side effect: puts `mes` on sys.path
from cuore.services import systems_map_bridge  # noqa: E402
from cuore.live import store as live_store  # noqa: E402

from mes import jobs as jobs_mod  # noqa: E402
from mes import mechanic_tests  # noqa: E402
from mes import systems as systems_mod  # noqa: E402

create_app()  # unused beyond its bootstrap side effect, same as other checks

VIN = "FIXTUREVIN00000001"  # no real corpus -- this file's own fixtures stand in

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


# === normalize_system: 25 keys, 25 labels, aliases, junk ====================

print("=== mes.systems.normalize_system ===")

bad_keys = [k for k in systems_mod.SYSTEMS if systems_mod.normalize_system(k) != k]
check("every one of the 25 SYSTEMS keys normalizes to itself",
     len(systems_mod.SYSTEMS) == 25 and not bad_keys, str(bad_keys))

bad_labels = [k for k, v in systems_mod.SYSTEMS.items()
             if systems_mod.normalize_system(v["label"]) != k]
check("every system's own label normalizes to its key", not bad_labels, str(bad_labels))

# >= 12 alias/free-text spellings, drawn from the electrical-layout tags,
# OBD-II monitor names and dossier-family keys this module's ALIASES table
# actually carries.
ALIAS_CASES = [
    ("Evap system", "evap"),
    ("evap system", "evap"),
    ("Evaporative emissions", "evap"),
    ("fuel_trim", "fuel"),
    ("fuel trim", "fuel"),
    ("chassis", "brakes_abs"),
    ("adas", "adas_sensors"),
    ("body", "body_comfort"),
    ("charging", "starting_charging"),
    ("cranking", "starting_charging"),
    ("tpms", "wheels_tpms"),
    ("network", "network"),
    ("catalyst", "exhaust_emissions"),
    ("oxygen sensor", "exhaust_emissions"),
    ("boost pressure", "air_intake_boost"),
    ("powertrain_other", "engine_management"),
]
bad_aliases = [(t, systems_mod.normalize_system(t), want) for t, want in ALIAS_CASES
              if systems_mod.normalize_system(t) != want]
check(f"at least 12 aliases resolve to the right key ({len(ALIAS_CASES)} tested)",
     len(ALIAS_CASES) >= 12 and not bad_aliases, str(bad_aliases))

check("junk text returns None",
     systems_mod.normalize_system("not a real system at all, just junk") is None, "")
check("blank/whitespace/None all return None",
     systems_mod.normalize_system("") is None
     and systems_mod.normalize_system("   ") is None
     and systems_mod.normalize_system(None) is None, "")


# === hypothesis system normalization + migration =============================

print("=== mes.jobs hypothesis system normalization ===")

job = jobs_mod.open(vin=VIN, technician="tester", complaint="EVAP check")
hyp = jobs_mod.add_hypothesis(job["id"], "ESIM signal path", system="Evap system")
check("add_hypothesis('Evap system') stores system='evap'", hyp.get("system") == "evap",
     str(hyp))
check("the original free text is kept in system_text",
     hyp.get("system_text") == "Evap system", str(hyp))

edited = jobs_mod.edit_hypothesis(job["id"], hyp["id"], system="EVAP (evaporative emissions)")
check("edit_hypothesis normalizes the new system text too",
     edited.get("system") == "evap" and edited.get("system_text") == "EVAP (evaporative emissions)",
     str(edited))

# Migration: a record written before system_text existed (old shape -- raw
# text sat in "system" itself) still normalizes correctly on read, and the
# log is never rewritten to fix it up -- _append() is the only writer, and
# this call bypasses add_hypothesis entirely to simulate an already-on-disk
# legacy record.
legacy_id = uuid.uuid4().hex[:8]
jobs_mod._append({  # noqa: SLF001 -- deliberately simulating a pre-migration record
    "op": "hypothesis_add", "job_id": job["id"], "id": legacy_id,
    "at": "2020-01-01T00:00:00", "text": "legacy free-text hypothesis",
    "system": "EVAP", "next_test": "", "codes": [], "likelihood": None, "by": None,
})
legacy_job = jobs_mod.get(job["id"])
legacy_hyp = next(h for h in legacy_job["hypotheses"] if h["id"] == legacy_id)
check("an old-shape record (no system_text) normalizes its free-text system on read",
     legacy_hyp.get("system") == "evap", str(legacy_hyp))
check("...and still carries its original raw text as system_text",
     legacy_hyp.get("system_text") == "EVAP", str(legacy_hyp))


# === mechanic_tests systems vocabulary =======================================

print("=== mes.mechanic_tests systems vocabulary ===")

bad_test_systems = [(t["id"], s) for t in mechanic_tests.all_tests() for s in t["systems"]
                    if s not in systems_mod.SYSTEMS]
check("every mechanic_tests test's systems entries are real SYSTEMS keys",
     not bad_test_systems, str(bad_test_systems[:5]))


# === systems_map_bridge.system_states: per-system VERIFIED_CLEAN ============

print("=== systems_map_bridge.system_states: per-system VERIFIED_CLEAN ===")

# A synthetic by_system/dossier-codes fixture standing in for the real
# corpus: one EVAP code, cleared but not yet re-verified. The whole-car
# verdict is deliberately set to VERIFIED_CLEAN here -- system_states must
# never shortcut through it (its own docstring: "never derive VERIFIED_CLEAN
# from the whole-car verdict").
FIXTURE_VIEW = {
    "codes": [{"code": "P0455", "status": "CLEARED_UNVERIFIED"}],
    "verdict": {"state": "VERIFIED_CLEAN"},
}
FIXTURE_CORR = {"by_system": [{"system": "evap", "codes": ["P0455-00"]}]}


def _append_observation(stream: str, at: str, data: dict) -> None:
    """Append one readiness observation straight to the observations log,
    with an explicit timestamp -- not ``live_store.record_observation``'s
    own ``now()`` stamp, which could tie at one-second resolution between
    two calls in the same test and leave "the newest reading" ambiguous."""
    entry = {"at": at, "kind": "readiness", "vin": VIN, "bus": "", "cable": "",
             "stream": stream, "data": data}
    with live_store.observations_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _evap_monitor(complete: bool) -> dict:
    return {"since_clear": {"monitors": [{"monitor": "Evaporative system",
                                          "supported": True, "complete": complete}],
                            "all_complete": complete}}


def _fixture_states() -> dict:
    with patch.object(systems_map_bridge, "_correlate", return_value=FIXTURE_CORR), \
         patch.object(systems_map_bridge, "_dossier_view", return_value=FIXTURE_VIEW):
        return systems_map_bridge.system_states(VIN)


before = _fixture_states()
check("no readiness read yet -> CLEARED_UNVERIFIED (not VERIFIED_CLEAN, "
     "despite the fixture's own whole-car verdict saying VERIFIED_CLEAN)",
     before["evap"]["state"] == "CLEARED_UNVERIFIED", str(before["evap"]))

_append_observation("demo", "2026-10-08T10:00:01", _evap_monitor(True))
demo_states = _fixture_states()
check("a demo-source readiness (stream='demo') claiming EVAP complete never "
     "gives VERIFIED_CLEAN", demo_states["evap"]["state"] != "VERIFIED_CLEAN",
     str(demo_states["evap"]))
check("is_from_car rejects that demo stream",
     not live_store.is_from_car({"stream": "demo"}), "")

_append_observation("serial COM3@115200", "2026-10-08T10:00:02", _evap_monitor(False))
incomplete_states = _fixture_states()
check("EVAP monitor incomplete from the car, codes cleared -> CLEARED_UNVERIFIED",
     incomplete_states["evap"]["state"] == "CLEARED_UNVERIFIED", str(incomplete_states["evap"]))

_append_observation("serial COM3@115200", "2026-10-08T10:00:03", _evap_monitor(True))
complete_states = _fixture_states()
check("EVAP monitor complete from the car, no code back since -> VERIFIED_CLEAN",
     complete_states["evap"]["state"] == "VERIFIED_CLEAN", str(complete_states["evap"]))
check("is_from_car accepts that serial stream",
     live_store.is_from_car({"stream": "serial COM3@115200"}), "")

# A system with no monitor at all (mes.systems.monitors_for_system returns
# []) must never reach VERIFIED_CLEAN, no matter what the readiness read
# says -- there is no monitor whose completeness could ever back it up.
no_monitor_keys = [k for k in systems_mod.SYSTEMS if not systems_mod.monitors_for_system(k)]
check("at least one system has no OBD monitor at all (a real case to guard)",
     bool(no_monitor_keys), "")
if no_monitor_keys:
    nm_key = no_monitor_keys[0]
    NM_VIEW = {"codes": [{"code": "B1176", "status": "CLEARED_UNVERIFIED"}],
              "verdict": {"state": "VERIFIED_CLEAN"}}
    NM_CORR = {"by_system": [{"system": nm_key, "codes": ["B1176-00"]}]}
    with patch.object(systems_map_bridge, "_correlate", return_value=NM_CORR), \
         patch.object(systems_map_bridge, "_dossier_view", return_value=NM_VIEW):
        nm_states = systems_map_bridge.system_states(VIN)
    check(f"a no-monitor system ({nm_key}) stays CLEARED_UNVERIFIED even with a "
         "from-car EVAP-complete reading on file and a VERIFIED_CLEAN whole-car verdict",
         nm_states[nm_key]["state"] == "CLEARED_UNVERIFIED", str(nm_states[nm_key]))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
