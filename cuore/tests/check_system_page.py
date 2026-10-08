"""Checks for the per-system dive-in page (``/v/{vin}/systems/{key}``,
phase 1 -- see ``cuore/services/system_detail_bridge.py``).

No Edge/CDP here -- ``fastapi.testclient.TestClient`` only, per this
feature's own test instructions. ``CUORE_STATE_DIR`` is pointed at a
throwaway directory before ``cuore`` is imported (same posture as
``cuore/tests/check_systems_page.py``), and ``cuore/web/system_routes.py``
is included on the app itself if ``create_app()`` did not already pick it
up.

Run:
    .venv/Scripts/python.exe cuore/tests/check_system_page.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-system-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import systems_bridge  # noqa: E402
from cuore.web import system_routes, systems_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

#: the 8 section headings every system page must carry, exactly as
#: cuore/web/templates/system.html renders them (h2 text, counts stripped).
SECTION_HEADINGS = [
    "Status", "Relationships", "Components", "How it fails here",
    "Hypotheses", "What this car has taught", "Others' experience",
    "What else should I look at?",
]

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def _app_with_routers():
    app = create_app()
    if not any(getattr(r, "path", "").startswith("/v/{vin}/systems/{key}") for r in app.routes):
        app.include_router(system_routes.router)
    if not any(getattr(r, "path", "") == "/v/{vin}/systems" for r in app.routes):
        app.include_router(systems_routes.router)
    return app


client = TestClient(_app_with_routers())

print("=== all 25 system keys render 200 with the 8 section headings ===")
all_keys = list(systems_bridge.systems().keys())
check("systems() returned the expected 25 keys", len(all_keys) == 25, str(len(all_keys)))

for key in all_keys:
    resp = client.get(f"/v/{VIN}/systems/{key}")
    ok = resp.status_code == 200
    check(f"{key}: page responds 200", ok, str(resp.status_code))
    if not ok:
        continue
    check(f"{key}: no template error leaked onto the page",
          "Jinja2" not in resp.text and "Traceback" not in resp.text)
    missing = [h for h in SECTION_HEADINGS if h not in resp.text]
    check(f"{key}: all 8 section headings present", not missing, str(missing))

print("=== EVAP page lists its chronic codes ===")
evap_resp = client.get(f"/v/{VIN}/systems/evap")
check("evap page responds 200", evap_resp.status_code == 200, str(evap_resp.status_code))
for code in ("P0440", "P0455", "P0456"):
    check(f"evap page lists {code}", f">{code}<" in evap_resp.text)

print("=== unknown key 404s ===")
bad_resp = client.get(f"/v/{VIN}/systems/not_a_real_system")
check("unknown system key responds 404", bad_resp.status_code == 404, str(bad_resp.status_code))

print("=== hot-only edges never say \"depends on\" ===")
# A system pair that only co-occurs (no documented dependency) must read
# "seen together on this car", never "depends on" -- the wording rule a
# dependency edge and a mere correlation must never share. Checked across
# every page's hot-only section, not just one system.
violations = []
for key in all_keys:
    resp = client.get(f"/v/{VIN}/systems/{key}")
    if resp.status_code != 200:
        continue
    text = resp.text
    marker = "Seen together on this car (no documented dependency)"
    if marker in text:
        section = text.split(marker, 1)[1]
        # Only the hot-only block itself (up to the next <details>) matters.
        section = section.split("</details>", 1)[0]
        if "depends on" in section.lower():
            violations.append(key)
check("no \"depends on\" wording inside any hot-only-edges block", not violations, str(violations))

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    print(f"{checks - len(failures)}/{checks} checks passed")
    sys.exit(1)
print(f"{checks}/{checks} checks passed")
