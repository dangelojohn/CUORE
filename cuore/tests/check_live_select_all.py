"""Live board: Select all/none buttons, per-channel record tick + priority 1-5, and the
session-start API accepting `priorities`. Rendered-HTML/JS-text checks only; no adapter.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_live_select_all.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-selall-")
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
STATIC = ROOT / "cuore" / "web" / "static"
fails: list[str] = []


def check(name: str, ok: bool) -> None:
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


client = TestClient(create_app())
r = client.get(f"/v/{VIN}/liveboard")
html = r.text
check("liveboard renders", r.status_code == 200)
check("whole-board Select all button", bool(re.search(r'<button type="button"[^>]*data-select="all"[^>]*data-scope="board"', html)))
check("whole-board Select none button", bool(re.search(r'<button type="button"[^>]*data-select="none"[^>]*data-scope="board"', html)))
check("per-group Select all/none", 'data-scope="group"' in html)
check("buttons say a word, not a bare mark", "Select all" in html and "Select none" in html)
check("per-channel record tick", 'class="lb-pick-box"' in html)
check("priority select 1-5", bool(re.search(r'class="lb-pick-sel"[^>]*>(\s*<option value="\d">\d</option>){5}', html)))
check("one-line priority explanation", "1 = every poll, 5 = every fifth poll" in html)
check("no digit key bindings in picker", "keydown" not in (STATIC / "liveboard.js").read_text(encoding="utf-8").split("_wirePicker = ")[1].split("_renderPickRates")[0])

js = (STATIC / "liveboard.js").read_text(encoding="utf-8")
check("session start sends priorities", "body.priorities" in js)
check("rates shown from channel_rates", "channel_rates" in js and "achieved_hz" in js)
css = (STATIC / "liveboard.css").read_text(encoding="utf-8")
pick_css = css.split("recording picker")[1]
check("picker CSS uses --fs tokens only", "font-size: var(--fs-" in pick_css and not re.search(r"font-size:\s*\d", pick_css))

# server side: session start accepts priorities (adapter-free: a bad body is rejected, not a 422 on the field)
resp = client.post("/api/live/session/start", json={"channels": [], "priorities": {"x": 3}})
check("priorities field accepted by the API schema", resp.status_code != 422)

api_src = (ROOT / "cuore" / "api" / "live.py").read_text(encoding="utf-8")
check("route declares priorities Body", "priorities: Optional[dict[str, int]]" in api_src)

print("FAILED: " + ", ".join(fails) if fails else "ALL PASS")
sys.exit(1 if fails else 0)
