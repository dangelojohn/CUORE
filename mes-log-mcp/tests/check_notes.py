"""Smoke checks for technician notes as evidence.

The notes store is append-only JSONL kept beside cuore's other state (same
posture as ``mes.dealer``). This suite must never touch the real bench's
notes, so ``CUORE_STATE_DIR`` is pointed at a throwaway directory before
anything under ``mes`` (or ``server``) is imported -- ``mes.notes.state_dir()``
reads the env var directly and creates/writes there.

The real corpus (chronic P0456 on this VIN) backs the workup/tree/gate
integration checks; the notes store itself is exercised entirely against the
temp directory.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Before any mes/server import: notes must land in a throwaway directory,
# never the bench's real evidence store.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="mes-check-notes-")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from mes import compact, faulttree, notes, workup  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
OTHER_VIN = "1C4RJFAG0JC000001"
failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


print("=== store: validation ===")
try:
    notes.add("", "text", "vehicle")
    check("empty vin rejected", False)
except ValueError:
    check("empty vin rejected", True)

try:
    notes.add(VIN, "", "vehicle")
    check("empty text rejected", False)
except ValueError:
    check("empty text rejected", True)

try:
    notes.add(VIN, "x" * 4001, "vehicle")
    check("text over 4000 chars rejected", False)
except ValueError:
    check("text over 4000 chars rejected", True)

try:
    notes.add(VIN, "text", "not_a_kind")
    check("unknown target_kind rejected", False)
except ValueError as exc:
    check("unknown target_kind rejected", "target_kind must be one of" in str(exc))

print("=== store: add / edit / hide / load ===")
n1 = notes.add(VIN, "purge valve replaced by me 2026-09-10", "vehicle",
               author="tech1", tags=["repair"])
check("add stamps id/at/vin", bool(n1.get("id")) and bool(n1.get("at")) and n1["vin"] == VIN)
check("add defaults target_kind/target_id",
      n1["target_kind"] == "vehicle" and n1["target_id"] == "")
check("add stamps author/tags", n1["author"] == "tech1" and n1["tags"] == ["repair"])

n2 = notes.add(VIN, "smoke test done at 0.5 psi, no leak", "code", target_id="P0456")
n3 = notes.add(VIN, "code note filed against the suffixed form", "code", target_id="P0456-00")
n4 = notes.add(VIN, "step E7 already done, no leak found", "tree_step",
               target_id="evap-leak:E7")
n5 = notes.add(VIN, "purge valve bench tested good, clicks fine", "component",
               target_id="purge valve")
notes.add(OTHER_VIN, "not this car's note", "vehicle")

loaded_vehicle = notes.load(VIN, target_kind="vehicle")
check("load filters by vin+target_kind",
      len(loaded_vehicle) == 1 and loaded_vehicle[0]["id"] == n1["id"])

loaded_code = notes.load(VIN, target_kind="code", target_id="P0456")
check("code notes match on base code (P0456 and P0456-00 both attach)",
      {n["id"] for n in loaded_code} == {n2["id"], n3["id"]})

edited = notes.edit(n1["id"], "purge valve replaced by me 2026-09-10; retested clean")
check("edit stamps id/text", edited["id"] == n1["id"] and "retested clean" in edited["text"])

resolved = notes.load(VIN, target_kind="vehicle")
check("load resolves current text after edit",
      resolved[0]["text"] == "purge valve replaced by me 2026-09-10; retested clean")
check("load keeps the prior text in history",
      bool(resolved[0]["history"]) and resolved[0]["history"][0]["text"] == n1["text"])

hidden = notes.hide(n2["id"])
check("hide stamps id", hidden["id"] == n2["id"])
after_hide = notes.load(VIN, target_kind="code", target_id="P0456")
check("hidden note excluded by default", n2["id"] not in {n["id"] for n in after_hide})
with_hidden = notes.load(VIN, target_kind="code", target_id="P0456", include_hidden=True)
check("include_hidden=True surfaces it, flagged hidden",
      any(n["id"] == n2["id"] and n["hidden"] for n in with_hidden))

try:
    notes.edit("nonexistent-id", "x")
    check("edit on unknown id rejected", False)
except ValueError:
    check("edit on unknown id rejected", True)

try:
    notes.hide("nonexistent-id")
    check("hide on unknown id rejected", False)
except ValueError:
    check("hide on unknown id rejected", True)

print("=== workup: vehicle-level and per-code notes ===")
dossier = workup.build(vin=VIN)
check("dossier carries the vehicle note",
      any(n["id"] == n1["id"] for n in dossier["notes"]["vehicle"]))
p0456 = next((r for r in dossier["history"]["chronic"] if r["dtc"] == "P0456-00"), None)
check("P0456-00 is chronic in this car's history (fixture)", p0456 is not None)
check("chronic P0456-00 entry carries the un-hidden code note (n3)",
      p0456 is not None and any(n["id"] == n3["id"] for n in p0456.get("notes", [])))
check("the hidden code note (n2) is not attached",
      p0456 is not None and not any(n["id"] == n2["id"] for n in p0456.get("notes", [])))

check("other VIN's notes do not leak into this VIN's dossier",
      not any(n.get("vin") == OTHER_VIN for n in dossier["notes"]["vehicle"]))

print("=== compact: notes kept as text/at/target only ===")
compact_dossier = compact.compact_workup(dossier)
compact_vehicle_notes = compact_dossier.get("notes", {}).get("vehicle", [])
check("compact workup keeps the vehicle note",
      bool(compact_vehicle_notes) and set(compact_vehicle_notes[0]) == {"text", "at", "target"})
compact_p0456 = next((r for r in compact_dossier["history"]["chronic"] if r["dtc"] == "P0456-00"), None)
check("compact history entry keeps the per-code note, reduced to text/at/target",
      compact_p0456 is not None and compact_p0456.get("notes")
      and set(compact_p0456["notes"][0]) == {"text", "at", "target"})
check("compact note target names the code (as originally filed, P0456-00)",
      compact_p0456 is not None and compact_p0456["notes"][0]["target"] == "code:P0456-00")

print("=== fault tree: tree_step + component notes as vehicle_evidence ===")
tree_result = faulttree.evaluate(["P0456"], vin=VIN)
evidence = tree_result.get("vehicle_evidence", [])
e7_notes = [e for e in evidence if e["step"] == "E7" and e["source"] == "technician note"]
check("tree_step note (evap-leak:E7) attached to step E7",
      any("step E7 already done" in e["finding"] for e in e7_notes))
e3_notes = [e for e in evidence if e["step"] == "E3" and e["source"] == "technician note"]
check("component note (purge valve) attached to the step naming it (E3)",
      any("purge valve bench tested good" in e["finding"] for e in e3_notes))

print("=== gate: note measurement cite ===")
MECH = ("canister charcoal bed saturated so the vent path is blocked, "
       "holding pressure and failing both leak monitors")
DISC = ("KOEO actuator test on the purge valve completed with an audible "
       "click, exonerating the purge side")

g = json.loads(server.diagnosis_verdict(
    vin=VIN, codes="P0456", component="vapor canister", mechanism=MECH,
    disconfirming_test=DISC,
    measurements=json.dumps([{"type": "note", "id": n4["id"]}])))
note_check = g["criteria"]["measurement"]["checked"][0]
check("gate accepts a note cite as attested", note_check["status"] == "attested")
check("gate surfaces the note text", "step E7 already done" in note_check["note"])
check("full evidence with a note cite is CONFIRMED", g["verdict"] == "CONFIRMED", g)

g_missing = json.loads(server.diagnosis_verdict(
    vin=VIN, codes="P0456", component="vapor canister", mechanism=MECH,
    disconfirming_test=DISC,
    measurements=json.dumps([{"type": "note", "id": "nonexistent-id"}])))
check("gate rejects a note cite with no matching id",
      g_missing["criteria"]["measurement"]["checked"][0]["status"] == "rejected")

g_no_id = json.loads(server.diagnosis_verdict(
    vin=VIN, codes="P0456", component="x", mechanism=MECH, disconfirming_test=DISC,
    measurements=json.dumps([{"type": "note"}])))
check("gate rejects a note cite with no id",
      g_no_id["criteria"]["measurement"]["checked"][0]["status"] == "rejected")

unknown_type = json.loads(server.diagnosis_verdict(
    vin=VIN, codes="P0456", component="x", mechanism=MECH, disconfirming_test=DISC,
    measurements=json.dumps([{"type": "totally_unknown"}])))
check("unknown measurement type lists note as a valid option",
      "note" in unknown_type["criteria"]["measurement"]["checked"][0]["note"])

print("=== MCP tools ===")
rec = json.loads(server.add_note(vin=VIN, text="via MCP tool", target_kind="vehicle"))
check("add_note tool records", rec["text"] == "via MCP tool" and rec["vin"] == VIN)

listed = json.loads(server.notes(vin=VIN, target_kind="vehicle"))
check("notes tool lists what was recorded",
      listed["vin"] == VIN and any(n["text"] == "via MCP tool" for n in listed["notes"]))

edited_tool = json.loads(server.edit_note(id=rec["id"], text="via MCP tool, edited"))
check("edit_note tool records the amendment", edited_tool["text"] == "via MCP tool, edited")

hidden_tool = json.loads(server.hide_note(id=rec["id"]))
check("hide_note tool records the hide", hidden_tool["id"] == rec["id"])

after_hide_tool = json.loads(server.notes(vin=VIN, target_kind="vehicle"))
check("hidden note excluded from the default tool listing",
      not any(n["id"] == rec["id"] for n in after_hide_tool["notes"]))

bad = json.loads(server.add_note(vin=VIN, text="", target_kind="vehicle"))
check("add_note tool surfaces validation errors", "error" in bad)

bad_kind = json.loads(server.add_note(vin=VIN, text="x", target_kind="not_a_kind"))
check("add_note tool surfaces target_kind validation errors", "error" in bad_kind)


print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
