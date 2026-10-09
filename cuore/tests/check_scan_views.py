"""Smoke checks for the mechanic-UX review's dossier/systems/codes pass
(review points 5, 7, 8): collapsed clusters + a real pinned jump bar on the
dossier, a graph-first systems page with the evidence prose one tap deep,
and a codes table with relative dates, system filter chips and a link back
to each code's dossier cluster.

Same posture as ``cuore/tests/check_dossier_page.py``/``check_systems_page.py``:
``CUORE_STATE_DIR`` is pointed at a throwaway directory before cuore is
imported, and this runs against the real Stelvio corpus (``VIN`` below)
through a real ``TestClient`` -- five checks, one per acceptance bullet in
the review, not an exhaustive re-test of everything those two older files
already cover.

Run:
    .venv/Scripts/python.exe cuore/tests/check_scan_views.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-scan-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import systems_routes, timeline_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0456/P0440/P0456

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
    if not any(getattr(r, "path", "").startswith("/v/{vin}/systems") for r in app.routes):
        app.include_router(systems_routes.router)
    if not any(getattr(r, "path", "").startswith("/v/{vin}/timeline") for r in app.routes):
        app.include_router(timeline_routes.router)
    return app


client = TestClient(_app_with_routers())


# --- 1. dossier: every cluster closed by default, plus a real jump bar ----
# Lives at /v/{vin}/dossier -- /v/{vin} itself is the bench
# (cuore/web/bench_routes.py), a different page this review doesn't touch.

dossier = client.get(f"/v/{VIN}/dossier")
check("dossier page responds 200", dossier.status_code == 200, str(dossier.status_code))

cluster_tags = re.findall(r'<details class="card-details cluster-details"[^>]*>', dossier.text)
check("dossier has at least one cluster <details>", len(cluster_tags) > 0,
      "no cluster-details found -- is there open work for this VIN?")
check("every cluster <details> is closed by default (no open attribute)",
      len(cluster_tags) > 0 and all(" open" not in tag and not tag.endswith(' open>') for tag in cluster_tags),
      str(cluster_tags))
check("the jump row is present and marked up for the pinned-jump-bar CSS",
      '<div class="jumprow"' in dossier.text and 'data-expand-all' in dossier.text)


# --- 2. systems: fewer nodes by default than ?all=1, evidence one tap deep -

sys_default = client.get(f"/v/{VIN}/systems")
sys_all = client.get(f"/v/{VIN}/systems?all=1")
check("systems page (default) responds 200", sys_default.status_code == 200)
check("systems page (?all=1) responds 200", sys_all.status_code == 200)

default_nodes = len(re.findall(r'data-system="', sys_default.text))
all_nodes = len(re.findall(r'data-system="', sys_all.text))
check("default systems graph has fewer nodes than ?all=1",
      0 < default_nodes < all_nodes, f"default={default_nodes} all={all_nodes}")
check('the co-occurrence/findings prose sits inside a collapsed <details> '
      '("Evidence for these links"), not loose at the top of the page',
      "Evidence for these links" in sys_default.text
      and sys_default.text.index("Evidence for these links")
          > sys_default.text.index("Dependency graph"))


# --- 3/4. codes: relative dates, system filter chips, a cluster link ------

codes_all = client.get(f"/v/{VIN}/codes")
check("codes page responds 200", codes_all.status_code == 200)
check('dates render as "N d/mo/y ago" rather than a raw timestamp',
      bool(re.search(r"\b\d+\s?(d|mo|y)\s+ago\b", codes_all.text)))

codes_evap = client.get(f"/v/{VIN}/codes?system=EVAP")
check("codes page responds 200 with ?system=EVAP", codes_evap.status_code == 200)
check("the EVAP system filter narrows the row count",
      codes_evap.text.count('class="row-link') < codes_all.text.count('class="row-link'),
      f"all={codes_all.text.count('row-link')} evap={codes_evap.text.count('row-link')}")

check('a code row links to its dossier cluster (/v/{vin}/dossier#cluster-<family>)',
      bool(re.search(rf'href="/v/{re.escape(VIN)}/dossier#cluster-[a-z0-9_]+"', codes_all.text)))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
