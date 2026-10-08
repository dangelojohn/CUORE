"""Smoke checks for the feedback UI: data-fact on the dossier, the no-JS
plain-form POST, the inbox listing, the answer form, and the counts
endpoint reflecting it.

``CUORE_STATE_DIR`` is pointed at a fresh tempdir BEFORE anything cuore/mes
is imported (same posture as ``check_parts_page.py``). Neither
``cuore.web.inbox_routes`` nor ``cuore.api.feedback`` is wired into
``cuore.app`` yet -- ``app.py`` is owned by another agent -- so this
includes them itself if ``create_app()`` did not already pick them up (same
posture as ``check_parts_page.py``/``check_timeline_page.py``).

Run:
    .venv/Scripts/python.exe cuore/tests/check_feedback_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-feedback-page-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import inbox_routes  # noqa: E402
from cuore.api import feedback as feedback_api  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def _app_with_router():
    app = create_app()
    if not any(getattr(r, "path", "") == "/v/{vin}/inbox" for r in app.routes):
        app.include_router(inbox_routes.router)
    if not any(getattr(r, "path", "") == "/api/vehicles/{vin}/feedback" for r in app.routes):
        app.include_router(feedback_api.router, prefix="/api")
    return app


client = TestClient(_app_with_router())


# === 1. the dossier carries data-fact and the feedback script ==============

r = client.get(f"/v/{VIN}")
check("dossier responds 200", r.status_code == 200, str(r.status_code))
check("dossier carries at least one data-fact attribute", 'data-fact="verdict|"' in r.text)
check("dossier loads feedback.js", "feedback.js" in r.text)
check("dossier carries the whole-page feedback FAB", 'id="feedback-fab"' in r.text)
check("dossier carries the no-JS feedback panel", 'id="feedback-page-panel"' in r.text)

# === 2. plain-form POST creates feedback and redirects back ================

r = client.post(f"/v/{VIN}/feedback", data={
    "redirect_to": f"/v/{VIN}",
    "page": f"/v/{VIN}", "section": "verdict", "item": "",
    "label": "(whole page)", "kind": "question",
    "text": "is this verdict still current after the smoke test?",
    "author": "tech1",
}, follow_redirects=False)
check("no-JS feedback POST redirects", r.status_code == 303, str(r.status_code))
check("redirects back to the page it came from", r.headers.get("location") == f"/v/{VIN}")

# === 3. inbox lists it, linking back to the page =============================

r = client.get(f"/v/{VIN}/inbox")
check("inbox page responds 200", r.status_code == 200, str(r.status_code))
check("inbox lists the question", "is this verdict still current" in r.text)
check("inbox links back to the dossier", f'href="/v/{VIN}' in r.text)

fb_rows = client.get(f"/api/vehicles/{VIN}/feedback").json()["feedback"]
check("exactly one feedback row recorded", len(fb_rows) == 1, str(len(fb_rows)))
fb_id = fb_rows[0]["id"]
check("row starts open", fb_rows[0]["status"] == "open", fb_rows[0]["status"])

# === 4. the answer form sets status answered ================================

r = client.post(f"/v/{VIN}/feedback/{fb_id}/answer", data={
    "redirect_to": f"/v/{VIN}/inbox",
    "text": "yes -- re-run after the latest clean scan, still VERIFIED_CLEAN.",
    "by": "claude",
}, follow_redirects=False)
check("answer POST redirects", r.status_code == 303, str(r.status_code))

answered = client.get(f"/api/vehicles/{VIN}/feedback").json()["feedback"][0]
check("row is now answered", answered["status"] == "answered", answered["status"])
check("answer text stored", "VERIFIED_CLEAN" in answered["answer"]["text"])

r = client.get(f"/v/{VIN}/inbox")
check("inbox shows the answer text", "VERIFIED_CLEAN" in r.text)

# === 5. the counts endpoint reflects it ======================================

key = f"/v/{VIN}|verdict|"
r = client.get(f"/api/vehicles/{VIN}/feedback/counts?targets={key}")
check("counts endpoint responds 200", r.status_code == 200, str(r.status_code))
tallies = r.json()["counts"].get(key)
check("counts show one answered, zero open", tallies == {"open": 0, "answered": 1,
                                                          "confirms": 0, "corrections": 0},
      str(tallies))


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(" -", f)
if failures:
    sys.exit(1)
