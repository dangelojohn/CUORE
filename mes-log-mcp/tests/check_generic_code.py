"""Smoke checks for generalising EVAP-only/family-only hardcoding.

EVAP was this project's first diagnosed family, and it earned a hand-written
fault tree, a hand-curated dossier open-work card, and a pair of hand-written
job-page hypotheses. This car throws every family SAE defines, not just
EVAP -- these checks confirm the generic fallbacks added alongside it:

  1. ``mes.faulttree.tree_for`` builds a sourced generic tree for a code with
     no hand-written tree (misfire, P0301).
  2. ``tree_for`` still returns the hand-written EVAP tree for a code that
     one covers (P0455).
  3. ``cuore.services.dossier_bridge.build_view`` turns a synthetic dossier
     with P0301 history into an open-work card for the "misfire" family.
  4. ``cuore.services.jobs_bridge.suggested_hypotheses`` on that same view
     includes a misfire hypothesis.
  5. ``mes.code_feel.lookup`` returns a generic, honestly-UNKNOWN fallback
     for a code with no exact or family entry (C1234), instead of ``None``.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_generic_code.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mes-log-mcp
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for cuore

from mes import faulttree, code_feel  # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


print("=== 1. generic tree for a code with no hand-written tree (P0301) ===")
misfire_tree = faulttree.tree_for("P0301")
check("P0301 gets a generated tree, flagged generic",
      misfire_tree.generic is True, misfire_tree.key)
check(">=4 sourced steps",
      len(misfire_tree.steps) >= 4
      and all(s.source for s in misfire_tree.steps),
      str(len(misfire_tree.steps)))
check("includes a coil/plug swap step",
      any("swap" in s.test.lower() and ("coil" in s.test.lower()
                                        or "plug" in s.test.lower()
                                        or "coil" in s.title.lower())
          for s in misfire_tree.steps),
      str([s.title for s in misfire_tree.steps]))
check("names the ignition system",
      any("ignition" in f.lower() for f in misfire_tree.framing),
      str(misfire_tree.framing))

print("=== 2. a code with a hand-written tree still gets it (P0455) ===")
evap_tree = faulttree.tree_for("P0455")
check("P0455 still routes to the hand-written EVAP tree",
      evap_tree.key == "evap-leak" and evap_tree.generic is False,
      evap_tree.key)

print("=== 3/4. dossier/job generalisation on a synthetic P0301 fixture ===")
try:
    from cuore.services import dossier_bridge, jobs_bridge
    CUORE_OK = True
except Exception as exc:  # noqa: BLE001 -- cuore may not be on the path in every env
    CUORE_OK = False
    print(f"  (skipping -- cuore not importable: {exc})")

if CUORE_OK:
    VIN = "TESTVIN-GENERIC-0301"
    dossier = {
        "history": {
            "chronic": [{
                "dtc": "P0301-00",
                "descriptions": ["Cylinder 1 Misfire Detected"],
                "last_seen": "2026-10-01 10:00:00",
                "first_seen": "2026-09-01 10:00:00",
                "sessions": 3,
                "distance_span_km": 50,
            }],
            "returned_after_clear": [],
            "seen_once": [],
        },
        "tsb_matches": {"per_code": {}, "family_findings": [],
                        "bulletins_considered": 0},
        "current_picture": {},
        "blind_spots": [],
        "provenance_note": "",
    }
    view = dossier_bridge.build_view(VIN, dossier, None)
    misfire_card = next((c for c in view["open_work"] if c["family"] == "misfire"),
                        None)
    check("a P0301-history fixture yields an open-work card for 'misfire'",
          misfire_card is not None, str(view["open_work"]))
    if misfire_card:
        check("the misfire card names P0301 and carries sourced steps",
              "P0301" in misfire_card["codes"] and len(misfire_card["steps"]) > 0,
              str(misfire_card))

    hyps = jobs_bridge.suggested_hypotheses(VIN, view)
    misfire_hyp = next((h for h in hyps if h.get("system") == "misfire"), None)
    check("suggested_hypotheses includes a misfire hypothesis",
          misfire_hyp is not None, str(hyps))
    if misfire_hyp:
        check("the misfire hypothesis names P0301",
              "P0301" in misfire_hyp["text"], misfire_hyp["text"])

print("=== 5. code_feel generic SAE fallback for an untabulated code (C1234) ===")
c1234 = code_feel.lookup("C1234")
check("C1234 returns a generic fallback instead of None",
      c1234 is not None, str(c1234))
if c1234:
    check("marked UNKNOWN confidence, honestly",
          c1234.get("confidence") == code_feel.UNKNOWN, str(c1234))
    check("matched as the generic SAE fallback",
          c1234.get("matched") == "generic:sae", str(c1234))

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
