"""Checks for the handbook pages (/handbook, /handbook/{slug}, cuore/services/handbook.py) and its search links.
Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_handbook.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-handbook-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.services import find, handbook  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


TOKEN = "handbook-token-123"
Path(_TMP, "web_token.txt").write_text(TOKEN, encoding="utf-8")
c = TestClient(create_app(), follow_redirects=False, raise_server_exceptions=False)
c.get(f"/login?token={TOKEN}")

# 1. index lists every file
files = sorted((ROOT / "docs/handbook").glob("*.md"))
r = c.get("/handbook")
check("index 200", r.status_code == 200, str(r.status_code))
check("one tile per file", all(f'href="/handbook/{f.stem}"' in r.text for f in files), str(len(files)))
check("lead: N how-to guides; start with", f"{len(files)} how-to guides; start with" in r.text)
check("tiles carry a summary", len(re.findall(r"<small>[^<]+</small>", r.text)) >= len(files) - 2)
check("no generated marker leaks", "cable-reference" not in r.text and "&lt;!--" not in r.text)

# 2. a page: headings with ids + TOC
r = c.get("/handbook/01-decisions-and-rules")
check("page 200", r.status_code == 200, str(r.status_code))
ids = re.findall(r'<h[23] id="([^"]+)"', r.text.split('<div class="body">')[1])
check("headings have ids", len(ids) >= 3 and len(set(ids)) == len(ids), str(ids[:5]))
check("TOC links to heading ids", all(f'href="#{i}"' in r.text for i in ids[:3]) and 'class="toc"' in r.text)
check("back link", 'href="/handbook"' in r.text)
r = c.get("/handbook/07-first-live-session")
check("generated block comments hidden", "cable-reference" not in r.text and "do not hand-edit" not in r.text)

# 3. escaping, with a fake handbook in a temp dir
fake = Path(tempfile.mkdtemp(prefix="cuore-fake-hb-"))
(fake / "evil.md").write_text(
    "# Evil <script>alert(1)</script>\n\nFirst <b>para</b> with **bold**, *it* and `<i>code</i>`.\n\n"
    "## Steps <img src=x onerror=alert(1)>\n\n- one <script>x</script>\n- two\n\n"
    "[bad](javascript:alert(1)) and [ok](https://example.com/a?b=1&c=2)\n\n"
    "| a | b |\n|---|---|\n| <u>1</u> | 2 |\n\n```\n<script>z</script>\n```\n\n<!-- hidden:start -->\n", encoding="utf-8")
os.environ["CUORE_HANDBOOK_DIR"] = str(fake)
r = c.get("/handbook/evil")
check("fake page 200", r.status_code == 200, str(r.status_code))
body = r.text.split('<div class="body">')[1]
check("no raw script tag", not re.search(r"<script>(alert|x|z)", body.lower()), "")
check("script text escaped", "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text)
check("no raw img/b/u/i tag", not re.search(r"<(img|b|u|i)[ >]", body))
check("javascript: link dropped", "javascript:" not in r.text.split('<div class="body">')[1])
check("https link kept, & escaped", 'href="https://example.com/a?b=1&amp;c=2"' in r.text)
check("bold/italic/code/table/list rendered", all(t in r.text for t in ("<strong>bold</strong>", "<em>it</em>", "<code>&lt;i&gt;code&lt;/i&gt;</code>", "<table>", "<li>one")))
check("comment hidden", "hidden:start" not in r.text)
check("fake index lists only fake", 'href="/handbook/evil"' in c.get("/handbook").text and "01-decisions" not in c.get("/handbook").text)

# 4. traversal and unknown slugs
for bad in ("..%2f..%2fapp", "%2e%2e", "%2e%2e%2fREADME", "nope", "evil.md", "01-decisions-and-rules"):
    check(f"slug {bad} 404", c.get(f"/handbook/{bad}").status_code == 404, bad)
os.environ.pop("CUORE_HANDBOOK_DIR")

# 5. find links how-to results
hs = handbook.headings((ROOT / "docs/handbook/01-decisions-and-rules.md").read_text(encoding="utf-8"))
h = next(x for x in hs if x["level"] == 2 and len(x["text"].split()) >= 2)
res = find.search(h["text"])
rows = [x for g in res["groups"] for x in g["rows"] if x["kind"] == "How-to"] + ([res["best"]] if res["best"] and res["best"]["kind"] == "How-to" else [])
check("how-to rows link to /handbook/slug#id", bool(rows) and all(re.match(r"^/handbook/[^#]+#[a-z0-9-]+$", x["href"]) for x in rows), str(rows[:2]))
check("link points at the right anchor", any(x["href"] == f"/handbook/01-decisions-and-rules#{h['id']}" for x in rows), h["id"])
page = c.get("/handbook/01-decisions-and-rules").text
check("search anchor exists on the page", f'id="{h["id"]}"' in page)
r = c.get("/find", params={"q": h["text"]})
check("find page shows the handbook link", f'href="/handbook/01-decisions-and-rules#{h["id"]}"' in r.text)
r = c.get("/find", params={"q": "how to"})
check("'how to' goes to the handbook", 'class="find-best" href="/handbook"' in r.text, "")

# 6. static
for t in ("handbook.html", "handbook_page.html"):
    src = (ROOT / "cuore/web/templates" / t).read_text(encoding="utf-8")
    check(f"{t} has no script", "<script" not in src.lower())
    check(f"{t} uses --fs tokens", "var(--fs-" in src)
tile = (ROOT / "cuore/web/templates/handbook.html").read_text(encoding="utf-8")
check("tile >= 56px", re.search(r"\.tile\s*\{[^}]*min-height:\s*(\d+)px", tile) and int(re.search(r"\.tile\s*\{[^}]*min-height:\s*(\d+)px", tile).group(1)) >= 56)

print(f"check_handbook: {checks - len(failures)}/{checks} passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
