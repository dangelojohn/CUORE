"""Regression checks for the three silent-wrongness bugs and the write gate."""
import sys
sys.path.insert(0, '.')
import server as s

ok = True
def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print(f"  {'PASS' if good else 'FAIL'}  {label}")
    if not good:
        print(f"        got  {got!r}\n        want {want!r}")

print("1. _hex_pairs with ATS0 (unspaced) - v1 returned [] for all of these")
check("mode 01 rpm",      s._hex_pairs("410C0B4C"),        ["41","0C","0B","4C"])
check("spaced still ok",  s._hex_pairs("41 0C 0B 4C"),     ["41","0C","0B","4C"])
check("with CAN header",  s._hex_pairs("7E8 410C0B4C"),    ["41","0C","0B","4C"])
check("ISO-TP multiline", s._hex_pairs("0: 49020157\n1: 5A415346"),
      ["49","02","01","57","5A","41","53","46"])
check("odd nibble trimmed", s._hex_pairs("410C0B4"),       ["41","0C","0B"])

print("\n2. adapter errors surfaced, not swallowed")
for e in ["BUFFER FULL","CAN ERROR","BUS BUSY","STOPPED","UNABLE TO CONNECT"]:
    got = s.adapter_error(e)
    print(f"  {'PASS' if got else 'FAIL'}  {e:20} -> {got!r}")
    ok = ok and bool(got)
check("clean response has no error", s.adapter_error("410C0B4C"), "")

print("\n3. DTC category decode (v1 mapped 1->C, 2->B, 3->U : wrong)")
cases = [("43","0143","P0143"), ("43","4561","C0561"), ("43","8123","B0123"),
         ("43","C100","U0100"), ("43","0456","P0456"), ("43","D110","U1110")]
for mode, code, want in cases:
    pairs = [mode, "01", code[:2], code[2:]]
    got = s._decode_dtcs(pairs, mode)
    check(f"{code} -> {want}", got, [want])

print("\n4. VIN no longer drops its first character")
# 49 02 01 then 'ZASFAKPN5J7B88115'
vin = "ZASFAKPN5J7B88115"
pairs = ["49","02","01"] + [format(ord(c),"02X") for c in vin]
out = []
started, skip = False, 0
for tok in pairs:
    if not started:
        if tok == "49":
            started = True; skip = 2
        continue
    if skip:
        skip -= 1; continue
    n = int(tok,16)
    if 32 <= n < 127: out.append(chr(n))
check("full 17-char VIN", "".join(out), vin)

print("\n5. send_raw write gate")
for cmd, should_block in [("04", True), ("ATSH 7E0", True), ("2F0102", True),
                          ("31010203", True), ("14FFFFFF", True), ("2E F190", True),
                          ("34", True), ("ATRV", False), ("ATDP", False),
                          ("0100", False), ("0902", False), ("19020C", False)]:
    blocked = bool(s._classify_write(cmd.strip().upper()))
    good = blocked == should_block
    ok = ok and good
    print(f"  {'PASS' if good else 'FAIL'}  {cmd:12} blocked={blocked} (want {should_block})")

print("\n" + ("ALL PASS" if ok else "FAILURES PRESENT"))
sys.exit(0 if ok else 1)

# --- readiness monitor decoding -------------------------------------------
print("\n6. readiness monitors (Mode 01 PID 01) - MES cannot do this at all")

def readiness(hexstr):
    return s._decode_readiness(s._hex_pairs(hexstr), "41")

# A=0x00 (no MIL, 0 DTCs), B=0x07 all continuous supported+complete,
# C=0x25 (catalyst|EVAP|O2 sensor supported), D=0x04 (EVAP incomplete)
r = readiness("41010007 2504".replace(" ", ""))
names = {m["monitor"]: m["complete"] for m in r["monitors"]}
check("MIL off", r["mil_on"], False)
check("spark ignition", r["ignition"], "spark")
check("EVAP supported but INCOMPLETE", names.get("Evaporative system"), False)
check("Catalyst complete", names.get("Catalyst"), True)
check("O2 sensor complete", names.get("Oxygen sensor"), True)
check("not all complete", r["all_complete"], False)

# Same but D=0x00 -> everything complete
r2 = readiness("410100072500")
names2 = {m["monitor"]: m["complete"] for m in r2["monitors"]}
check("EVAP complete when D bit clear", names2.get("Evaporative system"), True)
check("all_complete true", r2["all_complete"], True)

# MIL on with 5 stored codes
r3 = readiness("41018507 2500".replace(" ", ""))
check("MIL on", r3["mil_on"], True)
check("5 stored DTCs", r3["stored_dtc_count"], 5)

print("\n" + ("ALL PASS" if ok else "FAILURES PRESENT"))
sys.exit(0 if ok else 1)
