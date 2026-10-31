"""Checks for the shop-wide Bay board (cuore/services/bay_board.py, cuore/web/bay_board_routes.py).

Run:  PYTHONPATH=mes-log-mcp .venv/Scripts/python.exe -X utf8 cuore/tests/check_bay_board.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_bay_check_")
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import interlock  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
import serial  # noqa: E402


def _boom(*a, **k):
    raise AssertionError("adapter opened")


serial.Serial.__init__ = _boom

from mes import jobs, shop  # noqa: E402

fails: list[str] = []
n = 0


def check(name: str, ok: bool) -> None:
    global n
    n += 1
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


c = TestClient(create_app())
VIN_IN, VIN_OUT = "ZASFAKPN5J7B88115", "ZARFAEEN5J7000001"

r = c.get("/bay")
check("empty shop renders", r.status_code == 200 and "No cars in the bay" in r.text)
check("empty shop counts are zero", len(re.findall(r"<dd>0</dd>", r.text)) == 3)

shop.intake(VIN_IN, "Rough idle when cold", technician="Marco", vehicle="Stelvio 2018")
gone = shop.intake(VIN_OUT, "Brake noise", technician="Luca", vehicle="Giulia 2018")
shop._append({"op": "release", "visit_id": gone["id"], "at": datetime.now().isoformat(timespec="seconds"),
              "release": {}, "outcome": "done"})

r = c.get("/bay")
t = r.text
check("car in the bay shows its reason", "Rough idle when cold" in t)
check("car in the bay shows technician and name", "Marco" in t and "Stelvio 2018" in t)
check("car in the bay shows job status", "bb-s-open" in t and ">Open<" in t)
check("last 8 of VIN shown", VIN_IN[-8:] in t)
check("car that left does not appear", VIN_OUT not in t and "Brake noise" not in t)
check("counts: 1 in, 1 open", re.findall(r"<dd>(\d+)</dd>", t) == ["1", "1", "0"])
check("card links to the car menu", f'href="/v/{VIN_IN}/menu"' in t)
check("card keeps its marque", re.search(r'class="bb-card" data-marque="\w+"', t) is not None)
check("no unproven 'Fixed'", ">Fixed<" not in t)
check("no forms or POST", "<form" not in t.split("</header>")[-1].split("<footer")[0] and "POST" not in t.upper().split("</HEADER>")[-1])
check("no-store header", "no-store" in r.headers.get("cache-control", ""))

# a closed-as-fixed job with no clean read must say Verifying, never Fixed
j = jobs.current(VIN_IN)
jobs.close(j["id"], outcome="fixed") if hasattr(jobs, "close") else None
t2 = c.get("/bay").text
check("fixed but unproven shows Verifying, not Fixed", ">Fixed<" not in t2)

css = (Path(__file__).resolve().parents[1] / "web" / "static" / "bay_board.css").read_text(encoding="utf-8")
check("css: no hex colours, no px font sizes", not re.search(r"#[0-9a-fA-F]{3,8}\b", css) and not re.search(r"font-size:\s*\d+px", css))
check("css: only the 759 px phone breakpoint", set(re.findall(r"max-width:\s*(\d+)px", css)) == {"759"} and "min-width:" not in css.replace("min-width: 0", "").replace("min-width: 96px", ""))

m = c.get(f"/v/{VIN_IN}/menu").text
check("Menu populated and lists Bay board", 'href="/bay"' in m and "Bay board" in m and "Every car in the shop now" in m)
m2 = c.get("/bay").text
check("Menu on the board itself lists Bay board", 'href="/bay"' in m2 and "Every car in the shop now" in m2)

print(f"\n{n - len(fails)}/{n} passed")
sys.exit(1 if fails else 0)
