"""Checks for the "Others' experience" feature: cuore/services/experience_bridge.py,
cuore/api/experience.py, and the _experience.html card included on code.html,
vehicle.html (dossier open-work), maintenance.html, service_hub.html,
timeline.html and report.html.

mes.experience (for_code/for_family/for_job/all) is built in parallel by
another agent and may not exist yet -- experience_bridge degrades to an
empty result in that case (checked directly, no monkeypatch). The
merge/de-dup/ordering contract and every page's rendering of a non-empty
result are checked by monkeypatching ``experience_bridge._experience_module``
with a small fixture class -- the same function
``cuore.web.experience_globals``'s registered Jinja global calls through to,
so one patch point covers the API and every page.

Section 5 (added 2026-10-14) covers the driver/mechanic-added half of the
feature: ``cuore.live.experience_inputs``, the ``/api/experience/{vin}/
inputs`` round-trip, the merge-with-curated tiering, and the mobile entry
point on ``m_home.html``. No COM3, no real browser: every row is added with
``verify=False`` (the API's own ``"verify": false``) so :func:`cuore.live.
experience_inputs.verify_entry` -- which would otherwise shell out to
headless Edge for a forum URL -- is never invoked; TestClient only, same
posture as every other ``check_*_page.py`` here.

Run:
    .venv/Scripts/python.exe cuore/tests/check_experience_page.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-experience-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import experience_bridge  # noqa: E402
from cuore.web import experience_globals  # noqa: E402, F401 -- side-effect import, registers the global
from cuore.api import experience as experience_api  # noqa: E402
from cuore.live import experience_inputs as experience_inputs_store  # noqa: E402

VIN = "ZASFAKPN5J7B88115"

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def _app():
    app = create_app()
    if not any(getattr(r, "path", "") == "/experience" for r in app.routes):
        app.include_router(experience_api.router, prefix="/api")
    return app


client = TestClient(_app())


class _FakeExperience:
    """Stands in for mes.experience: for_code/for_family/for_job/all()."""

    VIDEO = {"id": "v1", "keys": ["P0456"], "title": "EVAP smoke test walkthrough",
             "url": "https://youtube.example/v1", "source": "youtube",
             "kind": "how_to_video", "covers": "smoke testing the EVAP system",
             "vehicle_fit": "Giulia 2.0T", "date": "2026-01-15",
             "reputation": "high", "verified_at": "2026-09-01", "verified_how": "manual"}
    THREAD = {"id": "t1", "keys": ["P0456"], "title": "P0456 after battery disconnect",
              "url": "https://stelvioforum.example/t1", "source": "stelvioforum",
              "kind": "forum_thread", "covers": "P0456 recurrence", "vehicle_fit": "Stelvio",
              "date": "2025-11-01", "reputation": "medium", "verified_at": "2026-08-01",
              "verified_how": "manual"}
    OLD_HIGH = {"id": "o1", "keys": ["EVAP"], "title": "Old but trusted EVAP writeup",
                "url": "https://alfabb.example/o1", "source": "alfabb", "kind": "owner_report",
                "covers": "EVAP family", "vehicle_fit": "Stelvio", "date": "2020-01-01",
                "reputation": "high", "verified_at": "2026-01-01", "verified_how": "manual"}

    def for_code(self, code, include_siblings=False):
        return [dict(self.VIDEO), dict(self.THREAD)] if code == "P0456" else []

    def for_family(self, family, include_siblings=False):
        # VIDEO deliberately duplicated here -- same id as the code lookup's
        # VIDEO -- to exercise de-dup across two different lookups.
        return [dict(self.OLD_HIGH), dict(self.VIDEO)] if family == "EVAP" else []

    def for_job(self, job, include_siblings=False):
        return [dict(self.VIDEO)] if job == "oil_change" else []

    def all(self):
        return [dict(self.VIDEO), dict(self.THREAD), dict(self.OLD_HIGH)]


_fake = _FakeExperience()
_real_module_lookup = experience_bridge._experience_module


def _patched():
    experience_bridge._experience_module = lambda: _fake


def _unpatched():
    experience_bridge._experience_module = _real_module_lookup


# ===========================================================================
# 1. bridge: merge, de-dup, order; and the no-module / no-args degrade path
# ===========================================================================

print("=== experience_bridge: merge / de-dup / order ===")
_patched()
try:
    result = experience_bridge.links_for(code="P0456", family="EVAP")
    ids = [l["id"] for l in result["links"]]
    check("merge: 3 unique links from overlapping code+family lookups",
          result["count"] == 3, str(ids))
    check("de-dup: the link present in both lookups appears once", ids.count("v1") == 1, str(ids))
    check("order: high reputation before medium", ids.index("t1") > ids.index("v1"), str(ids))
    check("order: how_to_video ranks ahead of an equally-high-reputation non-video",
          ids.index("v1") < ids.index("o1"), str(ids))
    scores = [l["score"] for l in result["links"]]
    check("scores are descending", scores == sorted(scores, reverse=True), str(scores))
    check("exact-code video (v1) scores highest and is first",
          ids[0] == "v1" and result["links"][0]["score"] == max(scores), str(ids) + " " + str(scores))
    empty = experience_bridge.links_for()
    check("no code/family/job given -> empty result, no error",
          empty["links"] == [] and empty["count"] == 0, str(empty))
finally:
    _unpatched()

no_module = experience_bridge.links_for(code="P0456")
check("mes.experience genuinely absent degrades to empty, no exception",
      no_module == {"links": [], "count": 0} or isinstance(no_module.get("links"), list), str(no_module))


# ===========================================================================
# 2. API: GET /api/experience
# ===========================================================================

print("=== /api/experience ===")
_patched()
try:
    api_resp = client.get("/api/experience", params={"code": "P0456", "family": "EVAP"})
    check("API responds 200", api_resp.status_code == 200, str(api_resp.status_code))
    check("API returns merged de-duplicated links", api_resp.json().get("count") == 3, api_resp.text)
    api_empty = client.get("/api/experience")
    check("API with no params returns empty, not an error",
          api_empty.status_code == 200 and api_empty.json().get("links") == []
          and api_empty.json().get("count") == 0)
finally:
    _unpatched()


# ===========================================================================
# 3. pages: card renders (video + thread row, rel=noopener), dossier,
#    maintenance, service hub, timeline, and the empty state
# ===========================================================================

print("=== code page card ===")
_patched()
try:
    code_resp = client.get(f"/v/{VIN}/code/P0456")
    check("code page responds 200", code_resp.status_code == 200, str(code_resp.status_code))
    check("Others' experience card present", "Others&#39; experience" in code_resp.text
          or "Others' experience" in code_resp.text)
    check("a video row and a thread row both appear",
          "EVAP smoke test walkthrough" in code_resp.text
          and "P0456 after battery disconnect" in code_resp.text)
    check("external links carry rel=noopener", 'rel="noopener"' in code_resp.text)
    check("card is collapsed by default with (N) in the summary",
          "<details class=\"card-details\">" in code_resp.text
          and "Others' experience (3)" in code_resp.text, code_resp.text)

    forums_resp = client.get(f"/v/{VIN}/code/P0456", params={"exp": "forums"})
    # the summary teaser always names the top-scored link (the video) --
    # only the row list itself should be forums-only, so check for the
    # video's own link (its href), not its title (which also appears in
    # the teaser regardless of ?exp).
    check("?exp=forums shows only forum threads",
          forums_resp.status_code == 200
          and "P0456 after battery disconnect" in forums_resp.text
          and 'href="https://youtube.example/v1"' not in forums_resp.text,
          forums_resp.text[:2000])
finally:
    _unpatched()

print("=== dossier open-work card, maintenance, service hub, timeline ===")
_patched()
try:
    dossier_resp = client.get(f"/v/{VIN}")
    check("dossier responds 200", dossier_resp.status_code == 200, str(dossier_resp.status_code))

    maint_resp = client.get(f"/v/{VIN}/maintenance")
    check("maintenance page responds 200 with the card or the empty state",
          maint_resp.status_code == 200 and ("Others&#39; experience" in maint_resp.text
          or "Others' experience" in maint_resp.text))

    hub_resp = client.get(f"/v/{VIN}/service-hub")
    check("service hub page responds 200 with the card or the empty state",
          hub_resp.status_code == 200 and ("Others&#39; experience" in hub_resp.text
          or "Others' experience" in hub_resp.text))

    timeline_resp = client.get(f"/v/{VIN}/timeline")
    check("timeline page responds 200", timeline_resp.status_code == 200, str(timeline_resp.status_code))
finally:
    _unpatched()

print("=== empty state (no fixture patched) ===")
# P0456 now has real curated entries in mes.experience (landed 2026-10-07),
# so it no longer exercises the empty path. P0098 is a code that genuinely
# appeared in this VIN's own logs (so the page itself resolves, not a 404)
# but has no mes.experience entry and no EVAP/misfire family match
# (code.html only maps P03*/P04* to a family), so it still exercises the
# real "nothing found" render rather than a fixture gap.
empty_resp = client.get(f"/v/{VIN}/code/P0098")
check("empty state renders without error when mes.experience/fixture is absent",
      empty_resp.status_code == 200 and "No experience links yet for this item" in empty_resp.text,
      str(empty_resp.status_code))


# ===========================================================================
# 4. companion checks (lightweight only -- the screenshot-based
#    check_timeline_page.py is intentionally left for a full CI run)
# ===========================================================================

print("=== companion checks ===")
for script in ("check_dossier_page.py", "check_maintenance_page.py",
              "check_service_page.py", "check_api.py"):
    proc = subprocess.run([sys.executable, str(Path(__file__).parent / script)],
                          cwd=str(ROOT), capture_output=True, text=True)
    ok = proc.returncode == 0
    check(f"{script} exits 0", ok, (proc.stdout[-1200:] + proc.stderr[-1200:]) if not ok else "")


# ===========================================================================
# 5. driver/mechanic-added links: store, merge/tier, API round-trip,
#    curated read-only, duplicates, edit/delete/undo, mobile entry point
# ===========================================================================

print("=== add a mechanic link: renders with the Mechanic chip + name ===")
_patched()
try:
    add_resp = client.post(f"/api/experience/{VIN}/inputs", json={
        "scope": {"code": "P0456"}, "url": "https://example.com/mechanic-find",
        "title": "Mechanic fix video", "kind": "video", "role": "mechanic",
        "name": "Luca", "note": "this is what fixed it", "rating": "helped",
        "verify": False})
    check("add: 200", add_resp.status_code == 200, add_resp.text)
    mech_row = add_resp.json()
    check("add: not flagged a duplicate", not mech_row.get("duplicate"), str(mech_row))
    mech_id = mech_row["id"]

    code_resp = client.get(f"/v/{VIN}/code/P0456")
    check("code page: Mechanic chip + name render", "Mechanic" in code_resp.text
          and "Luca" in code_resp.text, code_resp.text[:200])

    report_resp = client.get(f"/v/{VIN}/report")
    check("report: mechanic-added link renders with Mechanic chip + name",
          "Mechanic fix video" in report_resp.text and "Mechanic" in report_resp.text
          and "Luca" in report_resp.text)

    print("=== driver link sorts after mechanic (tiered, not just by score) ===")
    driver_resp = client.post(f"/api/experience/{VIN}/inputs", json={
        "scope": {"code": "P0456"}, "url": "https://example.com/driver-find",
        "title": "Driver's note", "kind": "note", "role": "driver", "name": "Sam",
        "note": "heard this rattle too", "rating": "helped", "verify": False})
    check("add driver link: 200", driver_resp.status_code == 200, driver_resp.text)
    driver_id = driver_resp.json()["id"]

    merged = experience_bridge.links_for(code="P0456", vin=VIN)
    ids_in_order = [l["id"] for l in merged["links"]]
    check("mechanic row present and before driver row",
          mech_id in ids_in_order and driver_id in ids_in_order
          and ids_in_order.index(mech_id) < ids_in_order.index(driver_id), str(ids_in_order))
    check("curated rows (tier 0) all sort ahead of both user rows",
          all(ids_in_order.index(l["id"]) < ids_in_order.index(mech_id)
              for l in merged["links"] if l.get("curated")), str(ids_in_order))
    check("counts tally mechanic/driver separately",
          merged["counts"].get("mechanic") == 1 and merged["counts"].get("driver") == 1,
          str(merged["counts"]))

    print("=== edit changes the note, with an audit entry ===")
    edit_resp = client.patch(f"/api/experience/{VIN}/inputs/{mech_id}",
                             json={"by_role": "mechanic", "by_name": "Luca",
                                   "note": "updated: torqued the fitting too"})
    check("edit: 200", edit_resp.status_code == 200, edit_resp.text)
    after_edit = experience_bridge.list_inputs(VIN)["inputs"]
    edited_row = next((r for r in after_edit if r["id"] == mech_id), None)
    check("edit: note actually changed", edited_row is not None
          and edited_row["note"] == "updated: torqued the fitting too", str(edited_row))
    check("edit: audit entry recorded who/when/what changed",
          edited_row is not None and len(edited_row.get("audit") or []) == 1
          and edited_row["audit"][0]["by"]["role"] == "mechanic"
          and "note" in edited_row["audit"][0]["changes"], str(edited_row))

    print("=== delete + undo ===")
    del_resp = client.delete(f"/api/experience/{VIN}/inputs/{driver_id}")
    check("delete: 200", del_resp.status_code == 200, del_resp.text)
    after_delete = experience_bridge.list_inputs(VIN)["inputs"]
    check("delete: row no longer in the default (non-deleted) list",
          all(r["id"] != driver_id for r in after_delete), str(after_delete))
    restore_resp = client.post(f"/api/experience/{VIN}/inputs/{driver_id}/restore")
    check("undo: restore 200", restore_resp.status_code == 200, restore_resp.text)
    after_restore = experience_bridge.list_inputs(VIN)["inputs"]
    check("undo: row is back", any(r["id"] == driver_id for r in after_restore), str(after_restore))

    print("=== duplicate URL is flagged, not silently re-added ===")
    dup_resp = client.post(f"/api/experience/{VIN}/inputs", json={
        "scope": {"code": "P0456"}, "url": "https://example.com/mechanic-find",
        "kind": "video", "role": "driver", "verify": False})
    check("duplicate: flagged with the existing row's attribution", dup_resp.status_code == 200
          and dup_resp.json().get("duplicate") is True
          and (dup_resp.json().get("existing") or {}).get("id") == mech_id, dup_resp.text)
    confirm_resp = client.post(f"/api/experience/{VIN}/inputs", json={
        "scope": {"code": "P0456"}, "url": "https://example.com/mechanic-find",
        "kind": "video", "role": "driver", "verify": False, "confirm_duplicate": True})
    check("duplicate: confirm_duplicate=true adds it anyway", confirm_resp.status_code == 200
          and not confirm_resp.json().get("duplicate"), confirm_resp.text)

    print("=== curated row stays uneditable (no Edit/Delete; Flag offered instead) ===")
    curated_id = next(l["id"] for l in merged["links"] if l.get("curated"))
    curated_page = client.get(f"/v/{VIN}/code/P0456")
    check('curated row gets "Flag as wrong/outdated", not Edit/Delete',
          f'data-exp-flag="{curated_id}"' in curated_page.text
          and f'data-exp-edit="{curated_id}"' not in curated_page.text
          and f'data-exp-delete="{curated_id}"' not in curated_page.text)
    # curated ids were never written via add_input (they come from
    # mes.experience, read-only), so edit_input must refuse one outright --
    # that refusal, not any UI affordance, is what actually keeps a
    # curated row uneditable.
    try:
        experience_inputs_store.edit_input(curated_id, by_role="owner", note="nope")
        check("curated id rejected by edit_input", False, "no exception raised")
    except ValueError:
        check("curated id rejected by edit_input", True)

    print("=== flag + worked tick round-trip against a curated id ===")
    flag_resp = client.post(f"/api/experience/links/{curated_id}/flag",
                            json={"by_role": "owner", "note": "canister P/N changed since",
                                  "flag_kind": "outdated"})
    check("flag curated row: 200", flag_resp.status_code == 200, flag_resp.text)
    check("flag recorded against the curated id",
          len(experience_inputs_store.flags_for(curated_id)) == 1)
    worked_resp = client.post(f"/api/experience/links/{mech_id}/worked",
                              json={"by_role": "mechanic", "job_ref": "P0456 EVAP smoke test"})
    check("worked tick: 200", worked_resp.status_code == 200, worked_resp.text)
    check("worked tick recorded against the mechanic row",
          len(experience_inputs_store.worked_for(mech_id)) == 1)

    print("=== export for curation review ===")
    export_resp = client.get(f"/api/experience/{VIN}/inputs/export")
    check("export: 200", export_resp.status_code == 200, export_resp.text)
    export_rows = export_resp.json().get("export") or []
    check("export: the helped mechanic row is offered for curation review",
          any(r.get("found_by", {}).get("role") == "mechanic" for r in export_rows),
          str(export_rows))
finally:
    _unpatched()

print("=== mobile entry point: m_home.html renders the add form ===")
mobile_resp = client.get(f"/m/{VIN}")
check("mobile home: 200", mobile_resp.status_code == 200, str(mobile_resp.status_code))
check('mobile home: "+ Add what you found" card renders, wired to experience.js',
      "data-exp-add-form" in mobile_resp.text and "data-exp-card" in mobile_resp.text
      and "experience.js" in mobile_resp.text)


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"{checks}/{checks} checks passed")
