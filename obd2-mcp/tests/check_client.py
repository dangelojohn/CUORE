"""Checks that the obd2 MCP tools are served by cuore, not by this process.

A stand-in HTTP server plays cuore: it records every request and answers
from a table. That pins the mapping from each tool to its route, arguments
and body, the error translation, the fallback when nothing listens, the
no-retry rule on timeouts, and the cable hand-off before in-process writes.

Run:
    .venv/Scripts/python.exe obd2-mcp/tests/check_client.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-client-")
os.environ["CUORE_AUTOSTART"] = "0"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1]))

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want) -> None:
    check(label, got == want, f"got {got!r} want {want!r}")


# --- the stand-in for cuore --------------------------------------------------

REQUESTS: list[dict] = []
REPLIES: dict[tuple[str, str], tuple[int, object]] = {}
SLOW: set[str] = set()


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _serve(self, method: str) -> None:
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"null") if n else None
        REQUESTS.append({"method": method, "path": u.path,
                         "query": {k: v[0] for k, v in parse_qs(u.query).items()},
                         "body": body, "token": self.headers.get("X-Cuore-Token")})
        if u.path in SLOW:
            time.sleep(1.5)
        status, payload = REPLIES.get((method, u.path), (200, {"ok": True, "path": u.path}))
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        try:
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # the timeout check hangs up on purpose

    def do_GET(self):
        self._serve("GET")

    def do_POST(self):
        self._serve("POST")


srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["CUORE_URL"] = f"http://127.0.0.1:{srv.server_address[1]}"

import cuore_client  # noqa: E402
import server  # noqa: E402
from cuore.live import ops  # noqa: E402


def last() -> dict:
    return REQUESTS[-1]


def run(fn, *a, **kw) -> dict:
    return json.loads(fn(*a, **kw))


# ===========================================================================
# 1. every read tool goes to its route with its arguments
# ===========================================================================

CASES = [
    (server.status, (), {}, "GET", "/api/live/status", {}, None),
    (server.list_ports, (), {}, "GET", "/api/live/ports", {}, None),
    (server.buses, (), {}, "GET", "/api/live/buses", {}, None),
    (server.modules, ("can_ch",), {}, "GET", "/api/live/modules", {"bus": "can_ch"}, None),
    (server.set_cable, ("grey_a6",), {}, "POST", "/api/live/cable", {}, {"cable": "grey_a6"}),
    (server.verify_bus, ("can_c", 3.0), {}, "POST", "/api/live/verify", {},
     {"bus": "can_c", "seconds": 3.0}),
    (server.read_dtcs, (), {}, "GET", "/api/live/obd/dtcs", {"kind": "stored"}, None),
    (server.read_pending_dtcs, (), {}, "GET", "/api/live/obd/dtcs", {"kind": "pending"}, None),
    (server.read_permanent_dtcs, (), {}, "GET", "/api/live/obd/dtcs", {"kind": "permanent"},
     None),
    (server.read_readiness, (), {}, "GET", "/api/live/obd/readiness", {}, None),
    (server.read_pid, ("0D",), {}, "GET", "/api/live/obd/pid/0D", {}, None),
    (server.read_freeze_frame, ("",), {}, "GET", "/api/live/obd/freeze", {}, None),
    (server.read_vin, (), {}, "GET", "/api/live/obd/vin", {}, None),
    (server.read_voltage, (), {}, "GET", "/api/live/obd/voltage", {}, None),
    (server.read_module_dtcs, ("ECM",), {"vin": "V", "confirm": False}, "GET",
     "/api/live/module/ECM/dtcs",
     {"vin": "V", "mask": "255", "confirm": "false", "detail": "false"}, None),
    (server.read_module_identity, ("ABS",), {"confirm": True}, "GET",
     "/api/live/module/ABS/identity", {"confirm": "true"}, None),
    (server.read_did, ("ECM", "F190"), {}, "GET", "/api/live/module/ECM/did/F190",
     {"confirm": "false"}, None),
    (server.scan_modules, ("can_c",), {}, "GET", "/api/live/scan",
     {"bus": "can_c", "mask": "255", "confirm": "false", "detail": "false"}, None),
    (server.connect, (), {}, "POST", "/api/live/probe",
     {"allow_while_mes_connected": "false"}, None),
    (server.audit_log, (5,), {}, "GET", "/api/live/audit", {"n": "5"}, None),
    (server.coverage, ("run",), {"pass_key": "ch", "confirm": True}, "POST",
     "/api/live/coverage/run", {}, {"key": "ch", "confirm": True}),
    (server.coverage, ("status",), {}, "GET", "/api/live/coverage", {}, None),
    (server.read_mode06, ("3C, 3B",), {}, "GET", "/api/live/obd/mode06", {"mids": "3C,3B"}, None),
    (server.read_dtc_detail, ("ECM", "P0456-00"), {"vin": "V"}, "GET",
     "/api/live/module/ECM/dtc/P0456-00", {"vin": "V", "confirm": "false"}, None),
    (server.read_all_module, ("TCM",), {}, "GET", "/api/live/module/TCM/all",
     {"include_unverified": "true", "confirm": "false"}, None),
    (server.learned_dids, ("V",), {}, "GET", "/api/live/learned", {"vin": "V"}, None),
    (server.list_actuators, ("V",), {}, "GET", "/api/live/actuators", {"vin": "V"}, None),
    (server.learn_correlate, ("cap.json", '[{"t": 1, "label": "x", "value": "y"}]'), {}, "POST",
     "/api/live/learn/correlate", {}, {"capture": "cap.json",
                                       "marks": [{"t": 1, "label": "x", "value": "y"}]}),
    (server.verify_repair, ("P0455, P0456",), {"vin": "V", "read": False}, "GET",
     "/api/live/module/ECM/repair",
     {"codes": "P0455,P0456", "vin": "V", "read": "false", "confirm": "false"}, None),
    (server.live_channels, (), {}, "GET", "/api/live/channels", {}, None),
    (server.live_session_stop, (), {}, "POST", "/api/live/session/stop", {}, None),
    (server.live_snapshot, (), {}, "GET", "/api/live/snapshot", {}, None),
    (server.live_session_start, (), {"preset": "engine_basics"}, "POST",
     "/api/live/session/start", {}, {"preset": "engine_basics"}),
]
for fn, a, kw, method, path, query, body in CASES:
    out = run(fn, *a, **kw)
    r = last()
    label = f"{fn.__name__}{a}"
    check_eq(f"{label} method", r["method"], method)
    check_eq(f"{label} path", r["path"], path)
    check_eq(f"{label} query", r["query"], query)
    if body is not None:
        check_eq(f"{label} body", r["body"], body)
    check(f"{label} was served by cuore, not in-process", "served_by" not in out, str(out))

out = run(server.discover_modules, "can_ch", vin="V", confirm=True, candidates=["28"])
check_eq("discover body carries candidates and confirm", last()["body"],
         {"bus": "can_ch", "vin": "V", "confirm": True, "candidates": ["28"],
          "per_target_timeout": 0.25})

out = run(server.live_session_start, preset="engine_basics", monitor_dtcs=True)
check_eq("live_session_start with monitor_dtcs carries it and the default interval",
         last()["body"], {"preset": "engine_basics", "monitor_dtcs": True, "dtc_interval_s": 10.0})
check("live_session_start with monitor_dtcs was served by cuore, not in-process",
      "served_by" not in out, str(out))

os.environ["CUORE_TOKEN"] = "s3cret"
run(server.status)
check_eq("the token is sent as X-Cuore-Token", last()["token"], "s3cret")
os.environ.pop("CUORE_TOKEN")


# ===========================================================================
# 2. errors from cuore come through as errors
# ===========================================================================

REPLIES[("GET", "/api/live/obd/dtcs")] = (403, {"error": "Refused", "status": 403,
                                                "detail": "bus can_c is silent: ..."})
out = run(server.read_dtcs)
check_eq("a refusal keeps its kind", out.get("kind"), "Refused")
check("a refusal keeps its message", "silent" in (out.get("error") or ""), str(out))
check("a refusal is not retried in-process", "served_by" not in out)
REPLIES.pop(("GET", "/api/live/obd/dtcs"))


# ===========================================================================
# 3. timeouts are reported, never retried elsewhere
# ===========================================================================

SLOW.add("/api/live/obd/readiness")
n_before = len(REQUESTS)
try:
    cuore_client.call("GET", "/live/obd/readiness", timeout=0.5)
    raised = None
except Exception as e:  # noqa: BLE001
    raised = e
check("a slow request raises CuoreTimeout", isinstance(raised, cuore_client.CuoreTimeout),
      repr(raised))
_orig_call = cuore_client.call
cuore_client.call = lambda *a, **k: (_ for _ in ()).throw(
    cuore_client.CuoreTimeout("did not finish"))
out = run(server.read_readiness)
cuore_client.call = _orig_call
check_eq("a timed-out tool reports Timeout", out.get("kind"), "Timeout")
check("a timed-out tool does not fall back in-process", "served_by" not in out, str(out))
SLOW.clear()
time.sleep(1.2)  # let the slow handler finish before the next section


# ===========================================================================
# 4. nothing listening: in-process fallback, labelled; or an error if disabled
# ===========================================================================

good_url = os.environ["CUORE_URL"]
os.environ["CUORE_URL"] = "http://127.0.0.1:9"   # discard port: nothing listens
out = run(server.buses)
check("unreachable cuore falls back in-process", "served_by" in out, str(out)[:200])
check("the fallback still answers", "buses" in out, str(out)[:200])
os.environ["CUORE_FALLBACK"] = "0"
out = run(server.buses)
check_eq("with fallback off the tool reports CuoreUnavailable", out.get("kind"),
         "CuoreUnavailable")
os.environ.pop("CUORE_FALLBACK")
try:
    cuore_client.ensure_server(wait=0.5)
    raised = None
except cuore_client.CuoreUnavailable as e:
    raised = e
check("ensure_server raises when autostart is off", raised is not None)
os.environ["CUORE_URL"] = "http://192.0.2.1:5000"
check("a non-local URL is never autostarted", not cuore_client._is_local(cuore_client.base_url()))
os.environ["CUORE_URL"] = good_url


# ===========================================================================
# 5. in-process writes adopt cuore's cable declaration
# ===========================================================================

REPLIES[("GET", "/api/live/status")] = (200, {"cable": {"cable": "grey_a6", "buses": []}})
server.link().set_cable("none")
adopted = server._sync_cable()
check_eq("_sync_cable returns cuore's cable", adopted, "grey_a6")
check_eq("the local link now matches cuore", server.link().cable, "grey_a6")
REPLIES.pop(("GET", "/api/live/status"))
os.environ["CUORE_URL"] = "http://127.0.0.1:9"
check_eq("_sync_cable with cuore down leaves the local cable", server._sync_cable(), None)
os.environ["CUORE_URL"] = good_url
server.link().set_cable("none")

srv.shutdown()
print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
