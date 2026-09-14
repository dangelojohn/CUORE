"""Readiness-monitor decoding (Mode 01 PID 01 / 41).

MultiEcuScan implements no generic OBD-II mode at all, so it cannot answer
"has the EVAP monitor actually run since the last clear?". That question is
the difference between a confirmed repair and a hopeful one, which is why
this decoder exists.

This test used to import ``server as s`` and call ``s._decode_readiness`` /
``s._hex_pairs``. obd2-mcp/server.py no longer defines those -- the parsing
logic moved to cuore.live. Import the real functions from there instead.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live.framing import hex_pairs  # noqa: E402
from cuore.live.obd import decode_readiness  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print(f"  {'PASS' if good else 'FAIL'}  {label}")
    if not good:
        print(f"        got  {got!r}\n        want {want!r}")


def readiness(hexstr):
    return decode_readiness(hex_pairs(hexstr.replace(" ", "")), "41")


print("Mode 01 PID 01 readiness decoding")

# A=00 no MIL / 0 DTCs · B=07 all continuous supported and complete
# C=25 catalyst + EVAP + O2 sensor supported · D=04 EVAP incomplete
r = readiness("41 01 00 07 25 04")
names = {m["monitor"]: m["complete"] for m in r["monitors"]}
check("MIL off", r["mil_on"], False)
check("0 stored DTCs", r["stored_dtc_count"], 0)
check("spark ignition", r["ignition"], "spark")
check("EVAP supported but NOT complete", names.get("Evaporative system"), False)
check("Catalyst complete", names.get("Catalyst"), True)
check("Oxygen sensor complete", names.get("Oxygen sensor"), True)
check("unsupported monitor absent", "EGR system" in names, False)
check("all_complete false", r["all_complete"], False)

# Same, D=00 -> every supported monitor has run
r2 = readiness("41 01 00 07 25 00")
names2 = {m["monitor"]: m["complete"] for m in r2["monitors"]}
check("EVAP complete when D bit clear", names2.get("Evaporative system"), True)
check("all_complete true", r2["all_complete"], True)

# MIL on, 5 stored codes
r3 = readiness("41 01 85 07 25 00")
check("MIL on", r3["mil_on"], True)
check("5 stored DTCs", r3["stored_dtc_count"], 5)

# Continuous monitors: B=17 -> misfire+fuel+components supported,
# bit4 set means misfire incomplete
r4 = readiness("41 01 00 17 00 00")
names4 = {m["monitor"]: m["complete"] for m in r4["monitors"]}
check("Misfire incomplete", names4.get("Misfire"), False)
check("Fuel system complete", names4.get("Fuel system"), True)
check("Comprehensive components complete",
      names4.get("Comprehensive components"), True)

# Compression ignition flag (B bit3)
r5 = readiness("41 01 00 0F 00 00")
check("compression ignition detected", r5["ignition"], "compression")

# Garbage in -> None, not a wrong answer
check("undecodable returns None", readiness("NO DATA"), None)

print("\n" + ("ALL PASS" if ok else "FAILURES PRESENT"))
sys.exit(0 if ok else 1)
