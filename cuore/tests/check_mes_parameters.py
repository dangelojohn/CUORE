"""Checks for the MES parameter inventory (service + page). Never touches the car or real logs.

Run:
    .venv/Scripts/python.exe -X utf8 cuore/tests/check_mes_parameters.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


from cuore.services import mes_parameters as mp  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
CAR = "Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir"


def entry(name, vin, vehicle=CAR, sim=False, at="2026-10-23 01:16:00"):
    return types.SimpleNamespace(name=name, path=Path(name), vin=vin, vehicle=vehicle, simulation=sim,
                                 mtime=1.0, timestamp=at, sort_key=(at, name))


ENTRIES = [
    entry("FESLog_A.txt", VIN, at="2026-10-23 01:16:00"),
    entry("FESLog_B.txt", VIN, sim=True),
    entry("FESLog_C.txt", "", at="2026-10-23 01:14:00"),                       # no VIN, same model
    entry("FESLog_D.txt", "", vehicle="Alfa Romeo Stelvio 2.9 V6 24V TwinTurbo"),  # other model
    entry("FESLog_E.txt", "OTHERVIN000000000"),
    entry("FESLog_F.txt", VIN, at="2026-06-07 10:08:00"),
]


def pv(name, raw, unit=""):
    return types.SimpleNamespace(name=name, raw=raw, unit=unit)


LOGS = {
    "FESLog_A.txt": ("Instrument Panel Continental", [[pv("Odometer", "41000 km", "km"), pv("Battery voltage", "12.4 V", "V")],
                                                      [pv("Odometer", "41001 km", "km")]]),
    "FESLog_B.txt": ("Instrument Panel Continental", [[pv("Simulated thing", "1")]]),
    "FESLog_C.txt": ("Service Interval Reset", [[pv("Days to service", "200")]]),
    "FESLog_D.txt": ("Instrument Panel Continental", [[pv("V6 only", "1")]]),
    "FESLog_E.txt": ("Instrument Panel Continental", [[pv("Other car", "1")]]),
    "FESLog_F.txt": ("Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)", [[pv("Engine speed", "780 rpm", "rpm")]]),
}


def fake_select(kind="", vin="", **kw):
    return [e for e in ENTRIES if not vin or e.vin == vin]


def fake_load(path, timestamp=""):
    ecu, samples = LOGS[Path(path).name]
    sim = next(e.simulation for e in ENTRIES if e.name == Path(path).name)
    return types.SimpleNamespace(ecu_description=ecu, simulation=sim,
                                 samples=[types.SimpleNamespace(values=s) for s in samples])


mp.catalog = types.SimpleNamespace(CATALOG=types.SimpleNamespace(select=fake_select))
mp.fes = types.SimpleNamespace(load_fes=fake_load)
mp._cache.update(key=None, logs=[])

inv = mp.inventory(VIN)
M = {m["code"]: m for m in inv["modules"]}
check(inv["total"] == len(mp.MODULES) and len(inv["modules"]) == len(mp.MODULES), "every module of the table is listed")
check(M["IPC"]["captured"] and M["ECM"]["captured"] and inv["captured"] == 2, "IPC and ECM captured from real logs")
names = {p["name"] for p in M["IPC"]["parameters"]}
check(names == {"Odometer", "Battery voltage"}, f"IPC parameters from its real log only ({names})")
odo = next(p for p in M["IPC"]["parameters"] if p["name"] == "Odometer")
check(odo["samples"] == 2 and odo["last"] == "41001 km" and odo["units"] == ["km"], "samples, last value, units kept")
check(not any(p["name"] in ("Simulated thing", "V6 only", "Other car")
              for m in inv["modules"] + inv["other"] for p in m["parameters"]),
      "simulation logs, other models and other VINs excluded")
svc = [o for o in inv["other"] if o["name"] == "Service Interval Reset"]
check(len(svc) == 1 and svc[0]["sessions"][0]["vin_in_log"] is False, "VIN-less log of the same model kept, flagged")
check(not M["TCM"]["captured"] and M["TCM"]["cable"] == "adapter alone", "uncaptured module with its cable")
check(M["ABS"]["cable"] == "grey A6 cable" and M["HVAC"]["cable"] == "blue A5 cable", "cable per bus")
check(inv["parameter_count"] == 4, f"parameter count ({inv['parameter_count']})")
csv_text = mp.to_csv(VIN)
lines = csv_text.strip().splitlines()
check(lines[0].startswith("module,module_name,bus,parameter") and len(lines) == 5, "CSV header plus one line per parameter")
check(any(line.startswith("IPC,Instrument Panel Continental,can_c,Odometer,km,41001 km,2,") for line in lines),
      "CSV line carries module, parameter, unit, last value, samples")

# --- page ------------------------------------------------------------------
from cuore.app import create_app  # noqa: E402

client = TestClient(create_app(), follow_redirects=False)
r = client.get(f"/v/{VIN}/mes-parameters")
check(r.status_code == 200 and "MES parameter inventory" in r.text, "page renders")
check("2 of " in r.text and "Still to capture" in r.text and "TCM" in r.text, "checklist shows captured count and to-do")
check("Odometer" in r.text and "41001 km" in r.text, "captured module lists its parameters")
check("no VIN in the log" in r.text, "VIN-less session is flagged on the page")
r = client.get(f"/v/{VIN}/mes-parameters.csv")
check(r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
      and "attachment" in r.headers.get("content-disposition", ""), "CSV downloads")
check("/mes-parameters" in client.get(f"/v/{VIN}/sensors").text, "sensor page links the inventory")

print(f"{passed}/{passed + len(failures)} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
