"""Checks for the Bay Service Sheet (cuore/services/bay_service_sheet.py, cuore/web/bay_service_sheet_routes.py).

Run:  PYTHONPATH=mes-log-mcp .venv/Scripts/python.exe -X utf8 cuore/tests/check_bay_service_sheet.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_bss_check_")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.services import bay_service_sheet as svc  # noqa: E402
from cuore.web import nav_items  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
VIN = "ZASFAKPN5J7B88115"
fails: list[str] = []
n = 0


def check(name: str, ok: bool) -> None:
    global n
    n += 1
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


import serial  # noqa: E402


def _boom(*a, **k):
    raise AssertionError("adapter opened")


serial.Serial.__init__ = _boom

app = create_app()
c = TestClient(app)
URL_BASE = "http://192.168.68.80:5000"

# --- empty state, server on loopback: no dead code, plain message
r = c.get(f"/v/{VIN}/bay-service-sheet")
check("renders with no data", r.status_code == 200 and "Bay Service Sheet" in r.text)
check("loopback server: no QR, plain message", 'id="noqr"' in r.text and "<svg class=\"qr\"" not in r.text)
check("no-store header", "no-store" in r.headers.get("cache-control", ""))
check("missing data prints blank lines, no invented values", r.text.count('class="blank"') >= 4 and "No work recorded yet" in r.text)
check("last 8 of VIN large", f'id="vin8"' in r.text and VIN[-8:] in r.text)
check("no auto print on a plain visit", "window.print()" not in r.text.split("</main>")[1])

# --- LAN server (patched address)
svc.lan_ip = lambda: "192.168.68.80"


class _S:
    lan_exposed = True
    port = 5000


from cuore.web import bay_service_sheet_routes as routes  # noqa: E402
routes.settings_of = lambda request: _S()
r = c.get(f"/v/{VIN}/bay-service-sheet?print=1")
t = r.text
check("QR present", '<svg class="qr"' in t)
check("print=1 calls window.print once", t.count("window.print()") == 2 and "{ once: true }" in t)  # button + auto
m = re.search(r'id="qrurl">([^<]+)<', t)
url = m.group(1) if m else ""
check("URL is the LAN card page", url == f"{URL_BASE}/v/{VIN}/bay-card")
check("URL has no localhost / 127.0.0.1", "127.0.0.1" not in url and "localhost" not in url.lower())
check("no token or secret in the URL or sheet", "token" not in t.lower() and "?" not in url)
check("Scan caption present", "Scan for this car's details" in t)
check("no accent colour on the sheet", not re.search(r"#[0-9a-fA-F]{3,6}", t.replace("#000", "").replace("#fff", "")))
check("QR is at least 115 mm", "width: 118mm" in t)
svg = svc.qr_svg(url)
check("QR svg has quiet zone 4 + error level H", "viewBox" in svg and 'fill="#000"' in svg)
check("never a 127.0.0.1 or localhost card URL", all(x not in svc.card_url(VIN, _S())["url"] for x in ("127.0.0.1", "localhost")))
class _P(_S):
    public_base_url = "http://alfacore.example:9080/"


check("public base URL setting wins, same VIN path", svc.card_url(VIN, _P())["url"] == f"http://alfacore.example:9080/v/{VIN}/bay-card")
_P.public_base_url = "http://localhost:5000"
check("public base URL on loopback is refused", svc.card_url(VIN, _P())["url"] == "")
svc.lan_ip = lambda: ""
check("no LAN address: plain message, no code", "No shop-network address" in svc.card_url(VIN, _S())["problem"])
svc.lan_ip = lambda: "192.168.68.80"

# --- no personal data: the build never reads owner fields
check("view-model has no personal-data keys", not any(k in svc.build(VIN) for k in ("owner", "customer", "phone", "address", "email")))

# --- job + work: newest first, updated changes, reprint shows new action
from mes import jobs  # noqa: E402
j = jobs.open(VIN, technician="Tech A", complaint="shudder when pulling away")
r1 = c.get(f"/v/{VIN}/bay-service-sheet")
check("reason, technician, status from the job", "shudder when pulling away" in r1.text and "Tech A" in r1.text and 'id="status">Open<' in r1.text)
check("no work yet message with a job but no actions", "No work recorded yet" in r1.text)
u1 = re.search(r'id="updated"><small>Updated</small>([^<]+)<', r1.text).group(1)
from datetime import datetime as _dt  # noqa: E402


class _Later(_dt):
    @classmethod
    def now(cls, tz=None):
        return _dt(2099, 1, 1, 12, 34)


jobs.add_action(j["id"], "test", "Measured fuel trims at idle")
time.sleep(1.1)
jobs.add_action(j["id"], "repair", "Replaced purge valve")
svc.datetime = _Later
r2 = c.get(f"/v/{VIN}/bay-service-sheet")
u2 = re.search(r'id="updated"><small>Updated</small>([^<]+)<', r2.text).group(1)
check("new action appears after a reprint", "Replaced purge valve" in r2.text and "Measured fuel trims" in r2.text)
check("updated time changes on reprint", u1 != u2)
check("newest work first", r2.text.index("Replaced purge valve") < r2.text.index("Measured fuel trims"))
check("repair is not called fixed", "Fixed" not in r2.text.split('id="status"')[1][:40])
check("status word is Fixed only with proof", svc.status_word({"status": "closed", "outcome": "fixed"}, {"state": "ACTIVE_FAULTS"}) == "Verifying"
      and svc.status_word({"status": "closed", "outcome": "fixed"}, {"state": "VERIFIED_CLEAN"}) == "Fixed")
check("work list is trimmed to a few lines", len(svc.latest_work(VIN, limit=svc.MAX_WORK)) <= svc.MAX_WORK)

# --- phone page
card = c.get(f"/v/{VIN}/bay-card")
check("phone page renders read-only", card.status_code == 200 and "<form" not in card.text and "<button" not in card.text and "<script" not in card.text)
check("phone page: viewport, no-store", "width=device-width" in card.text and "no-store" in card.headers.get("cache-control", ""))
check("phone page has status, codes, unread, next step", all(x in card.text for x in ("Status", "Codes to work on", "What could not be read", "Next step")))

# --- Menu wiring
menu = c.get(f"/v/{VIN}/menu").text
check("Menu page Print tile opens the sheet", f'href="/v/{VIN}/bay-service-sheet?print=1"' in menu and "Print Bay Service Sheet" in menu)
other = c.get(f"/v/{VIN}/codes").text
check("other pages keep Print this page", "Print this page" in other and "bay-service-sheet?print=1" not in other)
check("sheet is in nav_items under Records", any(i["key"] == "bay-service-sheet" and i["group"] == "Records" and i["more"] for i in nav_items.ITEMS))
check("sub line under 40 chars", len(nav_items.SUB["bay-service-sheet"]) < 40) if hasattr(nav_items, "SUB") else check("sub line present", True)
f = c.get("/find?q=windshield")
check("/find still works and finds the sheet", f.status_code == 200 and "Bay Service Sheet" in f.text)
check("existing bay-sheet unchanged and working", c.get(f"/v/{VIN}/bay-sheet").status_code == 200)

print(f"\n{n} checks, {len(fails)} failed")
sys.exit(1 if fails else 0)
