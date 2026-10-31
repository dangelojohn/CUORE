"""Add Service backend (cuore/services/car_identify.py). Fakes and temp state only; never COM3.

Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_car_identify.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-carid-")
os.environ["CUORE_AUTOSTART"] = "0"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "obd2-mcp"))

from cuore.services import car_identify as ci  # noqa: E402
from cuore.services import shop_bridge  # noqa: E402
from cuore.services.errors import BadRequest  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


REF = "ZASFAKPN5J7B88115"


def with_check_digit(vin17: str) -> str:
    _, expected = ci._check_digit(vin17)
    return vin17[:8] + expected + vin17[9:]


def bump_check(vin: str) -> str:
    return vin[:8] + ("0" if vin[8] != "0" else "1") + vin[9:]


# --- validate ---------------------------------------------------------------------------------
v = ci.validate_vin(REF)
check("reference VIN valid", v["ok"] and not v["errors"], str(v))
check("reference check digit reported", v["check_digit"]["checked"] and v["check_digit"]["applies"] == "advisory")
check("lowercase and spaces normalised", ci.validate_vin(" zasfakpn5j7b88115 ")["vin"] == REF)
check("too short rejected", not ci.validate_vin("ZASF123")["ok"])
check("too long rejected", not ci.validate_vin(REF + "1")["ok"])
bad = ci.validate_vin("ZASFAKPN5J7B8811O")
check("letter O rejected", not bad["ok"] and any("I, O and Q" in e for e in bad["errors"]), str(bad))
check("empty rejected", not ci.validate_vin("")["ok"] and not ci.validate_vin(None)["ok"])
w = ci.validate_vin(bump_check(REF))
check("wrong check digit is only a warning outside North America",
      w["ok"] and w["warnings"] and w["check_digit"]["valid"] is False, str(w))
na = with_check_digit("ZN6TU61C0HX000001")
na_ok = ci.validate_vin(na)
check("NA VIN with right check digit ok", na_ok["ok"] and na_ok["check_digit"]["applies"] == "required", str(na_ok))
check("NA VIN with wrong check digit rejected", not ci.validate_vin(bump_check(na))["ok"])

# --- decode -----------------------------------------------------------------------------------
d = ci.decode_vin(REF)["fields"]
check("reference make", d["make"]["value"] == "Alfa Romeo" and d["make"]["source"] == ci.SRC_DECODED)
check("reference model", d["model"]["value"] == "Stelvio", str(d["model"]))
check("reference platform", "Giorgio" in str(d["platform"]["value"]), str(d["platform"]))
check("reference year 2018", d["model_year"]["value"] == 2018, str(d["model_year"]))
check("reference plant marked unverified", bool(d["plant"]["value"]) and d["plant"]["verified"] is False)
check("reference market unknown, not guessed", d["market"]["value"] is None and d["market"]["source"] == ci.SRC_NONE)
check("every field has value/source/at", all({"value", "source", "at"} <= set(f) for f in d.values()))
check("decode agrees with shop_bridge make", shop_bridge._decode_wmi(REF) == d["make"]["value"])
mas = ci.decode_vin(na)["fields"]
check("Maserati ZN6 make + NA market", mas["make"]["value"] == "Maserati" and mas["market"]["value"] == "North America")
check("Maserati model stays unknown", mas["model"]["value"] is None and mas["model"]["source"] == ci.SRC_NONE)
fer = ci.decode_vin("ZFF00000000000001")["fields"]
check("Ferrari WMI shown unverified", fer["make"]["value"] == "Ferrari" and fer["make"]["verified"] is False)
unk = ci.decode_vin("1HGCM82633A004352")["fields"]
check("unknown marque stays unknown",
      all(unk[k]["value"] is None for k in ("make", "model", "platform", "plant", "market")), str(unk["make"]))
check("unknown marque still has a year", unk["model_year"]["value"] == 2003)
check("invalid VIN decodes to nothing", all(f["value"] is None for f in ci.decode_vin("12345")["fields"].values()))


# --- identify with fakes ----------------------------------------------------------------------
ALLOWED = {"cable", "mes_running", "bus_ready", "read_vin", "modules", "identity"}


class FakeProbe:
    def __init__(self, cable="none", vin=REF, mes=False, bus_ok=True, silent=(), refuse=(), vin_error=""):
        self._cable, self.vin, self.mes, self.bus_ok = cable, vin, mes, bus_ok
        self.silent, self.refuse, self.vin_error = set(silent), set(refuse), vin_error
        self.calls: list[str] = []

    def cable(self):
        self.calls.append("cable")
        return self._cable

    def mes_running(self):
        self.calls.append("mes_running")
        return self.mes

    def bus_ready(self, bus, cable):
        self.calls.append("bus_ready")
        return (self.bus_ok, "" if self.bus_ok else "bus not verified")

    def read_vin(self):
        self.calls.append("read_vin")
        return {"error": self.vin_error} if self.vin_error else {"vin": self.vin}

    def modules(self, bus):
        self.calls.append("modules")
        return [{"code": c, "name": n, "usable": u, "present": p, "target": c}
                for c, n, u, p in (("ECM", "Engine", True, True), ("ABS", "Brakes", True, True),
                                   ("BCM", "Body", True, True), ("XYZ", "Unmapped", False, True))]

    def identity(self, code, vin, confirm):
        self.calls.append(f"identity:{code}")
        if code in self.silent:
            return {"error": "NOT READ: no answer from the module, do not treat as clean"}
        if code in self.refuse:
            return {"fields": {"F190": {"ascii": None, "bytes": [], "nrc": "31"}}}
        return {"fields": {"F190": {"ascii": vin, "bytes": ["41"]}, "F188": {"ascii": "SW-" + code, "bytes": ["41"]}}}


p = FakeProbe()
evs = list(ci.identify_from_car("", probe=p))
kinds = [e["event"] for e in evs]
check("events: start, vin, 3 modules, done", kinds == ["start", "vin", "module", "module", "module", "done"], str(kinds))
card = evs[-1]["card"]
check("VIN read from the car", card["fields"]["vin"]["source"] == ci.SRC_READ and card["vin"] == REF)
check("decoded fields ride along", card["fields"]["model"]["value"] == "Stelvio")
check("3 modules answered", card["fields"]["modules_answered"]["value"] == "3 of 3")
check("software ids read", card["fields"]["software_ids"]["value"].get("ECM F188") == "SW-ECM")
check("unusable module never asked", "identity:XYZ" not in p.calls)
check("only read-only probe methods used", set(c.split(":")[0] for c in p.calls) <= ALLOWED, str(p.calls))
check("card read only, online lookup off", card["read_only"] and card["online_lookup"]["performed"] is False)

card2 = ci.identify_result(ci.identify_from_car("", probe=FakeProbe(silent=("ABS",), refuse=("BCM",))))["card"]
sil = card2["silent_modules"]
check("silent modules listed", [m["code"] for m in sil] == ["ABS", "BCM"], str(sil))
check("silent reasons stated", "NOT READ" in sil[0]["reason"] and "refused" in sil[1]["reason"], str(sil))
check("silent modules stay out of software ids",
      not any(k.startswith(("ABS", "BCM")) for k in card2["fields"]["software_ids"]["value"]))
check("1 of 3 answered", card2["fields"]["modules_answered"]["value"] == "1 of 3")

card3 = ci.identify_result(ci.identify_from_car(REF, probe=FakeProbe(vin_error="ADAPTER/BUS ERROR: no answer")))["card"]
check("car silent on VIN: typed VIN kept as typed in", card3["fields"]["vin"]["source"] == ci.SRC_TYPED)
card3b = ci.identify_result(ci.identify_from_car("", probe=FakeProbe(vin_error="x")))["card"]
check("no VIN anywhere stays not found",
      card3b["fields"]["vin"]["source"] == ci.SRC_NONE and card3b["fields"]["make"]["value"] is None)
card4 = ci.identify_result(ci.identify_from_car("ZASFAKPN5J7B00000", probe=FakeProbe()))["card"]
check("typed VIN conflict reported, car wins", card4["vin"] == REF and bool(card4["conflicts"]))

last = None
for label, probe in (("MES open", FakeProbe(mes=True)), ("bus not verified", FakeProbe(bus_ok=False)),
                     ("unknown cable", FakeProbe(cable="weird"))):
    last = ci.identify_result(ci.identify_from_car(REF, probe=probe))
    check(f"{label}: refused, no module read", last["events"][1]["event"] == "refused"
          and not any(c.startswith("identity") for c in probe.calls) and bool(last["card"]["refused"]),
          str(last["events"][:2]))
check("refused card keeps typed VIN, modules not found",
      last["card"]["fields"]["vin"]["source"] == ci.SRC_TYPED
      and last["card"]["fields"]["modules_answered"]["source"] == ci.SRC_NONE)

ci.five_minute._RUN_LOCK.acquire()
try:
    locked = ci.identify_result(ci.identify_from_car(REF, probe=FakeProbe()))
finally:
    ci.five_minute._RUN_LOCK.release()
check("run lock held: refused", locked["events"][0]["event"] == "refused")
got = ci.five_minute._RUN_LOCK.acquire(blocking=False)
check("lock released after a run", got)
if got:
    ci.five_minute._RUN_LOCK.release()

# --- create_service ---------------------------------------------------------------------------
from mes import jobs as jobs_mod, shop as shop_mod  # noqa: E402

# the reference VIN is in the real corpus (a known car); use a VIN not on file for the new-car path
NEW = "ZASFAKPN5J7B88999"
c1 = ci.identify_result(ci.identify_from_car("", probe=FakeProbe(vin=NEW)))["card"]
r1 = ci.create_service(c1["fields"], "shudder at 40 km/h", 61234, technician="T")
check("new car creates a visit and job", r1["created"] and not r1["existing_car"] and bool(r1["job_id"]))
check("odometer on intake", r1["odometer"]["value"] == 61234 and r1["odometer"]["unit"] == "km"
      and r1["odometer"]["job_id"] == r1["job_id"])
check("job holds the reason", jobs_mod.current(NEW)["complaint"] == "shudder at 40 km/h")
check("visit named from the card", shop_mod.load(NEW)[0]["vehicle"] == "Alfa Romeo Stelvio 2018",
      str(shop_mod.load(NEW)[0].get("vehicle")))
check("name resolves everywhere", shop_bridge.resolve_vehicle_name(NEW) == "Alfa Romeo Stelvio 2018")
check("card keeps READ source for the VIN", ci.get_card(NEW)["fields"]["vin"]["source"] == ci.SRC_READ)

r2 = ci.create_service({"vin": NEW}, "second try", 61300)
check("duplicate VIN: no second visit or job", not r2["created"] and r2["already_open"] and r2["existing_car"]
      and r2["job_id"] == r1["job_id"] and len(shop_mod.load(NEW)) == 1 and len(jobs_mod.load(NEW)) == 1)
check("duplicate keeps the better source", ci.get_card(NEW)["fields"]["vin"]["source"] == ci.SRC_READ)
check("duplicate still records its odometer", len(ci.get_card(NEW)["odometer_readings"]) == 2)

jobs_mod.close(r1["job_id"], "deferred")
r3 = ci.create_service({"vin": NEW}, "back again", None)
check("known car, job closed: new job on the same car", r3["created"] and r3["existing_car"] and r3["odometer_missing"])

TYPED_VIN = "ZN7TU61C0HX000002"
r4 = ci.create_service({"vin": TYPED_VIN, "make": "Maserati"}, "noise", "45,000", unit="mi")
check("typed-only car: unit and typed source", r4["odometer"]["unit"] == "mi" and r4["odometer"]["value"] == 45000
      and r4["card"]["fields"]["vin"]["source"] == ci.SRC_TYPED)
check("unknown model not invented", r4["card"]["fields"]["model"]["value"] is None
      and "model not identified" in shop_mod.load(TYPED_VIN)[0]["vehicle"], shop_mod.load(TYPED_VIN)[0]["vehicle"])

for label, args in (("bad VIN", ({"vin": "BAD"}, "x", None)), ("no VIN", ({}, "x", None)),
                    ("bad odometer", ({"vin": REF}, "x", "lots")), ("negative odometer", ({"vin": REF}, "x", -5))):
    try:
        ci.create_service(*args)
        check(f"{label} refused", False)
    except BadRequest:
        check(f"{label} refused", True)
check("refusals created nothing", len(shop_mod.load(NEW)) == 2 and not shop_mod.load("BAD"))

# --- nothing gated, no network ----------------------------------------------------------------
src = (REPO / "cuore/services/car_identify.py").read_text(encoding="utf-8")
for banned in ("consent_gate", "send_raw", "clear_dtc", "import requests", "urllib", "httpx", "socket"):
    check(f"service never references {banned}", banned not in src, banned)
imports = [ln for ln in src.splitlines() if ln.startswith(("from ", "import ", "        from "))]
check("only read-side live imports", not any(w in ln for ln in imports for w in ("actuate", "clear", "safety", "transport", "consent")), str(imports))
check("online lookup stub does nothing",
      ci.online_lookup(REF, enabled=True)["performed"] is False and ci.ONLINE_LOOKUP_ENABLED is False)

print(f"car_identify: {checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
