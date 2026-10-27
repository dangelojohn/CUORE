"""Web lock: session cookie login, read vs write auth (temp state dir).

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_web_login.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-weblogin-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_TOKEN", None)
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


PAGE = "/logs"
WRITE = "/api/feedback/nope/answer"
BODY = {"text": "x", "by": "t"}


def client() -> TestClient:
    return TestClient(create_app(), follow_redirects=False)


# --- no token: behaves as before ---------------------------------------------
c = client()
check("open: page 200", c.get(PAGE).status_code == 200, str(c.get(PAGE).status_code))
check("open: health 200", c.get("/api/health").status_code == 200)
check("open: docs 200", c.get("/api/docs").status_code == 200)
check("open: openapi 200", c.get("/api/openapi.json").status_code == 200)
r = c.post(WRITE, json=BODY)
check("open: write not blocked", r.status_code not in (401, 403), str(r.status_code))
check("open: /login redirects", c.get("/login").status_code == 302)

# --- token set via state-dir file -----------------------------------------------
TOKEN = "s3cret-token-for-test"
Path(STATE, "web_token.txt").write_text(TOKEN + "\n", encoding="utf-8")
c = client()
r = c.get(PAGE)
check("locked: page 302", r.status_code == 302, str(r.status_code))
check("locked: redirect to /login?next=", r.headers.get("location", "").startswith("/login?next=%2F"),
      r.headers.get("location", ""))
check("locked: login form 200", c.get("/login").status_code == 200)
check("locked: health always 200", c.get("/api/health").status_code == 200)
check("locked: docs blocked", c.get("/api/docs").status_code in (302, 401))
check("locked: openapi blocked", c.get("/api/openapi.json").status_code == 401)
check("locked: query token reads", c.get(PAGE + f"?token={TOKEN}").status_code == 200)
check("locked: header token reads",
      c.get(PAGE, headers={"X-Cuore-Token": TOKEN}).status_code == 200)

r = c.get("/login?token=wrong&next=/system")
check("wrong token 403", r.status_code == 403, str(r.status_code))
check("wrong token no cookie", "cuore_session" not in r.headers.get("set-cookie", ""))
check("wrong token still locked", c.get(PAGE).status_code == 302)

r = c.post(WRITE + f"?token={TOKEN}", json=BODY)
check("write with ?token= only -> 403", r.status_code == 403, str(r.status_code))
r = c.post(WRITE, json=BODY)
check("write with nothing -> 403", r.status_code == 403, str(r.status_code))

r = c.get(f"/login?token={TOKEN}&next=/system")
sc = r.headers.get("set-cookie", "")
check("login 302 to next", r.status_code == 302 and r.headers["location"] == "/system",
      f"{r.status_code} {r.headers.get('location')}")
check("cookie HttpOnly + SameSite=lax", "httponly" in sc.lower() and "samesite=lax" in sc.lower(), sc)
check("page renders with cookie", c.get(PAGE).status_code == 200)
r = c.post(WRITE, json=BODY)
check("write with cookie passes auth", r.status_code not in (401, 403), str(r.status_code))
check("docs with cookie", c.get("/api/docs").status_code == 200)

r = c.get(f"/login?token={TOKEN}&next=//evil.example/x")
check("open redirect refused", r.headers.get("location") == "/", r.headers.get("location", ""))
r = c.post("/login", content=f"token={TOKEN}&next=%2Fsystem",
           headers={"content-type": "application/x-www-form-urlencoded"})
check("form login works", r.status_code == 302 and r.headers["location"] == "/system")

# forged / tampered cookie
c2 = client()
c2.cookies.set("cuore_session", "abc.123.deadbeef")
check("forged cookie rejected", c2.get(PAGE).status_code == 302)

# logout
c.get("/logout")
check("logout locks again", c.get(PAGE).status_code == 302)

# rotate token ends old sessions
c3 = client()
c3.get(f"/login?token={TOKEN}")
check("c3 in", c3.get(PAGE).status_code == 200)
Path(STATE, "web_token.txt").write_text("another-token\n", encoding="utf-8")
check("rotate ends session", c3.get(PAGE).status_code == 302)

# env wins over file
os.environ["CUORE_TOKEN"] = "env-token"
c4 = TestClient(create_app(), follow_redirects=False)
check("env token honoured", c4.get(PAGE + "?token=env-token").status_code == 200)
check("env beats file", c4.get(PAGE + "?token=another-token").status_code == 302)
os.environ.pop("CUORE_TOKEN")

# --- rate limit: 5 failures / 10 min per client -> 429 + Retry-After ---------------
from cuore.web import login_routes  # noqa: E402

Path(STATE, "web_token.txt").write_text(TOKEN + "\n", encoding="utf-8")
login_routes._FAILS.clear()
c5 = client()
XF = {"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}
codes = [c5.get("/login?token=bad%d" % i, headers=XF).status_code for i in range(5)]
check("5 wrong tries are 403", codes == [403] * 5, str(codes))
r = c5.get("/login?token=bad6", headers=XF)
check("6th failed attempt -> 429", r.status_code == 429, str(r.status_code))
check("429 has Retry-After", r.headers.get("retry-after", "").isdigit() and 0 < int(r.headers["retry-after"]) <= 600,
      r.headers.get("retry-after", ""))
check("429 page says when to retry", "Try again in" in r.text and "bad6" not in r.text)
r = c5.get(f"/login?token={TOKEN}", headers=XF)
check("correct token still locked out while limited", r.status_code == 429 and "set-cookie" not in r.headers)
r = c5.post("/login", content="token=bad7", headers={**XF, "content-type": "application/x-www-form-urlencoded"})
check("POST form also limited", r.status_code == 429)
r = c5.get("/login?token=bad", headers={"X-Forwarded-For": "198.51.100.7"})
check("another client unaffected", r.status_code == 403, str(r.status_code))
tick = [login_routes.CLOCK()]
login_routes.CLOCK = lambda: tick[0]
login_routes._FAILS.clear()
for i in range(5):
    c5.get("/login?token=nope", headers=XF)
check("locked at 5 (fake clock)", c5.get("/login?token=x", headers=XF).status_code == 429)
tick[0] += 601
check("window expires after 10 min", c5.get("/login?token=x", headers=XF).status_code == 403)
login_routes._FAILS.clear()
for i in range(4):
    c5.get("/login?token=nope", headers=XF)
r = c5.get(f"/login?token={TOKEN}", headers=XF)
check("success under the limit logs in", r.status_code == 302 and "cuore_session" in r.headers.get("set-cookie", ""))
codes = [c5.get("/login?token=nope", headers=XF).status_code for _ in range(5)]
check("success reset the counter (5 more wrong tries allowed)", codes == [403] * 5, str(codes))

print(f"{checks} checks, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
