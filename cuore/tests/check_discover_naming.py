"""Checks for cuore.live.responders (record, name from MES logs, owner accept).

No car contact: fixture responder records and fixture MES text.
Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_discover_naming.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-naming-")
os.environ["CUORE_STATE_DIR"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import responders as rs, store  # noqa: E402
from cuore.live.errors import BadCommand  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


VIN = "ZASFAKPN5J7B88115"
logs = Path(tempfile.mkdtemp(prefix="cuore-check-meslogs-"))
# Fixture text in the real MES SCAN layout (values copied from SCAN_2610260906.txt).
(logs / "SCAN_2610260906.txt").write_text("""Scan vehicle for available modules and check each module for errors...

Gearbox / DTCM (Drive Train Control Module)
Magna Q4 Transfer Case
ISO Code: 00 43 50 91 14
VIN code: ZASFAKPN5J7B88115
Hardware number: M0045027.01 - Ver: 21
Software number: M0099947 - Ver: 0501

Gearbox / ESM/GSM/NSC (Gearbox Selector Module)
ZF Electronic Gear Shift Module
ISO Code: 00 16 50 B4 14
VIN code: ZASFAKPN5J7B88115
Hardware number: 1000597140 - Ver: 08
Software number: 1000678050 - Ver: 0019

Other / DASM (Driver Assistant System Module)
Driver assistant system module (DASM) radar Bosch
ISO Code: 00 39 70 7E 15
VIN code: ZASFAKPN5J7B88115
Hardware number: MRR1evo14F - Ver: 00
Software number: 52081920 - Ver: 0500

COMPLETED
""", encoding="utf-8")
# an older log of ANOTHER car must be ignored
(logs / "SCAN_2501010000.txt").write_text("""Gearbox / DTCM (Drive Train Control Module)
Magna Q4 Transfer Case
ISO Code: 00 43 50 91 14
VIN code: ZARFAEEN0J7000000
Hardware number: OTHERCAR123 - Ver: 01
Software number: OTHERCAR456 - Ver: 01
""", encoding="utf-8")
# FES log carrying a spare part number for the ESM (spare value is a fixture, not a real part number)
(logs / "FESLog_2610241313_Alfa Romeo Stelvio.txt").write_text("""(Multiecuscan 5.4)
10/24/2026 1:12:33 PM
Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir
ZF Electronic Gear Shift Module
--------------------------------------------------------------

ECU ISO code: 00 16 50 B4 14
VIN code: ZASFAKPN5J7B88115
Spare part number: FIXTURE-SPARE-001
Hardware number: 1000597140
Hardware version: 08
Software number: 1000678050
Software version: 0019

READING ERROR CODES:
No fault codes
""", encoding="utf-8")


def ident(**kw: tuple) -> dict:
    return {d: {"ascii": a, "hex": h} for d, (a, h) in kw.items()}


# fixture responder records (SYNTHETIC replies; addresses as a sweep would store them)
rs.upsert(VIN, {"address": "18DA29F1", "request": "18DA29F1", "response": "18DAF129", "bus": "can_c",
                "kind": "29bit", "target": "29",
                "identity": ident(F192=("M0045027.01", ""), F194=("M0099947", ""))})
rs.upsert(VIN, {"address": "18DA1FF1", "request": "18DA1FF1", "response": "18DAF11F", "bus": "can_c",
                "kind": "29bit", "target": "1F",
                "identity": ident(F187=("FIXTURE-SPARE-001", ""), F18C=("", "00 16 50 B4 14"))})
rs.upsert(VIN, {"address": "18DA77F1", "request": "18DA77F1", "response": "18DAF177", "bus": "can_c",
                "kind": "29bit", "target": "77", "identity": ident(F192=("NOSUCHPART999", ""))})
rs.upsert(VIN, {"address": "7E0", "request": "7E0", "response": "7E8", "bus": "can_ch",
                "kind": "11bit", "target": None, "identity": {}})

check("responders.json written", rs.path().exists() and rs.path().parent == Path(_TMP))

out = rs.name_responders(VIN, logs_dir=logs)
rows = {r["address"]: r for r in out["responders"]}

d = rows["18DA29F1"]
check("DTCM proposed", d["status"] == rs.PROPOSED and d["module"] == "DTCM", str(d))
check("DTCM reason cites log and line", "SCAN_2610260906.txt line 7" in d["reason"], d["reason"])
check("DTCM strong (two exact numbers)", d.get("strong") is True)
check("other car's log not used", "OTHERCAR" not in d["reason"])

e = rows["18DA1FF1"]
check("ESM proposed from spare part + ISO code", e["status"] == rs.PROPOSED and e["module"] == "ESM", str(e))
check("ESM evidence cites the FES log spare part", any(x["mes_field"] == "spare" and
      x["log"].startswith("FESLog_") and x["line"] for x in e["evidence"]), str(e.get("evidence")))
check("ESM ISO code matched by hex", any(x["mes_field"] == "iso" for x in e["evidence"]))

check("unknown string -> no MES log match", rows["18DA77F1"]["status"] == "no MES log match")
check("11-bit responder without identity: no match", rows["7E0"]["status"] == "no MES log match")
check("naming never promoted the table", store.confirmed_targets(VIN) == {})
check("responders.json untouched by naming", "accepted" not in rs._load()[VIN]["18DA29F1"])

# accept: owner decision
for label, args in (("11-bit accept refused", ("7E0", "DTCM")),
                    ("unknown address refused", ("18DA99F1", "DTCM")),
                    ("unknown module refused", ("29", "NOPE"))):
    try:
        rs.accept_responder(VIN, *args)
        check(label, False)
    except BadCommand:
        check(label, True)

acc = rs.accept_responder(VIN, "29", "DTCM")
check("accept promotes to confirmed (owner)", acc["status"] == "confirmed (owner)" and acc["target"] == "29")
check("modules table (addresses.json) now has DTCM at 29", store.confirmed_targets(VIN).get("DTCM") == 0x29)
check("source recorded as owner confirmation",
      store.all_confirmations()[VIN]["DTCM"]["source"] == "confirmed (owner)")
check("responder record marked accepted", rs._load()[VIN]["18DA29F1"]["accepted"]["module"] == "DTCM")
again = {r["address"]: r for r in rs.name_responders(VIN, logs_dir=logs)["responders"]}
check("accepted responder reported as confirmed (owner)", again["18DA29F1"]["status"] == "confirmed (owner)")


# record_sweep with a fake session: reads the Annex C set read-only, stores hex + ascii
class FakeSess:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def target_raw(self, req: str, resp: str) -> None:
        pass

    def untarget(self) -> None:
        pass

    def query(self, cmd: str, resp: str, timeout: float = 0.5) -> dict:
        self.sent.append(cmd)
        if cmd == "22F192":
            data = ["62", "F1", "92"] + [f"{ord(c):02X}" for c in "ABC1234"]
            return {"raw": "x", "error": None, "ecus": {"18DAF12A": data}, "all_ecus": {"18DAF12A": data}}
        return {"raw": "NO DATA", "error": None, "ecus": {}, "all_ecus": {}}


fs = FakeSess()
res = rs.record_sweep(fs, {"bus": "can_c", "cable": "none", "hits": [
    {"target": "2A", "request": "18DA2AF1", "response": "18DAF12A", "vin": VIN, "identity": {}}]}, vin=VIN)
rec = rs._load()[VIN]["18DA2AF1"]
check("record_sweep stored the responder", res["stored"] == ["18DA2AF1"], str(res))
check("record_sweep sent only 22 requests", fs.sent and all(c.startswith("22") for c in fs.sent), str(fs.sent))
check("record_sweep read the whole Annex C set", len(fs.sent) == len(rs.ANNEX_C_DIDS), str(fs.sent))
check("identity stored with ascii and hex", rec["identity"]["F192"]["ascii"] == "ABC1234" and
      rec["identity"]["F192"]["hex"].startswith("41 42 43"), str(rec["identity"]))

if failures:
    print(f"FAIL: {len(failures)} of {checks} checks failed")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"PASS: {checks} discovery naming checks")
