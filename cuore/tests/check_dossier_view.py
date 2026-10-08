"""Smoke checks for the dossier redesign's data side: ``dossier_bridge.build_view``
and the routers over it (the checklist store, the view JSON, "verify repair").

Same posture as ``cuore/tests/check_dealer_page.py``/``check_notes_page.py``:
``CUORE_STATE_DIR`` is pointed at a throwaway directory BEFORE cuore is
imported, so nothing here ever touches the bench's real state. The MES log
corpus is NOT overridden -- VIN ZASFAKPN5J7B88115's real corpus (chronic
EVAP trio, cleared 2026-09-29, never re-verified) is the fixture, same as
every other dossier test in this suite.

``cuore.app.create_app`` may not yet wire ``cuore.api.checklists``,
``cuore.api.dossier`` or ``cuore.web.dossier_routes`` (another agent owns
that edit to ``app.py``) -- this file includes them itself, defensively, so
it is self-sufficient today and a harmless no-op once ``app.py`` is updated.

Run:
    .venv/Scripts/python.exe cuore/tests/check_dossier_view.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: everything here goes to a throwaway directory,
# never the bench's real evidence store.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-dossier-view-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.api import checklists as checklists_api  # noqa: E402
from cuore.api import dossier as dossier_api  # noqa: E402
from cuore.web import dossier_routes  # noqa: E402
from cuore.live import store as live_store  # noqa: E402
from cuore.services import dossier_bridge, mes_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, EVAP trio cleared 2026-09-29

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


app = create_app()
existing_paths = {getattr(r, "path", None) for r in app.routes}
if "/api/vehicles/{vin}/checklist" not in existing_paths:
    app.include_router(checklists_api.router, prefix="/api")
if "/api/vehicles/{vin}/view" not in existing_paths:
    app.include_router(dossier_api.router, prefix="/api")
if "/v/{vin}/verify" not in existing_paths:
    app.include_router(dossier_routes.router)

client = TestClient(app)


# --- build_view() directly, against the real corpus -------------------------

dossier = mes_bridge.workup(vin=VIN)
view = dossier_bridge.build_view(VIN, dossier, None)

check("verdict state is UNVERIFIED_REPAIR today",
      view["verdict"]["state"] == "UNVERIFIED_REPAIR", view["verdict"]["state"])
check("verdict cleared_at is 2026-09-29",
      view["verdict"]["cleared_at"] == "2026-09-29", str(view["verdict"]["cleared_at"]))

p0455 = next((f for f in view["freeze_frames"] if f["code"] == "P0455-00"), None)
check("a P0455 freeze frame is present", p0455 is not None, str(view["freeze_frames"]))
if p0455:
    fuel = next((p for p in p0455["key"] if p["name"] == "Fuel level"), None)
    check("P0455 frame has a Fuel level entry", fuel is not None, str(p0455["key"]))
    check("P0455 frame flags fuel above 85%",
          bool(fuel and fuel["flag"] and "85" in fuel["flag"]), str(fuel))

p0456 = next((f for f in view["freeze_frames"] if f["code"] == "P0456-00"), None)
check("a P0456 freeze frame is present", p0456 is not None, str(view["freeze_frames"]))
if p0456:
    fuel456 = next((p for p in p0456["key"] if p["name"] == "Fuel level"), None)
    check("P0456 frame (80%) has no fuel flag",
          bool(fuel456) and fuel456["flag"] is None, str(fuel456))

bulletin_ids = [b["id"] for b in view["bulletins"]]
check("bulletins are deduplicated: S2125000002 appears once",
      bulletin_ids.count("S2125000002") == 1, str(bulletin_ids))
check("bulletins are deduplicated: 18-030-17 REV. B appears once",
      bulletin_ids.count("18-030-17 REV. B") == 1, str(bulletin_ids))

evap_card = next((c for c in view["open_work"] if c["family"] == "EVAP"), None)
check("open_work has an EVAP card", evap_card is not None, str(view["open_work"]))
if evap_card:
    check("EVAP card has 6 steps", len(evap_card["steps"]) == 6, str(evap_card["steps"]))
    check("EVAP step 1 cites S2125000002",
          evap_card["steps"][0]["ref"] == "S2125000002", str(evap_card["steps"][0]))

check("every code row's status is one of the 3 values",
      all(r["status"] in ("ACTIVE", "CLEARED_UNVERIFIED", "STALE") for r in view["codes"]),
      str({r["code"]: r["status"] for r in view["codes"]}))
check("last_seen_short never carries seconds",
      all(":" not in (r["last_seen_short"] or "").split(" ")[-1]
          or (r["last_seen_short"] or "").count(":") <= 1 for r in view["codes"]),
      str([r["last_seen_short"] for r in view["codes"]]))

failed_ops = [a for a in view["attempted"] if a["outcome"] == "FAILED TO EXECUTE"]
ok_ops = [a for a in view["attempted"] if a["outcome"] != "FAILED TO EXECUTE"]
check("attempted: failures sort first",
      view["attempted"][:len(failed_ops)] == failed_ops if failed_ops else True,
      str([(a["operation"], a["outcome"]) for a in view["attempted"]]))
pairs = [(a["operation"], a["outcome"]) for a in view["attempted"]]
check("attempted: each (operation, outcome) pair appears once",
      len(pairs) == len(set(pairs)), str(pairs))
thermostat = next((a for a in view["attempted"]
                   if a["operation"] == "Electronic thermostat"), None)
check("the interlock footnote rides on the row whose reason is Engine running, not elsewhere",
      all((a["footnote"] is None) or ("engine running" in (a["reason"] or "").lower())
          for a in view["attempted"]),
      str([(a["operation"], a["reason"], a["footnote"]) for a in view["attempted"]]))


# --- checklist store: JSON API --------------------------------------------------

step_id = evap_card["steps"][0]["id"] if evap_card else "evap-1"

empty = client.get(f"/api/vehicles/{VIN}/checklist")
check("empty checklist responds 200", empty.status_code == 200, str(empty.status_code))
check("empty checklist has no steps recorded", empty.json()["checklist"] == {},
      str(empty.json()))

posted = client.post(f"/api/vehicles/{VIN}/checklist",
                     json={"step_id": step_id, "done": True, "by": "tech"})
check("posting a known step id responds 200", posted.status_code == 200, posted.text)
check("posted step comes back done", posted.json()["done"] is True, posted.text)

after_post = client.get(f"/api/vehicles/{VIN}/checklist")
check("GET reflects the POST", after_post.json()["checklist"].get(step_id, {}).get("done") is True,
      str(after_post.json()))

bad = client.post(f"/api/vehicles/{VIN}/checklist",
                  json={"step_id": "not-a-real-step", "done": True})
check("an unknown step id is rejected with 400", bad.status_code == 400, str(bad.status_code))


# --- the view JSON route ---------------------------------------------------------

view_resp = client.get(f"/api/vehicles/{VIN}/view")
check("GET .../view responds 200", view_resp.status_code == 200, str(view_resp.status_code))
check("GET .../view carries the same verdict state",
      view_resp.json()["verdict"]["state"] == "UNVERIFIED_REPAIR",
      str(view_resp.json()["verdict"]))
check("GET .../view reflects the checklist POST above",
      any(s["id"] == step_id and s["done"] for c in view_resp.json()["open_work"]
          for s in c["steps"]),
      str(view_resp.json()["open_work"]))


# --- the dossier page itself ------------------------------------------------------

page = client.get(f"/v/{VIN}")
check("dossier page responds 200", page.status_code == 200, str(page.status_code))

form_post = client.post(f"/v/{VIN}/checklist", data={"step_id": step_id, "done": "0"},
                        follow_redirects=False)
check("the HTML checklist form redirects back to the dossier",
      form_post.status_code == 303 and form_post.headers["location"].endswith("#open-work"),
      f"status={form_post.status_code} location={form_post.headers.get('location')}")

bad_form = client.post(f"/v/{VIN}/checklist", data={"step_id": "nope", "done": "1"})
check("an unknown step id on the HTML form is rejected (400, not a 500)",
      bad_form.status_code == 400, str(bad_form.status_code))


# --- /v/{vin}/verify: no adapter configured in this test environment -------------

verify_page = client.get(f"/v/{VIN}/verify")
check("verify page responds 200 with no car connected",
      verify_page.status_code == 200, str(verify_page.status_code))


# --- synthetic readiness observations flip (or don't flip) the verdict -----------

def _fresh_view() -> dict:
    d = mes_bridge.workup(vin=VIN)
    return dossier_bridge.build_view(VIN, d, None)


readiness_payload = {
    "since_clear": {
        "monitors": [{"monitor": "Evaporative system", "supported": True, "complete": True}],
        "all_complete": True,
    },
}

before = _fresh_view()
check("before any readiness observation, verdict is still UNVERIFIED_REPAIR",
      before["verdict"]["state"] == "UNVERIFIED_REPAIR", str(before["verdict"]))

live_store.record_observation("readiness", readiness_payload, vin=VIN, stream="live-fake")
not_flipped = _fresh_view()
check("a non-serial-tagged observation (stream=live-fake) does not flip the verdict",
      not_flipped["verdict"]["state"] == "UNVERIFIED_REPAIR", str(not_flipped["verdict"]))

live_store.record_observation("readiness", readiness_payload, vin=VIN,
                              stream="serial COM3@38400")
flipped = _fresh_view()
check("a readiness observation from the car (serial stream) flips the verdict "
      "to VERIFIED_CLEAN",
      flipped["verdict"]["state"] == "VERIFIED_CLEAN", str(flipped["verdict"]))

check("is_from_car rejects the synthetic non-serial stream",
      not live_store.is_from_car({"stream": "live-fake"}))
check("is_from_car accepts a serial stream",
      live_store.is_from_car({"stream": "serial COM3@38400"}))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
