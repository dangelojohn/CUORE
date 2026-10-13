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


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(" -", f)
if failures:
    sys.exit(1)
