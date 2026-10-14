"""Smoke checks for "Tell CUORE" (cuore/live/owner_events.py,
cuore/services/owner_events_bridge.py, cuore/api/owner_events.py,
cuore/web/owner_routes.py).

``CUORE_STATE_DIR`` is pointed at a fresh tempdir BEFORE anything cuore/mes
is imported (same posture as ``check_feedback_page.py``). Neither
``cuore.web.owner_routes`` nor ``cuore.api.owner_events`` is wired into
``cuore.app`` yet -- ``app.py`` is owned by another agent -- so this
includes them itself if ``create_app()`` did not already pick them up.

TestClient only, no Edge, no subprocess server -- everything here runs
against one in-process app.

Run:
    .venv/Scripts/python.exe cuore/tests/check_owner_page.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-owner-page-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import owner_routes  # noqa: E402
from cuore.api import owner_events as owner_events_api  # noqa: E402
from cuore.live import owner_events as store  # noqa: E402
from cuore.services import mes_bridge, systems_bridge  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, has EVAP codes

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def _app_with_router():
    app = create_app()
    if not any(getattr(r, "path", "") == "/m/{vin}" for r in app.routes):
        app.include_router(owner_routes.router)
    if not any(getattr(r, "path", "") == "/owner/{vin}/taxonomy" for r in app.routes):
        app.include_router(owner_events_api.router, prefix="/api")
    return app


client = TestClient(_app_with_router())

VALID_SYSTEM_KEYS = set(systems_bridge.systems().keys())


# === 1. taxonomy shape =======================================================

tax = store.TAXONOMY
check("taxonomy has at least 8 categories", len(tax) >= 8, str(len(tax)))
total_kinds = sum(len(c["kinds"]) for c in tax.values())
check("taxonomy has at least 40 kinds", total_kinds >= 40, str(total_kinds))

bad_systems = []
for cat_key, cat in tax.items():
    for kind_key, kd in cat["kinds"].items():
        for sys_key in kd["systems"]:
            if sys_key not in VALID_SYSTEM_KEYS:
                bad_systems.append(f"{cat_key}/{kind_key}: {sys_key}")
check("every kind's systems are valid mes.systems keys", not bad_systems, "; ".join(bad_systems))

r = client.get(f"/api/owner/{VIN}/taxonomy")
check("taxonomy API responds 200", r.status_code == 200, str(r.status_code))
check("taxonomy API carries the same category count",
      len(r.json()["categories"]) == len(tax))


# === 2. POST fill-up, stores and shows on history with "reported" label =====

r = client.post(f"/api/owner/{VIN}/events", json={
    "category": "fuel", "kind": "fill_up", "by_role": "owner",
    "fields": {"octane": "91", "cap_clicked": False, "litres": 42.0},
})
check("fill-up POST responds 200", r.status_code == 200, str(r.status_code))
fillup = r.json()
check("stored kind is fill_up", fillup.get("kind") == "fill_up")
check("stored confidence is 'reported'", fillup.get("confidence") == "reported")
fillup_id = fillup.get("id")
check("fill-up got an id", bool(fillup_id))

r = client.get(f"/m/{VIN}/history")
check("history page responds 200", r.status_code == 200, str(r.status_code))
check("history shows the fill-up", "Fill-up" in r.text)
check("history shows the 'reported' badge", "reported" in r.text.lower())


# === 3. bad kind -> 400 ======================================================

r = client.post(f"/api/owner/{VIN}/events", json={
    "category": "fuel", "kind": "not_a_real_kind", "by_role": "owner", "fields": {},
})
check("unknown kind returns 400", r.status_code == 400, str(r.status_code))

r = client.post(f"/api/owner/{VIN}/events", json={
    "category": "not_a_real_category", "kind": "fill_up", "by_role": "owner", "fields": {},
})
check("unknown category returns 400", r.status_code == 400, str(r.status_code))


# === 4. correlation: the fill-up as "possible link" for an EVAP code ========

evap_code = None
evap_at = None
try:
    dossier = mes_bridge.workup(vin=VIN)
    history = dossier.get("history") or {}
    for bucket in ("chronic", "returned_after_clear", "seen_once"):
        for rec in history.get(bucket, []):
            code = (rec.get("dtc") or "").split("-")[0].strip().upper()
            hits = systems_bridge.systems_for_code(code)
            if any(h.get("system") == "evap" for h in hits):
                occs = sorted(rec.get("occurrences", []), key=lambda o: o.get("timestamp") or "")
                if occs and occs[0].get("timestamp"):
                    evap_code, evap_at = code, occs[0]["timestamp"]
                    break
        if evap_code:
            break
except Exception as exc:  # noqa: BLE001
    check("could read this VIN's DTC history to find an EVAP code", False,
          f"{type(exc).__name__}: {exc}")

if evap_code and evap_at:
    near_at = (datetime.strptime(evap_at[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
              - timedelta(days=2)).isoformat(timespec="seconds")
    r = client.post(f"/api/owner/{VIN}/events", json={
        "category": "fuel", "kind": "fill_up", "by_role": "owner", "at": near_at,
        "fields": {"octane": "91", "cap_clicked": False},
    })
    check("second (near-EVAP-code) fill-up POST responds 200", r.status_code == 200,
          str(r.status_code))

    r = client.get(f"/api/owner/{VIN}/correlations")
    check("correlations endpoint responds 200", r.status_code == 200, str(r.status_code))
    corr = r.json().get("correlations", [])
    hit = next((c for c in corr if c.get("code") == evap_code), None)
    check(f"correlation found for {evap_code}", hit is not None, str(corr)[:300])
    if hit:
        check("correlation is worded 'owner-reported, possible link', never 'cause'",
              hit.get("note") == "owner-reported, possible link")
        check("correlation carries the near fill-up event",
              any(e.get("kind") == "fill_up" for e in hit.get("owner_events", [])))
else:
    check("found an EVAP code with a dated occurrence on this VIN to correlate against",
          False, "no EVAP-implicated code found in this VIN's corpus")


# === 5. messages: a CUORE prompt for an active EVAP code ====================

r = client.get(f"/api/owner/{VIN}/messages")
check("messages endpoint responds 200", r.status_code == 200, str(r.status_code))
msgs = r.json().get("messages", [])
check("at least one message exists", len(msgs) > 0, str(len(msgs)))
cuore_prompts = [m for m in msgs if m.get("author") == "cuore"]
check("messages include at least one CUORE-authored prompt", len(cuore_prompts) > 0,
      str(msgs)[:300])
if evap_code:
    evap_prompt = [m for m in cuore_prompts if m.get("target", {}).get("section") == evap_code]
    check(f"a CUORE prompt targets the active EVAP code {evap_code}", len(evap_prompt) > 0,
          str(cuore_prompts)[:300])

r = client.get(f"/m/{VIN}/messages")
check("messages page responds 200", r.status_code == 200, str(r.status_code))


# === 6. reply stores ==========================================================

if cuore_prompts:
    mid = cuore_prompts[0]["id"]
    r = client.post(f"/api/owner/{VIN}/messages/{mid}/reply",
                    json={"text": "yes, filled up two days ago, cap clicked", "by": "owner"})
    check("reply POST responds 200", r.status_code == 200, str(r.status_code))
    check("reply stored under answer.text",
          r.json().get("answer", {}).get("text", "").startswith("yes, filled up"))

    r = client.get(f"/api/owner/{VIN}/messages")
    replied = next((m for m in r.json()["messages"] if m["id"] == mid), None)
    check("message status is now answered", replied is not None
          and replied.get("status") == "answered", str(replied))


# === 7. /m/{vin} renders with the bottom nav, no desktop tab bar ============

r = client.get(f"/m/{VIN}")
check("/m/{vin} responds 200", r.status_code == 200, str(r.status_code))
check("mobile page carries the bottom nav", "m-bottomnav" in r.text)
check("mobile page has no desktop vtabs strip", 'class="vtabs"' not in r.text)
check("mobile page carries the ATTESTED footer", "ATTESTED" in r.text)
check("mobile page sets a phone viewport meta",
      'name="viewport"' in r.text and "width=device-width" in r.text)


# === 8. nothing under 12px in the mobile CSS (font sizes specifically --
# a 1px border or an 8px gap is normal layout, not the "nothing under 12px"
# rule, which is about text legibility) ======================================

css_path = ROOT / "cuore" / "web" / "static" / "m.css"
css_text = css_path.read_text(encoding="utf-8")
font_sizes = re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", css_text)
check("m.css declares at least one font-size", len(font_sizes) > 0)
too_small = [v for v in font_sizes if float(v) < 12]
check("no font-size in m.css is under 12px", not too_small, str(too_small))


# --- remembered free-text fields (oil filter brand etc.), 2026-10-13 --------
def _check_remembered_values() -> None:
    from cuore.live import owner_events as _store
    _store.add(VIN, "fluids", "engine_oil_change", by_role="mechanic",
               fields={"brand": "Selenia", "filter_brand": "UFI", "filter_part_no": "23.598.00"})
    _store.add("OTHERVIN00000001", "fluids", "engine_oil_change", by_role="mechanic",
               fields={"brand": "Petronas", "filter_brand": "Mann Filter"})
    rv = _store.recent_values(VIN, "engine_oil_change", "filter_brand")
    check("remembered: this car's filter brand first, then the garage's", rv[:2] == ["UFI", "Mann Filter"], str(rv))
    html = client.get(f"/m/{VIN}/add/fluids/engine_oil_change").text
    check("oil-change form: filter brand is open text with a datalist of last-used values",
          'name="filter_brand"' in html and 'list="dl-filter_brand"' in html and ">UFI<" in html)
    check("oil-change form: filter part number field present", 'name="filter_part_no"' in html)


_check_remembered_values()


# === 9. Mobile rebuild (2026-10-13): hero + quick actions + intro overlay ===

home_html = client.get(f"/m/{VIN}").text
check("home responds with the four quick-action tiles",
      home_html.count('class="m-quick-card') == 4, str(home_html.count('class="m-quick-card')))
for label in ("Fill-up", "Oil &amp; fluids", "Battery &amp; electrical", "Snap &amp; fill"):
    check(f"home shows the {label!r} quick action", label in home_html)
check("home carries the opening-reveal overlay markup",
      "intro-overlay" in home_html and 'id="intro-dismiss"' in home_html)


# === 10. fill-up form: octane chip preselects the last used =================

r = client.post(f"/api/owner/{VIN}/events", json={
    "category": "fuel", "kind": "fill_up", "by_role": "owner",
    "fields": {"octane": "93", "cap_clicked": True, "litres": 38.0, "station": "Petro-Canada"},
})
check("a second fill-up (octane 93) POST responds 200", r.status_code == 200, str(r.status_code))

fillup_form_html = client.get(f"/m/{VIN}/add/fuel/fill_up").text
check("fill-up form renders the octane chips", 'name="octane"' in fillup_form_html and ">93<" in fillup_form_html)
check("fill-up form preselects the last-used octane (93), not the earlier 91",
      'value="93" checked' in fillup_form_html, fillup_form_html.count('checked'))
check("fill-up form preselects the last-used station (Petro-Canada)",
      'value="Petro-Canada"' in fillup_form_html)


# === 11. snap page: camera tile with capture=environment ====================

snap_html = client.get(f"/m/{VIN}/snap").text
check("snap page responds 200 and carries the camera file input",
      'type="file"' in snap_html and 'capture="environment"' in snap_html
      and 'accept="image/*"' in snap_html)
check("snap page offers the hint chips", 'name="hint"' in snap_html)


# === 12. HTML form path: source_octane=photo -> fields_meta.octane=="photo" =

r = client.post(f"/m/{VIN}/add/fuel/fill_up", data={
    "station": "Shell", "octane": "91", "litres": "40", "price": "60",
    "source_octane": "photo",
}, follow_redirects=False)
check("fill-up form POST (source_octane=photo) redirects to the confirm screen",
      r.status_code == 303 and "/confirm/" in r.headers.get("location", ""),
      f"{r.status_code} {r.headers.get('location')}")
_confirm_event_id = r.headers.get("location", "").rsplit("/", 1)[-1]
_photo_event = next((e for e in store.load(VIN) if e.get("id") == _confirm_event_id), None)
check("the stored event exists", _photo_event is not None, _confirm_event_id)
if _photo_event:
    check("fields_meta.octane == 'photo' on the stored event",
          (_photo_event.get("fields_meta") or {}).get("octane") == "photo",
          str(_photo_event.get("fields_meta")))

confirm_html = client.get(r.headers.get("location", "")).text
check("confirm screen (record card) responds and shows the photo chip",
      "m-card" in confirm_html and "m-chip-photo" in confirm_html)


# === 13. JSON API: fields_meta accepted, validated to known field keys and
# to "photo"/"typed" values (the API-contract follow-up, 2026-10-13) ========

r = client.post(f"/api/owner/{VIN}/events", json={
    "category": "fuel", "kind": "fill_up", "by_role": "owner",
    "fields": {"octane": "89", "litres": 10.0},
    "fields_meta": {"octane": "photo", "not_a_real_field": "photo", "litres": "not-a-valid-value"},
})
check("JSON API accepts a fields_meta body key", r.status_code == 200, str(r.status_code))
_api_meta = (r.json().get("fields_meta") or {})
check("JSON API stores fields_meta.octane == 'photo'", _api_meta.get("octane") == "photo", str(_api_meta))
check("JSON API drops a fields_meta key that isn't a real field of this kind",
      "not_a_real_field" not in _api_meta, str(_api_meta))
check("JSON API drops a fields_meta value that isn't 'photo'/'typed'",
      "litres" not in _api_meta, str(_api_meta))


# === 14. the vision endpoint now exists (wired by another agent) but still
# defaults to provider "none" -- the Snap page's own no-JS POST must not
# depend on it ever succeeding ===============================================

vision_resp = client.post(f"/api/vision/{VIN}/read",
                          files={"file": ("x.jpg", b"not a real jpeg", "image/jpeg")},
                          data={"hint": "fuel_pump"})
check("vision endpoint responds 200 (default provider is 'none')",
      vision_resp.status_code == 200, str(vision_resp.status_code))
check("default vision provider reports unavailable (no key configured)",
      vision_resp.json().get("available") is False, str(vision_resp.json()))

snap_post = client.post(f"/m/{VIN}/snap",
                        files={"photo": ("pump.jpg", b"not a real jpeg", "image/jpeg")},
                        data={"hint": "fuel_pump"}, follow_redirects=False)
check("snap POST (no JS, vision unavailable) still redirects somewhere useful",
      snap_post.status_code == 303, str(snap_post.status_code))
check("snap's own fallback routes a fuel_pump hint straight to fuel/fill_up",
      "/add/fuel/fill_up" in snap_post.headers.get("location", ""),
      snap_post.headers.get("location"))
check("the photo taken on the snap screen carries through as media_id",
      "media_id=" in snap_post.headers.get("location", ""))


# === 15. Edit (2026-10-13): PATCH octane 91 -> 94, history shows it, audit
# has one entry, fields_meta flips to typed for the edited key only ========

r = client.post(f"/api/owner/{VIN}/events", json={
    "category": "fuel", "kind": "fill_up", "by_role": "owner",
    "fields": {"octane": "91", "litres": 40.0, "cap_clicked": True},
    "fields_meta": {"octane": "photo"},
})
check("fill-up to edit POSTs 200", r.status_code == 200, str(r.status_code))
edit_id = r.json()["id"]

r = client.patch(f"/api/owner/{VIN}/events/{edit_id}", json={
    "fields": {"octane": "94"}, "by_role": "mechanic",
})
check("PATCH edit responds 200", r.status_code == 200, str(r.status_code))
edited = r.json()

r = client.get(f"/api/owner/{VIN}/events")
stored = next((e for e in r.json()["events"] if e["id"] == edit_id), None)
check("stored event now shows octane 94", stored is not None
      and stored.get("fields", {}).get("octane") == "94", str(stored))
check("audit has exactly one entry", stored is not None and len(stored.get("audit") or []) == 1,
      str(stored.get("audit") if stored else None))
if stored:
    entry = stored["audit"][0]
    check("audit entry's by.role is the editor ('mechanic')",
          entry.get("by", {}).get("role") == "mechanic", str(entry))
    check("audit entry records only the octane change",
          list((entry.get("changes", {}).get("fields") or {}).keys()) == ["octane"], str(entry))
    check("fields_meta.octane flips to 'typed' (value actually changed)",
          (stored.get("fields_meta") or {}).get("octane") == "typed", str(stored.get("fields_meta")))
check("edited_at is set on the stored event", stored is not None and stored.get("edited_at"),
      str(stored.get("edited_at") if stored else None))

r = client.get(f"/m/{VIN}/history")
check("history page shows the edited octane (94)", "94" in r.text)
check("history page shows the 'Edited' marker", "Edited" in r.text)


# === 16. PATCH with an unknown field key -> 400 =============================

r = client.patch(f"/api/owner/{VIN}/events/{edit_id}", json={"fields": {"not_a_real_field": "x"}})
check("PATCH with an unknown field key returns 400", r.status_code == 400, str(r.status_code))


# === 17. PATCH on a deleted event -> 404 =====================================

r = client.post(f"/api/owner/{VIN}/events", json={
    "category": "fuel", "kind": "fill_up", "by_role": "owner", "fields": {"litres": 20.0},
})
to_delete_id = r.json()["id"]
r = client.delete(f"/api/owner/{VIN}/events/{to_delete_id}")
check("DELETE responds 200", r.status_code == 200, str(r.status_code))

r = client.patch(f"/api/owner/{VIN}/events/{to_delete_id}", json={"fields": {"litres": 25.0}})
check("PATCH on a deleted event returns 404", r.status_code == 404, str(r.status_code))

r = client.patch(f"/api/owner/{VIN}/events/not-a-real-id", json={"fields": {"litres": 25.0}})
check("PATCH on an unknown id returns 404", r.status_code == 404, str(r.status_code))


# === 18. Edit via the HTML form: GET prefills, POST stores, history shows it,
# and the Delete-at-bottom web action soft-deletes with an Undo screen =======

r = client.post(f"/m/{VIN}/add/fuel/fill_up", data={
    "station": "Costco", "octane": "91", "litres": "35", "price": "50",
}, follow_redirects=False)
html_edit_id = r.headers.get("location", "").rsplit("/", 1)[-1]

edit_form_html = client.get(f"/m/{VIN}/edit/{html_edit_id}").text
check("edit form responds and is titled 'Edit fill-up'", "Edit fill-up" in edit_form_html)
check("edit form prefills the saved octane (91)", 'value="91" checked' in edit_form_html)
check("edit form carries a Delete action", 'm-delete-btn' in edit_form_html
      and f"/m/{VIN}/history/{html_edit_id}/delete" in edit_form_html)
check("edit form carries a Cancel action", "Cancel" in edit_form_html)

r = client.post(f"/m/{VIN}/edit/{html_edit_id}", data={
    "station": "Costco", "octane": "94", "litres": "35", "price": "50",
    "by_role": "owner",
}, follow_redirects=False)
check("HTML edit form POST redirects to the edit confirm screen",
      r.status_code == 303 and f"/m/{VIN}/edit/{html_edit_id}/confirm" in r.headers.get("location", ""),
      f"{r.status_code} {r.headers.get('location')}")

confirm2 = client.get(r.headers.get("location", ""))
check("edit confirm screen shows 'Edited' and the audit disclosure",
      "Edited" in confirm2.text and "m-audit" in confirm2.text)

html_event = next((e for e in store.load(VIN) if e.get("id") == html_edit_id), None)
check("HTML-form edit actually stored octane 94",
      html_event is not None and html_event.get("fields", {}).get("octane") == "94",
      str(html_event))
check("HTML-form edit: litres/station/cap_clicked re-submitted unchanged add no spurious changes",
      html_event is not None and len(html_event.get("audit") or []) == 1
      and list((html_event["audit"][0].get("changes", {}).get("fields") or {}).keys()) == ["octane"],
      str(html_event.get("audit") if html_event else None))

r = client.post(f"/m/{VIN}/history/{html_edit_id}/delete", follow_redirects=False)
check("web Delete action redirects to the deleted/Undo screen",
      r.status_code == 303 and f"/m/{VIN}/deleted/{html_edit_id}" in r.headers.get("location", ""),
      f"{r.status_code} {r.headers.get('location')}")
deleted_html = client.get(r.headers.get("location", "")).text
check("deleted screen offers Undo", "Undo" in deleted_html)

r = client.get(f"/m/{VIN}/history")
check("deleted event no longer shows on history", html_edit_id not in r.text or "Costco" not in r.text)

r = client.post(f"/m/{VIN}/history/{html_edit_id}/restore", follow_redirects=False)
check("Undo (restore) redirects back to history", r.status_code == 303, str(r.status_code))
restored = next((e for e in store.load(VIN) if e.get("id") == html_edit_id), None)
check("restore brings the event back (not deleted)", restored is not None
      and not restored.get("deleted"), str(restored))


# === 19. Scan-done message + live-scan EVAP/network prompts with one-tap
# chip answers (2026-10-14). Fixture: real ``obd_dtcs``/``mode06``/
# ``module_dtcs`` observation lines for this VIN, read verbatim from
# ``C:\ProgramData\cuore\observations.jsonl`` at test time and appended to
# this test's own isolated ``CUORE_STATE_DIR`` -- the real file is only
# ever read, never written. ====================================================

_REAL_OBSERVATIONS = Path(r"C:\ProgramData\cuore\observations.jsonl")

#: The 2026-10-13 ~20:02-20:03 cluster: P0440 stored/pending/permanent, the
#: readiness read that tags the cluster with this VIN, and the Mode 06 read
#: carrying MID 3A's (large-leak) failed row.
_SCAN_DONE_AT = {"2026-10-13T20:02:56", "2026-10-13T20:02:57", "2026-10-13T20:02:58",
                "2026-10-13T20:03:00", "2026-10-13T20:03:54"}
#: The later BCM module scan carrying the active U1713-2F network code.
_BCM_AT = {"2026-10-13T20:24:25"}


def _copy_real_observation_lines(wanted_ats: set, ecu: str = "") -> list[str]:
    """Verbatim JSON lines from the real observations file whose own
    ``at`` is in ``wanted_ats`` (and, when ``ecu`` is given, whose
    ``data.ecu`` matches -- the 20:24:25 timestamp carries five separate
    ``module_dtcs`` rows, one per ECU). Read-only: this never opens the
    real file for writing."""
    if not _REAL_OBSERVATIONS.exists():
        return []
    out: list[str] = []
    for line in _REAL_OBSERVATIONS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("at") not in wanted_ats:
            continue
        if ecu and (obj.get("data") or {}).get("ecu") != ecu:
            continue
        out.append(line)
    return out


def _append_test_observations(lines: list[str]) -> None:
    from cuore.live import store as live_store
    p = live_store.observations_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def _badge_count(html: str) -> "int | None":
    m = re.search(r'class="m-badge">(\d+)<', html)
    return int(m.group(1)) if m else None


scan_fixture_lines = _copy_real_observation_lines(_SCAN_DONE_AT)
check("fixture: found the real P0440 + Mode 06 (MID 3A) lines to copy",
      len(scan_fixture_lines) == 5, str(len(scan_fixture_lines)))
_append_test_observations(scan_fixture_lines)

r = client.get(f"/api/owner/{VIN}/messages")
check("messages endpoint responds 200 after the scan fixture", r.status_code == 200, str(r.status_code))
msgs = r.json()["messages"]

scan_msgs = [m for m in msgs if m.get("target", {}).get("section") == "scan"]
check("exactly one scan-done message was filed", len(scan_msgs) == 1, str(scan_msgs)[:300])
scan_text = scan_msgs[0]["text"] if scan_msgs else ""
check("scan-done message says 'Scan 1 of 10'", "Scan 1 of 10" in scan_text, scan_text)
check("scan-done message asks not to clear the light", "don't clear" in scan_text, scan_text)
check("scan-done message names the fuel-vapour system not holding vacuum",
      "fuel-vapour" in scan_text and "vacuum" in scan_text, scan_text)
check("scan-done message names the large-leak test, not small/gross",
      "large-leak" in scan_text, scan_text)
check("scan-done message says nothing else failed",
      "Nothing else failed" in scan_text, scan_text)
check("scan-done message points at the ESIM switch test next",
      "ESIM switch test" in scan_text, scan_text)
check("scan-done message carries the EVAP owner actions (fill level/cap/overfill)",
      "cap" in scan_text and "top" in scan_text, scan_text)
check("scan-done message never says 'cause' or 'fixed'",
      "cause" not in scan_text.lower() and "fixed" not in scan_text.lower(), scan_text)

# Re-reading must not refile the same scan's note a second time.
r2 = client.get(f"/api/owner/{VIN}/messages")
scan_msgs2 = [m for m in r2.json()["messages"] if m.get("target", {}).get("section") == "scan"]
check("the scan-done message is deduped per scan id on a second read",
      len(scan_msgs2) == 1, str(scan_msgs2)[:300])

p0440_prompts = [m for m in msgs if m.get("author") == "cuore"
                and m.get("target", {}).get("section") == "P0440"]
check("a CUORE prompt fired for the active P0440", len(p0440_prompts) >= 1, str(p0440_prompts)[:300])
fillup_prompt = next((m for m in p0440_prompts
                      if m.get("target", {}).get("item") == "evap_fillup_recent"), None)
check("the fill-up/cap/pump question fired for P0440", fillup_prompt is not None,
      str(p0440_prompts)[:300])
if fillup_prompt:
    check("question covers fill-up, cap and pump-stop",
          all(s in fillup_prompt["text"] for s in ("fill up", "cap", "pump")),
          fillup_prompt["text"])
    check("the open question carries its one-tap chips",
          len(fillup_prompt.get("chips") or []) >= 3, str(fillup_prompt.get("chips")))

r = client.get(f"/m/{VIN}/messages")
check("messages page responds 200 with the scan-done note and chips",
      r.status_code == 200 and "Scan 1 of 10" in r.text and "m-chip-btn" in r.text,
      str(r.status_code))

# --- the later BCM scan: U1713-2F (active) fires the network prompt --------

bcm_fixture_lines = _copy_real_observation_lines(_BCM_AT, ecu="BCM")
check("fixture: found the real BCM module_dtcs line (U1713-2F)",
      len(bcm_fixture_lines) == 1, str(len(bcm_fixture_lines)))
_append_test_observations(bcm_fixture_lines)

r = client.get(f"/api/owner/{VIN}/messages")
msgs = r.json()["messages"]
u1713_prompts = [m for m in msgs if m.get("author") == "cuore"
                and m.get("target", {}).get("section") == "U1713"]
check("a CUORE prompt fired for the active BCM network code U1713",
      len(u1713_prompts) >= 1, str(msgs)[:400])
network_prompt = next((m for m in u1713_prompts
                       if m.get("target", {}).get("item") == "network_recent_elec"), None)
check("network prompt text covers aftermarket electrical, battery and car wash",
      network_prompt is not None
      and all(s in network_prompt["text"] for s in
             ("aftermarket electrical", "Battery changed", "Car washed")),
      str(network_prompt))

# --- reply -> matching owner event, via the JSON API (EVAP chip) -----------

if fillup_prompt:
    chip = next(c for c in fillup_prompt["chips"] if c.get("category"))
    open_before = sum(1 for m in msgs if m.get("status") == "open")
    home_before = _badge_count(client.get(f"/m/{VIN}").text)

    r = client.post(f"/api/owner/{VIN}/messages/{fillup_prompt['id']}/reply",
                    json={"text": chip["label"], "by": "owner"})
    check("chip-answer reply (JSON API) responds 200", r.status_code == 200, str(r.status_code))
    check("message is now answered", r.json().get("status") == "answered", str(r.json()))

    r = client.get(f"/api/owner/{VIN}/messages")
    open_after = sum(1 for m in r.json()["messages"] if m.get("status") == "open")
    check("open/unread message count drops by 1 after the reply",
          open_after == open_before - 1, f"{open_before} -> {open_after}")
    home_after = _badge_count(client.get(f"/m/{VIN}").text)
    check("home badge count drops by 1 after the reply",
          home_before is not None and home_after == home_before - 1,
          f"{home_before} -> {home_after}")

    new_event = next((e for e in store.load(VIN) if e.get("category") == "fuel"
                      and e.get("kind") == "fill_up"
                      and (e.get("fields") or {}).get("cap_clicked") is True
                      and (e.get("fields") or {}).get("overfilled") is False), None)
    check("the chip answer created the matching fuel/fill_up owner event",
          new_event is not None, str(new_event))

# --- reply -> matching owner event, via the HTML chip form (network chip) --

if network_prompt and network_prompt.get("chips"):
    chip2 = next(c for c in network_prompt["chips"] if c.get("category"))
    r = client.post(f"/m/{VIN}/messages/{network_prompt['id']}/reply",
                    data={"text": chip2["label"], "by": "mechanic"},
                    follow_redirects=False)
    check("HTML chip-form reply redirects to messages#saved",
          r.status_code == 303 and "messages#saved" in r.headers.get("location", ""),
          f"{r.status_code} {r.headers.get('location')}")
    new_event2 = next((e for e in store.load(VIN)
                       if e.get("category") == chip2["category"]
                       and e.get("kind") == chip2["kind"]
                       and e.get("by", {}).get("role") == "mechanic"), None)
    check(f"the network chip answer created a {chip2['category']}/{chip2['kind']} owner event",
          new_event2 is not None, str(new_event2))


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(" -", f)
if failures:
    sys.exit(1)
