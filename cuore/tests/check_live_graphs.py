"""Checks for the live list sort bar (Live board) and the stacked Graphs panel (Gauges page).

Rendered-HTML/JS checks only: no adapter, no COM port, no browser.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_live_graphs.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-graphs-")
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.web import live_dashboard_routes  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
STATIC = ROOT / "cuore" / "web" / "static"
fails: list[str] = []


def check(name: str, ok: bool) -> None:
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


app = create_app()
if not any(getattr(r, "path", "") == "/v/{vin}/gauges" for r in app.routes):
    app.include_router(live_dashboard_routes.router)
c = TestClient(app)

g = c.get(f"/v/{VIN}/gauges")
check("gauges page 200", g.status_code == 200)
html = g.text
check("graphs panel + count control + script present",
      'id="gg-panel"' in html and 'id="gg-count"' in html and "live/graphs.js" in html)

lb = c.get(f"/v/{VIN}/liveboard")
check("liveboard 200 with sort bar (hidden until JS) and 4 sort options",
      lb.status_code == 200 and 'id="lb-sortbar"' in lb.text and " hidden>" in lb.text.split('id="lb-sortbar"')[1][:200]
      and all(f'data-sort="{m}"' in lb.text for m in ("name", "value", "alarm", "group")))

js = (STATIC / "live" / "graphs.js").read_text(encoding="utf-8")
check("graphs.js reads the --fs-md token, no hard-coded font size",
      "var(--fs-md)" in js and not re.search(r"font\s*=\s*['\"]\d+px", js))
check("graphs.js binds no digit keys and no keydown",
      "keydown" not in js and "keypress" not in js)
check("graphs.js per-VIN localStorage + token on API calls",
      "cuore.gg." in js and "encodeURIComponent(this.token)" in js)
css = (STATIC / "live" / "dashboard.css").read_text(encoding="utf-8")
check("graphs css uses only --fs-* tokens", not re.search(r"\.gg-[^{]*\{[^}]*font-size:\s*\d", css))

# Pure helpers (cursor value lookup, min/max) executed under node when available.
try:
    out = subprocess.run(
        ["node", "-e",
         "global.window=global;global.document=undefined;require(%r);"
         "const G=window.CuoreGraphs;const h=[[1,5],[2,9],[3,7]];"
         "console.log(JSON.stringify([G.valueAt(h,2.5),G.minMax(h,2),G.valueAt(h,0.5)]))" % str(STATIC / "live" / "graphs.js")],
        capture_output=True, text=True, timeout=20)
    check("valueAt/minMax helpers", out.stdout.strip() == '[[2,9],{"min":7,"max":9},null]')
except FileNotFoundError:
    print("SKIP helpers (node not installed)")

print("FAILED" if fails else "ALL PASSED")
sys.exit(1 if fails else 0)
