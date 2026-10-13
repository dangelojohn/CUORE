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


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(" -", f)
if failures:
    sys.exit(1)
