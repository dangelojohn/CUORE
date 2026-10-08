"""Checks for the "Others' experience" feature: cuore/services/experience_bridge.py,
cuore/api/experience.py, and the _experience.html card included on code.html,
vehicle.html (dossier open-work), maintenance.html, service_hub.html and
timeline.html.

mes.experience (for_code/for_family/for_job/all) is built in parallel by
another agent and may not exist yet -- experience_bridge degrades to an
empty result in that case (checked directly, no monkeypatch). The
merge/de-dup/ordering contract and every page's rendering of a non-empty
result are checked by monkeypatching ``experience_bridge._experience_module``
with a small fixture class -- the same function
``cuore.web.experience_globals``'s registered Jinja global calls through to,
so one patch point covers the API and every page.

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

    def for_code(self, code):
        return [dict(self.VIDEO), dict(self.THREAD)] if code == "P0456" else []

    def for_family(self, family):
        # VIDEO deliberately duplicated here -- same id as the code lookup's
        # VIDEO -- to exercise de-dup across two different lookups.
        return [dict(self.OLD_HIGH), dict(self.VIDEO)] if family == "EVAP" else []

    def for_job(self, job):
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
    empty = experience_bridge.links_for()
    check("no code/family/job given -> empty result, no error",
          empty == {"links": [], "count": 0}, str(empty))
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
          api_empty.status_code == 200 and api_empty.json() == {"links": [], "count": 0})
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


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"{checks}/{checks} checks passed")
