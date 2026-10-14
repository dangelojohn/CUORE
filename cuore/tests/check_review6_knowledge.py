"""Checks for EXTERNAL_REVIEW_6_2026-10-14.md's KNOWLEDGE items (1-5):

  1. Flooded/saturated-canister hypothesis: TSB 9100471 is on file
     (docs/reference/TSB_CATALOGUE.md, mes.knowledge.BULLETINS), so the
     EVAP fault tree for P0455/P0440 carries a sourced
     "EVAP: flooded canister / vent-path restriction" hypothesis with real
     mechanic_tests ids and real mes.parts ids, never invented content.
  2. The Body/comfort open-work group splits: a mechanical B-code
     (B1176 -- window regulator) gets its own card, separate from a
     communication-type B/U code (B1040-87).
  3. C104B (ABS: leaks in hydraulic group) gets the brake-fluid-level /
     hydraulic-leak inspection as the FIRST step in its generated tree,
     ahead of any electrical/module step, and its open-work card is
     flagged ``safety_relevant``.
  4. Open-work demotion: a seen-once code older than 180 days with no
     later occurrence is left out of open work but never deleted --
     still in the dossier's own history, now also listed in
     ``demoted_open_work`` with the wording "seen once on <date>, not
     since" (P0098/P00F5/P105E/P1189, Sept 2025).
  5. (Documentation only, checked by inspection above: every rule here
     carries a 2026-10-14 docstring/comment naming this review.)

Same posture as ``check_review6_logic.py``: ``CUORE_STATE_DIR`` is a
throwaway directory, pointed there before ``cuore``/``mes`` are imported.
Items 2-4 use small synthetic dossiers built in this file -- they are
display-grouping logic over a ``dossier['history']``/``tsb_matches`` shape,
not from-car facts, so no real log corpus is needed for them. Item 1 reads
the real, hand-written ``mes.faulttree.EVAP_LEAK`` tree and the real
``mes.mechanic_tests``/``mes.parts`` catalogues directly -- also no log
corpus needed. A ``TestClient`` boot of the real app is included as a
baseline sanity check that nothing here broke app startup.

No subagents, no COM3. At most 10 suites per the house rule; this is one.

Run:
    .venv/Scripts/python.exe cuore/tests/check_review6_knowledge.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-review6-knowledge-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import dossier_bridge  # noqa: E402

from mes import faulttree, mechanic_tests, parts, symptoms as symptoms_mod  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


# ===========================================================================
# Baseline: the app still boots with these changes on the import path.
# ===========================================================================

client = TestClient(create_app())
root_resp = client.get("/")
check("0. the app boots and answers its root route",
     root_resp.status_code in (200, 307, 308), str(root_resp.status_code))


# ===========================================================================
# 1. Flooded-canister hypothesis on the EVAP tree for P0455/P0440
# ===========================================================================

tree_455 = faulttree.tree_for("P0455")
tree_440 = faulttree.tree_for("P0440")
check("1a. P0455 and P0440 resolve to the same hand-written EVAP tree",
     tree_455.key == "evap-leak" and tree_440.key == "evap-leak" and not tree_455.generic,
     f"{tree_455.key} / {tree_440.key}")

hyp = next((h for h in tree_455.hypotheses if h.key == "evap-flooded-canister"), None)
check("1b. a 'flooded canister / vent-path restriction' hypothesis is present",
     hyp is not None, str([h.key for h in tree_455.hypotheses]))

if hyp is not None:
    check("1c. its text names flooded canister / vent-path restriction",
         hyp.text == "EVAP: flooded canister / vent-path restriction", hyp.text)
    check("1d. it cites TSB 9100471 (on file, never UNKNOWN -- the TSB exists)",
         "9100471" in hyp.source, hyp.source)

    # -- tests: real mechanic_tests ids, resolvable, EVAP-related ---------
    resolved_tests = [mechanic_tests.test(t) for t in hyp.tests]
    check("1e. every cited test id resolves in mes.mechanic_tests",
         all(t is not None for t in resolved_tests), str(hyp.tests))
    check("1f. the tests cover the liquid-fuel-in-canister check",
         any("canister" in t["id"] and "liquid_fuel" in t["id"]
             for t in resolved_tests if t), str(hyp.tests))
    check("1g. the tests cover the tank-to-canister vapour-line kink check",
         any("vapour_line" in t["id"] or "kink" in t["id"]
             for t in resolved_tests if t), str(hyp.tests))
    check("1h. both tests are related to P0455/P0440",
         all(t and ("P0455" in t["related_codes"] or "P0440" in t["related_codes"])
             for t in resolved_tests), str(hyp.tests))

    # -- parts: real mes.parts ids, numbers only from that table ----------
    resolved_parts = {p: parts.get(p) for p in hyp.parts}
    check("1i. every cited part id resolves in mes.parts",
         all(v is not None for v in resolved_parts.values()), str(hyp.parts))
    check("1j. the parts are the canister and the ESIM",
         set(hyp.parts) == {"evap_canister", "esim"}, str(hyp.parts))
    oems = {k: [o.get("number") for o in (v.get("oem") or [])]
           for k, v in resolved_parts.items() if v}
    check("1k. canister/ESIM OEM numbers come from mes.parts, not invented here",
         all(oems.get(k) for k in ("evap_canister", "esim")), str(oems))

    # -- nozzle-click-off / hard-to-fill symptom link, from the symptoms store
    check("1l. the symptoms store defines the hard-to-refuel tag this "
         "hypothesis's note points at",
         "hard_to_refuel" in symptoms_mod.SYMPTOM_TAGS, str(symptoms_mod.SYMPTOM_TAGS))
    check("1m. the hypothesis's own note names that symptom link",
         "hard_to_refuel" in hyp.note or "nozzle" in hyp.note.lower(), hyp.note)

    # -- to_dict() carries hypotheses through for callers (e.g. jobs_bridge)
    d = tree_455.to_dict()
    check("1n. Tree.to_dict() exposes hypotheses",
         any(hd["key"] == "evap-flooded-canister" for hd in d.get("hypotheses", [])),
         str(d.get("hypotheses")))


# ===========================================================================
# Synthetic dossiers for items 2-4: a display-grouping concern over
# dossier['history']/['tsb_matches'], not a from-car fact -- built here
# rather than against the real corpus so this suite is not hostage to
# whatever codes happen to be on file on the machine running it.
# ===========================================================================

def _dossier(seen_once: list[dict]) -> dict:
    return {
        "history": {"chronic": [], "returned_after_clear": [], "seen_once": seen_once},
        "tsb_matches": {"family_findings": []},
    }


# ===========================================================================
# 2. Body group split: B1176 (mechanical) vs. B1040-87 (comms-like)
# ===========================================================================

dossier2 = _dossier([
    {"dtc": "B1176-97", "last_seen": "2026-10-01 10:00:00"},
    {"dtc": "B1040-87", "last_seen": "2026-10-01 10:00:00"},
])
comms2 = frozenset(dossier_bridge._comms_like_bases(dossier2, []))
check("2a. B1040-87's failure-type byte (87) is classified communication-like",
     "B1040" in comms2, str(comms2))
check("2b. B1176-97's failure-type byte (97) is NOT classified communication-like",
     "B1176" not in comms2, str(comms2))

cards2 = dossier_bridge._build_open_work("TESTVIN", dossier2, {}, frozenset(), comms2)
card_body = next((c for c in cards2 if c["family"] == "body"), None)
card_comms = next((c for c in cards2 if c["family"] == "body_comms"), None)
check("2c. B1176 lands on its own 'body' (mechanical) card",
     bool(card_body) and card_body["codes"] == ["B1176"], str(cards2))
check("2d. B1040 lands on a separate 'body_comms' card",
     bool(card_comms) and card_comms["codes"] == ["B1040"], str(cards2))
check("2e. the two codes are never on the same card",
     card_body is not card_comms and (not card_body or "B1040" not in card_body["codes"]),
     str(cards2))


# ===========================================================================
# 3. C104B: hydraulic inspection first, card flagged safety_relevant
# ===========================================================================

tree_c104b = faulttree.tree_for("C104B")
check("3a. C104B's generated tree has at least one step",
     len(tree_c104b.steps) > 0, str(tree_c104b.steps))
if tree_c104b.steps:
    first = tree_c104b.steps[0]
    check("3b. the FIRST step is the brake-fluid-level / hydraulic-leak inspection",
         "hydraulic" in first.title.lower() and "fluid" in first.test.lower(),
         f"{first.title} / {first.test}")
    check("3c. that first step cites the existing brake_hydraulic test id",
         "brake_hydraulic_pressure_bleed" in first.if_abnormal, first.if_abnormal)
    electrical_before = any(
        "electrical" in s.title.lower() or "module connector" in s.title.lower()
        for s in tree_c104b.steps[:tree_c104b.steps.index(first)])
    check("3d. no electrical/module step precedes it",
         not electrical_before, str([s.title for s in tree_c104b.steps]))

dossier3 = _dossier([{"dtc": "C104B-00", "last_seen": "2026-10-01 10:00:00"}])
cards3 = dossier_bridge._build_open_work("TESTVIN", dossier3, {}, frozenset(), frozenset())
card_c104b = next((c for c in cards3 if "C104B" in c["codes"]), None)
check("3e. C104B gets an open-work card",
     card_c104b is not None, str(cards3))
check("3f. that card is flagged safety_relevant",
     bool(card_c104b) and card_c104b.get("safety_relevant") is True, str(card_c104b))
if card_c104b:
    check("3g. the card's own first step is still the hydraulic inspection",
         "hydraulic" in card_c104b["steps"][0]["text"].lower(), str(card_c104b["steps"][0]))


# ===========================================================================
# 4. Stale single-session codes: demoted from open work, never deleted
# ===========================================================================

dossier4 = _dossier([
    {"dtc": "P0098-00", "last_seen": "2025-09-05 10:00:00"},
    {"dtc": "P00F5-00", "last_seen": "2025-09-05 10:00:00"},
    {"dtc": "P105E-00", "last_seen": "2025-09-05 10:00:00"},
    {"dtc": "P1189-00", "last_seen": "2025-09-05 10:00:00"},
])
cards4 = dossier_bridge._build_open_work("TESTVIN", dossier4, {}, frozenset(), frozenset())
codes_in_open_work4 = {c for card in cards4 for c in card["codes"]}
check("4a. none of the four 2025 codes appear in open work",
     codes_in_open_work4.isdisjoint({"P0098", "P00F5", "P105E", "P1189"}),
     str(codes_in_open_work4))

check("4b. all four are still in the dossier's own history (never deleted)",
     {rec["dtc"].split("-")[0] for rec in dossier4["history"]["seen_once"]}
     == {"P0098", "P00F5", "P105E", "P1189"},
     str(dossier4["history"]["seen_once"]))

demoted4 = dossier_bridge._demoted_single_session_codes(dossier4)
demoted_codes4 = {d["code"] for d in demoted4}
check("4c. all four appear in demoted_open_work",
     demoted_codes4 == {"P0098", "P00F5", "P105E", "P1189"}, str(demoted4))
check("4d. each carries the 'seen once on <date>, not since' wording",
     all(d["wording"].startswith("seen once on ") and d["wording"].endswith(", not since")
         for d in demoted4),
     str(demoted4))

# A chronic code just as old is never demoted by this rule (age alone is
# never the test for chronic/returned codes).
dossier4b = {
    "history": {
        "chronic": [{"dtc": "P0300-00", "last_seen": "2025-01-01 10:00:00"}],
        "returned_after_clear": [], "seen_once": [],
    },
    "tsb_matches": {"family_findings": []},
}
check("4e. an old chronic code is never demoted (only seen_once + age)",
     dossier_bridge._demoted_single_session_codes(dossier4b) == [], "")
check("4f. that old chronic code still counts as open-work-eligible history",
     "P0300" in dossier_bridge._history_codes(dossier4b), "")

# A recent seen-once code (inside the 180-day window) is not demoted.
dossier4c = _dossier([{"dtc": "P0442-00", "last_seen": "2026-10-10 10:00:00"}])
check("4g. a recent seen-once code is not demoted",
     dossier_bridge._demoted_single_session_codes(dossier4c) == [], "")
check("4h. a recent seen-once code is still open-work-eligible",
     "P0442" in dossier_bridge._history_codes(dossier4c), "")


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
