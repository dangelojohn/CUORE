"""Checks for the Modifications layer -- the catalogue
(:mod:`mes.modifications`), the per-VIN ledger
(:mod:`cuore.live.modifications`), the bridge
(:mod:`cuore.services.modifications_bridge`), the ``/api/mods*`` HTTP
surface, and the ``/v/{vin}/mods`` pages.

**Decided 2026-10-14: CUORE diagnoses; it never performs coding/
configuration writes itself.** Every row/record here is a handoff or a
record of a handoff already done -- nothing in this feature writes to the
car. See ``docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md``,
``docs/research/mes_paddle_shift_function.json`` and
``docs/handbook/01-decisions-and-rules.md``.

Same posture as ``cuore/tests/check_mes_handoff.py``: ``CUORE_STATE_DIR``
pointed at a throwaway directory before ``cuore`` (and therefore ``mes``)
is imported, plain script, ``check()``, exit 1 on failure, no pytest.

Six groups of checks:
  1. The catalogue has >=1 entry, the paddle-shift entry is first and fully
     sourced (prerequisites, risks with the sourced "dire consequences"
     wording, reversible, sources, confidence), no duplicate ids, every
     row has a valid kind/confidence.
  2. The ledger: record/edit/delete/restore round-trips, with an audit
     trail on edit, and status() reflects stock vs modified.
  3. non_stock(vin) returns a chip naming the modification once recorded,
     empty for a stock car, and merges an owner-reported "part fitted
     elsewhere" event read-side without a second write.
  4. The HTTP surface: GET catalog, GET one catalog item + its handoff
     card, GET/POST/PATCH/DELETE/restore the ledger, GET non-stock --
     all round-trip over TestClient.
  5. Pages: /v/{vin}/mods and /v/{vin}/mods/{mod_id} respond 200 and carry
     the "Modifications — not diagnostics" rule text.
  6. API contract doc: the mods rows this pass added to
     docs/mobile/API_CONTRACT.md's path table are still in the live schema
     (same drift guard check_api_contract.py applies to the rest of the
     table, scoped here to just this feature's own rows).

Run:
    .venv/Scripts/python.exe cuore/tests/check_mods.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- same fixture VIN every other check uses
OTHER_VIN = "ZN661XUA9JX000001"

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-mods-state-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LOG_DIRS", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import modifications as live_mods  # noqa: E402
from cuore.live import owner_events  # noqa: E402
from cuore.services import modifications_bridge as bridge  # noqa: E402

from mes import modifications as mods_mod  # noqa: E402

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
# 1. catalogue
# ===========================================================================

print("=== mes.modifications catalogue ===")
rows = mods_mod.all_mods()
check("at least 1 modification catalogued", len(rows) >= 1, str(len(rows)))
check("no duplicate ids", len({r["id"] for r in rows}) == len(rows))
check("every row has a valid kind", all(r["kind"] in mods_mod.KINDS for r in rows))
check("every row has a valid confidence",
     all(r["confidence"] in ("CONFIRMED", "CORROBORATED", "SINGLE-SOURCE", "UNKNOWN")
         for r in rows))
check("mod() returns None for an unknown id", mods_mod.mod("not-a-real-id") is None)

print("=== paddle-shift NA/Euro entry (catalogue entry one) ===")
check("the paddle-shift entry is first in catalogue order",
     rows[0]["id"] == "paddle_shift_na_eu", rows[0]["id"])
paddle = mods_mod.mod("paddle_shift_na_eu")
check("the paddle entry exists", paddle is not None)
if paddle is not None:
    check("it names the BCM module", "BCM" in paddle["module"], paddle["module"])
    check("it has at least one prerequisite", len(paddle["prerequisites"]) >= 1)
    check("it carries the sourced 'dire consequences' caution",
         any("dire consequences" in r for r in paddle["risks"]), str(paddle["risks"]))
    check("it is marked reversible", paddle["reversible"] is True)
    check("it has a non-empty reversal method", bool(paddle["reversal_method"].strip()))
    check("it has at least one source", len(paddle["sources"]) >= 1)
    check("its confidence is SINGLE-SOURCE (per the research pass's own grading)",
         paddle["confidence"] == "SINGLE-SOURCE")
    check("it cross-references the mes_functions handoff id",
         paddle.get("mes_function_id") == "paddle_shifter_logic")
    check("CUORE write support is explicitly not_supported",
         paddle["cuore_write_support"]["status"] == "not_supported")

print("=== search / module lookup ===")
check("search('paddle shift') finds the paddle entry",
     any(r["id"] == "paddle_shift_na_eu" for r in mods_mod.search("paddle shift")))
check("mods_for_module('BCM') finds at least the paddle entry",
     any(r["id"] == "paddle_shift_na_eu" for r in mods_mod.mods_for_module("BCM")))

# ===========================================================================
# 2. the per-VIN ledger
# ===========================================================================

print("=== cuore.live.modifications ledger ===")
check("a fresh VIN is stock", live_mods.status(VIN)["status"] == "stock")

entry = live_mods.add(
    VIN, mod_id="paddle_shift_na_eu", by_role="mechanic", by_name="Tony",
    tool="MES", from_value="NA (0x50)", to_value="EU (0x40)",
    backup="proxi_backup_2610.txt", verification_how="test drive",
    verification_when="2026-10-14", verification_result="both paddles reach Neutral",
    proxi_realigned=True, notes="byte 156 bits 4-5 only",
)
check("add() returns a record with an id", bool(entry.get("id")))
check("status is now modified", live_mods.status(VIN)["status"] == "modified")

loaded = live_mods.load(VIN)
check("load() returns the recorded entry", any(r["id"] == entry["id"] for r in loaded))

edit_entry = live_mods.edit(entry["id"], notes="updated after the test drive", by_name="Tony")
check("edit() returns a record_edit row", edit_entry["op"] == "record_edit")
folded = live_mods.load(VIN)[0]
check("the folded view carries the edited note",
     folded["notes"] == "updated after the test drive", folded["notes"])
check("the folded view carries an audit trail of exactly one edit",
     len(folded["audit"]) == 1, str(folded["audit"]))

live_mods.delete(entry["id"])
check("after delete, the entry is hidden from load()",
     not any(r["id"] == entry["id"] for r in live_mods.load(VIN)))
check("status reverts to stock after the only entry is deleted",
     live_mods.status(VIN)["status"] == "stock")

live_mods.restore(entry["id"])
check("after restore, the entry is visible again",
     any(r["id"] == entry["id"] for r in live_mods.load(VIN)))
check("status is modified again after restore",
     live_mods.status(VIN)["status"] == "modified")

try:
    live_mods.add(VIN)
    check("add() with neither mod_id nor free_text raises", False)
except ValueError as exc:
    check("add() with neither mod_id nor free_text raises ValueError", True, str(exc))

try:
    live_mods.edit("not-a-real-id", notes="x")
    check("edit() of an unknown id raises", False)
except ValueError:
    check("edit() of an unknown id raises ValueError", True)

# ===========================================================================
# 3. non_stock() and the owner_events read-side merge
# ===========================================================================

print("=== non_stock() and owner_events merge ===")
check("non_stock is empty for the never-modified other VIN", bridge.non_stock(OTHER_VIN) == [])

chips = bridge.non_stock(VIN)
check("non_stock returns at least one chip for the modified VIN", len(chips) >= 1)
if chips:
    check("the chip names the paddle-shift modification",
         "paddle" in chips[0]["label"].lower(), chips[0]["label"])
    check("the chip's detail names who recorded it",
         "Tony" in chips[0]["detail"], chips[0]["detail"])

owner_events.add(VIN, "parts_repairs_elsewhere", "part_fitted_elsewhere",
                 fields={"part": "Aftermarket cold-air intake", "who": "JoesGarage"})
merged = bridge.ledger(VIN)
check("the owner-reported part-fitted event appears in the merged ledger",
     any(r.get("source") == "reported_by_owner" for r in merged))
chips_after = bridge.non_stock(VIN)
check("non_stock reflects the owner-reported event too",
     any("cold-air intake" in c["label"].lower() for c in chips_after), str(chips_after))
check("the owner-event merge did not write a second copy to the ledger file",
     len(live_mods.load(VIN)) == 1)

handoff = bridge.handoff_for("paddle_shift_na_eu")
check("handoff_for returns a card for the paddle-shift entry", handoff is not None)
if handoff is not None:
    check("the handoff card never claims to write to the car",
         handoff["writes_to_car"] is False)

# ===========================================================================
# 4. HTTP surface
# ===========================================================================

print("=== HTTP: /api/mods/* ===")
client = TestClient(create_app())

cat_resp = client.get("/api/mods/catalog")
check("GET /api/mods/catalog responds 200", cat_resp.status_code == 200)
check("catalog count matches the module", cat_resp.json()["count"] == len(mods_mod.all_mods()))

item_resp = client.get("/api/mods/catalog/paddle_shift_na_eu")
check("GET one catalog item responds 200", item_resp.status_code == 200)
check("GET an unknown catalog item responds 404",
     client.get("/api/mods/catalog/not-a-real-id").status_code == 404)

handoff_resp = client.get("/api/mods/catalog/paddle_shift_na_eu/handoff")
check("GET the handoff endpoint responds 200", handoff_resp.status_code == 200)
check("the handoff endpoint returns a non-null card",
     handoff_resp.json().get("handoff") is not None)

record_resp = client.post(f"/api/mods/{VIN}/record",
                          json={"mod_id": "paddle_shift_na_eu", "by_name": "Sam",
                                "tool": "MES", "to_value": "EU"})
check("POST record responds 200", record_resp.status_code == 200, str(record_resp.text))
rec_id = record_resp.json()["id"]

status_resp = client.get(f"/api/mods/{VIN}")
check("GET ledger/status responds 200", status_resp.status_code == 200)
check("status is modified over HTTP too", status_resp.json()["status"] == "modified")

nonstock_resp = client.get(f"/api/mods/{VIN}/non-stock")
check("GET non-stock responds 200", nonstock_resp.status_code == 200)
check("GET non-stock returns at least one chip", nonstock_resp.json()["count"] >= 1)

patch_resp = client.patch(f"/api/mods/{VIN}/{rec_id}", json={"notes": "patched over HTTP"})
check("PATCH one ledger entry responds 200", patch_resp.status_code == 200, str(patch_resp.text))

del_resp = client.delete(f"/api/mods/{VIN}/{rec_id}")
check("DELETE one ledger entry responds 200", del_resp.status_code == 200)

restore_resp = client.post(f"/api/mods/{VIN}/{rec_id}/restore")
check("POST restore responds 200", restore_resp.status_code == 200)

bad_record = client.post(f"/api/mods/{VIN}/record", json={"by_name": "Nobody"})
check("POST record with neither mod_id nor free_text responds 400",
     bad_record.status_code == 400, str(bad_record.status_code))

# ===========================================================================
# 5. pages
# ===========================================================================

print("=== pages: /v/{vin}/mods, /v/{vin}/mods/{mod_id} ===")
page = client.get(f"/v/{VIN}/mods")
check("the mods page responds 200", page.status_code == 200)
check("the mods page carries the 'Modifications — not diagnostics' rule",
     "Modifications — not diagnostics" in page.text
     or "Modifications &mdash; not diagnostics" in page.text)
check("the mods page shows the catalogue's paddle entry",
     "paddle_shift_na_eu" in page.text or "Paddle shift" in page.text)

detail_page = client.get(f"/v/{VIN}/mods/paddle_shift_na_eu")
check("the mod detail page responds 200", detail_page.status_code == 200)
check("the detail page shows the handoff card",
     "mod-handoff" in detail_page.text)

unknown_detail = client.get(f"/v/{VIN}/mods/not-a-real-id")
check("the detail page for an unknown mod id responds 404",
     unknown_detail.status_code == 404, str(unknown_detail.status_code))

form_resp = client.post(f"/v/{VIN}/mods/record",
                        data={"free_text": "Aftermarket wheels fitted",
                              "by_role": "mechanic", "tool": "other"},
                        follow_redirects=False)
check("the plain-form record POST redirects (303) back to the mods page",
     form_resp.status_code == 303 and "saved=1" in (form_resp.headers.get("location") or ""),
     str(form_resp.headers.get("location")))

# ===========================================================================
# 6. API contract doc
# ===========================================================================

print("=== docs/mobile/API_CONTRACT.md: mods rows ===")
DOC_PATH = ROOT / "docs" / "mobile" / "API_CONTRACT.md"
doc_text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
check("API_CONTRACT.md exists", bool(doc_text))
check("API_CONTRACT.md documents GET /api/mods/catalog", "/api/mods/catalog" in doc_text)
check("API_CONTRACT.md documents the per-VIN ledger route", "/api/mods/{vin}" in doc_text)

ROW_RE = re.compile(r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*(/api/mods\S*?)\s*\|", re.MULTILINE)
app_live = create_app()
live_paths = app_live.openapi()["paths"]
doc_rows = ROW_RE.findall(doc_text)
check("API_CONTRACT.md's own /api/mods rows are all still live", len(doc_rows) >= 1)
for method, doc_path in doc_rows:
    entry_live = live_paths.get(doc_path)
    check(f"{method} {doc_path} is in the live schema", entry_live is not None)
    if entry_live is not None:
        check(f"{method} {doc_path} still supports that method",
             method.lower() in entry_live)

# ===========================================================================
print(f"\n{checks} checks, {len(failures)} failures")
if failures:
    for f in failures:
        print(f"FAILED: {f}")
    sys.exit(1)
print("All checks passed.")
