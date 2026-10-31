"""Address resolution is bus-aware and consistent, and identity reads report every
identifier on its own. Fakes only; no adapter is opened.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_address_resolve.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

TMP = tempfile.mkdtemp(prefix="cuore_addr_resolve_")
os.environ["CUORE_STATE_DIR"] = TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import addressing, read_state, store, uds  # noqa: E402
from cuore.live.errors import BadCommand  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def refuses(fn, label: str, *needles: str) -> None:
    try:
        fn()
        check(False, f"{label}: should refuse")
    except BadCommand as exc:
        check(all(n in str(exc) for n in needles), f"{label}: message {exc}")


def write(data: dict) -> None:
    Path(TMP, "addresses.json").write_text(json.dumps(data), encoding="utf-8")


A, B = "ZASFAKPN5J7B88115", "ZARFAEXXXXX000001"
CONF = {"ABS": {"target": "2A"}, "ECM": {"target": "10"}, "DTCM": {"target": "1A"},
        "ESM": {"target": "1F"}, "DASM": {"target": "2A"}}

# --- the static table no longer claims what the car contradicts ---------------------
check(addressing.by_code("DTCM").target is None, "static DTCM does not carry the unverified 0x29")
check(0x29 not in addressing.sweep_candidates("can_c")[:3], "0x29 not promoted as a DTCM guess")
check([m.code for m in addressing.by_target(0x2A, "can_ch")] == ["ABS"], "0x2A on CAN-CH is ABS")
check(addressing.by_target(0x2A, "can_c") == [], "static table has no 0x2A on CAN-C (needs the car)")

# --- same answer with and without vin -----------------------------------------------
write({A: CONF})
for code, want in (("DTCM", 0x1A), ("ESM", 0x1F), ("DASM", 0x2A), ("ABS", 0x2A), ("ECM", 0x10)):
    check(uds.resolve_module(code).target == want, f"{code} resolves to {want:02X} with no vin")
    check(uds.resolve_module(code, A).target == want, f"{code} resolves to {want:02X} with vin")
    check(uds.resolve_module(code, "").target == want, f"{code} resolves with empty vin")

# --- 0x2A resolves by bus -----------------------------------------------------------
check(uds.module_at(0x2A, "can_ch").code == "ABS", "0x2A on CAN-CH is the ABS")
check(uds.module_at(0x2A, "can_c").code == "DASM", "0x2A on CAN-C is the DASM")
check(uds.module_at(0x2A, "can_ihs") is None, "0x2A on CAN-IHS is nothing")
check(uds.module_at(0x1A, "can_c").code == "DTCM" and uds.module_at(0x1F, "can_c").code == "ESM",
      "DTCM and ESM found by their confirmed bytes")
check(uds.module_at(0x29, "can_c") is None, "0x29 is no module on this car")
refuses(lambda: uds.resolve_module("ABS", A, bus="can_c"), "ABS asked on CAN-C", "can_ch", "not can_c")
check(uds.resolve_module("DASM", A, bus="can_c").target == 0x2A, "DASM on its own bus resolves")
t = {r["code"]: r for r in uds.address_table(A)}
check(t["DASM"]["bus"] == "can_c" and t["ABS"]["bus"] == "can_ch" and not t["DASM"]["clash"],
      "same byte on two buses is not a clash")
check(t["DTCM"]["source"].startswith("confirmed on this car"),
      "table says where the address came from")
check(t["EPS"]["target"] is None and t["EPS"]["source"] is None, "EPS stays unaddressed")

# --- no confirmed address: refuse, never guess ---------------------------------------
refuses(lambda: uds.resolve_module("EPS"), "EPS unknown", "no confirmed address")
refuses(lambda: uds.resolve_module("AFLS"), "AFLS unknown", "no confirmed address")
refuses(lambda: uds.resolve_module("NOPE"), "unknown code", "unknown module")
refuses(lambda: uds.resolve_module("ORC"), "ORC registry 0x50 is unverified", "no confirmed address", "not used")
write({})
refuses(lambda: uds.resolve_module("DTCM"), "no car on file", "no confirmed address")
check(uds.resolve_module("ECM").target == 0x10, "registry-confirmed ECM still resolves with no car on file")

# --- clash on one bus refuses ----------------------------------------------------------
write({A: {"DTCM": {"target": "1F"}, "ESM": {"target": "1F"}}})
refuses(lambda: uds.resolve_module("ESM", A), "two modules on one byte", "DTCM", "1F")
check(uds.module_at(0x1F, "can_c", A) is None, "clash: module_at gives no answer")

# --- several cars: explicit vin, connected car, or refuse -----------------------------
write({A: CONF, B: {"DTCM": {"target": "29"}}})
refuses(lambda: uds.resolve_module("DASM"), "two cars, car unknown", "pass vin=")
check(uds.resolve_module("DTCM", B).target == 0x29, "explicit vin picks its own car")
uds.set_vin_provider(lambda: A.lower())
check(uds.resolve_module("DASM").target == 0x2A and uds.resolve_module("DTCM").target == 0x1A,
      "two cars, connected car known: its addresses apply with no vin")
uds.set_vin_provider(lambda: "ZZZZZZZZZZZZZZZZZ")
refuses(lambda: uds.resolve_module("DASM"), "connected car not on file", "pass vin=")
uds.set_vin_provider(lambda: (_ for _ in ()).throw(RuntimeError("no link")))
refuses(lambda: uds.resolve_module("DASM"), "provider broken", "pass vin=")
uds.set_vin_provider(None)


# --- identity: one status per identifier ------------------------------------------------
class FakeSess:
    bus = SimpleNamespace(key="can_c")

    def __init__(self, script):
        self.script, self.asked = script, []

    def uds(self, ecu, service, payload, timeout=0):
        assert service == 0x22, "identity uses 0x22 only"
        did = payload.hex().upper()
        self.asked.append(did)
        kind = self.script.get(did, "ok")
        r = {"positive": {}, "nrc": {}, "error": None}
        if kind == "ok":
            r["positive"] = {"18DAF11F": ["62", did[:2], did[2:]] + [f"{ord(c):02X}" for c in "ABC1234"]}
        elif kind == "silent":
            pass
        elif kind == "error":
            r["error"] = "CAN ERROR"
        elif kind.startswith("nrc"):
            r["nrc"] = {"18DAF11F": int(kind[3:], 16)}
        return r


write({A: CONF})
ESM = uds.resolve_module("ESM", A)

full = uds.identity(FakeSess({"F189": "nrc31"}), ESM)
s = full["summary"]
check(len(full["fields"]) == 9 and len(s["answered"]) == 8, "8 answered, 9 asked")
check(s["refused"] == {"F189": "requestOutOfRange"}, f"F189 refusal shows its NRC: {s['refused']}")
check(full["read_state"] == read_state.READ and not full.get("partial"),
      "answered or refused everything is a complete read")
check(full["fields"]["F189"]["status"] == "refused" and full["fields"]["F190"]["status"] == "answered",
      "per-field status")

part = uds.identity(FakeSess({"F188": "silent", "F18C": "error", "F189": "nrc31"}), ESM)
ps = part["summary"]
check(part["read_state"] == "partial" and part.get("partial") is True, "silent and errored fields make it partial")
check(ps["no_answer"] == ["F188"] and list(ps["error"]) == ["F18C"] and ps["refused"].keys() == {"F189"},
      "answered / refused / silent / errored are told apart")
check("PARTIAL" in part["partial_reason"] and "F188" in ps["line"] and "F18C" in ps["line"]
      and "F189" in ps["line"], "the line names every non-answer")
check(len(part["fields"]) == 9 and part["fields"]["F195"]["status"] == "answered",
      "reading goes on past a failed identifier")
check(part.get("error") == "CAN ERROR", "first bus error still on top for callers that retry on it")
check(read_state.reason(part) == part["partial_reason"] and not read_state.is_read(part),
      "read_state.reason names a partial identity; it is not a clean read")

dead = uds.identity(FakeSess({d: "error" for d in ("F190", "F187", "F188", "F189", "F18C",
                                                  "F191", "F192", "F194", "F195")}), ESM)
check(dead["read_state"] == "not_read" and dead["summary"]["answered"] == [], "nothing answered is not read")
check(sum(f["status"] == "not_asked" for f in dead["fields"].values()) == 6,
      "after three bus errors in a row the rest are marked not asked")
check(not read_state.is_read(dead) and dead["not_read"].startswith("NOT READ"), "dead identity carries the banner")

refused_all = uds.identity(FakeSess({d: "nrc31" for d in ("F190", "F187", "F188", "F189", "F18C",
                                                         "F191", "F192", "F194", "F195")}), ESM)
check(refused_all["read_state"] == "not_read" and len(refused_all["summary"]["refused"]) == 9,
      "refusing everything is not an identity")
sess = FakeSess({})
uds.identity(sess, ESM)
check(sess.asked == [f"{d:04X}" for d in uds.IDENTITY_ORDER], "each identifier asked once, by its own 22 read")

print(f"{passed}/{passed + len(failures)} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
