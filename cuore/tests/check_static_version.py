"""Smoke checks for cache-busted static assets (cuore/web/static_version.py).

Same lightweight TestClient posture as ``check_dossier_page.py``:
``CUORE_STATE_DIR`` is pointed at a throwaway directory before cuore is
imported, so this needs no real corpus. ``/tools`` is used as the page under
test because it renders with no VIN and no auth token configured.

Two checks:

  1. A rendered page's ``cuore.css`` link carries a ``?v=`` cache-buster
     (``base.html`` -> ``static_url('cuore.css')``).
  2. A response actually served from the ``/static`` mount carries
     ``Cache-Control: no-cache, must-revalidate`` (the middleware in
     ``cuore.app.create_app``), so a browser revalidates instead of
     serving a stale copy straight from disk cache.

Run:
    .venv/Scripts/python.exe cuore/tests/check_static_version.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: state goes to a throwaway directory.
os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-staticver-")
os.environ.pop("CUORE_AUDIT_PATH", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())

page = client.get("/tools")
check("the tools page loads", page.status_code == 200, str(page.status_code))
check("its cuore.css link carries a cache-busting ?v=",
      'static/cuore.css?v=' in page.text, page.text[:4000])

static_resp = client.get("/static/cuore.css")
check("the /static response loads", static_resp.status_code == 200,
      str(static_resp.status_code))
check("the /static response carries the no-cache header",
      static_resp.headers.get("cache-control", "") == "no-cache, must-revalidate",
      repr(static_resp.headers.get("cache-control")))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
