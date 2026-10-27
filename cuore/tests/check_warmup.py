"""Checks for cuore.services.warmup. Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_warmup.py"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-warmup-")
os.environ.pop("CUORE_NO_WARMUP", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from cuore.services import warmup  # noqa: E402

fails: list[str] = []


def check(name: str, ok: bool) -> None:
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


ran: list[str] = []
tids: list[int] = []


def slow():
    tids.append(threading.get_ident())
    time.sleep(0.5)
    ran.append("slow")


def boom():
    raise RuntimeError("x")


def last():
    ran.append("last")


steps = [("slow", slow), ("boom", boom), ("last", last)]

t0 = time.perf_counter()
th = warmup.start(vin="VIN", steps=steps)
dt = time.perf_counter() - t0
check("start() returns before the steps finish", th is not None and dt < 0.3 and not ran)
th.join(5)
check("runs in a separate daemon thread", th.daemon and tids and tids[0] != threading.get_ident())
check("a failing step does not stop the others", ran == ["slow", "last"])

res = warmup.run(vin="VIN", steps=steps)
check("failed step reported negative, others positive", res["boom"] < 0 < res["last"] + 1 and res["slow"] > 0)

ran.clear()
os.environ["CUORE_NO_WARMUP"] = "1"
check("CUORE_NO_WARMUP=1 skips", warmup.start(vin="VIN", steps=steps) is None and not ran)
os.environ.pop("CUORE_NO_WARMUP")

check("no vehicle -> nothing runs", warmup.run(steps=steps) == {})

print("all green" if not fails else f"FAILURES: {fails}")
sys.exit(1 if fails else 0)
