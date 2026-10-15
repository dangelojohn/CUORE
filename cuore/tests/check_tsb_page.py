"""Checks for the TSB layer: cuore/data/tsb_catalogue.json, the loader,
cuore/services/tsb_bridge.py and GET/POST /tsb (cuore/web/tsb_routes.py).

``CUORE_STATE_DIR`` points at a throwaway directory BEFORE cuore is
imported. The dossier cross-link check fakes the workup by swapping
``tsb_routes._dossier`` for a stub carrying a ``tsb_matches.per_code``.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_tsb_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-tsb-")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.data import load_tsb_catalogue  # noqa: E402
from cuore.services import tsb_bridge  # noqa: E402
from cuore.web import tsb_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
SEED = ("18-030-17 REV. B", "18-048-23", "9100471")

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# 1. loader reads the seed (and tolerates extra / missing optional fields)
cat = load_tsb_catalogue()
nums = [i["number"] for i in cat["items"]]
extra = load_tsb_catalogue('{"items": [{"id": "x1", "whatever": 1}, {"title": "no id"}]}')
check("loader reads seed", all(n in nums for n in SEED) and cat["vehicle"].get("model") == "Stelvio"
      and extra["items"][0]["links"] == [] and extra["items"][0]["whatever"] == 1
      and len(extra["items"]) == 1, f"{nums} / {extra}")

# 2. checklist defaults to open
cl = tsb_bridge.checklist(VIN)
seed_rows = [r for r in cl["items"] if r["number"] in SEED]
check("checklist seed rows default open", len(seed_rows) == 3
      and all(r["status"] == "open" for r in seed_rows), str([(r["number"], r["status"]) for r in seed_rows]))

# 3. set_status persists and reads back
tsb_bridge.set_status(VIN, "tsb-9100471", "to_verify", "ask dealer")
row = next(r for r in tsb_bridge.checklist(VIN)["items"] if r["id"] == "tsb-9100471")
on_disk = tsb_bridge.path().read_text(encoding="utf-8")
check("set_status persists", row["status"] == "to_verify" and row["note"] == "ask dealer"
      and "ask dealer" in on_disk and tsb_bridge.checklist(VIN)["counts"]["to_verify"] == 1, str(row))

# 4/5. page renders with all three numbers; cross-link for a dossier match
FAKE = {"identity": {}, "tsb_matches": {"per_code": {
    "P0456": [{"bulletin": "18-048-23", "title": "SLVT"}]}}}
tsb_routes._dossier = lambda vin: FAKE  # type: ignore[assignment]
client = TestClient(create_app())
resp = client.get(f"/tsb?vin={VIN}")
html = resp.text
check("GET /tsb 200 with seed numbers", resp.status_code == 200 and all(n in html for n in SEED),
      f"status {resp.status_code}")
check("dossier cross-link anchor", f'href="/v/{VIN}/dossier#tsb-18-048-23"' in html,
      "anchor missing")

# bonus (not counted in the five): form POST round-trips through the route
r = client.post("/tsb/status", data={"vin": VIN, "item_id": "tsb-18-048-23", "status": "done",
                                     "note": "SLVT pass"}, follow_redirects=False)
row = next(r for r in tsb_bridge.checklist(VIN)["items"] if r["id"] == "tsb-18-048-23")
if r.status_code != 303 or row["status"] != "done":
    failures.append(f"POST /tsb/status form -- {r.status_code} {row['status']}")

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
