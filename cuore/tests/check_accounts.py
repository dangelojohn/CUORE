"""Checks for accounts and roles (cuore.services.accounts, deps identify/require_role, /accounts).
Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_accounts.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-accounts-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ.pop("CUORE_AUDIT_PATH", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import accounts  # noqa: E402
from cuore.web import accounts_routes, routes as web_routes  # noqa: E402
from cuore.live import interlock  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
VIN = "ZASFAKPN5J7B88115"
TOKEN = "machine-token-123"
failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def build():
    app = create_app()
    app.include_router(accounts_routes.router)      # until app.py registers it
    return TestClient(app, follow_redirects=False, raise_server_exceptions=False)


Path(_TMP, "web_token.txt").write_text(TOKEN, encoding="utf-8")
c0 = build()

# --- 1. mode off by default: existing token behaviour unchanged -----------------------------------
check("no accounts file", not Path(_TMP, "accounts.json").exists())
check("mode off", accounts.mode_active() is False)
check("no token -> 302 to login", c0.get("/").status_code == 302)
check("header token ok", c0.get("/api/health").status_code == 200
      and c0.get("/api/vehicles", headers={"X-Cuore-Token": TOKEN}).status_code == 200)
check("wrong header 401", c0.get("/api/vehicles", headers={"X-Cuore-Token": "no"}).status_code == 401)
r = c0.get(f"/login?token={TOKEN}")
check("token login sets cookie", r.status_code == 302 and "cuore_session" in r.headers.get("set-cookie", ""))
check("token cookie works", c0.get("/api/vehicles").status_code == 200)
check("login page is token form", "Access token" in build().get("/login").text)

# an admin that exists but mode not enabled -> still off
accounts.create("boss", "correct horse 1", "admin", "Boss", "main", "dealer")
check("admin alone does not turn mode on", accounts.mode_active() is False)
try:
    accounts.set_mode(True)
    accounts.set_mode(False)
    check("set_mode round trip", accounts.mode_active() is False)
except Exception as exc:  # noqa: BLE001
    check("set_mode", False, str(exc))

# --- 2. create + enable ---------------------------------------------------------------------------
accounts.create("lead1", "lead password 1", "shop_lead", "Lead One", "shopA", "independent")
accounts.create("tech1", "tech password 1", "technician", "Tech One", "shopA", "independent")
accounts.create("tech2", "tech password 2", "technician", "Tech Two", "shopB", "dealer")
for bad, why in ((("x", "longenough1"), "short name"), (("ok name", "longenough1"), "space"),
                 (("fine", "short"), "short password"), (("tech1", "longenough1"), "duplicate")):
    try:
        accounts.create(*bad)
        check(f"create rejects {why}", False)
    except accounts.AccountError:
        check(f"create rejects {why}", True)
accounts.set_mode(True)
check("mode on", accounts.mode_active())
raw = Path(_TMP, "accounts.json").read_text(encoding="utf-8")
check("password not stored plain", "correct horse 1" not in raw and "tech password 1" not in raw)
check("list has no hashes", all("password" not in u and "hash" not in u for u in accounts.list_users())
      and "hash" not in json.dumps(accounts.list_users()))

# --- 3. login ok / bad / lockout ------------------------------------------------------------------
def login(user, pw, client=None):
    c = client or build()
    r = c.post("/login", data={"username": user, "password": pw, "next": "/"})
    return c, r


check("login page asks username", "Username" in build().get("/login").text)
t1, r = login("tech1", "tech password 1")
check("login ok -> 302 + cookie", r.status_code == 302 and "cuore_session" in r.headers.get("set-cookie", ""))
check("session works", t1.get("/api/vehicles").status_code == 200)
_, r = login("tech1", "wrong password")
check("bad password 403 generic", r.status_code == 403 and "Username or password" in r.text
      and "wrong password" not in r.text)
_, r = login("nobody", "whatever123")
check("unknown user same message", r.status_code == 403 and "Username or password" in r.text)
now = [1000.0]
accounts.CLOCK = lambda: now[0]
for _ in range(accounts.MAX_FAILS):
    login("tech2", "bad bad bad")
_, r = login("tech2", "tech password 2")
check("lockout even with right password", r.status_code == 429 and "Retry-After" in r.headers)
now[0] += accounts.COOLDOWN + 5
_, r = login("tech2", "tech password 2")
check("lockout expires", r.status_code == 302)
accounts.CLOCK = __import__("time").monotonic

# --- 4. machine token path keeps full access ------------------------------------------------------
H = {"X-Cuore-Token": TOKEN}
anon = build()
check("anonymous GET api 401", anon.get("/api/vehicles").status_code == 401)
check("anonymous page -> login", anon.get("/accounts").status_code == 302)
check("token header full API", anon.get("/api/vehicles", headers=H).status_code == 200)
check("token header POST allowed past gates",
      anon.post("/api/live/proxi/accept", headers=H,
                json={"vin": VIN, "did": "2010", "reason": "x"}).status_code != 403)
check("token on /accounts", anon.get("/accounts", headers=H).status_code == 200)

# --- 5. roles --------------------------------------------------------------------------------------
lead, _ = login("lead1", "lead password 1")
lead_c = lead
check("technician 403 on /accounts", t1.get("/accounts").status_code == 403)
check("technician 403 on proxi accept (web)",
      t1.post(f"/v/{VIN}/configuration/accept", data={"did": "2010"}).status_code == 403)
check("technician 403 on proxi accept (api)",
      t1.post("/api/live/proxi/accept", json={"vin": VIN, "did": "2010", "reason": "x"}).status_code == 403)
check("technician keeps ordinary pages", t1.get("/api/vehicles").status_code == 200)
check("shop_lead may accept (not 403)",
      lead_c.post(f"/v/{VIN}/configuration/accept", data={"did": "2010"}).status_code == 303)
r = lead_c.get("/accounts")
check("shop_lead sees /accounts", r.status_code == 200)
check("shop_lead sees own shop only", "tech1" in r.text and "lead1" in r.text and "tech2" not in r.text
      and "boss" not in r.text)
check("no hash/password in page", "scrypt" not in r.text and "salt" not in r.text
      and "tech password" not in r.text and accounts._hash("x", b"0" * 16) not in r.text)
r = lead_c.post("/accounts/add", data={"username": "tech3", "password": "tech password 3",
                                       "role": "admin", "shop_id": "shopB"})
u3 = accounts.get("tech3")
check("lead adds technician in own shop (role/shop forced)", u3 and u3["role"] == "technician"
      and u3["shop_id"] == "shopA")
check("lead cannot disable other shop", lead_c.post("/accounts/disable", data={"username": "tech2"}).status_code == 403)
check("lead disables own tech", lead_c.post("/accounts/disable", data={"username": "tech3"}).status_code == 303
      and accounts.get("tech3")["disabled"])
check("lead cannot reset password", lead_c.post("/accounts/password", data={"username": "tech1", "password": "newpassword9"}).status_code == 403)
check("disabled user cannot log in", login("tech3", "tech password 3")[1].status_code == 403)
admin, _ = login("boss", "correct horse 1")
r = admin.get("/accounts")
check("admin sees all shops", "tech2" in r.text and "tech1" in r.text and "boss" in r.text)
admin.post("/accounts/password", data={"username": "tech1", "password": "brand new pass"})
check("admin resets password", login("tech1", "brand new pass")[1].status_code == 302
      and login("tech1", "tech password 1")[1].status_code == 403)
try:
    accounts.disable("boss")
    check("last admin protected", False)
except accounts.AccountError:
    check("last admin protected", True)

# --- 6. attribution --------------------------------------------------------------------------------
seen = {}
web_routes.mes_bridge.add_note = lambda vin, text, **kw: seen.update(kw)
t1b, _ = login("tech1", "brand new pass")
t1b.post(f"/v/{VIN}/notes", data={"text": "hello", "author": "someone else"})
check("note author is logged-in user", seen.get("author") == "tech1", str(seen))

# --- 7. logout --------------------------------------------------------------------------------------
r = t1b.get("/logout")
check("logout redirects and clears cookie", r.status_code == 302 and "cuore_session" in r.headers.get("set-cookie", ""))
t1b.cookies.clear()
check("after logout no access", t1b.get("/api/vehicles").status_code == 401)
tampered, _ = login("tech1", "brand new pass")
ck = tampered.cookies.get("cuore_session")
tampered.cookies.clear()
tampered.cookies.set("cuore_session", ck.replace("~technician~", "~admin~"))
check("tampered role cookie rejected", tampered.get("/api/vehicles").status_code == 401)

# --- 8. turning mode off restores token-only behaviour -----------------------------------------------
accounts.set_mode(False)
check("mode off again -> tech cookie no longer user", build().get("/api/vehicles").status_code == 401)
check("token still ok", build().get("/api/vehicles", headers=H).status_code == 200)

print(f"{checks} checks, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
