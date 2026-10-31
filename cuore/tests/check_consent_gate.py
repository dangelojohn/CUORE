"""The human-only consent gate (cuore/live/consent_gate.py, cuore/web/approve_routes.py).

Fakes only: a fake adapter stream, a temp CUORE_STATE_DIR, no COM port, no running CUORE. The CUORE
server and the obd2 MCP server are two processes in real life; here one process plays both, with the
module-global "authority" swapped in and out so the MCP side holds no approval state, exactly as it
would not in its own process. The MCP tools reach the "server" through consent_gate's remote hook,
wired to a TestClient with the machine token.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_consent_gate.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-consent-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ["CUORE_AUTOSTART"] = "0"              # the tools' cuore_client must never spawn a cuore
os.environ["CUORE_URL"] = "http://127.0.0.1:9"   # ... nor reach a running one
os.environ.pop("OBD_PORT", None)
os.environ.pop("CUORE_TOKEN", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "obd2-mcp"))

TOKEN = "machine-token-for-consent-test"
Path(STATE, "web_token.txt").write_text(TOKEN + "\n", encoding="utf-8")

from fastapi.testclient import TestClient  # noqa: E402

from cuore.live import actuate, audit, consent_gate, interlock, store  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
# obd2-mcp/server.py must be imported before cuore.app: the app's bootstrap puts mes-log-mcp (which has
# its own server.py) first on sys.path.
import server  # noqa: E402
import cuore_client  # noqa: E402
from cuore.app import create_app  # noqa: E402
from cuore.services import accounts  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


class Fake(Stream):
    """An adapter that records everything written to it."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self._buf = bytearray()
        self._open = False

    def open(self): self._open = True
    def close(self): self._open = False
    def is_open(self): return self._open
    @property
    def describe(self): return "serial COM99@115200 (fake)"

    def write(self, data: bytes) -> None:
        cmd = data.decode("ascii", "replace").strip()
        self.sent.append(cmd)
        if cmd.startswith("STP "):
            r = "OK"
        elif cmd in ("STM", "STMA"):
            r = "1E36000100112233\r1E36000B00112233"
        elif cmd == "0100":
            r = "7E806410098180001"
        elif cmd == "010D":
            r = "7E803410D00"
        elif cmd == "04":
            r = "7E80144"
        elif cmd.startswith(("AT", "ST")):
            r = "OK"
        else:
            r = "NO DATA"
        self._buf.extend(r.encode() + b"\r>")

    def read(self, n): c = bytes(self._buf[:max(n, 1)]); del self._buf[:max(n, 1)]; return c
    def reset_input_buffer(self): self._buf.clear()
    def in_waiting(self): return len(self._buf)


def fresh_car() -> Fake:
    car = Fake()
    lk = AdapterLink(stream_factory=lambda p, b: car, process="check_consent_gate")
    lk.auto_verify_seconds = 0.2
    set_link(lk)
    return car


def wire_sent(car: Fake) -> list[str]:
    """Everything that reached the adapter except adapter setup and the legislated reads."""
    return [c for c in car.sent if c and c[:2] not in ("AT", "ST") and c not in ("0100", "010D", "010C")]


# --- the two "processes" -------------------------------------------------------------------------
SERVER = consent_gate.ConsentStore()
NOW = [1000.0]
SERVER.clock = lambda: NOW[0]
app = create_app()


def as_server(fn):
    """Run ``fn`` as the CUORE server process: it, and only it, holds the approval store."""
    consent_gate.activate_authority(SERVER)
    try:
        return fn()
    finally:
        consent_gate.deactivate_authority()


machine = TestClient(app, follow_redirects=False)       # the MCP side's HTTP client (token header)
MACHINE_HDR = {"x-cuore-token": TOKEN}


def remote(method, path, *, query=None, body=None, timeout=0):
    """cuore_client.call, in-process: same mapping of HTTP errors onto {"error": ...}."""
    r = as_server(lambda: machine.request(method, "/api" + path, json=body, headers=MACHINE_HDR))
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        return {"error": detail or f"HTTP {r.status_code}", "status": r.status_code}
    return r.json()


consent_gate.deactivate_authority()
consent_gate.set_remote(remote, (cuore_client.CuoreUnavailable, cuore_client.CuoreTimeout))


class Browser:
    """A person's browser: logged in with a session cookie, same-origin form posts."""

    def __init__(self, login: str = f"/login?token={TOKEN}") -> None:
        self.c = TestClient(app, follow_redirects=False)
        if login:
            self.c.get(login)

    def page(self, rid: str, **kw):
        return as_server(lambda: self.c.get(f"/approve/{rid}", **kw))

    @staticmethod
    def secrets(html: str) -> tuple[str, str]:
        n = re.search(r'name="nonce" value="([^"]+)"', html)
        p = re.search(r'class="phrase mono">([^<]+)<', html)
        return (n.group(1) if n else ""), (p.group(1).strip() if p else "")

    def approve(self, rid: str, *, phrase=None, nonce=None, origin="http://testserver", extra=None,
                url=None):
        html = self.page(rid).text
        n, ph = self.secrets(html)
        hdrs = {"origin": origin} if origin is not None else {}
        hdrs.update(extra or {})
        data = {"phrase": ph if phrase is None else phrase, "nonce": n if nonce is None else nonce}
        return as_server(lambda: self.c.post(url or f"/approve/{rid}", data=data, headers=hdrs))


def tool(fn, *a, **kw) -> dict:
    return json.loads(fn(*a, **kw))


def pending_id(r: dict) -> str:
    return r.get("request_id") or ""


PHRASES = ("CLEAR ECM", "CLEAR ALL EMISSIONS CODES", "ACTUATE ECM", "SEND RAW")
FLAG = dict(i_understand_this_writes_to_the_vehicle=True)

# a learned actuator procedure so run_actuator reaches the gate
store_dir_proc = {"target": "10", "kind": "io_control", "replayable": True, "reasons": [],
                  "requires_security_access": False, "ended_with_terminator": True,
                  "synthesised_terminator": None, "used_tester_present": False,
                  "session_sub": "03", "name": "Test A", "steps": [
                      {"t_req": 0.0, "t_resp": 0.01, "service": "10", "payload": ["03"],
                       "request": ["10", "03"], "response": None, "nrc": None, "synthesised": False},
                      {"t_req": 0.1, "t_resp": 0.11, "service": "2F", "payload": ["12", "34", "03", "AA"],
                       "request": ["2F", "12", "34", "03", "AA"], "response": None, "nrc": None,
                       "synthesised": False},
                      {"t_req": 0.2, "t_resp": 0.21, "service": "2F", "payload": ["12", "34", "00"],
                       "request": ["2F", "12", "34", "00"], "response": None, "nrc": None,
                       "synthesised": False}]}
actuate.save_actuator(VIN, "ECM", "Test A", store_dir_proc, source="test", tool="MES")


def calls():
    """The four tools, each with its arguments, as an LLM would call them with no approval."""
    return {
        "send_raw": lambda **k: tool(server.send_raw, "1101", module="ECM", vin=VIN, **FLAG, **k),
        "clear_dtcs": lambda **k: tool(server.clear_dtcs, confirm=True, vin=VIN, **k),
        "clear_module_dtcs": lambda **k: tool(server.clear_module_dtcs, "ECM", vin=VIN, confirm=True, **k),
        "run_actuator": lambda **k: tool(server.run_actuator, "ECM", "Test A", vin=VIN, confirm=True, **k),
    }


# === 1. no approval: refused, a pending request is created, nothing sent, no phrase ================
print("1. refused without approval")
SUPPLIED = {
    "send_raw": "SEND RAW 11 TO ECM", "clear_dtcs": "CLEAR ALL EMISSIONS CODES",
    "clear_module_dtcs": "CLEAR ECM", "run_actuator": "ACTUATE ECM TEST A",
}
ids = {}
for name, call in calls().items():
    car = fresh_car()
    r = call()
    ids[name] = pending_id(r)
    check(f"{name}: refused with no approval", "refused" in r and r.get("consent_required") is True, str(r))
    check(f"{name}: refusal carries a request id and the page to open",
          bool(r.get("request_id")) and r.get("approve_page", "").endswith(f"/approve/{r.get('request_id')}"), str(r))
    check(f"{name}: refusal text contains no consent phrase",
          not any(p in json.dumps(r).upper() for p in PHRASES), json.dumps(r))
    check(f"{name}: nothing sent to the car", wire_sent(car) == [], str(car.sent))
    # a caller-supplied consent string alone, right phrase included, authorises nothing
    r2 = call(consent=SUPPLIED[name])
    check(f"{name}: supplied consent string alone still refuses", r2.get("consent_required") is True, str(r2))
    check(f"{name}: supplied consent string alone sends nothing", wire_sent(car) == [], str(car.sent))
    # confirm=True alone (already set in these calls; send_raw has the flag too)
    check(f"{name}: confirm=True alone sends nothing", wire_sent(car) == [], str(car.sent))
    # made-up request id
    r3 = call(consent=SUPPLIED[name], request_id="made-up-id")
    check(f"{name}: invented request id refused", "refused" in r3 and not r3.get("consent_required"), str(r3))
    check(f"{name}: invented request id sends nothing", wire_sent(car) == [], str(car.sent))
check("identical pending action reuses one request (one page)",
      calls()["send_raw"]().get("request_id") == ids["send_raw"])

# === 2. the approve page rejects anything that is not a browser session ============================
print("2. approve page")
rid = ids["send_raw"]
b = Browser()

# machine token on GET: no phrase, no form
r = as_server(lambda: machine.get(f"/approve/{rid}", headers=MACHINE_HDR))
check("machine-token GET shows no phrase", r.status_code == 200 and "SEND RAW" not in r.text and 'name="nonce"' not in r.text)
# machine token header POST
r = as_server(lambda: machine.post(f"/approve/{rid}", data={"phrase": "SEND RAW 11 TO ECM", "nonce": "x"},
                                   headers={**MACHINE_HDR, "origin": "http://testserver"}))
check("POST with x-cuore-token header refused", r.status_code == 403, str(r.status_code))
# header plus a real browser cookie jar: still refused
r = b.approve(rid, extra=MACHINE_HDR)
check("POST from a logged-in browser carrying x-cuore-token refused", r.status_code == 403, str(r.status_code))
# ?token=
r = b.approve(rid, url=f"/approve/{rid}?token={TOKEN}")
check("POST with ?token= refused", r.status_code in (400, 403), str(r.status_code))
check("... and the request is still pending", SERVER.status(rid) == "pending", str(SERVER.status(rid)))
# bad nonce
r = b.approve(rid, nonce="forged-nonce")
check("POST with a bad nonce refused", r.status_code == 400 and SERVER.status(rid) == "pending", str(r.status_code))
# wrong origin / none / cross-site
r = b.approve(rid, origin="http://evil.example")
check("POST with a wrong Origin refused", r.status_code == 403 and SERVER.status(rid) == "pending", str(r.status_code))
r = b.approve(rid, origin=None)
check("POST with no Origin and no Referer refused", r.status_code == 403, str(r.status_code))
r = b.approve(rid, origin=None, extra={"referer": "http://evil.example/x"})
check("POST with a foreign Referer refused", r.status_code == 403, str(r.status_code))
r = b.approve(rid, extra={"sec-fetch-site": "cross-site"})
check("POST flagged cross-site by the browser refused", r.status_code == 403, str(r.status_code))
r = b.approve(rid, origin="null")
check("POST with Origin: null refused", r.status_code == 403, str(r.status_code))
# nonce valid but the consent cookie is not held (the MCP client does not hold it)
html = b.page(rid).text
n, ph = b.secrets(html)
other = Browser()                                  # logged in, but never rendered this page
r = as_server(lambda: other.c.post(f"/approve/{rid}", data={"phrase": ph, "nonce": n},
                                   headers={"origin": "http://testserver"}))
check("valid nonce without the page's cookie refused", r.status_code == 400 and SERVER.status(rid) == "pending", str(r.status_code))
# an older render's nonce stops working once the page is rendered again
n_old = n
b.page(rid)
r = as_server(lambda: b.c.post(f"/approve/{rid}", data={"phrase": ph, "nonce": n_old},
                               headers={"origin": "http://testserver"}))
check("a superseded page nonce is refused", r.status_code == 400, str(r.status_code))
# wrong phrase
r = b.approve(rid, phrase="send raw 99 to ecm")
check("wrong phrase refused", r.status_code == 400 and SERVER.status(rid) == "pending", str(r.status_code))
# no login at all
anon = TestClient(app, follow_redirects=False)
r = as_server(lambda: anon.post(f"/approve/{rid}", data={"phrase": ph, "nonce": n},
                                headers={"origin": "http://testserver"}))
check("POST with no session refused", r.status_code in (401, 403), str(r.status_code))
# no approve route under /api, for the machine token
for path in (f"/api/consent/approve/{rid}", f"/api/approve/{rid}", f"/api/consent/{rid}/approve"):
    r = as_server(lambda p=path: machine.post(p, json={"phrase": ph}, headers=MACHINE_HDR))
    check(f"machine token has no approve route ({path})", r.status_code in (404, 405), str(r.status_code))
check("page for an unknown id is a 404", b.page("nope").status_code == 404)
page_text = b.page(rid).text
check("the page says what is sent, to which module and car, what changes, what is saved",
      all(k in page_text for k in ("ECM", VIN, "What it changes", "Evidence saved", "1101")))
check("the page shows the phrase to a browser session", ph == "SEND RAW 11 TO ECM", ph)

# === 3. approval works from a browser session; replay and changed arguments refuse ==================
print("3. approve, redeem once, replay, changed argument")
car = fresh_car()
r = b.approve(rid)
check("approval from a browser session works", r.status_code == 200 and SERVER.status(rid) == "approved", str(r.status_code))
check("approval page tells the person what to do next", "Approved" in r.text)
before = len(wire_sent(car))
r = tool(server.send_raw, "1102", module="ECM", vin=VIN, request_id=rid, **FLAG)
check("changed argument (command) refused", "refused" in r and not r.get("raw"), str(r))
check("changed argument voids the approval", SERVER.status(rid) == "voided", str(SERVER.status(rid)))
check("changed argument sends nothing", len(wire_sent(car)) == before, str(car.sent))
r = tool(server.send_raw, "1101", module="ECM", vin=VIN, request_id=rid, **FLAG)
check("the voided approval cannot be used even with the right arguments", "refused" in r, str(r))

# fresh request for the full happy path
r = calls()["send_raw"]()
rid2 = pending_id(r)
b.approve(rid2)
car = fresh_car()
r = calls()["send_raw"](request_id=rid2)
check("approved call runs", "refused" not in r and r.get("command") == "1101", str(r))
check("approved call reached the fake adapter", "1101" in car.sent, str(car.sent))
car.sent.clear()
r = calls()["send_raw"](request_id=rid2)
check("replay of a consumed approval refused", "refused" in r and "already used" in r["refused"], str(r))
check("replay sends nothing", wire_sent(car) == [], str(car.sent))
check("the consumed request is spent", SERVER.status(rid2) == "consumed")
# a different VIN / module / argument each refuse
for label, kw in (("module", dict(module="BCM")), ("vin", dict(vin="ZASFAKPN5J7B00000"))):
    rr = pending_id(calls()["send_raw"]())
    b.approve(rr)
    args = dict(module="ECM", vin=VIN)
    args.update(kw)
    car = fresh_car()
    out = tool(server.send_raw, "1101", request_id=rr, **args, **FLAG)
    check(f"changed {label} refused", "refused" in out and wire_sent(car) == [], str(out))
# clear_dtcs: changing override_speed_check changes the action
rc = pending_id(calls()["clear_dtcs"]())
b.approve(rc)
car = fresh_car()
out = tool(server.clear_dtcs, confirm=True, vin=VIN, override_speed_check=True, request_id=rc)
check("clear_dtcs with a changed argument refused, no Mode 04 sent", "refused" in out and "04" not in car.sent, str(out))
# the approved clear_dtcs path itself (fake car): approve then run
rc2 = pending_id(calls()["clear_dtcs"]())
b.approve(rc2)
car = fresh_car()
out = calls()["clear_dtcs"](request_id=rc2)
check("approved clear_dtcs runs on the fake", "refused" not in out and "04" in car.sent, str(out))

# approved clear_module_dtcs: runs on the fake exactly once (14 sent only after approval)
rr = pending_id(calls()["clear_module_dtcs"]())
car = fresh_car()
check("clear_module_dtcs: nothing sent before approval", "14FFFFFF" not in car.sent, str(car.sent))
b.approve(rr)
out = calls()["clear_module_dtcs"](request_id=rr)
check("clear_module_dtcs: approved call consumed and ran on the fake",
      SERVER.status(rr) == "consumed" and car.sent.count("14FFFFFF") == 1 and out.get("module") == "ECM", str(out))
car.sent.clear()
out = calls()["clear_module_dtcs"](request_id=rr)
check("clear_module_dtcs: replay refused, no second 14", "refused" in out and "14FFFFFF" not in car.sent, str(out))
# approved run_actuator: consumed, then the existing interlock (RPM/speed unreadable on this fake) stops it
rr = pending_id(calls()["run_actuator"]())
b.approve(rr)
car = fresh_car()
out = calls()["run_actuator"](request_id=rr)
check("run_actuator: approved call is consumed", SERVER.status(rr) == "consumed", str(SERVER.status(rr)))
check("run_actuator: existing interlock still runs after approval", "error" in out and "RPM" in out["error"], str(out))
check("run_actuator: no 10/2F/31 reached the fake", all(not c.startswith(("2F", "31", "1003")) for c in car.sent), str(car.sent))

# === 4. expiry =====================================================================================
print("4. expiry")
rx = pending_id(calls()["send_raw"]())
b.approve(rx)
NOW[0] += consent_gate.REQUEST_TTL_S + 1
car = fresh_car()
out = calls()["send_raw"](request_id=rx)
check("expired approval refused", "refused" in out and "expired" in out["refused"], str(out))
check("expired approval sends nothing", wire_sent(car) == [], str(car.sent))
ry = pending_id(calls()["send_raw"]())            # new request after the clock moved
NOW[0] += consent_gate.REQUEST_TTL_S + 1
r = b.approve(ry)
check("an expired request cannot be approved", r.status_code in (200, 400) and SERVER.status(ry) == "expired", str(SERVER.status(ry)))

# === 5. fail closed: the CUORE server is not there =================================================
print("5. fail closed")
down_calls = {"n": 0}


def down(*a, **k):
    down_calls["n"] += 1
    raise cuore_client.CuoreUnavailable("cuore is not answering (test)")


consent_gate.set_remote(down, (cuore_client.CuoreUnavailable, cuore_client.CuoreTimeout))
for name, call in calls().items():
    car = fresh_car()
    r = call()
    check(f"{name}: CUORE unreachable -> refused", "refused" in r and not r.get("request_id"), str(r))
    r = call(consent=SUPPLIED[name], request_id=rid2)
    check(f"{name}: CUORE unreachable + supplied consent + request id -> refused", "refused" in r, str(r))
    check(f"{name}: CUORE unreachable -> nothing sent", wire_sent(car) == [], str(car.sent))
consent_gate.set_remote(None)
car = fresh_car()
r = calls()["send_raw"]()
check("no consent authority at all -> refused", "refused" in r and wire_sent(car) == [], str(r))

# the _via in-process fallback may run a read, but any car-affecting request it tries is refused
import cuore.live.ops as ops  # noqa: E402
car = fresh_car()
orig_call = cuore_client.call
cuore_client.call = lambda *a, **k: (_ for _ in ()).throw(cuore_client.CuoreUnavailable("down"))


def sneaky_local():
    with ops.link().session("sneaky", bus=ops._bus("can_c")) as sess:
        return sess.cmd("14FFFFFF", 2)


out = json.loads(server._via("POST", "/live/x", sneaky_local))
cuore_client.call = orig_call
check("_via fallback: a write attempted in-process is refused", "error" in out, str(out))
check("_via fallback: nothing car-affecting reached the adapter", wire_sent(car) == [], str(car.sent))

# the transport belt, directly
car = fresh_car()
with ops.link().session("belt", bus=ops._bus("can_c")) as sess:
    for cmd in ("14FFFFFF", "04", "1003", "1101", "2F123403AA", "3B0102", "08"):
        try:
            sess.cmd(cmd, 2)
            ok = False
        except consent_gate.ConsentRefused:
            ok = True
        check(f"transport belt refuses {cmd} outside an approved scope", ok)
    sess.cmd("1001", 2)       # default session is not gated
    sess.cmd("22F190", 2)     # reads are not gated
check("transport belt sent none of the gated requests", wire_sent(car) == ["1001", "22F190"], str(car.sent))
grant = None
try:
    consent_gate.write_scope(object()).__enter__()
except consent_gate.ConsentRefused:
    grant = "refused"
check("a forged grant object cannot open a write scope", grant == "refused")

# === 6. blocklists still win, even for an approved request =========================================
print("6. blocklisted modules")
consent_gate.set_remote(remote, (cuore_client.CuoreUnavailable, cuore_client.CuoreTimeout))
r = as_server(lambda: machine.post("/api/consent/request", headers=MACHINE_HDR, json={"action": {
    "tool": "send_raw", "module": "ORC", "service": "11", "vin": VIN, "args": {"command": "1101"}}}))
check("a request for a blocklisted module is never created", r.status_code == 403, str(r.status_code))
r = as_server(lambda: machine.post("/api/consent/request", headers=MACHINE_HDR, json={"action": {
    "tool": "run_actuator", "module": "ABS", "service": "2F", "vin": VIN, "args": {"name": "x", "routine": False}}}))
check("... nor for an actuator on a safety module", r.status_code == 403, str(r.status_code))
# approve an ORC request anyway (validation bypassed) -- the tool's own gates must still refuse
real_validate = consent_gate.validate_action
consent_gate.validate_action = lambda a: None
try:
    act = consent_gate.Action(tool="send_raw", module="ORC", service="11", vin=VIN,
                              args={"command": "1101", "bus": "can_c", "confirm": False})
    info = as_server(lambda: SERVER.create(act))
    b.approve(info["request_id"])
    car = fresh_car()
    out = tool(server.send_raw, "1101", module="ORC", vin=VIN, request_id=info["request_id"], **FLAG)
    check("approved send_raw to ORC still refused", "refused" in out and "ORC" in out["refused"], str(out))
    check("approved send_raw to ORC sends nothing", wire_sent(car) == [], str(car.sent))
    store.confirm_target(VIN, "ABS", 0x28, source="test")
    store_dir_proc_abs = dict(store_dir_proc, name="Test B")
    actuate.save_actuator(VIN, "ABS", "Test B", store_dir_proc_abs, source="test", tool="MES")
    act3 = consent_gate.Action(tool="run_actuator", module="ABS", service="10,2F", vin=VIN, args={"name": "Test B"})
    info3 = as_server(lambda: SERVER.create(act3))
    b.approve(info3["request_id"])
    car = fresh_car()
    out = tool(server.run_actuator, "ABS", "Test B", vin=VIN, request_id=info3["request_id"])
    check("approved run_actuator on ABS still refused", "error" in out or "refused" in out, str(out))
    check("approved run_actuator on ABS sends nothing", wire_sent(car) == [], str(car.sent))
finally:
    consent_gate.validate_action = real_validate

# === 7. restart, memory and audit ================================================================
print("7. restart voids, nothing on disk, audit")
rz = pending_id(calls()["send_raw"]())
b.approve(rz)
SERVER2 = consent_gate.ConsentStore()
consent_gate.deactivate_authority()
SERVER_OLD = SERVER
SERVER = SERVER2                                  # the server restarted: an empty store
car = fresh_car()
out = calls()["send_raw"](request_id=rz)
check("a server restart voids every approval", "refused" in out and wire_sent(car) == [], str(out))
SERVER = SERVER_OLD

disk = []
for p in Path(STATE).rglob("*"):
    if p.is_file() and p.name != "audit.jsonl":
        try:
            if rz in p.read_text(encoding="utf-8", errors="ignore"):
                disk.append(p.name)
        except OSError:
            pass
check("no approval state is written to any file (only the audit log names request ids)", disk == [], str(disk))

rows = audit.read_recent(5000)
events = {r["event"] for r in rows}
for ev in ("consent_requested", "consent_approved", "consent_consumed", "consent_refused",
           "consent_expired", "consent_approve_rejected"):
    check(f"audit row written: {ev}", ev in events, str(sorted(events)))
appr = [r for r in rows if r["event"] == "consent_approved"]
check("audit records who approved", appr and all(r.get("approver") for r in appr), str(appr[:1]))
blob = json.dumps(rows)
check("audit never holds a consent phrase", not any(p in blob.upper() for p in ("ACTUATE ECM TEST", "CLEAR ALL EMISSIONS CODES")), "")
check("audit never holds the machine token", TOKEN not in blob)

# === 8. accounts mode ============================================================================
print("8. accounts mode")
accounts.create("boss", "correct horse 1", "admin", "Boss", "main", "dealer")
accounts.create("tech1", "tech password 1", "technician", "Tech One", "shopA", "independent")
accounts.set_mode(True)
consent_gate.set_remote(remote, (cuore_client.CuoreUnavailable, cuore_client.CuoreTimeout))
ra = pending_id(calls()["send_raw"]())


def login(user, pw):
    c = Browser(login="")
    as_server(lambda: c.c.post("/login", data={"username": user, "password": pw, "next": "/"}))
    return c


# the shared machine token in accounts mode: header path refused, machine cookie is not a person
r = as_server(lambda: machine.post(f"/approve/{ra}", data={"phrase": "x", "nonce": "y"},
                                   headers={**MACHINE_HDR, "origin": "http://testserver"}))
check("accounts: machine-token POST refused", r.status_code == 403 and SERVER.status(ra) == "pending", str(r.status_code))
mb = Browser()                                   # logs in with the shared token -> machine session cookie
html = mb.page(ra).text
check("accounts: a machine-token session sees no phrase and no form", "SEND RAW" not in html and 'name="nonce"' not in html)
r = mb.approve(ra)
check("accounts: a machine-token session cannot approve", r.status_code == 403 and SERVER.status(ra) == "pending", str(r.status_code))
anon2 = TestClient(app, follow_redirects=False)
r = as_server(lambda: anon2.get(f"/approve/{ra}"))
check("accounts: anonymous GET is sent to log in", r.status_code == 302, str(r.status_code))
# a signed-in person with a permitted role
consent_gate.APPROVER_ROLES = ("admin",)
tb = login("tech1", "tech password 1")
r = tb.approve(ra)
check("accounts: a role outside APPROVER_ROLES cannot approve", r.status_code == 403 and SERVER.status(ra) == "pending", str(r.status_code))
consent_gate.APPROVER_ROLES = ("admin", "shop_lead", "technician")
tb = login("tech1", "tech password 1")
r = tb.approve(ra)
check("accounts: a signed-in technician can approve", r.status_code == 200 and SERVER.status(ra) == "approved", str(r.status_code))
view = SERVER.page_view(ra)
check("accounts: the approver is recorded", view["approver"] == "tech1", str(view["approver"]))
rows = audit.read_recent(5000)
check("accounts: audit names the approver", any(r["event"] == "consent_approved" and r.get("approver") == "tech1" for r in rows))
car = fresh_car()
out = calls()["send_raw"](request_id=ra)
check("accounts: the approved call then runs", "refused" not in out and "1101" in car.sent, str(out))
accounts.set_mode(False)

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
