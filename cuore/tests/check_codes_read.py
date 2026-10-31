"""Checks for the Codes page "Read now" list (services/codes_read.py + POST /v/{vin}/codes/read).

A fake reader and a fake module list stand in for the guarded read; no port, no adapter, no car.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_codes_read.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-cr-")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.services import codes_read as C  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


VIN = "ZASFAKPN5J7B88115"
MODS = {"modules": [
    {"code": "ECM", "name": "Engine", "bus": "can_c", "usable": True},
    {"code": "BCM", "name": "Body", "bus": "can_c", "usable": True},
    {"code": "ESM", "name": "Gear", "bus": "can_c", "usable": False},
    {"code": "ABS", "name": "Brakes", "bus": "can_ch", "usable": True}]}
mods = lambda **kw: MODS  # noqa: E731
calls: list[tuple] = []


def reader_ok(code, vin="", detail=True):
    calls.append((code, vin, detail))
    return {"ecu": code, "active": ["P0456"], "history": ["P0455"], "read_state": "read"}


def reader_silent(code, vin="", detail=True):
    return {"ecu": code, "warning": "no answer from the module"}


def reader_boom(code, vin="", detail=True):
    raise RuntimeError("adapter busy: live session running")


check([m["code"] for m in C.readable_modules(VIN, mods)] == ["ECM", "BCM"], "only confirmed CAN-C modules are offered")
r = C.read_now(VIN, "ecm", reader_ok, mods)
check(r["ok"] and r["line"] == "ECM: 2 stored codes", "stored count is active plus history")
check(calls == [("ECM", VIN, False)], "reader called once, compact, with the VIN")
r = C.read_now(VIN, "ABS", reader_ok, mods)
check(not r["ok"] and len(calls) == 1, "a CAN-CH module is refused without any read")
r = C.read_now(VIN, "ESM", reader_ok, mods)
check(not r["ok"] and len(calls) == 1, "an unconfirmed module is refused without any read")
r = C.read_now(VIN, "", reader_ok, mods)
check(not r["ok"] and len(calls) == 1, "an empty module is refused")
r = C.read_now(VIN, "BCM", reader_silent, mods)
check(not r["ok"] and r["state"] == "not_read" and "NOT READ" in r["line"] and "no stored" not in r["line"],
      "silence is NOT READ, never no codes")
r = C.read_now(VIN, "BCM", reader_boom, mods)
check(not r["ok"] and "do not treat as clean" in r["line"] and "adapter busy" in r["line"], "an error is said, not hidden")
s = C.summarise({"ecu": "TCM", "active": [], "history": [], "read_state": "read"})
check(s["state"] == "read" and s["line"] == "TCM: no stored codes", "zero codes is stated only for a real read")
s = C.summarise({"ecu": "TCM", "dtcs": [{"code": "U0100", "status": 0x08}, {"code": "P0000", "status": 0x40}]})
check(s["count"] == 1, "a full reply counts only stored-status records")

p = C.panel(VIN, mods, reads={"ECM": {"state": "read", "line": "ECM: no stored codes", "at": "2026-10-31T00:36:10"}})
check(p[0]["when"] == "2026-10-31 00:36" and p[0]["line"] == "no stored codes", "panel shows the last read")
check(p[1]["state"] == "never" and p[1]["line"] == "never read from the car", "panel says never read")

# web: fake the list and the reader inside the service, then post
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

orig_read = C.read_now
C.readable_modules = lambda vin, fn=None: [{"code": "ECM", "name": "Engine"}]  # type: ignore[assignment]
C.read_now = lambda vin, code, reader=None, modules_fn=None: orig_read(vin, code, reader_ok, mods)  # type: ignore[assignment]
c = TestClient(create_app(), follow_redirects=False)
r = c.post(f"/v/{VIN}/codes/read", data={"module": "ECM"})
check(r.status_code == 303 and "msg=ECM%3A%202%20stored%20codes" in r.headers["location"], "post redirects with the result line")
page = c.get(f"/v/{VIN}/codes?msg=ECM%3A%202%20stored%20codes&mk=ok")
check(page.status_code == 200 and 'id="read-now"' in page.text and 'aria-label="Read ECM codes now"' in page.text,
      "codes page lists the Read button")
check("window.print()" in page.text and "Print code list" in page.text, "codes page can be printed")
check("ECM: 2 stored codes" in page.text, "the result line is shown")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
