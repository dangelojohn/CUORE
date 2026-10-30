"""Checks for site-wide search (/find, cuore/services/find.py, Menu-sheet search bar).
Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_find.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-find-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import interlock  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


TOKEN = "find-token-123"
Path(_TMP, "web_token.txt").write_text(TOKEN, encoding="utf-8")
c = TestClient(create_app(), follow_redirects=False, raise_server_exceptions=False)
c.get(f"/login?token={TOKEN}")


def best(q, vin=VIN):
    r = c.get("/find", params={"q": q, "vin": vin})
    m = re.search(r'class="find-best" href="([^"]+)">Go to: ([^<]*)', r.text)
    return r, (m.group(1) if m else ""), (m.group(2).strip() if m else "")


# 1. the bar in the Menu sheet
r = c.get("/catalog")
check("/catalog renders", r.status_code == 200, str(r.status_code))
bar = re.search(r'<div class="navsheet-bar">.*?</div>', r.text, re.S)
check("menu bar has search form to /find", bool(bar) and 'action="/find"' in bar.group(0) and 'name="q"' in bar.group(0))
check("placeholder text", "Search CUORE: a page, code, part, bulletin or task" in r.text)
check("accessible label", 'for="navsheet-q"' in r.text and 'type="search"' in r.text)
check("no vin hidden on /catalog", 'name="vin"' not in (bar.group(0) if bar else ""))
r = c.get(f"/v/{VIN}/fuses")
bar = re.search(r'<div class="navsheet-bar">.*?</div>', r.text, re.S)
check("vehicle page: hidden vin in bar", bool(bar) and f'name="vin" value="{VIN}"' in bar.group(0), str(r.status_code))
check("no script inside the search form", "<script" not in (bar.group(0) if bar else "<script"))

# 2. queries
r, href, title = best("oil reset")
check("oil reset -> Adjustments", href.endswith("/adjustments") and title.startswith("Adjustments"), f"{href} {title}")
check("best has answer line", "service resets" in r.text)
_, href, title = best("fuse")
check("fuse -> Fuses", href.endswith("/fuses"), f"{href} {title}")
_, href, title = best("paddle")
check("paddle -> Configuration", href.endswith("/configuration"), f"{href} {title}")
_, href, title = best("Fuses")
check("exact label (case)", href.endswith("/fuses"), href)
_, href, title = best("fúses")
check("accents ignored", href.endswith("/fuses"), href)
_, href, title = best("fuses blown")
check("plural words", href.endswith("/fuses"), href)
r, href, title = best("P0456")
check("code -> codes page row", href.startswith(f"/v/{VIN}/codes") and "P0456" in href, href)
check("code in Fault codes", "Code P0456" in r.text)
r, href, title = best("p0456", vin="")
check("code without car still answers", "Code P0456" in r.text)

items = json.loads((ROOT / "cuore/data/tsb_catalogue.json").read_text(encoding="utf-8"))["items"]
num = next(i["number"] for i in items if i.get("number") and i["number"][:1].isdigit())
r, href, title = best(num)
check("bulletin number -> TSB", href.startswith("/tsb") and "#tsb-row-" in href, f"{num} {href}")

r, href, title = best("zzqxv nonsense")
check("nonsense -> no match", "No match for" in r.text and "zzqxv nonsense" in r.text)
for k in ("Bench", "Job", "Codes", "Adjustments", "Parts catalogue", "Library"):
    check(f"start tile {k}", re.search(r'class="navtile" href="[^"]+"><span>' + k + "</span>", r.text) is not None)
r = c.get("/find")
check("empty query shows start tiles", r.status_code == 200 and "navtile" in r.text)

# 3. static
html = (ROOT / "cuore/web/templates/find.html").read_text(encoding="utf-8")
check("find.html has no script", "<script" not in html.lower())
css = (ROOT / "cuore/web/static/cuore.css").read_text(encoding="utf-8")
check("input >= 56px", re.search(r"\.navsheet-q[^{]*\{[^}]*min-height: 56px", css) is not None)
check("button >= 56px", re.search(r"\.navsheet-go[^{]*\{[^}]*min-height: 56px", css) is not None)
check("input text >= fs-lg", re.search(r"\.navsheet-q[^{]*\{[^}]*font-size: var\(--fs-lg\)", css) is not None)
check("phone: search full row", re.search(r"max-width: 600px\).*?\.navsheet-search \{[^}]*flex: 1 1 100%", css, re.S) is not None)

print(f"check_find: {checks - len(failures)}/{checks} passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
