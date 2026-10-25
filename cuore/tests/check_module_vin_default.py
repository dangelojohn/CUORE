"""Checks that a module read with no ``vin`` still uses the addresses saved
by discovery (``addresses.json``) when only one car is on file, and refuses
to guess when two cars are.

Run:
    .venv/Scripts/python.exe cuore/tests/check_module_vin_default.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="cuore_vin_default_")
os.environ["CUORE_STATE_DIR"] = TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import store, uds  # noqa: E402
from cuore.live.errors import BadCommand  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def write(data: dict) -> None:
    Path(TMP, "addresses.json").write_text(json.dumps(data), encoding="utf-8")


check(store.path().parent == Path(TMP), "store uses the temp state dir")

A, B = "ZASFAKPN5J7B88115", "ZARFAEXXXXX000001"
write({A: {"DTCM": {"target": "1A"}, "DASM": {"target": "2A"}}})
check(uds.resolve_module("DTCM").target == 0x1A, "one car: DTCM resolves with no vin")
check(uds.resolve_module("DASM", "").target == 0x2A, "one car: empty vin resolves DASM")
check(uds.resolve_module("DTCM", A).target == 0x1A, "explicit vin still works")

write({A: {"DTCM": {"target": "1A"}}, B: {"DTCM": {"target": "29"}}})
check(uds.resolve_module("DTCM", B).target == 0x29, "two cars: explicit vin picks its own")
try:
    uds.resolve_module("DASM")
    check(False, "two cars, no vin: DASM should be refused")
except BadCommand as exc:
    check("pass vin=" in str(exc), "two cars, no vin: error says to pass vin")

write({})
try:
    uds.resolve_module("DASM")
    check(False, "no cars: DASM should be refused")
except BadCommand as exc:
    check("pass vin=" not in str(exc), "no cars: no misleading vin hint")

print(f"{passed}/{passed + len(failures)} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
