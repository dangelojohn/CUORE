"""Smoke checks for technician notes: the JSON routes and the pages.

Same posture as ``cuore/tests/check_dealer_page.py``: ``CUORE_STATE_DIR`` is
pointed at a throwaway directory BEFORE cuore is imported, so nothing here
ever touches the bench's real notes store. The MES log corpus is NOT
overridden -- this VIN's real corpus (chronic P0456) is the fixture for the
dossier/code/tree page checks, same posture as ``cuore/tests/check_api.py``.

Run:
    .venv/Scripts/python.exe cuore/tests/check_notes_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: notes go to a throwaway directory, never the
# bench's real evidence store.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-notes-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import mes_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0456
OTHER_VIN = "1C4RJFAG0JC000001"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())


# --- JSON routes: empty, add, edit, hide -------------------------------------

empty = client.get(f"/api/vehicles/{VIN}/notes")
check("empty list responds 200", empty.status_code == 200, str(empty.status_code))
check("empty list has no notes", empty.json()["notes"] == [], str(empty.json()))

bad = client.post(f"/api/vehicles/{VIN}/notes", json={"text": "", "target_kind": "vehicle"})
check("empty text is rejected", bad.status_code == 400, str(bad.status_code))

bad_kind = client.post(f"/api/vehicles/{VIN}/notes",
                       json={"text": "x", "target_kind": "not_a_kind"})
check("unknown target_kind is rejected", bad_kind.status_code == 400, str(bad_kind.status_code))

vnote = client.post(f"/api/vehicles/{VIN}/notes", json={
    "text": "purge valve replaced by me 2026-09-10",
    "target_kind": "vehicle",
    "tags": ["repair"],
})
check("vehicle note recorded", vnote.status_code == 200, str(vnote.text))
vnote_id = vnote.json()["id"]
check("vehicle note response carries vin/target_kind/tags",
      vnote.json()["vin"] == VIN and vnote.json()["target_kind"] == "vehicle"
      and vnote.json()["tags"] == ["repair"], str(vnote.json()))

cnote = client.post(f"/api/vehicles/{VIN}/notes", json={
    "text": "smoke test done at 0.5 psi, no leak",
    "target_kind": "code", "target_id": "P0456",
})
check("code note recorded", cnote.status_code == 200, str(cnote.text))

other = client.post(f"/api/vehicles/{OTHER_VIN}/notes",
                    json={"text": "not this car", "target_kind": "vehicle"})
check("other VIN's note recorded independently", other.status_code == 200, str(other.text))

listed = client.get(f"/api/vehicles/{VIN}/notes")
check("list responds 200 after recording", listed.status_code == 200)
rows = listed.json()["notes"]
check("list has exactly this VIN's two notes", len(rows) == 2, str(rows))
check("list excludes the other VIN", all(r["vin"] == VIN for r in rows))

filtered = client.get(f"/api/vehicles/{VIN}/notes",
                      params={"target_kind": "code", "target_id": "P0456"})
check("filtered list matches on base code", len(filtered.json()["notes"]) == 1,
      str(filtered.json()))

edited = client.post(f"/api/vehicles/{VIN}/notes/{vnote_id}/edit",
                     json={"text": "purge valve replaced; retested clean"})
check("edit responds 200", edited.status_code == 200, str(edited.text))
check("edit updates the text", edited.json()["text"] == "purge valve replaced; retested clean")

after_edit = client.get(f"/api/vehicles/{VIN}/notes").json()["notes"]
vnote_after = next(n for n in after_edit if n["id"] == vnote_id)
check("resolved note shows the edited text",
      vnote_after["text"] == "purge valve replaced; retested clean")
check("resolved note keeps the original text in history",
      bool(vnote_after["history"]) and vnote_after["history"][0]["text"]
      == "purge valve replaced by me 2026-09-10")

hidden = client.post(f"/api/vehicles/{VIN}/notes/{vnote_id}/hide")
check("hide responds 200", hidden.status_code == 200, str(hidden.text))
after_hide = client.get(f"/api/vehicles/{VIN}/notes").json()["notes"]
check("hidden note excluded from the default listing",
      not any(n["id"] == vnote_id for n in after_hide))

bad_edit = client.post(f"/api/vehicles/{VIN}/notes/nonexistent-id/edit",
                       json={"text": "x"})
check("editing an unknown id is rejected", bad_edit.status_code == 400, str(bad_edit.status_code))


# --- pages: dossier, code, tree, and the notes listing -----------------------

dossier_page = client.get(f"/v/{VIN}")
check("dossier page responds 200", dossier_page.status_code == 200)

code_page = client.get(f"/v/{VIN}/code/P0456")
check("code page responds 200", code_page.status_code == 200)
check("code page shows the note filed against this code",
      "smoke test done at 0.5 psi" in code_page.text)

tree_page = client.get(f"/v/{VIN}/tree", params={"codes": "P0456"})
check("tree page responds 200", tree_page.status_code == 200)

step_note = client.post(f"/v/{VIN}/notes", data={
    "text": "step E7 already done, no leak found",
    "target_kind": "tree_step", "target_id": "evap-leak:E7",
    "redirect_to": f"/v/{VIN}/tree?codes=P0456",
})
check("posting a tree-step note form redirects back to the tree page",
      step_note.status_code == 200 and str(step_note.url).endswith("/tree?codes=P0456"),
      f"status={step_note.status_code} url={step_note.url}")
check("tree page (after redirect) shows the tree-step note as vehicle evidence",
      "step E7 already done" in step_note.text)

notes_list_page = client.get(f"/v/{VIN}/notes")
check("notes listing page responds 200", notes_list_page.status_code == 200)
check("notes listing shows the tree-step note", "step E7 already done" in notes_list_page.text)
check("notes listing does not show the hidden note's text",
      "retested clean" not in notes_list_page.text)

posted = client.post(f"/v/{VIN}/notes", data={
    "text": "posted from the notes page itself",
    "target_kind": "vehicle", "target_id": "",
    "redirect_to": f"/v/{VIN}/notes",
})
check("posting from the notes page responds 200", posted.status_code == 200)
check("posted note shows up on the rendered page",
      "posted from the notes page itself" in posted.text)

after = mes_bridge.notes(VIN)["notes"]
check("service layer sees everything the pages recorded",
      len(after) == 3, str(after))  # code note, tree-step note, notes-page note (vnote hidden)


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
